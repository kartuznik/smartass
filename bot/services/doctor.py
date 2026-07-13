"""Self-diagnostics and self-healing service for bot runtime."""

from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import Any, Callable

from aiogram import Bot

from bot.services.vector_store import VectorStore
from bot.utils.config import Settings


class Doctor:
    """Runtime health checker for Telegram API, ChromaDB, and disk usage."""

    def __init__(self, settings: Settings, bot: Bot | None = None) -> None:
        self.settings = settings
        self.bot = bot
        self.started_at = time.time()
        self.vector_store = VectorStore(settings)
        self.db_status = "Connected"
        self.last_errors: list[str] = []

    async def check_telegram_api(self) -> bool:
        """Ping Telegram getMe endpoint using current bot session."""
        if self.bot is None:
            self._remember_error("Telegram bot instance is not configured.")
            return False

        try:
            await self.bot.get_me()
            return True
        except Exception as exc:  # pragma: no cover - runtime network/API errors
            self._remember_error(f"Telegram API check failed: {exc}")
            return False

    async def check_database(self) -> bool:
        """Check ChromaDB availability and auto-heal by reconnecting."""
        try:
            await self._list_collections()
            self.db_status = "Connected"
            return True
        except Exception as exc:
            self._remember_error(f"Database check failed: {exc}")

        try:
            self.vector_store = VectorStore(self.settings)
            await self._list_collections()
            self.db_status = "Reconnected"
            return True
        except Exception as exc:  # pragma: no cover - runtime storage failures
            self.db_status = "Disconnected"
            self._remember_error(f"Database auto-heal failed: {exc}")
            return False

    def check_disk_space(self) -> tuple[bool, str, float]:
        """Check free disk percentage for configured data directory."""
        data_dir = Path(self.settings.data_dir)
        data_dir.mkdir(parents=True, exist_ok=True)

        usage = shutil.disk_usage(data_dir)
        free_percent = (usage.free / usage.total) * 100 if usage.total else 0.0
        free_gb = usage.free / (1024**3)
        message = f"{free_gb:.2f} GB free ({free_percent:.1f}%)"
        healthy = free_percent >= 10.0
        if not healthy:
            self._remember_error(f"Low disk space: {message}")
        return healthy, message, free_percent

    async def get_system_status(self) -> str:
        """Build current system diagnostics report."""
        db_ok = await self.check_database()
        disk_ok, disk_message, _ = self.check_disk_space()
        uptime_seconds = int(time.time() - self.started_at)
        uptime = self._format_uptime(uptime_seconds)

        errors = "\n".join(f"- {item}" for item in self.last_errors[-5:]) if self.last_errors else "None"
        db_label = "Connected" if db_ok else self.db_status

        return (
            f"🟢 Bot Uptime: {uptime}\n"
            f"{'🟢' if db_ok else '🔴'} DB Status: {db_label}\n"
            f"{'🟢' if disk_ok else '🔴'} Disk Space: {disk_message}\n"
            f"{'🔴' if self.last_errors else '🟢'} Errors: {errors}"
        )

    async def notify_admin(self, message: str) -> None:
        """Send diagnostic message to all configured admins."""
        if self.bot is None:
            self._remember_error("Cannot notify admin: bot instance is not configured.")
            return

        for admin_id in self.settings.admin_user_ids:
            try:
                await self.bot.send_message(chat_id=admin_id, text=message)
            except Exception as exc:  # pragma: no cover - runtime network/API errors
                self._remember_error(f"Failed to notify admin {admin_id}: {exc}")

    async def _list_collections(self) -> None:
        """Query ChromaDB collections from current client."""
        await self._to_thread(self.vector_store._client.list_collections)  # noqa: SLF001

    async def _to_thread(self, func: Callable[[], Any]) -> Any:
        """Run sync function in a thread."""
        import asyncio

        return await asyncio.to_thread(func)

    def _remember_error(self, error: str) -> None:
        """Keep bounded diagnostics error history."""
        self.last_errors.append(error)
        if len(self.last_errors) > 50:
            self.last_errors = self.last_errors[-50:]

    def _format_uptime(self, total_seconds: int) -> str:
        """Format uptime as HH:MM:SS."""
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


_doctor_instance: Doctor | None = None


def set_doctor_instance(doctor: Doctor) -> None:
    """Store global doctor instance for handlers."""
    global _doctor_instance
    _doctor_instance = doctor


def get_doctor_instance() -> Doctor | None:
    """Return global doctor instance if configured."""
    return _doctor_instance
