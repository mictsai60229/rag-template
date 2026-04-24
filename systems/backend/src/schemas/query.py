"""Pydantic models for the query API request and response.

These schemas are used as FastAPI request/response body types and for internal
data transfer between the route handler and ``QueryService``.
"""

from pydantic import BaseModel, ConfigDict, Field


class SourceRef(BaseModel):
    """A single retrieved chunk cited in a ``QueryResponse``."""

    chunk_id: str = Field(..., description="Identifier of the retrieved chunk.")
    content: str = Field(..., description="Chunk text content (for citation display).")
    source: str = Field(..., description="Origin file path or URL of the chunk.")
    score: float = Field(..., description="Retrieval score (normalised 0–1).")


class QueryRequest(BaseModel):
    """Request body for ``POST /query``."""

    query: str = Field(..., min_length=1, description="Natural-language question from the caller.")
    retrieval_mode: str | None = Field(
        default=None,
        description="Override retrieval mode: 'vector', 'keyword', or 'hybrid'. "
        "Defaults to the server-side config value when not provided.",
    )
    top_k: int | None = Field(
        default=None,
        description="Number of chunks to retrieve. Defaults to the server-side config value.",
    )
    filters: dict[str, str] | None = Field(
        default=None,
        description="Metadata filter map (e.g. {'source': 'report.pdf'}) applied before ranking.",
    )


class QueryResponse(BaseModel):
    """Response body for ``POST /query``."""

    sources: list[SourceRef] = Field(
        ..., description="Ordered list of retrieved chunks used as context."
    )
    retrieval_mode: str = Field(..., description="Actual retrieval mode used for this query.")
    latency_ms: int = Field(..., description="Total end-to-end latency in milliseconds.")
