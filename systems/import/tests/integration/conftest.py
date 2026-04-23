"""Integration test fixtures for the RAG Data Import pipeline.

Uses ``testcontainers`` to start a real OpenSearch container for each test
session. Docker must be running on the host.
"""

import pytest
from testcontainers.opensearch import OpenSearchContainer

from src.providers.opensearch_provider import OpenSearchProvider

OPENSEARCH_IMAGE = "opensearchproject/opensearch:2.13.0"


@pytest.fixture(scope="session")
def opensearch_container():
    """Start a real OpenSearch container and yield connection info.

    The container starts once per session (all integration tests share it).
    Security plugin is disabled to avoid TLS/auth complexity in tests.
    """
    with OpenSearchContainer(image=OPENSEARCH_IMAGE, security_enabled=False) as container:
        config = container.get_config()
        yield {
            "host": config["host"],
            "port": int(config["port"]),
        }


@pytest.fixture(scope="function")
def opensearch_provider(opensearch_container, unique_index_name):
    """Return an ``OpenSearchProvider`` pointed at the test container.

    Uses a unique index name per test function to ensure isolation.
    Deletes the index after the test completes.
    """
    provider = OpenSearchProvider(
        host=opensearch_container["host"],
        port=opensearch_container["port"],
        index=unique_index_name,
    )
    yield provider
    # Cleanup: delete the test index after each test.
    try:
        if provider.index_exists():
            provider.delete_index()
    except Exception:  # noqa: BLE001
        pass


@pytest.fixture(scope="function")
def unique_index_name(request) -> str:
    """Return a unique OpenSearch index name derived from the test node ID."""
    # Sanitise: lowercase, replace non-alphanumeric with hyphens, truncate.
    name = request.node.nodeid.lower()
    sanitised = "".join(c if c.isalnum() else "-" for c in name)
    # OpenSearch index names must be <= 255 chars and not start with "-" or "_".
    return f"test-{sanitised[-200:]}"
