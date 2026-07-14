"""General command handlers: start/help/stats and bot command menu."""

from __future__ import annotations

import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import BotCommand, Message

from bot.handlers.documents import get_vector_store
from bot.services.cache import cache
from bot.services.doctor import get_doctor_instance
from bot.utils.config import get_settings

router = Router(name="commands")
logger = logging.getLogger(__name__)
settings = get_settings()


def get_bot_commands() -> list[BotCommand]:
    """Return command list for Telegram command menu."""
    return [
        BotCommand(command="start", description="Запуск бота"),
        BotCommand(command="help", description="Помощь по командам"),
        BotCommand(command="upload", description="Как загрузить документ"),
        BotCommand(command="list", description="Список загруженных документов"),
        BotCommand(command="delete", description="Удалить документ по ID"),
        BotCommand(command="stats", description="Статистика базы документов"),
        BotCommand(command="doctor", description="Диагностика системы"),
        BotCommand(command="clearcache", description="Очистить кэш ответов"),
    ]


@router.message(Command("start"))
async def start_command_handler(message: Message) -> None:
    """Send greeting and quick usage overview."""
    await message.answer(
        "Привет! 👋 Я ваш умный помощник по работе с документами.\n\n"
        "Что я умею:\n"
        "📥 Принимаю файлы (PDF, Markdown)\n"
        "🔍 Мгновенно нахожу нужную информацию\n"
        "💡 Отвечаю на вопросы по их содержимому\n\n"
        "Чтобы начать, загрузите первый документ командой /upload или просто задайте мне вопрос!"
    )


@router.message(Command("help"))
async def help_command_handler(message: Message) -> None:
    """Show supported commands."""
    await message.answer(
        "С радостью помогу! Вот что можно сделать:\n\n"
        "📥 `/upload` — загрузить файл\n"
        "📚 `/list` — посмотреть загруженные документы\n"
        "🗑 `/delete <id>` — удалить документ\n"
        "📊 `/stats` — посмотреть общую статистику\n"
        "❓ `/help` — открыть эту подсказку снова"
    )


@router.message(Command("stats"))
async def stats_command_handler(message: Message) -> None:
    """Show amount of indexed documents and chunks."""
    try:
        if message.from_user is None:
            await message.answer("Не удалось определить пользователя.")
            return
        vector_store = get_vector_store()
        documents = await vector_store.list_documents(user_id=message.from_user.id)
        chunks_count = await vector_store.count_chunks(user_id=message.from_user.id)

        await message.answer(
            "Текущая статистика:\n"
            f"- Документов: `{len(documents)}`\n"
            f"- Фрагментов текста: `{chunks_count}`\n"
            "- Запросов: `пока не отслеживается`"
        )
    except Exception as exc:  # pragma: no cover - defensive runtime guard
        logger.exception("Failed to build stats: %s", exc)
        await message.answer("Не удалось получить статистику.")


@router.message(Command("doctor"))
async def doctor_command_handler(message: Message) -> None:
    """Return runtime health report for admins only."""
    if message.from_user is None or message.from_user.id not in settings.admin_user_ids:
        await message.answer("Команда доступна только администраторам.")
        return

    doctor = get_doctor_instance()
    if doctor is None:
        await message.answer("Сервис диагностики ещё не инициализирован.")
        return

    report = await doctor.get_system_status()
    await message.answer(report)


@router.message(Command("clearcache"))
async def clearcache_command_handler(message: Message) -> None:
    """Clear Redis cache for repeated RAG queries (admins only)."""
    if message.from_user is None or message.from_user.id not in settings.admin_user_ids:
        await message.answer("Команда доступна только администраторам.")
        return

    deleted = await cache.clear()
    await message.answer(f"✅ Кэш очищен (ключей удалено: {deleted})")
