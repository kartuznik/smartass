"""MCP SSE server exposing documentation RAG tools."""

from __future__ import annotations

import os
from typing import Any

from mcp_server.config import get_mcp_logger
from mcp_server.tools import get_document_info, list_documents, search_docs

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as exc:  # pragma: no cover - import guard for missing dependency
    raise RuntimeError(
        "Python package 'mcp' is not installed. Install dependencies with 'pip install -r requirements.txt'."
    ) from exc


def create_server() -> FastMCP:
    """Initialize FastMCP application and register tools."""
    logger = get_mcp_logger()
    logger.info("Initializing MCP server.")
    host = os.getenv("MCP_SERVER_HOST", "0.0.0.0")
    port = int(os.getenv("MCP_SERVER_PORT", "8000"))

    mcp = FastMCP("rag-telegram-bot", host=host, port=port, sse_path="/sse")

    @mcp.tool(
        name="search_docs",
        description="Поиск по документации и ответ с источниками.",
    )
    async def search_docs_tool(query: str, top_k: int = 3) -> str:
        return await search_docs(query=query, top_k=top_k)

    @mcp.tool(
        name="list_documents",
        description="Список загруженных документов.",
    )
    async def list_documents_tool(payload: dict[str, Any] | None = None) -> str:
        return await list_documents(payload=payload)

    @mcp.tool(
        name="get_document_info",
        description="Детальная информация о документе по его ID.",
    )
    async def get_document_info_tool(document_id: str) -> str:
        return await get_document_info(document_id=document_id)

    return mcp


def main() -> None:
    """Entrypoint for running MCP server over SSE transport."""
    logger = get_mcp_logger()
    server = create_server()
    host = os.getenv("MCP_SERVER_HOST", "0.0.0.0")
    port = int(os.getenv("MCP_SERVER_PORT", "8000"))
    logger.info("Starting MCP SSE server on %s:%s.", host, port)
    server.run(transport="sse")


if __name__ == "__main__":
    main()
