"""Prometheus metrics for RAG bot runtime."""

from __future__ import annotations

import time
from threading import Lock

from prometheus_client import Counter, Gauge, Histogram

rag_queries_total = Counter(
    "rag_queries_total",
    "Total number of successful RAG queries.",
)

rag_queries_failed_total = Counter(
    "rag_queries_failed_total",
    "Total number of failed RAG queries.",
)

rag_query_duration_seconds = Histogram(
    "rag_query_duration_seconds",
    "Total time spent processing RAG query (search + generation).",
)

active_users_total = Gauge(
    "active_users_total",
    "Unique active users over the last 24 hours.",
)

documents_indexed_total = Gauge(
    "documents_indexed_total",
    "Total number of indexed documents.",
)

disk_free_percent = Gauge(
    "disk_free_percent",
    "Free disk space percent for bot data directory.",
)

db_connected = Gauge(
    "db_connected",
    "Database connection status (1 connected, 0 disconnected).",
)

_active_user_lock = Lock()
_active_user_last_seen: dict[int, float] = {}
_ACTIVE_WINDOW_SECONDS = 24 * 60 * 60


def track_active_user(user_id: int) -> int:
    """Track active user and return currently active users count."""
    now = time.time()
    with _active_user_lock:
        _active_user_last_seen[user_id] = now
        cutoff = now - _ACTIVE_WINDOW_SECONDS
        expired = [uid for uid, last_seen in _active_user_last_seen.items() if last_seen < cutoff]
        for uid in expired:
            _active_user_last_seen.pop(uid, None)
        current_count = len(_active_user_last_seen)
        active_users_total.set(current_count)
        return current_count


def set_documents_indexed(count: int) -> None:
    """Set total indexed documents gauge value."""
    documents_indexed_total.set(max(0, count))


def set_active_users(count: int) -> None:
    """Set active users gauge value from external diagnostics."""
    active_users_total.set(max(0, count))


def set_disk_free_percent(percent: float) -> None:
    """Set free disk percent gauge value."""
    disk_free_percent.set(max(0.0, percent))


def set_db_connected(is_connected: bool) -> None:
    """Set database connection status gauge."""
    db_connected.set(1.0 if is_connected else 0.0)
