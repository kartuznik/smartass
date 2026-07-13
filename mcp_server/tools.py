"""MCP tool implementations for documentation search and inspection."""

from __future__ import annotations

from typing import Any

from mcp_server.config import get_mcp_logger, get_rag_service, get_vector_store


def _format_sources_markdown(sources: list[Any]) -> str:
    """Render sources section in readable markdown."""
    if not sources:
        return "_Источники не найдены._"

    lines = []
    for source in sources:
        document_id = getattr(source, "document_id", "unknown")
        score = float(getattr(source, "score", 0.0))
        lines.append(f"- `{document_id}` (насколько подходит: {score:.3f})")
    return "\n".join(lines)


async def search_docs(query: str, top_k: int = 3) -> str:
    """Search documentation and return generated answer with sources."""
    logger = get_mcp_logger()
    rag_service = get_rag_service()
    effective_top_k = max(1, top_k)

    try:
        logger.info("MCP search_docs called: query_length=%s top_k=%s", len(query), effective_top_k)
        context = await rag_service.search(query=query, top_k=effective_top_k)
        answer_result = await rag_service.generate_answer(
            query=query,
            context=context,
            conversation_history=[],
        )
        sources_md = _format_sources_markdown(answer_result.sources)
        return (
            f"## Ответ\n{answer_result.answer}\n\n"
            f"## Источники\n{sources_md}"
        )
    except Exception as exc:  # pragma: no cover - runtime guard
        logger.exception("MCP search_docs failed: %s", exc)
        return (
            "Не удалось выполнить поиск по документации. "
            "Проверьте настройки сервиса и повторите запрос."
        )


async def list_documents(payload: dict[str, Any] | None = None) -> str:
    """Return markdown table with all indexed documents.

    Accepts and ignores optional payload to stay compatible with clients
    that send empty arguments object or null-like payloads for no-arg tools.
    """
    logger = get_mcp_logger()
    vector_store = get_vector_store()

    try:
        logger.info("MCP list_documents called")
        documents = await vector_store.list_documents()
        if not documents:
            return "Документы пока не загружены."

        rows = [
            "| ID | Файл | Фрагментов |",
            "| --- | --- | ---: |",
        ]
        for item in documents:
            rows.append(
                f"| `{item.get('id', '')}` | {item.get('filename', 'unknown')} | {item.get('chunks_count', 0)} |"
            )
        return "\n".join(rows)
    except Exception as exc:  # pragma: no cover - runtime guard
        logger.exception("MCP list_documents failed: %s", exc)
        return "Не удалось получить список документов."


async def get_document_info(document_id: str) -> str:
    """Return detailed metadata for one document."""
    logger = get_mcp_logger()
    vector_store = get_vector_store()

    try:
        logger.info("MCP get_document_info called: document_id=%s", document_id)
        info = await vector_store.get_document_info(document_id)
        if not info:
            return f"Документ `{document_id}` не найден."

        metadata = info.get("metadata", {})
        metadata_lines = "\n".join(
            f"- **{key}**: {value}" for key, value in metadata.items()
        ) or "- _нет дополнительных данных_"

        return (
            f"## Документ `{info.get('id')}`\n"
            f"- **Имя файла**: {info.get('filename')}\n"
            f"- **Загрузил пользователь**: {info.get('uploaded_by')}\n"
            f"- **Дата загрузки**: {info.get('uploaded_at')}\n"
            f"- **Фрагментов**: {info.get('chunks_count')}\n\n"
            "### Метаданные\n"
            f"{metadata_lines}"
        )
    except Exception as exc:  # pragma: no cover - runtime guard
        logger.exception("MCP get_document_info failed: %s", exc)
        return f"Не удалось получить информацию о документе `{document_id}`."
