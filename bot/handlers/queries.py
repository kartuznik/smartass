"""Telegram query handlers with RAG search and answer generation."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram import Bot
from aiogram.types import Message

from bot.models.document import Source
from bot.services.memory import ConversationMemory
from bot.services.metrics import (
    rag_queries_failed_total,
    rag_queries_total,
    rag_query_duration_seconds,
    track_active_user,
)
from bot.services.rag import RAGService
from bot.utils.config import get_settings

router = Router(name="queries")
logger = logging.getLogger(__name__)

_settings = get_settings()
_history_limit = min(7, _settings.max_history_messages)
_memory = ConversationMemory(
    db_path=f"{_settings.data_dir}/bot_memory.db",
    max_messages=_history_limit,
)
_rag_service = RAGService(settings=_settings)


@router.message(F.text)
async def query_message_handler(message: Message) -> None:
    """Handle user question with retrieval and grounded response generation."""
    query = (message.text or "").strip()
    if not query or query.startswith("/"):
        return

    if message.from_user is None:
        await message.answer("Не удалось определить пользователя.")
        return

    user_id = message.from_user.id
    bot: Bot = message.bot
    await bot.send_chat_action(chat_id=message.chat.id, action="typing")

    try:
        await _memory.add_message(user_id=user_id, role="user", content=query)
        history = await _memory.get_history(user_id)
        track_active_user(user_id)

        with rag_query_duration_seconds.time():
            context = await _rag_service.search(
                query=query,
                top_k=_settings.default_top_k,
                user_id=user_id,
            )
            answer_result = await _rag_service.generate_answer(
                query=query,
                context=context,
                conversation_history=history,
            )

        await _memory.add_message(user_id=user_id, role="assistant", content=answer_result.answer)
        rag_queries_total.inc()
        await message.answer(_format_answer(answer_result.answer, answer_result.found, answer_result.sources))
    except Exception as exc:  # pragma: no cover - defensive runtime guard
        rag_queries_failed_total.inc()
        logger.exception("RAG pipeline failed for user_id=%s: %s", user_id, exc)
        await message.answer("Извините, сервис временно недоступен. Попробуйте через пару минут.")


def _format_answer(answer: str, found: bool, sources: list[Source]) -> str:
    """Format answer payload and append source lines when available."""
    if not found:
        return answer

    if not sources:
        return answer

    lines = [answer, "", "📚 Источники:"]
    for source in sources:
        document_id = source.document_id or "unknown"
        score = source.score
        lines.append(f"• Документ: {document_id} (насколько подходит: {score:.3f})")
    return "\n".join(lines)
