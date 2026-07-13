"""Shared configuration/bootstrap for MCP server runtime."""

from __future__ import annotations

import logging
from functools import lru_cache

from bot.services.rag import RAGService
from bot.services.vector_store import VectorStore
from bot.utils.config import Settings, get_settings
from bot.utils.logger import configure_logging


@lru_cache(maxsize=1)
def get_mcp_settings() -> Settings:
    """Return shared settings for MCP server."""
    return get_settings()


@lru_cache(maxsize=1)
def get_mcp_logger() -> logging.Logger:
    """Configure and return MCP logger."""
    settings = get_mcp_settings()
    configure_logging(settings)
    return logging.getLogger("mcp_server")


@lru_cache(maxsize=1)
def get_vector_store() -> VectorStore:
    """Return singleton vector store for MCP tools."""
    settings = get_mcp_settings()
    return VectorStore(settings)


@lru_cache(maxsize=1)
def get_rag_service() -> RAGService:
    """Return singleton RAG service for MCP tools."""
    settings = get_mcp_settings()
    return RAGService(settings=settings, vector_store=get_vector_store())
