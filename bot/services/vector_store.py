"""Vector storage service backed by ChromaDB and OpenAI embeddings."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import chromadb
from chromadb.api.models.Collection import Collection
from openai import AsyncOpenAI

from bot.models.document import Chunk, Document, QueryResult
from bot.utils.config import Settings


class VectorStore:
    """Persist chunks, search semantic similarity, and manage documents."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        persist_dir = Path(settings.chroma_persist_directory)
        persist_dir.mkdir(parents=True, exist_ok=True)

        self._client = chromadb.PersistentClient(path=str(persist_dir))
        self._collection: Collection = self._client.get_or_create_collection(
            name=settings.chroma_collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        self._openai = AsyncOpenAI(api_key=settings.openai_api_key)

    async def add_document(self, document: Document, chunks: list[Chunk]) -> int:
        """Embed chunks and persist them into Chroma collection."""
        if not chunks:
            return 0

        texts = [chunk.text for chunk in chunks]
        embeddings = await self._embed_texts(texts)
        metadatas = [self._build_metadata(document, chunk) for chunk in chunks]

        await asyncio.to_thread(
            self._collection.upsert,
            ids=[chunk.id for chunk in chunks],
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas,
        )
        return len(chunks)

    async def search_similar(self, query: str, top_k: int | None = None) -> list[QueryResult]:
        """Return top-k semantically similar chunks."""
        if not query.strip():
            return []

        n_results = top_k or self.settings.default_top_k
        query_embedding = (await self._embed_texts([query]))[0]

        query_result = await asyncio.to_thread(
            self._collection.query,
            query_embeddings=[query_embedding],
            n_results=n_results,
            include=["documents", "metadatas", "distances"],
        )

        documents = query_result.get("documents", [[]])[0]
        metadatas = query_result.get("metadatas", [[]])[0]
        distances = query_result.get("distances", [[]])[0]
        ids = query_result.get("ids", [[]])[0]

        results: list[QueryResult] = []
        for idx, content in enumerate(documents):
            metadata = metadatas[idx] if idx < len(metadatas) and metadatas[idx] else {}
            distance = float(distances[idx]) if idx < len(distances) else 1.0
            similarity_score = max(0.0, 1.0 - distance)
            chunk_id = ids[idx] if idx < len(ids) else ""
            results.append(
                QueryResult(
                    chunk_id=chunk_id,
                    document_id=str(metadata.get("document_id", "")),
                    source_filename=str(metadata.get("source_filename", "unknown")),
                    content=content,
                    score=similarity_score,
                    metadata=self._normalize_metadata(metadata),
                )
            )

        return results

    async def delete_document(self, document_id: str) -> int:
        """Delete all chunks belonging to a document id."""
        existing = await asyncio.to_thread(
            self._collection.get,
            where={"document_id": document_id},
            include=[],
        )
        chunk_ids = existing.get("ids", [])
        if not chunk_ids:
            return 0

        await asyncio.to_thread(self._collection.delete, ids=chunk_ids)
        return len(chunk_ids)

    async def list_documents(self) -> list[dict[str, Any]]:
        """List unique uploaded documents inferred from chunk metadata."""
        payload = await asyncio.to_thread(
            self._collection.get,
            include=["metadatas"],
        )
        metadatas = payload.get("metadatas", [])

        by_document: dict[str, dict[str, Any]] = {}
        for metadata in metadatas:
            if not metadata:
                continue
            document_id = str(metadata.get("document_id", "")).strip()
            if not document_id:
                continue
            if document_id not in by_document:
                by_document[document_id] = {
                    "id": document_id,
                    "filename": metadata.get("filename", metadata.get("source_filename", "unknown")),
                    "uploaded_by": metadata.get("uploaded_by"),
                    "uploaded_at": metadata.get("uploaded_at"),
                    "chunks_count": 0,
                }
            by_document[document_id]["chunks_count"] += 1

        return sorted(
            by_document.values(),
            key=lambda item: str(item.get("uploaded_at") or ""),
            reverse=True,
        )

    async def count_chunks(self) -> int:
        """Return total chunks in collection."""
        return await asyncio.to_thread(self._collection.count)

    async def get_document_info(self, document_id: str) -> dict[str, Any] | None:
        """Return aggregated metadata for a document by id."""
        payload = await asyncio.to_thread(
            self._collection.get,
            where={"document_id": document_id},
            include=["metadatas"],
        )
        chunk_ids = payload.get("ids", [])
        metadatas = payload.get("metadatas", [])
        if not chunk_ids or not metadatas:
            return None

        first_metadata = next((item for item in metadatas if item), {})
        return {
            "id": document_id,
            "filename": first_metadata.get("filename", first_metadata.get("source_filename", "unknown")),
            "uploaded_by": first_metadata.get("uploaded_by"),
            "uploaded_at": first_metadata.get("uploaded_at"),
            "chunks_count": len(chunk_ids),
            "metadata": self._normalize_metadata(first_metadata),
        }

    async def _embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Get embedding vectors from OpenAI API."""
        response = await self._openai.embeddings.create(
            model=self.settings.embedding_model,
            input=texts,
        )
        return [item.embedding for item in response.data]

    def _build_metadata(self, document: Document, chunk: Chunk) -> dict[str, str | int | float | bool]:
        """Create Chroma-safe metadata map for chunk row."""
        metadata: dict[str, str | int | float | bool] = {
            "document_id": document.id,
            "filename": document.filename,
            "source_filename": chunk.source_filename,
            "chunk_index": chunk.chunk_index,
            "token_count": chunk.token_count,
            "uploaded_by": document.uploaded_by,
            "uploaded_at": document.uploaded_at.isoformat(),
        }

        for key, value in chunk.metadata.items():
            safe = self._to_chroma_value(value)
            if safe is not None:
                metadata[f"chunk_{key}"] = safe

        return metadata

    def _normalize_metadata(self, metadata: dict[str, Any]) -> dict[str, Any]:
        """Convert metadata to plain serializable dictionary."""
        normalized: dict[str, Any] = {}
        for key, value in metadata.items():
            if isinstance(value, (str, int, float, bool)):
                normalized[key] = value
            else:
                normalized[key] = str(value)
        return normalized

    def _to_chroma_value(self, value: Any) -> str | int | float | bool | None:
        """Return metadata value supported by Chroma; fallback to string."""
        if value is None:
            return None
        if isinstance(value, (str, int, float, bool)):
            return value
        return str(value)
