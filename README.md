# RAG Telegram Bot

Production-oriented Telegram bot with RAG (Retrieval-Augmented Generation),
ChromaDB vector store, and MCP server integration.

## Stage 1 Status

Completed:

- Project structure scaffolded
- Environment configuration template added
- Typed settings loader via `pydantic-settings`
- Logging setup with rotating file logs
- Base data models (`Document`, `Chunk`, `QueryResult`)

## Quick Start (local)

1. Copy environment template:

   ```bash
   cp .env.example .env
   ```

2. Install dependencies:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

3. Fill required values in `.env`:
   - `TELEGRAM_BOT_TOKEN`
   - `OPENAI_API_KEY`

## Planned Next Stages

- Document processing (PDF/Markdown + chunking)
- ChromaDB integration and retrieval
- RAG answer generation
- aiogram handlers and dialog context
- MCP server tools
- Docker deployment and tests
