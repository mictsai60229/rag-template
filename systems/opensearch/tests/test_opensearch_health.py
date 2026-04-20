"""
Cluster health smoke test for OpenSearch.

Requires a running OpenSearch instance. Set OPENSEARCH_URL to override the
default http://localhost:9200.

Run with:
    export OPENSEARCH_URL=http://localhost:9200
    pytest tests/test_opensearch_health.py -v

To exclude this test from unit test runs use:
    pytest -m "not integration"
"""

import os

import pytest
from opensearchpy import OpenSearch

pytestmark = pytest.mark.integration


def _client() -> OpenSearch:
    url = os.environ.get("OPENSEARCH_URL", "http://localhost:9200")
    return OpenSearch(hosts=[url], use_ssl=False, verify_certs=False)


def test_cluster_health_is_green_or_yellow() -> None:
    """Assert that the OpenSearch cluster is reachable and healthy."""
    client = _client()
    response = client.cluster.health()
    assert response["status"] in ("green", "yellow"), (
        f"Unexpected cluster health status: {response['status']!r}. "
        "Expected 'green' or 'yellow'."
    )
