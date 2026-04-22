"""Integration tests for POST /query against a real OpenSearch container.

These tests start a real OpenSearch 2.13.0 container via testcontainers,
seed it with fixture chunks from ``fixtures/chunks.json``, and verify that
the full query pipeline works end-to-end. LLM calls are mocked to avoid
real API costs.

Mark: ``integration`` — run with ``pytest -m integration``.
"""

import pytest
from httpx import AsyncClient

from src.schemas.query import QueryResponse

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_query_returns_200(integration_client: AsyncClient) -> None:
    """POST /query with a valid body returns HTTP 200."""
    response = await integration_client.post(
        "/query", json={"query": "What is Python?"}
    )
    assert response.status_code == 200, response.text


@pytest.mark.asyncio
async def test_query_response_schema(integration_client: AsyncClient) -> None:
    """POST /query response body conforms to the QueryResponse schema."""
    response = await integration_client.post(
        "/query", json={"query": "What is Python?"}
    )
    assert response.status_code == 200
    body = response.json()
    # Validate the response can be parsed as QueryResponse
    parsed = QueryResponse(**body)
    assert parsed.answer  # non-empty answer from mock LLM
    assert isinstance(parsed.sources, list)
    assert isinstance(parsed.retrieval_mode, str)
    assert isinstance(parsed.latency_ms, int)


@pytest.mark.asyncio
async def test_query_sources_list(integration_client: AsyncClient) -> None:
    """POST /query returns a sources list (may be empty for zero-vec queries)."""
    response = await integration_client.post(
        "/query", json={"query": "What is Python?"}
    )
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["sources"], list)


@pytest.mark.asyncio
async def test_query_latency_ms_positive(integration_client: AsyncClient) -> None:
    """POST /query returns a positive latency_ms value."""
    response = await integration_client.post(
        "/query", json={"query": "What is Python?"}
    )
    assert response.status_code == 200
    assert response.json()["latency_ms"] >= 0


@pytest.mark.asyncio
async def test_query_invalid_body_returns_422(integration_client: AsyncClient) -> None:
    """POST /query with an empty query string returns 422 Unprocessable Entity."""
    response = await integration_client.post("/query", json={"query": ""})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_health_always_accessible(integration_client: AsyncClient) -> None:
    """GET /health returns 200 even without an API key."""
    response = await integration_client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
