"""Telegram bot entrypoint with routers and polling startup."""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.handlers.commands import get_bot_commands
from bot.handlers.commands import router as commands_router
from bot.handlers.documents import router as documents_router
from bot.handlers.queries import router as queries_router
from bot.utils.config import get_settings
from bot.utils.logger import configure_logging


async def run_bot() -> None:
    """Initialize bot and start polling."""
    settings = get_settings()
    logger = configure_logging(settings)
    logger.info("Starting RAG Telegram Bot (env=%s)", settings.app_env)

    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN),
    )
    dp = Dispatcher()

    dp.include_router(commands_router)
    dp.include_router(documents_router)
    dp.include_router(queries_router)

    await bot.set_my_commands(get_bot_commands())
    logger.info("Bot commands registered.")

    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


def main() -> None:
    """Run bot with asyncio event loop."""
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("Bot stopped by user.")


if __name__ == "__main__":
    main()
