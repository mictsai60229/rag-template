"""Shared fixtures for integration tests.

Starts a real OpenSearch container via testcontainers, seeds a small set of
fixture chunks directly, and provides an ``AsyncClient`` wired to the FastAPI
app with config overriding pointing at the test cluster. LLM calls are mocked
so no real API keys are needed.

Fixtures:
    opensearch_container (session): Starts/stops the OpenSearch container.
    seeded_index (session): Creates the index and bulk-indexes fixture chunks.
    integration_client: AsyncClient with overridden config and mocked LLM.
"""

from __future__ import annotations

import json
import pathlib
import time
from typing import Generator
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from opensearchpy import OpenSearch

from src.config import Config
from src.config import get_config as src_get_config
from src.dependencies.query import get_llm_provider, get_query_service
from src.main import app
from src.providers.llm_provider import LLMProvider
from src.schemas.query import QueryResponse, SourceRef

# Path to the OpenSearch mapping used by the import pipeline.
_MAPPING_FILE = (
    pathlib.Path(__file__).parent.parent.parent.parent.parent
    / "systems"
    / "opensearch"
    / "mappings"
    / "rag_index.json"
)

# Path to the fixture chunk documents.
_FIXTURES_FILE = pathlib.Path(__file__).parent / "fixtures" / "chunks.json"

# Test index name — isolated from any real index.
_TEST_INDEX = "rag-test-integration"

# Embedding dimension expected by the index mapping.
_EMBEDDING_DIM = 1536


def _load_mapping() -> dict:
    """Load the canonical OpenSearch index mapping from disk."""
    with _MAPPING_FILE.open() as f:
        return json.load(f)


def _load_fixture_chunks() -> list[dict]:
    """Load fixture chunks, injecting 1536-dim zero-vector embeddings."""
    with _FIXTURES_FILE.open() as f:
        raw: list[dict] = json.load(f)
    zero_vec = [0.0] * _EMBEDDING_DIM
    for chunk in raw:
        chunk["embedding"] = zero_vec
    return raw


# ---------------------------------------------------------------------------
# Session-scoped OpenSearch container
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def opensearch_container():  # type: ignore[return]
    """Start a real OpenSearch container for the entire test session.

    Yields the base URL (e.g. ``http://localhost:49200``) after the cluster
    is healthy.
    """
    from testcontainers.opensearch import OpenSearchContainer  # type: ignore[import-untyped]

    container = OpenSearchContainer("opensearchproject/opensearch:2.13.0")
    container.start()
    url = container.get_url()

    # Wait for the cluster to become available.
    client = OpenSearch(hosts=[url], verify_certs=False, ssl_show_warn=False)
    deadline = time.time() + 120
    while time.time() < deadline:
        try:
            health = client.cluster.health(wait_for_status="yellow", timeout="5s")
            if health.get("status") in ("green", "yellow"):
                break
        except Exception:
            time.sleep(2)
    else:
        container.stop()
        pytest.fail("OpenSearch container did not become healthy within 120 s")

    yield url
    container.stop()


# ---------------------------------------------------------------------------
# Session-scoped seeded index
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def seeded_index(opensearch_container: str) -> Generator[str, None, None]:
    """Create the test index, seed fixture chunks, then delete on teardown.

    Yields the URL of the OpenSearch container so callers can build a config.
    """
    client = OpenSearch(
        hosts=[opensearch_container],
        verify_certs=False,
        ssl_show_warn=False,
    )

    # Create the index using the canonical mapping.
    mapping = _load_mapping()
    if client.indices.exists(index=_TEST_INDEX):
        client.indices.delete(index=_TEST_INDEX)
    client.indices.create(index=_TEST_INDEX, body=mapping)

    # Bulk-index fixture chunks.
    chunks = _load_fixture_chunks()
    bulk_body: list[dict] = []
    for chunk in chunks:
        bulk_body.append({"index": {"_index": _TEST_INDEX, "_id": chunk["chunk_id"]}})
        bulk_body.append(chunk)

    response = client.bulk(body=bulk_body)
    if response.get("errors"):
        pytest.fail(f"Bulk indexing fixture chunks failed: {response}")

    # Refresh so documents are immediately searchable.
    client.indices.refresh(index=_TEST_INDEX)

    yield opensearch_container

    client.indices.delete(index=_TEST_INDEX, ignore=[404])


# ---------------------------------------------------------------------------
# Per-test AsyncClient with overridden dependencies
# ---------------------------------------------------------------------------


def _make_integration_config(opensearch_url: str) -> Config:
    """Build a Config pointing at the test OpenSearch container."""
    # Parse host and port from the URL.
    from urllib.parse import urlparse

    parsed = urlparse(opensearch_url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 9200

    return Config.model_construct(  # type: ignore[arg-type]
        OPENAI_API_KEY="sk-test-not-used",
        OPENSEARCH_HOST=host,
        OPENSEARCH_PORT=port,
        OPENSEARCH_INDEX=_TEST_INDEX,
        EMBEDDING_PROVIDER="openai",
        EMBEDDING_MODEL="text-embedding-3-small",
        LLM_MODEL="gpt-4o-mini",
        API_KEY="",
        ENV="dev",
        TOP_K=5,
        RETRIEVAL_MODE="keyword",  # use keyword so zero-vec embeddings don't matter
        KEYWORD_BOOST=0.3,
        EMBEDDING_BATCH_SIZE=32,
        LOG_LEVEL="INFO",
    )


@pytest_asyncio.fixture
async def integration_client(seeded_index: str):  # type: ignore[return]
    """Yield an AsyncClient with:

    - ``get_config`` overridden to point at the test OpenSearch container.
    - ``get_llm_provider`` overridden to return a mock that always answers
      ``"Test answer."`` (avoids real OpenAI API calls).
    """
    cfg = _make_integration_config(seeded_index)

    mock_llm = MagicMock(spec=LLMProvider)
    mock_llm.generate.return_value = "Test answer."

    app.dependency_overrides[src_get_config] = lambda: cfg
    app.dependency_overrides[get_llm_provider] = lambda: mock_llm

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            yield client
    finally:
        app.dependency_overrides.pop(src_get_config, None)
        app.dependency_overrides.pop(get_llm_provider, None)
