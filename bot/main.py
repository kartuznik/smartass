"""Telegram bot entrypoint with routers and polling startup."""

from __future__ import annotations

import asyncio
import logging
import threading

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from prometheus_client import start_http_server

from bot.handlers.commands import get_bot_commands
from bot.handlers.commands import router as commands_router
from bot.handlers.documents import router as documents_router
from bot.handlers.queries import router as queries_router
from bot.services.doctor import Doctor, set_doctor_instance
from bot.utils.config import get_settings
from bot.utils.logger import configure_logging


async def health_check_loop(doctor: Doctor) -> None:
    """Run periodic health checks and notify admins on critical failures."""
    logger = logging.getLogger(__name__)
    while True:
        try:
            db_ok = await doctor.check_database()
            disk_ok, disk_message, _ = doctor.check_disk_space()
            logger.info(
                "Health check: db_ok=%s, disk_ok=%s, disk_free=%s",
                db_ok,
                disk_ok,
                disk_message,
            )

            if not db_ok:
                await doctor.notify_admin("🔴 Критично: не удалось восстановить подключение к базе данных.")
            if not disk_ok:
                await doctor.notify_admin(
                    f"🔴 Критично: свободное место на диске ниже порога: {disk_message} (<10%)."
                )

            await asyncio.sleep(300)
        except asyncio.CancelledError:
            logger.info("Health check loop cancelled.")
            raise
        except Exception as exc:  # pragma: no cover - defensive runtime guard
            logger.exception("Health check loop failed: %s", exc)
            await doctor.notify_admin(f"🔴 Ошибка health-check цикла: {exc}")
            await asyncio.sleep(30)


def start_metrics_server_in_background(port: int) -> None:
    """Start Prometheus HTTP exporter in background daemon thread."""
    threading.Thread(target=start_http_server, args=(port,), daemon=True).start()


async def run_bot() -> None:
    """Initialize bot and start polling."""
    settings = get_settings()
    logger = configure_logging(settings)
    logger.info("Starting RAG Telegram Bot (env=%s)", settings.app_env)
    start_metrics_server_in_background(8001)
    logger.info("Prometheus metrics server started on 0.0.0.0:8001")

    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN),
    )
    doctor = Doctor(settings=settings, bot=bot)
    set_doctor_instance(doctor)

    dp = Dispatcher()

    dp.include_router(commands_router)
    dp.include_router(documents_router)
    dp.include_router(queries_router)

    await bot.set_my_commands(get_bot_commands())
    logger.info("Bot commands registered.")
    health_task = asyncio.create_task(health_check_loop(doctor))

    try:
        await dp.start_polling(bot)
    finally:
        health_task.cancel()
        try:
            await health_task
        except asyncio.CancelledError:
            logger.info("Health check task stopped.")
        await bot.session.close()


def main() -> None:
    """Run bot with asyncio event loop."""
    try:
        asyncio.run(run_bot())
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("Bot stopped by user.")


if __name__ == "__main__":
    main()
