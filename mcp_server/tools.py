"""MCP tool implementations for documentation search and inspection."""

from __future__ import annotations

from typing import Any, Optional

from mcp_server.config import get_mcp_logger, get_rag_service, get_vector_store

ADMIN_USER_ID = 0


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


def _extract_field(
    direct_value: Any,
    field_name: str,
    payload: dict[str, Any] | None,
    arguments: dict[str, Any] | None,
) -> Any:
    """Resolve field value from direct arg, payload or nested arguments."""
    if direct_value is not None:
        return direct_value

    merged: dict[str, Any] = {}
    if isinstance(arguments, dict):
        merged.update(arguments)
    if isinstance(payload, dict):
        merged.update(payload)

    nested_arguments = merged.get("arguments")
    if isinstance(nested_arguments, dict):
        merged.update(nested_arguments)

    return merged.get(field_name)


async def search_docs(
    query: Optional[str] = None,
    top_k: Optional[int] = 3,
    payload: dict[str, Any] | None = None,
    arguments: dict[str, Any] | None = None,
) -> str:
    """Search documentation and return generated answer with sources."""
    logger = get_mcp_logger()
    rag_service = get_rag_service()
    logger.info(
        "search_docs called with query=%r top_k=%r payload=%r arguments=%r",
        query,
        top_k,
        payload,
        arguments,
    )

    resolved_query = _extract_field(query, "query", payload, arguments)
    resolved_top_k = _extract_field(top_k, "top_k", payload, arguments)
    if not isinstance(resolved_query, str) or not resolved_query.strip():
        return "Параметр `query` обязателен и должен быть непустой строкой."

    try:
        parsed_top_k = int(resolved_top_k) if resolved_top_k is not None else 3
    except (TypeError, ValueError):
        parsed_top_k = 3
    effective_top_k = max(1, parsed_top_k)

    try:
        logger.info("MCP search_docs resolved: query_length=%s top_k=%s", len(resolved_query), effective_top_k)
        context = await rag_service.search(query=resolved_query, top_k=effective_top_k, user_id=ADMIN_USER_ID)
        answer_result = await rag_service.generate_answer(
            query=resolved_query,
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


async def list_documents(
    payload: dict[str, Any] | None = None,
    arguments: dict[str, Any] | None = None,
) -> str:
    """Return markdown table with all indexed documents.

    Accepts and ignores optional payload to stay compatible with clients
    that send empty arguments object or null-like payloads for no-arg tools.
    """
    logger = get_mcp_logger()
    vector_store = get_vector_store()

    try:
        logger.info("list_documents called with payload=%r arguments=%r", payload, arguments)
        documents = await vector_store.list_documents(user_id=ADMIN_USER_ID)
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


async def get_document_info(
    document_id: Optional[str] = None,
    payload: dict[str, Any] | None = None,
    arguments: dict[str, Any] | None = None,
) -> str:
    """Return detailed metadata for one document."""
    logger = get_mcp_logger()
    vector_store = get_vector_store()
    logger.info(
        "get_document_info called with document_id=%r payload=%r arguments=%r",
        document_id,
        payload,
        arguments,
    )

    resolved_document_id = _extract_field(document_id, "document_id", payload, arguments)
    if not isinstance(resolved_document_id, str) or not resolved_document_id.strip():
        return "Параметр `document_id` обязателен и должен быть непустой строкой."

    try:
        logger.info("MCP get_document_info resolved: document_id=%s", resolved_document_id)
        info = await vector_store.get_document_info(resolved_document_id, user_id=ADMIN_USER_ID)
        if not info:
            return f"Документ `{resolved_document_id}` не найден."

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
        return f"Не удалось получить информацию о документе `{resolved_document_id}`."
