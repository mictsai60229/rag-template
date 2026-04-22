"""Unit tests for the POST /query route handler.

The ``QueryService`` dependency is mocked so no real providers are needed.
The ``get_config`` dependency is also mocked since ``require_api_key`` depends
on it, and we want auth bypassed in tests (ENV=dev).
"""

from unittest.mock import MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from src.config import Config
from src.config import get_config as config_get_config
from src.dependencies.query import get_query_service
from src.main import app
from src.schemas.query import QueryResponse, SourceRef


def _make_dev_config() -> Config:
    """Build a ``Config`` in dev mode so auth is bypassed."""
    return Config.model_construct(  # type: ignore[arg-type]
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


def _make_mock_service(answer: str = "Test answer.") -> MagicMock:
    """Return a mock ``QueryService`` whose ``query()`` returns a fixed response."""
    mock_service = MagicMock()
    mock_service.query.return_value = QueryResponse(
        answer=answer,
        sources=[
            SourceRef(
                chunk_id="chunk-1",
                content="Python is a programming language.",
                source="doc.pdf",
                score=0.95,
            )
        ],
        retrieval_mode="hybrid",
        latency_ms=42,
    )
    return mock_service


@pytest.fixture
def mock_query_service() -> MagicMock:
    return _make_mock_service()


@pytest.fixture(autouse=True)
def _mock_config_for_auth() -> None:
    """Override get_config globally so require_api_key uses dev mode (no auth)."""
    dev_cfg = _make_dev_config()
    app.dependency_overrides[config_get_config] = lambda: dev_cfg
    yield
    app.dependency_overrides.pop(config_get_config, None)


@pytest.mark.asyncio
async def test_query_returns_200(mock_query_service: MagicMock) -> None:
    """POST /query with a valid body returns HTTP 200."""
    app.dependency_overrides[get_query_service] = lambda: mock_query_service
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post("/query", json={"query": "What is Python?"})
        assert response.status_code == 200
    finally:
        app.dependency_overrides.pop(get_query_service, None)


@pytest.mark.asyncio
async def test_query_response_schema(mock_query_service: MagicMock) -> None:
    """POST /query response conforms to the QueryResponse schema."""
    app.dependency_overrides[get_query_service] = lambda: mock_query_service
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post("/query", json={"query": "What is Python?"})

        body = response.json()
        assert "answer" in body
        assert "sources" in body
        assert "retrieval_mode" in body
        assert "latency_ms" in body
        assert isinstance(body["sources"], list)
        assert isinstance(body["latency_ms"], int)
    finally:
        app.dependency_overrides.pop(get_query_service, None)


@pytest.mark.asyncio
async def test_query_calls_service_query_method(mock_query_service: MagicMock) -> None:
    """Route delegates to service.query() exactly once."""
    app.dependency_overrides[get_query_service] = lambda: mock_query_service
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post("/query", json={"query": "What is Python?"})

        mock_query_service.query.assert_called_once()
    finally:
        app.dependency_overrides.pop(get_query_service, None)


@pytest.mark.asyncio
async def test_query_empty_string_returns_422(mock_query_service: MagicMock) -> None:
    """POST /query with an empty query string returns HTTP 422."""
    app.dependency_overrides[get_query_service] = lambda: mock_query_service
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post("/query", json={"query": ""})
        assert response.status_code == 422
    finally:
        app.dependency_overrides.pop(get_query_service, None)


@pytest.mark.asyncio
async def test_query_missing_body_returns_422(mock_query_service: MagicMock) -> None:
    """POST /query with no body returns HTTP 422."""
    app.dependency_overrides[get_query_service] = lambda: mock_query_service
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post("/query", content=b"")
        assert response.status_code == 422
    finally:
        app.dependency_overrides.pop(get_query_service, None)


@pytest.mark.asyncio
async def test_query_response_answer_matches_service(mock_query_service: MagicMock) -> None:
    """Route returns the answer exactly as returned by the service."""
    app.dependency_overrides[get_query_service] = lambda: mock_query_service
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post("/query", json={"query": "What is Python?"})

        assert response.json()["answer"] == "Test answer."
    finally:
        app.dependency_overrides.pop(get_query_service, None)
