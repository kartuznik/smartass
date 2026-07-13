# RAG Telegram Bot

Telegram-бот для вопросов по загруженным PDF/Markdown документам с RAG-поиском, ChromaDB и MCP-сервером для Claude/Cursor.

## ⚙️ Настройка окружения

1. Скопируйте шаблон переменных:

```bash
cp .env.example .env
```

2. Заполните в `.env` минимум:
- `TELEGRAM_BOT_TOKEN`
- `OPENAI_API_KEY`

По умолчанию бот хранит данные в:
- `data/chroma_db` — база поиска по документам
- `docs` — загруженные файлы

## 🚀 Быстрый старт с Docker

Запуск бота:

```bash
docker compose up -d --build
```

Проверка логов:

```bash
docker compose logs -f bot
```

Остановка:

```bash
docker compose down
```

## 🔌 Интеграция MCP

MCP-сервер запускается как HTTP(SSE) сервис на VPS:

```bash
docker compose up -d --build mcp
```

По умолчанию он слушает `0.0.0.0:8000`, а SSE endpoint доступен по URL:

```text
http://YOUR_VPS_IP:8000/sse
```

Пример настройки MCP для Cursor:

```json
{
  "mcpServers": {
    "smartass-rag": {
      "url": "http://YOUR_VPS_IP:8000/sse"
    }
  }
}
```

Если запускаете без Docker:

```bash
python3 -m mcp_server.server
```

Доступные MCP-инструменты:
- `search_docs(query, top_k=3)`
- `list_documents()`
- `get_document_info(document_id)`

## 🛠 Локальная разработка

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 -m bot.main
```

Ручная проверка RAG без Telegram:

```bash
python3 tests/test_rag_manual.py
```
