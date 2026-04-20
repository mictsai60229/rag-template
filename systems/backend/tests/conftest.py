"""Shared test fixtures for the RAG backend test suite.

Provides a ``client`` fixture backed by ``httpx.AsyncClient`` pointing at the
FastAPI app imported from ``src.main``. Tests that call ``GET /health`` or
other read-only endpoints do not need a running OpenSearch or LLM provider
because ``Config`` is not loaded at import time — only when a route handler
actually calls ``get_config()``.
"""

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from src.main import app


@pytest_asyncio.fixture
async def client() -> AsyncClient:  # type: ignore[misc]
    """Return an ``AsyncClient`` wired to the FastAPI test app."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
