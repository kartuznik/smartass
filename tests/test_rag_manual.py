"""Manual RAG smoke test (run as a script, not as unit test)."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from time import perf_counter

from bot.services.document_processor import DocumentProcessor
from bot.services.rag import RAGService
from bot.services.vector_store import VectorStore
from bot.utils.config import get_settings
from bot.utils.logger import configure_logging


async def run_manual_test(question: str, document_path: str | None, top_k: int) -> None:
    """Ingest one test document, run retrieval/generation, and print diagnostics."""
    settings = get_settings()
    logger = configure_logging(settings)

    processor = DocumentProcessor(settings)
    vector_store = VectorStore(settings)
    rag_service = RAGService(settings=settings, vector_store=vector_store)

    docs_dir = Path(settings.docs_dir)
    docs_dir.mkdir(parents=True, exist_ok=True)

    cleanup_path: Path | None = None
    if document_path:
        source_path = Path(document_path).expanduser().resolve()
    else:
        source_path = docs_dir / "manual_rag_test.md"
        source_path.write_text(
            "# Manual RAG test document\n\n"
            "RAG (Retrieval-Augmented Generation) combines semantic search and LLM generation.\n"
            "The vector database stores embeddings for document chunks.\n"
            "Chunks are retrieved by relevance score and then passed as context to the model.\n",
            encoding="utf-8",
        )
        cleanup_path = source_path

    logger.info("Manual RAG test started with document: %s", source_path)

    document, chunks = await processor.process_document(source_path, uploaded_by=0)
    await vector_store.add_document(document, chunks)

    search_started_at = perf_counter()
    found_chunks = await rag_service.search(question, top_k=top_k)
    search_ms = int((perf_counter() - search_started_at) * 1000)

    generate_started_at = perf_counter()
    answer = await rag_service.generate_answer(
        query=question,
        context=found_chunks,
        conversation_history=[
            {"role": "user", "text": "Привет!"},
            {"role": "assistant", "text": "Здравствуйте, чем помочь?"},
        ],
    )
    generate_ms = int((perf_counter() - generate_started_at) * 1000)

    print("\n=== RAG MANUAL TEST ===")
    print(f"Question: {question}")
    print(f"Found context: {answer.found}")
    print(f"Search time: {search_ms} ms")
    print(f"Generation time: {generate_ms} ms")
    print("\nAnswer:")
    print(answer.answer)
    print("\nSources:")
    if not answer.sources:
        print("- none")
    for source in answer.sources:
        preview = source.text[:160].replace("\n", " ")
        print(
            f"- doc_id={source.document_id} chunk_id={source.chunk_id} "
            f"score={source.score:.4f} text='{preview}...'"
        )

    await vector_store.delete_document(document.id)
    if cleanup_path and cleanup_path.exists():
        cleanup_path.unlink()

    logger.info("Manual RAG test finished.")


def parse_args() -> argparse.Namespace:
    """Parse script command line arguments."""
    parser = argparse.ArgumentParser(description="Run manual RAG smoke test.")
    parser.add_argument(
        "--question",
        type=str,
        default="Что такое RAG и как он работает?",
        help="Question passed to retrieval and generation.",
    )
    parser.add_argument(
        "--document",
        type=str,
        default=None,
        help="Optional path to .md/.pdf document used for ingestion.",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=3,
        help="How many chunks to retrieve.",
    )
    return parser.parse_args()


def main() -> None:
    """Entry point for manual execution."""
    args = parse_args()
    asyncio.run(run_manual_test(args.question, args.document, args.top_k))


if __name__ == "__main__":
    main()
