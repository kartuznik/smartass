"""RAG service: semantic retrieval plus grounded answer generation."""

from __future__ import annotations

import asyncio
import logging
from time import perf_counter
from typing import Any

from openai import APITimeoutError, AsyncOpenAI

from bot.models.document import AnswerResult, Chunk, Source
from bot.services.vector_store import VectorStore
from bot.utils.config import Settings

logger = logging.getLogger(__name__)

EMPTY_CONTEXT_MESSAGE = (
    "К сожалению, я не нашёл информации об этом в загруженной документации. "
    "Попробуйте перефразировать вопрос или загрузите соответствующий документ."
)

SYSTEM_PROMPT_TEMPLATE = """Ты — полезный ассистент, отвечающий на вопросы строго по предоставленной документации.

ПРАВИЛА:
1. Используй ТОЛЬКО информацию из блока "КОНТЕКСТ".
2. Если ответа в контексте нет, так и скажи: "В документации нет информации по этому вопросу".
3. В конце ответа обязательно указывай источники в формате: "Источник: [Имя документа]".
4. Отвечай на русском языке, сохраняя дружелюбный и профессиональный тон.

КОНТЕКСТ:
{context_text}

ИСТОРИЯ ДИАЛОГА:
{history_text}

ВОПРОС ПОЛЬЗОВАТЕЛЯ:
{query}
"""


class RAGService:
    """Perform semantic retrieval from Chroma and grounded answer generation."""

    def __init__(self, settings: Settings, vector_store: VectorStore | None = None) -> None:
        self.settings = settings
        self.vector_store = vector_store or VectorStore(settings)
        self._openai = AsyncOpenAI(api_key=settings.openai_api_key)

    async def search(self, query: str, top_k: int = 3) -> list[Chunk]:
        """Search relevant chunks and return them as Chunk objects with score metadata."""
        search_started_at = perf_counter()
        normalized_query = query.strip()
        if not normalized_query:
            logger.info("RAG search skipped: empty query.")
            return []

        limit = top_k if top_k > 0 else self.settings.default_top_k
        logger.info("RAG search started: query_length=%s, top_k=%s", len(normalized_query), limit)

        query_results = await self.vector_store.search_similar(normalized_query, top_k=limit)
        chunks: list[Chunk] = []
        for item in query_results:
            chunk_metadata = dict(item.metadata)
            chunk_metadata["score"] = item.score
            chunk_index = self._safe_int(chunk_metadata.get("chunk_index"), default=0)
            token_count = self._safe_int(chunk_metadata.get("token_count"), default=0)
            chunks.append(
                Chunk(
                    id=item.chunk_id or "",
                    document_id=item.document_id,
                    chunk_index=chunk_index,
                    text=item.content,
                    token_count=max(0, token_count),
                    source_filename=item.source_filename,
                    metadata=chunk_metadata,
                )
            )

        elapsed_ms = int((perf_counter() - search_started_at) * 1000)
        logger.info("RAG search completed: results=%s, duration_ms=%s", len(chunks), elapsed_ms)
        return chunks

    async def generate_answer(
        self,
        query: str,
        context: list[Chunk],
        conversation_history: list[dict[str, str]] | None = None,
    ) -> AnswerResult:
        """Generate grounded answer based on provided context chunks and dialog history."""
        if not context:
            logger.info("RAG generate skipped: no context for query.")
            return AnswerResult(
                answer=EMPTY_CONTEXT_MESSAGE,
                sources=[],
                found=False,
                query=query,
            )

        generation_started_at = perf_counter()
        logger.info("RAG generation started: query_length=%s, context_chunks=%s", len(query), len(context))

        context_text = self._build_context_text(context)
        history_text = self._build_history_text(conversation_history or [])
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
            context_text=context_text,
            history_text=history_text,
            query=query.strip(),
        )

        response_text = await self._request_completion_with_retry(system_prompt)
        sources = self._build_sources(context)
        elapsed_ms = int((perf_counter() - generation_started_at) * 1000)
        logger.info("RAG generation completed: sources=%s, duration_ms=%s", len(sources), elapsed_ms)

        return AnswerResult(
            answer=response_text,
            sources=sources,
            found=True,
            query=query,
        )

    async def _request_completion_with_retry(self, prompt: str) -> str:
        """Call OpenAI chat completion with retries on timeout."""
        max_retries = 2
        for attempt in range(max_retries + 1):
            try:
                response = await self._openai.chat.completions.create(
                    model=self.settings.llm_model,
                    temperature=0.1,
                    messages=[
                        {"role": "system", "content": prompt},
                    ],
                )
                text = response.choices[0].message.content or ""
                return text.strip() or "В документации нет информации по этому вопросу"
            except (APITimeoutError, asyncio.TimeoutError) as exc:
                logger.warning("OpenAI timeout on attempt %s/%s: %s", attempt + 1, max_retries + 1, exc)
                if attempt >= max_retries:
                    raise
                await asyncio.sleep(0.75 * (attempt + 1))
            except Exception:
                logger.exception("OpenAI completion failed with non-timeout error.")
                raise

    def _build_context_text(self, context: list[Chunk]) -> str:
        """Render retrieved chunks into a deterministic context block."""
        lines: list[str] = []
        for idx, chunk in enumerate(context, start=1):
            score = float(chunk.metadata.get("score", 0.0))
            lines.append(
                f"[{idx}] Документ: {chunk.source_filename}; "
                f"DocumentID: {chunk.document_id}; ChunkID: {chunk.id}; Score: {score:.4f}\n"
                f"{chunk.text}"
            )
        return "\n\n".join(lines)

    def _build_history_text(self, conversation_history: list[dict[str, str]]) -> str:
        """Format recent dialog history in compact readable form."""
        if not conversation_history:
            return "История отсутствует."

        limit = min(self.settings.max_history_messages, 7)
        sliced_history = conversation_history[-limit:]
        rendered: list[str] = []
        for item in sliced_history:
            role = str(item.get("role", "")).lower()
            text = str(item.get("text", item.get("content", ""))).strip()
            if not text:
                continue
            if role == "assistant":
                rendered.append(f"Ассистент: {text}")
            else:
                rendered.append(f"Пользователь: {text}")

        return "\n".join(rendered) if rendered else "История отсутствует."

    def _build_sources(self, context: list[Chunk]) -> list[Source]:
        """Map retrieved chunks into source references for answer payload."""
        sources: list[Source] = []
        for chunk in context:
            sources.append(
                Source(
                    text=chunk.text,
                    document_id=chunk.document_id,
                    chunk_id=chunk.id,
                    score=float(chunk.metadata.get("score", 0.0)),
                )
            )
        return sources

    def _safe_int(self, value: Any, default: int) -> int:
        """Convert unknown value into integer fallback-safe."""
        try:
            return int(value)
        except (TypeError, ValueError):
            return default
