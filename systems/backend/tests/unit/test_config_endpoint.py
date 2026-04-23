"""Unit tests for the GET /config endpoint.

The ``get_config`` dependency is overridden so no real env vars are needed.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from src.config import Config, get_config
from src.main import app


def _make_test_config(**overrides: object) -> Config:
    """Build a ``Config`` instance with test values, bypassing env-var loading."""
    defaults: dict[str, object] = {
        "OPENAI_API_KEY": "sk-secret-key",
        "OPENSEARCH_HOST": "localhost",
        "OPENSEARCH_PORT": 9200,
        "OPENSEARCH_INDEX": "rag-index",
        "EMBEDDING_PROVIDER": "openai",
        "EMBEDDING_MODEL": "text-embedding-3-small",
        "LLM_MODEL": "gpt-4o-mini",
        "API_KEY": "test-api-key",
        "ENV": "production",
    }
    defaults.update(overrides)
    return Config.model_construct(**defaults)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_openai_api_key_is_absent_from_response() -> None:
    """OPENAI_API_KEY must never appear in the /config response."""
    test_cfg = _make_test_config(ENV="dev")
    app.dependency_overrides[get_config] = lambda: test_cfg
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/config")
        body = response.json()
        assert "OPENAI_API_KEY" not in body
    finally:
        app.dependency_overrides.pop(get_config, None)


@pytest.mark.asyncio
async def test_api_key_is_absent_from_response() -> None:
    """API_KEY must never appear in the /config response."""
    test_cfg = _make_test_config(ENV="dev")
    app.dependency_overrides[get_config] = lambda: test_cfg
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/config")
        body = response.json()
        assert "API_KEY" not in body
    finally:
        app.dependency_overrides.pop(get_config, None)


@pytest.mark.asyncio
async def test_non_secret_fields_are_present() -> None:
    """Non-secret fields such as OPENSEARCH_HOST and RETRIEVAL_MODE are present."""
    test_cfg = _make_test_config(ENV="dev")
    app.dependency_overrides[get_config] = lambda: test_cfg
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/config")
        body = response.json()
        assert "OPENSEARCH_HOST" in body
        assert body["OPENSEARCH_HOST"] == "localhost"
        assert "RETRIEVAL_MODE" in body
    finally:
        app.dependency_overrides.pop(get_config, None)


@pytest.mark.asyncio
async def test_auth_bypassed_in_dev_mode() -> None:
    """GET /config returns 200 in ENV=dev without an API key header."""
    test_cfg = _make_test_config(ENV="dev", API_KEY="some-key")
    app.dependency_overrides[get_config] = lambda: test_cfg
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/config")
        # In Phase 2 there is no auth dependency yet; this test verifies
        # the endpoint itself is reachable regardless of ENV.
        assert response.status_code == 200
    finally:
        app.dependency_overrides.pop(get_config, None)


@pytest.mark.asyncio
async def test_config_returns_200() -> None:
    """GET /config returns HTTP 200 with a non-empty body."""
    test_cfg = _make_test_config(ENV="dev")
    app.dependency_overrides[get_config] = lambda: test_cfg
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/config")
        assert response.status_code == 200
        assert isinstance(response.json(), dict)
        assert len(response.json()) > 0
    finally:
        app.dependency_overrides.pop(get_config, None)


@pytest.mark.asyncio
async def test_fields_with_password_in_name_are_redacted() -> None:
    """Fields whose name contains 'PASSWORD' (case-insensitive) are excluded."""
    # We test the redaction helper directly via a subclass.
    from src.api.config_endpoint import _is_secret_field

    assert _is_secret_field("OPENSEARCH_PASSWORD") is True
    assert _is_secret_field("db_password") is True
    assert _is_secret_field("MY_SECRET_TOKEN") is True
    assert _is_secret_field("OPENSEARCH_HOST") is False


@pytest.mark.asyncio
async def test_opensearch_port_present_and_correct_type() -> None:
    """Numeric config fields are returned with their correct type."""
    test_cfg = _make_test_config(ENV="dev")
    app.dependency_overrides[get_config] = lambda: test_cfg
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/config")
        body = response.json()
        assert "OPENSEARCH_PORT" in body
        assert isinstance(body["OPENSEARCH_PORT"], int)
    finally:
        app.dependency_overrides.pop(get_config, None)


@pytest.mark.asyncio
async def test_production_missing_api_key_returns_401() -> None:
    """GET /config in ENV=production without X-API-Key returns 401."""
    test_cfg = _make_test_config(ENV="production", API_KEY="real-secret")
    app.dependency_overrides[get_config] = lambda: test_cfg
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/config")
        assert response.status_code == 401
    finally:
        app.dependency_overrides.pop(get_config, None)
