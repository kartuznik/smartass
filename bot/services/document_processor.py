"""Document loading and chunking service for RAG ingestion."""

from __future__ import annotations

import asyncio
import hashlib
import mimetypes
from pathlib import Path
from typing import Any

import tiktoken
from pypdf import PdfReader

from bot.models.document import Chunk, Document
from bot.utils.config import Settings


class DocumentProcessingError(Exception):
    """Base exception for document processing failures."""


class UnsupportedDocumentTypeError(DocumentProcessingError):
    """Raised when document extension is not supported."""


class EmptyDocumentError(DocumentProcessingError):
    """Raised when a document has no extractable text."""


class DocumentProcessor:
    """Load source files, extract text, and split into overlapping chunks."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.docs_dir = Path(settings.docs_dir)
        self.docs_dir.mkdir(parents=True, exist_ok=True)
        self._encoding = self._build_tokenizer()

    def _build_tokenizer(self) -> tiktoken.Encoding:
        """Create tokenizer for configured embedding model."""
        try:
            return tiktoken.encoding_for_model(self.settings.embedding_model)
        except KeyError:
            return tiktoken.get_encoding("cl100k_base")

    async def process_document(self, file_path: str | Path, uploaded_by: int) -> tuple[Document, list[Chunk]]:
        """Extract metadata and chunks from PDF/Markdown documents."""
        source_path = Path(file_path).expanduser().resolve()
        if not source_path.exists():
            raise FileNotFoundError(f"Document not found: {source_path}")

        extension = source_path.suffix.lower()
        if extension not in {".pdf", ".md", ".markdown"}:
            raise UnsupportedDocumentTypeError(
                f"Unsupported extension '{extension}'. Supported: .pdf, .md, .markdown"
            )

        stat_result = await asyncio.to_thread(source_path.stat)
        mime_type = mimetypes.guess_type(source_path.name)[0] or "application/octet-stream"
        checksum = await self._calculate_checksum(source_path)

        text, extra_metadata = await self._extract_text(source_path)
        if not text.strip():
            raise EmptyDocumentError(f"File '{source_path.name}' does not contain extractable text")

        document = Document(
            filename=source_path.name,
            file_path=str(source_path),
            mime_type=mime_type,
            size_bytes=stat_result.st_size,
            uploaded_by=uploaded_by,
            checksum_sha256=checksum,
            metadata={
                "extension": extension,
                **extra_metadata,
            },
        )

        chunks = self._build_chunks(document, text)
        return document, chunks

    async def _calculate_checksum(self, file_path: Path) -> str:
        """Calculate SHA-256 checksum for source file."""
        file_bytes = await asyncio.to_thread(file_path.read_bytes)
        return hashlib.sha256(file_bytes).hexdigest()

    async def _extract_text(self, file_path: Path) -> tuple[str, dict[str, Any]]:
        """Extract text depending on file type."""
        if file_path.suffix.lower() == ".pdf":
            return await asyncio.to_thread(self._extract_pdf_sync, file_path)

        markdown_text = await asyncio.to_thread(file_path.read_text, "utf-8")
        return markdown_text, {"pages": 1}

    def _extract_pdf_sync(self, file_path: Path) -> tuple[str, dict[str, Any]]:
        """Synchronously extract all text from a PDF file."""
        reader = PdfReader(str(file_path))
        pages_text: list[str] = []
        for page in reader.pages:
            pages_text.append((page.extract_text() or "").strip())

        joined = "\n\n".join(chunk for chunk in pages_text if chunk)
        return joined, {"pages": len(reader.pages)}

    def _build_chunks(self, document: Document, text: str) -> list[Chunk]:
        """Split text into overlapping token-based chunks."""
        encoded = self._encoding.encode(text)
        if not encoded:
            return []

        chunk_size = self.settings.chunk_size_tokens
        overlap = self.settings.chunk_overlap_tokens
        step = chunk_size - overlap
        if step <= 0:
            raise ValueError("CHUNK_SIZE_TOKENS must be greater than CHUNK_OVERLAP_TOKENS")

        chunks: list[Chunk] = []
        for chunk_index, start in enumerate(range(0, len(encoded), step)):
            end = min(start + chunk_size, len(encoded))
            token_slice = encoded[start:end]
            chunk_text = self._encoding.decode(token_slice).strip()
            if chunk_text:
                chunks.append(
                    Chunk(
                        document_id=document.id,
                        chunk_index=chunk_index,
                        text=chunk_text,
                        token_count=len(token_slice),
                        source_filename=document.filename,
                        metadata={
                            "start_token": start,
                            "end_token": end,
                        },
                    )
                )
            if end >= len(encoded):
                break

        return chunks
