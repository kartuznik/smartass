"""Application configuration loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


load_dotenv()


class Settings(BaseSettings):
    """Typed settings for bot, RAG services, and MCP server."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    telegram_bot_token: str = Field(..., alias="TELEGRAM_BOT_TOKEN")
    openai_api_key: str = Field(..., alias="OPENAI_API_KEY")

    app_env: str = Field("development", alias="APP_ENV")
    log_level: str = Field("INFO", alias="LOG_LEVEL")
    log_dir: str = Field("./logs", alias="LOG_DIR")
    log_file: str = Field("rag-bot.log", alias="LOG_FILE")
    log_max_bytes: int = Field(10 * 1024 * 1024, alias="LOG_MAX_BYTES")
    log_backup_count: int = Field(5, alias="LOG_BACKUP_COUNT")

    data_dir: str = Field("./data", alias="DATA_DIR")
    docs_dir: str = Field("./docs", alias="DOCS_DIR")
    chroma_persist_directory: str = Field("./data/chroma_db", alias="CHROMA_PERSIST_DIRECTORY")
    chroma_collection_name: str = Field("documentation_chunks", alias="CHROMA_COLLECTION_NAME")

    embedding_model: str = Field("text-embedding-3-small", alias="EMBEDDING_MODEL")
    llm_model: str = Field("gpt-4o-mini", alias="LLM_MODEL")
    default_top_k: int = Field(3, alias="DEFAULT_TOP_K", ge=1, le=20)
    chunk_size_tokens: int = Field(500, alias="CHUNK_SIZE_TOKENS", ge=100, le=4000)
    chunk_overlap_tokens: int = Field(50, alias="CHUNK_OVERLAP_TOKENS", ge=0, le=500)
    max_history_messages: int = Field(10, alias="MAX_HISTORY_MESSAGES", ge=1, le=50)

    admin_user_ids: list[int] = Field(default_factory=list, alias="ADMIN_USER_IDS")

    mcp_server_host: str = Field("0.0.0.0", alias="MCP_SERVER_HOST")
    mcp_server_port: int = Field(8081, alias="MCP_SERVER_PORT", ge=1, le=65535)

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, value: str) -> str:
        """Normalize and validate logging level string."""
        normalized = value.upper()
        allowed = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}
        if normalized not in allowed:
            raise ValueError(f"Unsupported LOG_LEVEL={value}. Allowed: {sorted(allowed)}")
        return normalized

    @field_validator(
        "log_dir",
        "data_dir",
        "docs_dir",
        "chroma_persist_directory",
        mode="before",
    )
    @classmethod
    def normalize_path(cls, value: str) -> str:
        """Expand relative/env paths into normalized string paths."""
        return str(Path(value).expanduser())

    @field_validator("chunk_overlap_tokens")
    @classmethod
    def validate_chunk_overlap(cls, value: int, info: ValidationInfo) -> int:
        """Ensure overlap is lower than chunk size."""
        chunk_size = int(info.data.get("chunk_size_tokens", 500))
        if value >= chunk_size:
            raise ValueError("CHUNK_OVERLAP_TOKENS must be smaller than CHUNK_SIZE_TOKENS")
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
