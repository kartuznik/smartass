"""In-memory conversation history storage per Telegram user."""

from __future__ import annotations

from collections import defaultdict


class ConversationMemory:
    """Store bounded chat history in RAM keyed by user_id."""

    def __init__(self, max_messages: int = 7) -> None:
        self.max_messages = max(1, max_messages)
        self._storage: dict[int, list[dict[str, str]]] = defaultdict(list)

    def add(self, user_id: int, role: str, content: str) -> None:
        """Append message to user history and keep only recent items."""
        normalized_content = content.strip()
        if not normalized_content:
            return

        history = self._storage[user_id]
        history.append({"role": role, "content": normalized_content})
        if len(history) > self.max_messages:
            self._storage[user_id] = history[-self.max_messages :]

    def get(self, user_id: int) -> list[dict[str, str]]:
        """Return copy of user history for safe external usage."""
        return list(self._storage.get(user_id, []))

    def clear(self, user_id: int) -> None:
        """Clear stored conversation for a user."""
        self._storage.pop(user_id, None)
