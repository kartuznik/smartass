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

MCP-сервер запускается через stdio:

```bash
python3 -m mcp_server.server
```

Пример блока для `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "rag-telegram-bot": {
      "command": "python3",
      "args": ["-m", "mcp_server.server"],
      "cwd": "/absolute/path/to/rag-telegram-bot"
    }
  }
}
```

Для Cursor добавьте MCP-сервер с той же командой запуска:
- command: `python3`
- args: `-m mcp_server.server`
- cwd: абсолютный путь к проекту

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
