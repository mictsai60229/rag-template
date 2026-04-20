"""In-memory data models shared between providers and services.

These are plain Python dataclasses, not Pydantic models, to keep them
dependency-free and fast to construct when mapping OpenSearch hits.
"""

from dataclasses import dataclass


@dataclass
class Chunk:
    """A single retrieved text chunk returned by ``OpenSearchProvider.search()``.

    Mirrors the ``Chunk`` data model defined in the SAD, augmented with a
    ``score`` field populated from the OpenSearch hit ``_score``.
    """

    chunk_id: str
    doc_id: str
    content: str
    source: str
    doc_type: str
    page_number: int | None
    chunk_index: int
    ingested_at: str
    score: float
