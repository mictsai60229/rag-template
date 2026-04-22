"""Unit tests for the require_api_key authentication dependency.

Covers dev mode bypass, missing key, wrong key, and correct key scenarios.
Also verifies that GET /health is accessible without any API key.
"""

from unittest.mock import MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from src.config import Config, get_config
from src.dependencies.query import get_query_service
from src.main import app
from src.schemas.query import QueryResponse, SourceRef


def _make_config(env: str = "production", api_key: str = "secret-key") -> Config:
    """Build a ``Config`` with the given env and api_key values."""
    return Config.model_construct(  # type: ignore[arg-type]
        OPENAI_API_KEY="sk-test",
        OPENSEARCH_HOST="localhost",
        OPENSEARCH_PORT=9200,
        OPENSEARCH_INDEX="rag-index",
        EMBEDDING_PROVIDER="openai",
        EMBEDDING_MODEL="text-embedding-3-small",
        LLM_MODEL="gpt-4o-mini",
        API_KEY=api_key,
        ENV=env,
    )


def _make_mock_service() -> MagicMock:
    """Return a mock QueryService that returns a minimal valid QueryResponse."""
    svc = MagicMock()
    svc.query.return_value = QueryResponse(
        answer="ok",
        sources=[
            SourceRef(chunk_id="c1", content="ctx", source="doc.pdf", score=0.9)
        ],
        retrieval_mode="hybrid",
        latency_ms=1,
    )
    return svc


# ---------------------------------------------------------------------------
# Dev-mode bypass
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dev_mode_bypasses_auth_for_query() -> None:
    """In ENV=dev, POST /query is accessible without X-API-Key."""
    cfg = _make_config(env="dev", api_key="secret")
    svc = _make_mock_service()
    app.dependency_overrides[get_config] = lambda: cfg
    app.dependency_overrides[get_query_service] = lambda: svc
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post("/query", json={"query": "hello"})
        assert response.status_code == 200
    finally:
        app.dependency_overrides.pop(get_config, None)
        app.dependency_overrides.pop(get_query_service, None)


@pytest.mark.asyncio
async def test_dev_mode_bypasses_auth_for_config() -> None:
    """In ENV=dev, GET /config is accessible without X-API-Key."""
    cfg = _make_config(env="dev", api_key="secret")
    app.dependency_overrides[get_config] = lambda: cfg
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/config")
        assert response.status_code == 200
    finally:
        app.dependency_overrides.pop(get_config, None)


# ---------------------------------------------------------------------------
# Missing key in production
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_key_in_production_returns_401_for_query() -> None:
    """In ENV=production with API_KEY set, missing X-API-Key returns 401."""
    cfg = _make_config(env="production", api_key="secret")
    svc = _make_mock_service()
    app.dependency_overrides[get_config] = lambda: cfg
    app.dependency_overrides[get_query_service] = lambda: svc
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post("/query", json={"query": "hello"})
        assert response.status_code == 401
    finally:
        app.dependency_overrides.pop(get_config, None)
        app.dependency_overrides.pop(get_query_service, None)


@pytest.mark.asyncio
async def test_missing_key_in_production_returns_401_for_config() -> None:
    """In ENV=production with API_KEY set, missing X-API-Key returns 401."""
    cfg = _make_config(env="production", api_key="secret")
    app.dependency_overrides[get_config] = lambda: cfg
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/config")
        assert response.status_code == 401
    finally:
        app.dependency_overrides.pop(get_config, None)


# ---------------------------------------------------------------------------
# Wrong key in production
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_wrong_key_in_production_returns_401() -> None:
    """In ENV=production, providing the wrong X-API-Key returns 401."""
    cfg = _make_config(env="production", api_key="correct-key")
    svc = _make_mock_service()
    app.dependency_overrides[get_config] = lambda: cfg
    app.dependency_overrides[get_query_service] = lambda: svc
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/query",
                json={"query": "hello"},
                headers={"X-API-Key": "wrong-key"},
            )
        assert response.status_code == 401
    finally:
        app.dependency_overrides.pop(get_config, None)
        app.dependency_overrides.pop(get_query_service, None)


# ---------------------------------------------------------------------------
# Correct key in production
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_correct_key_in_production_passes_for_query() -> None:
    """In ENV=production, providing the correct X-API-Key returns 200."""
    cfg = _make_config(env="production", api_key="correct-key")
    svc = _make_mock_service()
    app.dependency_overrides[get_config] = lambda: cfg
    app.dependency_overrides[get_query_service] = lambda: svc
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/query",
                json={"query": "hello"},
                headers={"X-API-Key": "correct-key"},
            )
        assert response.status_code == 200
    finally:
        app.dependency_overrides.pop(get_config, None)
        app.dependency_overrides.pop(get_query_service, None)


@pytest.mark.asyncio
async def test_correct_key_in_production_passes_for_config() -> None:
    """In ENV=production, providing the correct X-API-Key to /config returns 200."""
    cfg = _make_config(env="production", api_key="correct-key")
    app.dependency_overrides[get_config] = lambda: cfg
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get(
                "/config",
                headers={"X-API-Key": "correct-key"},
            )
        assert response.status_code == 200
    finally:
        app.dependency_overrides.pop(get_config, None)


# ---------------------------------------------------------------------------
# Health endpoint — always accessible
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_is_accessible_without_api_key_in_production() -> None:
    """GET /health is accessible without an API key even in production mode."""
    # Do NOT override get_config — health route does not call it.
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/health")
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# Empty API_KEY disables auth regardless of ENV
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_api_key_disables_auth() -> None:
    """When API_KEY is empty string, auth is skipped even in production."""
    cfg = _make_config(env="production", api_key="")
    svc = _make_mock_service()
    app.dependency_overrides[get_config] = lambda: cfg
    app.dependency_overrides[get_query_service] = lambda: svc
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post("/query", json={"query": "hello"})
        assert response.status_code == 200
    finally:
        app.dependency_overrides.pop(get_config, None)
        app.dependency_overrides.pop(get_query_service, None)
