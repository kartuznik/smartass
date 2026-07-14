"""FastAPI-based web admin panel for bot operations."""

from __future__ import annotations

import secrets
import time
from pathlib import Path
from uuid import uuid4

import aiofiles
import uvicorn
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile, status
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from bot.services.cache import cache
from bot.services.document_processor import DocumentProcessor
from bot.services.vector_store import VectorStore
from bot.utils.config import get_settings

app = FastAPI(title="RAG Bot Admin Panel")
security = HTTPBasic()
settings = get_settings()

document_processor = DocumentProcessor(settings)
vector_store = VectorStore(settings)
started_at = time.time()
allowed_extensions = {".pdf", ".md", ".markdown", ".txt"}


def _authenticate(credentials: HTTPBasicCredentials = Depends(security)) -> str:
    """Validate HTTP Basic credentials for admin panel."""
    is_valid_user = secrets.compare_digest(credentials.username, "admin")
    is_valid_password = secrets.compare_digest(credentials.password, settings.admin_password)
    if not (is_valid_user and is_valid_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


def _format_uptime(seconds: int) -> str:
    hours, remainder = divmod(seconds, 3600)
    minutes, sec = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{sec:02d}"


@app.get("/", response_class=HTMLResponse)
async def admin_index(_: str = Depends(_authenticate)) -> str:
    """Return admin panel single-page HTML."""
    return """<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>RAG Admin Panel</title>
  <style>
    body { font-family: Arial, sans-serif; background:#111827; color:#e5e7eb; margin:0; padding:24px; }
    h1 { margin:0 0 16px 0; }
    .grid { display:grid; grid-template-columns: repeat(3,minmax(0,1fr)); gap:12px; margin-bottom:20px; }
    .card { background:#1f2937; border:1px solid #374151; border-radius:12px; padding:14px; }
    .label { color:#9ca3af; font-size:13px; }
    .value { font-size:24px; font-weight:700; margin-top:6px; }
    .row { display:flex; gap:10px; margin:10px 0; }
    button { background:#2563eb; color:white; border:none; border-radius:8px; padding:10px 14px; cursor:pointer; }
    button:hover { background:#1d4ed8; }
    input[type=file] { background:#111827; color:#e5e7eb; border:1px solid #374151; border-radius:8px; padding:8px; }
    table { width:100%; border-collapse: collapse; margin-top:10px; }
    th, td { border-bottom:1px solid #374151; text-align:left; padding:8px; font-size:14px; }
    .muted { color:#9ca3af; font-size:13px; }
  </style>
</head>
<body>
  <h1>RAG Admin Panel</h1>
  <p class="muted">Управление документами, кэшем и состоянием бота.</p>

  <div class="grid">
    <div class="card"><div class="label">Документы</div><div id="stat-docs" class="value">-</div></div>
    <div class="card"><div class="label">Кэш (ключей)</div><div id="stat-cache" class="value">-</div></div>
    <div class="card"><div class="label">Аптайм</div><div id="stat-uptime" class="value">-</div></div>
  </div>

  <div class="card">
    <h3>Загрузка файла</h3>
    <div class="row">
      <input id="fileInput" type="file" accept=".pdf,.md,.markdown,.txt" />
      <button onclick="uploadFile()">Загрузить</button>
      <button onclick="clearCache()">Очистить кэш</button>
    </div>
    <div id="upload-status" class="muted"></div>
  </div>

  <div class="card" style="margin-top:12px;">
    <h3>Список документов</h3>
    <table>
      <thead><tr><th>ID</th><th>Файл</th><th>Фрагментов</th></tr></thead>
      <tbody id="docs-table"></tbody>
    </table>
  </div>

  <script>
    async function refreshStats() {
      const data = await fetch('/api/stats').then(r => r.json());
      document.getElementById('stat-docs').textContent = data.documents_count;
      document.getElementById('stat-cache').textContent = data.cache_keys;
      document.getElementById('stat-uptime').textContent = data.uptime;
    }

    async function refreshDocs() {
      const rows = await fetch('/api/documents').then(r => r.json());
      const tbody = document.getElementById('docs-table');
      tbody.innerHTML = '';
      for (const row of rows) {
        const tr = document.createElement('tr');
        tr.innerHTML = `<td>${row.id}</td><td>${row.filename}</td><td>${row.chunks_count}</td>`;
        tbody.appendChild(tr);
      }
      if (!rows.length) {
        const tr = document.createElement('tr');
        tr.innerHTML = '<td colspan="3" class="muted">Документы отсутствуют</td>';
        tbody.appendChild(tr);
      }
    }

    async function uploadFile() {
      const input = document.getElementById('fileInput');
      if (!input.files.length) return;
      const form = new FormData();
      form.append('file', input.files[0]);
      const result = await fetch('/api/upload', { method: 'POST', body: form }).then(r => r.json());
      document.getElementById('upload-status').textContent = result.message || JSON.stringify(result);
      await refreshDocs();
      await refreshStats();
    }

    async function clearCache() {
      const result = await fetch('/api/cache/clear', { method: 'POST' }).then(r => r.json());
      document.getElementById('upload-status').textContent = result.message || JSON.stringify(result);
      await refreshStats();
    }

    refreshStats();
    refreshDocs();
    setInterval(refreshStats, 10000);
    setInterval(refreshDocs, 15000);
  </script>
</body>
</html>
"""


@app.post("/api/upload")
async def upload_document(
    file: UploadFile = File(...),
    _: str = Depends(_authenticate),
) -> dict[str, str]:
    """Upload PDF/Markdown/TXT document and index it."""
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in allowed_extensions:
        raise HTTPException(status_code=400, detail="Supported formats: PDF, Markdown, TXT.")

    docs_dir = Path(settings.docs_dir)
    docs_dir.mkdir(parents=True, exist_ok=True)
    safe_name = (file.filename or "uploaded").replace("/", "_").replace("\\", "_")
    local_path = docs_dir / f"{uuid4()}_{safe_name}"

    async with aiofiles.open(local_path, "wb") as out:
        content = await file.read()
        await out.write(content)

    document, chunks = await document_processor.process_document(file_path=local_path, uploaded_by=0)
    await vector_store.add_document(document, chunks)
    return {"message": f"Файл загружен: {safe_name}. Фрагментов: {len(chunks)}"}


@app.get("/api/documents")
async def get_documents(_: str = Depends(_authenticate)) -> list[dict]:
    """Return indexed documents."""
    return await vector_store.list_documents(user_id=0)


@app.post("/api/cache/clear")
async def clear_cache(_: str = Depends(_authenticate)) -> dict[str, str]:
    """Clear Redis query cache."""
    deleted = await cache.clear()
    return {"message": f"Кэш очищен. Удалено ключей: {deleted}"}


@app.get("/api/stats")
async def get_stats(_: str = Depends(_authenticate)) -> dict[str, str | int]:
    """Return basic admin stats."""
    documents = await vector_store.list_documents(user_id=0)
    cache_keys = await cache.size()
    uptime = _format_uptime(int(time.time() - started_at))
    return {
        "documents_count": len(documents),
        "cache_keys": cache_keys,
        "uptime": uptime,
    }


if __name__ == "__main__":
    uvicorn.run("admin_panel.app:app", host="0.0.0.0", port=8003)
