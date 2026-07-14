"""Unit tests for Redis-backed RAG cache."""

from __future__ import annotations

import pytest

from bot.models.document import Source
from bot.services.cache import RAGCache


class _FakeRedis:
    def __init__(self) -> None:
        self.storage: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.storage.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> bool:  # noqa: ARG002
        self.storage[key] = value
        return True

    async def keys(self, pattern: str) -> list[str]:
        if pattern == "rag:query:*":
            return list(self.storage.keys())
        return []

    async def delete(self, *keys: str) -> int:
        deleted = 0
        for key in keys:
            if key in self.storage:
                del self.storage[key]
                deleted += 1
        return deleted


@pytest.mark.asyncio
async def test_cache_set_get_clear_roundtrip() -> None:
    """Arrange cache, act set/get/clear, assert correct lifecycle."""
    fake_redis = _FakeRedis()
    cache = RAGCache(ttl_seconds=3600)
    cache._redis = fake_redis  # noqa: SLF001

    query = "How does cache work?"
    sources = [Source(text="chunk text", document_id="doc-1", chunk_id="chunk-1", score=0.91)]

    await cache.set(query, "cached answer", sources)
    cached = await cache.get(query)

    assert cached is not None
    answer, loaded_sources = cached
    assert answer == "cached answer"
    assert len(loaded_sources) == 1
    assert loaded_sources[0].document_id == "doc-1"

    deleted = await cache.clear()
    assert deleted == 1
    assert await cache.get(query) is None
