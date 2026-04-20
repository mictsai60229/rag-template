"""Smoke test for GET /health."""

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_returns_200_ok(client: AsyncClient) -> None:
    """GET /health must return HTTP 200 and body ``{"status": "ok"}``."""
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
