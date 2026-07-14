"""Unit tests for vector store add/search behavior."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from bot.models.document import Chunk, Document
from bot.services.vector_store import VectorStore
from bot.utils.config import Settings


class _FakeCollection:
    def __init__(self) -> None:
        self.upsert_calls: list[dict] = []
        self.next_query_result: dict = {
            "documents": [["stored chunk"]],
            "metadatas": [[{"document_id": "doc-1", "source_filename": "file.pdf"}]],
            "distances": [[0.2]],
            "ids": [["chunk-1"]],
        }

    def upsert(self, **kwargs) -> None:  # noqa: ANN003
        self.upsert_calls.append(kwargs)

    def query(self, **kwargs) -> dict:  # noqa: ANN003
        _ = kwargs
        return self.next_query_result

    def get(self, **kwargs) -> dict:  # noqa: ANN003
        _ = kwargs
        return {"ids": [], "metadatas": []}

    def count(self) -> int:
        return 0

    def delete(self, **kwargs) -> None:  # noqa: ANN003
        _ = kwargs


class _FakeClient:
    def __init__(self, collection: _FakeCollection) -> None:
        self.collection = collection

    def get_or_create_collection(self, **kwargs):  # noqa: ANN003
        _ = kwargs
        return self.collection


@pytest.mark.asyncio
async def test_vector_store_add_and_search_with_mocks(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Arrange mocked Chroma/OpenAI, act add+search, assert persisted and retrieved."""
    collection = _FakeCollection()

    monkeypatch.setattr(
        "bot.services.vector_store.chromadb.PersistentClient",
        lambda path: _FakeClient(collection),
    )
    monkeypatch.setattr(
        "bot.services.vector_store.AsyncOpenAI",
        lambda api_key: SimpleNamespace(api_key=api_key),
    )

    settings = Settings(
        TELEGRAM_BOT_TOKEN="token",
        OPENAI_API_KEY="key",
        CHROMA_PERSIST_DIRECTORY=str(tmp_path / "chroma"),
        DATA_DIR=str(tmp_path / "data"),
        DOCS_DIR=str(tmp_path / "docs"),
    )
    store = VectorStore(settings)

    async def _fake_embed_texts(texts: list[str]) -> list[list[float]]:
        return [[0.1, 0.2] for _ in texts]

    monkeypatch.setattr(store, "_embed_texts", _fake_embed_texts)

    document = Document(
        id="doc-1",
        filename="file.pdf",
        file_path=str(tmp_path / "file.pdf"),
        mime_type="application/pdf",
        size_bytes=100,
        uploaded_by=123,
    )
    chunk = Chunk(
        id="chunk-1",
        document_id=document.id,
        chunk_index=0,
        text="stored chunk",
        token_count=2,
        source_filename=document.filename,
    )

    inserted = await store.add_document(document, [chunk])
    results = await store.search_similar("stored", top_k=1, user_id=123)

    assert inserted == 1
    assert len(collection.upsert_calls) == 1
    assert len(results) == 1
    assert results[0].document_id == "doc-1"
    assert results[0].score == pytest.approx(0.8)
