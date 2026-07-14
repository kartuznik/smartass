"""Self-diagnostics and self-healing service for bot runtime."""

from __future__ import annotations

import logging
import shutil
import time
from pathlib import Path
from typing import Any, Callable

import aiosqlite
from aiogram import Bot

from bot.services.metrics import (
    set_active_users,
    set_bot_uptime_seconds,
    set_db_connected,
    set_disk_free_percent,
    set_documents_indexed,
)
from bot.services.vector_store import VectorStore
from bot.utils.config import Settings

logger = logging.getLogger(__name__)


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
        """Check free disk percentage relative to bot data usage budget."""
        data_dir = Path(self.settings.data_dir)
        data_dir.mkdir(parents=True, exist_ok=True)

        usage = shutil.disk_usage(data_dir)
        data_used_bytes = sum(
            path.stat().st_size for path in data_dir.rglob("*") if path.is_file()
        )
        data_capacity_bytes = data_used_bytes + usage.free
        free_percent = (usage.free / data_capacity_bytes) * 100 if data_capacity_bytes else 0.0
        free_gb = usage.free / (1024**3)
        message = f"{free_gb:.2f} GB free ({free_percent:.1f}%) in data budget"
        healthy = free_percent >= 20.0
        logger.info("Disk free: %.1f%% (data_dir=%s, free_gb=%.2f)", free_percent, data_dir, free_gb)
        if not healthy:
            self._remember_error(f"Low disk space: {message}")
        set_disk_free_percent(free_percent)
        return healthy, message, free_percent

    async def get_system_status(self) -> str:
        """Build current system diagnostics report."""
        db_ok = await self.check_database()
        disk_ok, disk_message, free_percent = self.check_disk_space()
        uptime_seconds = int(time.time() - self.started_at)
        uptime = self._format_uptime(uptime_seconds)
        documents_count = len(await self.vector_store.list_documents(user_id=0))
        active_users_count = await self._count_active_users_24h()
        set_documents_indexed(documents_count)
        set_active_users(active_users_count)
        set_disk_free_percent(free_percent)
        set_db_connected(db_ok)
        set_bot_uptime_seconds(uptime_seconds)

        errors = "\n".join(f"- {item}" for item in self.last_errors[-5:]) if self.last_errors else "None"
        db_label = "Connected" if db_ok else self.db_status

        return (
            f"🟢 Bot Uptime: {uptime}\n"
            f"{'🟢' if db_ok else '🔴'} DB Status: {db_label}\n"
            f"{'🟢' if disk_ok else '🔴'} Disk Space: {disk_message}\n"
            f"🟢 Documents Indexed: {documents_count}\n"
            f"🟢 Active Users (24h): {active_users_count}\n"
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

    async def _count_active_users_24h(self) -> int:
        """Count unique users with messages in last 24 hours."""
        db_path = Path(self.settings.data_dir) / "bot_memory.db"
        if not db_path.exists():
            return 0

        async with aiosqlite.connect(str(db_path)) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS chat_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cursor = await db.execute(
                """
                SELECT COUNT(DISTINCT user_id)
                FROM chat_history
                WHERE timestamp >= datetime('now', '-1 day')
                """
            )
            row = await cursor.fetchone()
        return int(row[0] or 0)

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
