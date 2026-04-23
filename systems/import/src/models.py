"""Shared in-memory data models for the RAG Data Import pipeline.

These dataclasses are the only objects that cross module boundaries.
They contain no business logic — they are pure data containers.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class RawDocument:
    """Raw document loaded from a file, URL, or directory."""

    content: str
    source: str  # file path or URL
    doc_type: str  # "pdf" | "txt" | "md" | "docx" | "url"
    doc_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    loaded_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Chunk:
    """A chunk of text derived from a RawDocument, ready for embedding and indexing."""

    doc_id: str
    content: str
    source: str
    doc_type: str
    chunk_index: int
    ingested_at: datetime = field(default_factory=datetime.utcnow)
    chunk_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    page_number: int | None = None
