"""Telegram handlers for document upload and document management commands."""

from __future__ import annotations

import logging
from pathlib import Path
from uuid import uuid4

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.services.document_processor import (
    DocumentProcessingError,
    DocumentProcessor,
    EmptyDocumentError,
    UnsupportedDocumentTypeError,
)
from bot.services.vector_store import VectorStore
from bot.utils.config import get_settings

router = Router(name="documents")
logger = logging.getLogger(__name__)

_settings = get_settings()
_document_processor = DocumentProcessor(_settings)
_vector_store = VectorStore(_settings)

_ALLOWED_EXTENSIONS = {".pdf", ".md", ".markdown"}


def get_vector_store() -> VectorStore:
    """Return shared vector store instance used by handlers."""
    return _vector_store


@router.message(Command("upload"))
async def upload_command_handler(message: Message) -> None:
    """Show upload instructions for PDF/Markdown files."""
    await message.answer(
        "Отправьте мне файл прямо в этот чат 📎\n\n"
        "Поддерживаемые форматы:\n"
        "• PDF документы\n"
        "• Markdown файлы (.md)\n\n"
        "Как только вы отправите файл, я его проанализирую и сразу смогу отвечать на любые вопросы по его содержимому! ✨"
    )


@router.message(F.document)
async def handle_document_upload(message: Message) -> None:
    """Handle uploaded Telegram document and ingest it into vector storage."""
    document = message.document
    if document is None:
        return

    file_name = (document.file_name or "").strip()
    extension = Path(file_name).suffix.lower()
    if extension not in _ALLOWED_EXTENSIONS:
        await message.answer(
            "К сожалению, я не могу обработать этот файл 😔\n"
            "Поддерживаю только PDF и Markdown (.md) документы.\n"
            "Попробуйте загрузить файл в одном из этих форматов!"
        )
        return

    if message.from_user is None:
        await message.answer("Не удалось определить пользователя загрузки.")
        return

    docs_dir = Path(_settings.docs_dir)
    docs_dir.mkdir(parents=True, exist_ok=True)
    safe_name = file_name.replace("/", "_").replace("\\", "_")
    local_path = docs_dir / f"{uuid4()}_{safe_name}"

    try:
        telegram_file = await message.bot.get_file(document.file_id)
        await message.bot.download_file(telegram_file.file_path, destination=local_path)

        source_document, chunks = await _document_processor.process_document(
            file_path=local_path,
            uploaded_by=message.from_user.id,
        )
        await _vector_store.add_document(source_document, chunks)

        await message.answer(
            "Отлично! Документ загружен и готов к работе 📚\n"
            "Теперь вы можете задавать вопросы по его содержимому — я найду нужную информацию!"
        )
    except (UnsupportedDocumentTypeError, EmptyDocumentError, DocumentProcessingError) as exc:
        logger.warning("Failed to process document '%s': %s", file_name, exc)
        await message.answer(f"Не удалось обработать документ: {exc}")
    except Exception as exc:  # pragma: no cover - defensive runtime guard
        logger.exception("Unexpected error while uploading '%s': %s", file_name, exc)
        await message.answer("Внутренняя ошибка при обработке документа. Попробуйте позже.")


@router.message(Command("list"))
async def list_documents_handler(message: Message) -> None:
    """List all indexed documents from vector store."""
    try:
        documents = await _vector_store.list_documents()
        if not documents:
            await message.answer("Список документов пуст.")
            return

        lines = ["Загруженные документы:"]
        for item in documents:
            lines.append(
                f"- `{item['id']}` | {item['filename']} | фрагментов: {item['chunks_count']}"
            )
        await message.answer("\n".join(lines))
    except Exception as exc:  # pragma: no cover - defensive runtime guard
        logger.exception("Failed to list documents: %s", exc)
        await message.answer("Не удалось получить список документов.")


@router.message(Command("delete"))
async def delete_document_handler(message: Message) -> None:
    """Delete all indexed chunks for provided document id."""
    text = (message.text or "").strip()
    parts = text.split(maxsplit=1)
    if len(parts) < 2 or not parts[1]:
        await message.answer("Использование: `/delete <document_id>`")
        return

    document_id = parts[1].strip()
    try:
        deleted = await _vector_store.delete_document(document_id)
        if deleted == 0:
            await message.answer(f"Документ `{document_id}` не найден.")
            return
        await message.answer(f"Документ `{document_id}` удалён. Удалено фрагментов: `{deleted}`.")
    except Exception as exc:  # pragma: no cover - defensive runtime guard
        logger.exception("Failed to delete document '%s': %s", document_id, exc)
        await message.answer("Не удалось удалить документ.")
