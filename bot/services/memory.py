"""Persistent async SQLite-based conversation memory per user."""

from __future__ import annotations

import aiosqlite


class ConversationMemory:
    """Store bounded chat history in SQLite keyed by user_id."""

    def __init__(self, db_path: str, max_messages: int = 7) -> None:
        self.db_path = db_path
        self.max_messages = max(1, max_messages)
        self._initialized = False

    async def add_message(self, user_id: int, role: str, content: str) -> None:
        """Append message and keep only recent items for user."""
        normalized_content = content.strip()
        if not normalized_content:
            return

        await self._ensure_initialized()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO chat_history (user_id, role, content)
                VALUES (?, ?, ?)
                """,
                (user_id, role, normalized_content),
            )
            await db.execute(
                """
                DELETE FROM chat_history
                WHERE user_id = ?
                  AND id NOT IN (
                    SELECT id
                    FROM chat_history
                    WHERE user_id = ?
                    ORDER BY timestamp DESC, id DESC
                    LIMIT ?
                  )
                """,
                (user_id, user_id, self.max_messages),
            )
            await db.commit()

    async def get_history(self, user_id: int) -> list[dict[str, str]]:
        """Return last N messages for user ordered oldest->newest."""
        await self._ensure_initialized()
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                """
                SELECT role, content
                FROM chat_history
                WHERE user_id = ?
                ORDER BY timestamp DESC, id DESC
                LIMIT ?
                """,
                (user_id, self.max_messages),
            )
            rows = await cursor.fetchall()

        return [
            {"role": row[0], "content": row[1]}
            for row in reversed(rows)
        ]

    async def clear(self, user_id: int) -> None:
        """Clear stored conversation for a user."""
        await self._ensure_initialized()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM chat_history WHERE user_id = ?", (user_id,))
            await db.commit()

    async def _ensure_initialized(self) -> None:
        """Create storage table once before first use."""
        if self._initialized:
            return

        async with aiosqlite.connect(self.db_path) as db:
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
            await db.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_chat_history_user_time
                ON chat_history (user_id, timestamp DESC)
                """
            )
            await db.commit()
        self._initialized = True
