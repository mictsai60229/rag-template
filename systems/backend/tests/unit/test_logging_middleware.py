"""Unit tests for RequestIDMiddleware.

Verifies that:
- Every response includes an ``X-Request-ID`` header with a UUID4 value.
- Two concurrent requests get different ``request_id`` values.
"""

import asyncio
import re

import pytest
from httpx import ASGITransport, AsyncClient

from src.main import app

# UUID4 pattern
_UUID4_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


@pytest.mark.asyncio
async def test_response_includes_x_request_id_header() -> None:
    """Every response must include an X-Request-ID header."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/health")

    assert "x-request-id" in response.headers


@pytest.mark.asyncio
async def test_x_request_id_is_uuid4_format() -> None:
    """The X-Request-ID value must be a valid UUID4 string."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/health")

    request_id = response.headers["x-request-id"]
    assert _UUID4_PATTERN.match(request_id), (
        f"X-Request-ID '{request_id}' is not a valid UUID4"
    )


@pytest.mark.asyncio
async def test_two_sequential_requests_get_different_request_ids() -> None:
    """Two requests must receive different X-Request-ID values."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        r1 = await client.get("/health")
        r2 = await client.get("/health")

    assert r1.headers["x-request-id"] != r2.headers["x-request-id"]


@pytest.mark.asyncio
async def test_concurrent_requests_get_different_request_ids() -> None:
    """Concurrent requests must receive different X-Request-ID values."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        results = await asyncio.gather(
            client.get("/health"),
            client.get("/health"),
            client.get("/health"),
        )

    request_ids = [r.headers["x-request-id"] for r in results]
    assert len(set(request_ids)) == len(request_ids), (
        f"Duplicate request IDs detected: {request_ids}"
    )


@pytest.mark.asyncio
async def test_middleware_on_query_path() -> None:
    """X-Request-ID header is present on non-health endpoints too."""
    from unittest.mock import MagicMock

    from src.config import get_config as cfg_get_config
    from src.config import Config
    from src.dependencies.query import get_query_service
    from src.schemas.query import QueryResponse, SourceRef

    dev_cfg = Config.model_construct(  # type: ignore[arg-type]
        OPENAI_API_KEY="sk-test",
        OPENSEARCH_HOST="localhost",
        OPENSEARCH_PORT=9200,
        OPENSEARCH_INDEX="rag-index",
        EMBEDDING_PROVIDER="openai",
        EMBEDDING_MODEL="text-embedding-3-small",
        LLM_MODEL="gpt-4o-mini",
        API_KEY="",
        ENV="dev",
    )
    svc = MagicMock()
    svc.query.return_value = QueryResponse(
        answer="ok",
        sources=[SourceRef(chunk_id="c1", content="ctx", source="doc.pdf", score=0.9)],
        retrieval_mode="hybrid",
        latency_ms=1,
    )

    app.dependency_overrides[cfg_get_config] = lambda: dev_cfg
    app.dependency_overrides[get_query_service] = lambda: svc
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post("/query", json={"query": "hello"})
        assert "x-request-id" in response.headers
        assert _UUID4_PATTERN.match(response.headers["x-request-id"])
    finally:
        app.dependency_overrides.pop(cfg_get_config, None)
        app.dependency_overrides.pop(get_query_service, None)
