# RAG Telegram Bot (smartass) — Runbook

Операционное руководство для self-hosted деплоя. Секреты, hostname и публичные IP сюда не пишем — используйте `.env` и Compose-проект окружения.

> Каталог `docs/` совмещает **аплоады корпуса** (PDF/MD пользователей) и ops-файлы (`RUNBOOK.md`, `demo/`). При backup копируйте аплоады; при docs-задачах **не изменяйте** загруженные файлы пользователей.

## Deploy

1. Клонируйте репозиторий и создайте `.env` из `.env.example`.
2. Обязательно: `TELEGRAM_BOT_TOKEN`, `OPENAI_API_KEY`, `ADMIN_USER_IDS`, `TELEGRAM_ALERT_CHAT_ID`, `REDIS_URL`, `ADMIN_PASSWORD`.
3. Опционально: `EMBEDDING_MODEL`, `LLM_MODEL`, пути `DATA_DIR` / `DOCS_DIR` / `CHROMA_PERSIST_DIRECTORY`.
4. Запуск:

```bash
docker compose up -d --build
docker compose ps
```

5. Проверка:
   - Логи bot: `docker compose logs --tail=100 bot`
   - MCP SSE отвечает на порту `:8000`
   - Admin panel на `:8003` (пароль из `ADMIN_PASSWORD`)
   - Prometheus `:9090`, Grafana `:3000`, Redis `:6379`
   - Метрики бота `:8001/metrics`, MCP host-mapping `:8002/metrics`

После docs-only изменений пересборка не нужна. После изменений кода:

```bash
docker compose up -d --build bot mcp admin-panel
```

(при необходимости также `prometheus` / `grafana`).

## Backup и restore

### Что включать

| Путь | Содержимое |
|---|---|
| `data/chroma_db/` | Векторный индекс ChromaDB |
| `data/bot_memory.db` | Память/состояние бота (SQLite) |
| `docs/*.pdf`, прочие пользовательские аплоады в `docs/` | Загруженный корпус |
| `.env` | Секреты — **вне** git, отдельное шифрованное хранилище |

Не обязательно бэкапить как «данные продукта»: `docs/RUNBOOK.md`, `docs/demo/` (они в git).

### Холодный backup (пример)

```bash
docker compose stop bot mcp admin-panel
mkdir -p ./backups
tar -czf ./backups/rag-data-$(date +%Y%m%d).tar.gz data
# аплоады корпуса (исключая ops, если удобно фильтровать вручную):
tar -czf ./backups/rag-uploads-$(date +%Y%m%d).tar.gz --exclude='docs/RUNBOOK.md' --exclude='docs/demo' docs
docker compose start bot mcp admin-panel
```

### Restore

1. Остановить сервисы, пишущие в `data/` / `docs/`.
2. Распаковать архивы на место.
3. `docker compose up -d`
4. Smoke: `/start`, простой вопрос по известному документу, вход в admin `:8003`, `/doctor` (админ).

## Ротация ключей

Ротируйте один секрет за раз; после recreate — smoke.

| Секрет | Шаги |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Новый токен в BotFather → `.env` → recreate `bot` (и Grafana, если тот же токен в алертах) |
| `OPENAI_API_KEY` | Новый ключ → `.env` → recreate `bot` и `mcp` → отозвать старый после smoke |
| `ADMIN_PASSWORD` | Обновить `.env` → recreate `admin-panel` |
| `TELEGRAM_ALERT_CHAT_ID` | Обновить `.env` → recreate `grafana` |
| `REDIS_URL` | Обновить при смене Redis → recreate потребителей кэша |

После ручной правки `.env`: `grep '^VAR=' .env` по каждой изменённой строке **до** recreate (см. `/opt/standards/RULES.md` §4a).

## Инциденты

### RAG не отвечает / ошибки OpenAI

- Логи `bot` / `mcp`; баланс и валидность `OPENAI_API_KEY`.
- Проверьте, что документы проиндексированы (`/list`).
- Пользователю — честный отказ; не маскировать сбой «общими знаниями» модели как ответ по корпусу.

### MCP недоступен

- `docker compose ps` / `logs mcp`; порт `:8000`.
- Конфиг Cursor: URL SSE без секретов в git.

### Redis / кэш

- При падении Redis кэш soft-fail; проверьте `REDIS_URL` и контейнер `redis`.
- Очистка кэша (осознанно): `docker compose exec redis redis-cli FLUSHALL`

### Grafana / алерты

- `docker compose logs --tail=100 grafana`
- Contact point через env (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALERT_CHAT_ID`), не через YAML с секретами.

### Admin panel

- Порт `:8003`, пароль `ADMIN_PASSWORD` (не печатать в чат).
- Права на тома `data` / `docs` / `logs`.

## Rollback

```bash
git log --oneline -5
git checkout <known-good-sha>
docker compose up -d --build
```

При повреждении индекса/БД — restore из backup `data/` (и аплоадов при необходимости) до smoke.
