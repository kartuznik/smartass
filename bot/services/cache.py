"""Redis-backed cache for repeated RAG queries."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from redis.asyncio import Redis

from bot.models.document import Source
from bot.utils.config import get_settings

logger = logging.getLogger(__name__)


class RAGCache:
    """Cache layer for query -> answer+sources with TTL."""

    def __init__(self, ttl_seconds: int = 3600) -> None:
        self.ttl_seconds = ttl_seconds
        self._redis: Redis | None = None
        self._settings = get_settings()

    async def _get_redis(self) -> Redis:
        if self._redis is None:
            self._redis = Redis.from_url(self._settings.redis_url, decode_responses=True)
        return self._redis

    @staticmethod
    def _key(query: str) -> str:
        return f"rag:query:{hashlib.md5(query.strip().lower().encode('utf-8')).hexdigest()}"

    async def get(self, query: str) -> tuple[str, list[Source]] | None:
        """Get cached answer and sources by query text."""
        if not query.strip():
            return None
        try:
            redis = await self._get_redis()
            payload = await redis.get(self._key(query))
            if not payload:
                return None
            data = json.loads(payload)
            answer = str(data.get("answer", ""))
            raw_sources = data.get("sources", [])
            sources = [Source(**item) for item in raw_sources if isinstance(item, dict)]
            return answer, sources
        except Exception as exc:  # pragma: no cover - runtime infra guard
            logger.warning("Cache get failed: %s", exc)
            return None

    async def set(self, query: str, answer: str, sources: list[Source]) -> None:
        """Store answer and sources by query text."""
        if not query.strip():
            return
        try:
            redis = await self._get_redis()
            payload: dict[str, Any] = {
                "answer": answer,
                "sources": [source.model_dump() for source in sources],
            }
            await redis.set(self._key(query), json.dumps(payload, ensure_ascii=False), ex=self.ttl_seconds)
        except Exception as exc:  # pragma: no cover - runtime infra guard
            logger.warning("Cache set failed: %s", exc)

    async def clear(self) -> int:
        """Clear all RAG cache keys and return removed count."""
        try:
            redis = await self._get_redis()
            keys = await redis.keys("rag:query:*")
            if not keys:
                return 0
            return int(await redis.delete(*keys))
        except Exception as exc:  # pragma: no cover - runtime infra guard
            logger.warning("Cache clear failed: %s", exc)
            return 0

    async def size(self) -> int:
        """Return number of cached query keys."""
        try:
            redis = await self._get_redis()
            keys = await redis.keys("rag:query:*")
            return len(keys)
        except Exception as exc:  # pragma: no cover - runtime infra guard
            logger.warning("Cache size check failed: %s", exc)
            return 0


cache = RAGCache()
