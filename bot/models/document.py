"""Core data models for documents, chunks, and retrieval results."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class Document(BaseModel):
    """Uploaded source document metadata."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    filename: str
    file_path: str
    mime_type: str
    size_bytes: int = Field(ge=0)
    uploaded_by: int
    uploaded_at: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
    checksum_sha256: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class Chunk(BaseModel):
    """Document chunk saved into vector storage."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    document_id: str
    chunk_index: int = Field(ge=0)
    text: str
    token_count: int = Field(ge=0)
    source_filename: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class QueryResult(BaseModel):
    """Single retrieved chunk with distance/score."""

    chunk_id: str
    document_id: str
    source_filename: str
    content: str
    score: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class Source(BaseModel):
    """Source citation used to justify generated answer."""

    text: str
    document_id: str
    chunk_id: str
    score: float


class AnswerResult(BaseModel):
    """Final generated answer with source list and retrieval status."""

    answer: str
    sources: list[Source] = Field(default_factory=list)
    found: bool
    query: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(tz=UTC))
