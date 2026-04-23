"""
Index lifecycle smoke tests for OpenSearch.

Verifies that:
- An index can be created using the reference mapping (rag_index.json).
- The knn_vector field accepts a document with a 1536-dimension vector.
- The knn_vector field rejects a document with the wrong vector dimension.
- An index can be deleted and confirmed absent.

Requires a running OpenSearch instance. Set OPENSEARCH_URL to override
the default http://localhost:9200.

Run with:
    docker compose up -d
    sleep 30
    OPENSEARCH_URL=http://localhost:9200 pytest tests/test_index_lifecycle.py -v -m integration
"""

import json
import os
from pathlib import Path
from uuid import uuid4

import pytest
from opensearchpy import OpenSearch, RequestError

pytestmark = pytest.mark.integration

# Path to the canonical reference mapping relative to this file.
_MAPPING_PATH = Path(__file__).parent.parent / "mappings" / "rag_index.json"


@pytest.fixture
def opensearch_client() -> OpenSearch:
    """Return an opensearch-py client configured from OPENSEARCH_URL."""
    url = os.environ.get("OPENSEARCH_URL", "http://localhost:9200")
    return OpenSearch(hosts=[url], use_ssl=False, verify_certs=False)


@pytest.fixture
def test_index_name() -> str:
    """Return a unique test index name to avoid collisions between test runs."""
    short_id = uuid4().hex[:8]
    return f"rag-test-smoke-{short_id}"


@pytest.fixture(autouse=True)
def cleanup_index(opensearch_client: OpenSearch, test_index_name: str):
    """Delete the test index after each test, regardless of outcome."""
    yield
    if opensearch_client.indices.exists(index=test_index_name):
        opensearch_client.indices.delete(index=test_index_name)


def _load_reference_mapping() -> dict:
    """Load and return the canonical index mapping from rag_index.json."""
    with open(_MAPPING_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def test_create_index_with_reference_mapping(
    opensearch_client: OpenSearch,
    test_index_name: str,
) -> None:
    """Creating an index with the reference mapping must be acknowledged."""
    mapping = _load_reference_mapping()
    response = opensearch_client.indices.create(index=test_index_name, body=mapping)
    assert response["acknowledged"] is True, (
        f"Index creation was not acknowledged: {response}"
    )


def test_knn_field_accepts_correct_dimension(
    opensearch_client: OpenSearch,
    test_index_name: str,
) -> None:
    """Indexing a document with a 1536-dimension zero-vector must succeed."""
    mapping = _load_reference_mapping()
    opensearch_client.indices.create(index=test_index_name, body=mapping)

    doc = {
        "chunk_id": str(uuid4()),
        "doc_id": str(uuid4()),
        "content": "smoke test document",
        "embedding": [0.0] * 1536,
        "source": "smoke_test",
        "doc_type": "txt",
        "page_number": None,
        "chunk_index": 0,
        "ingested_at": "2024-01-01T00:00:00Z",
    }
    response = opensearch_client.index(
        index=test_index_name,
        body=doc,
        refresh=True,
    )
    assert response["result"] == "created", (
        f"Expected result='created', got: {response['result']!r}"
    )


def test_knn_field_rejects_wrong_dimension(
    opensearch_client: OpenSearch,
    test_index_name: str,
) -> None:
    """Indexing a document with a 3-dimension vector must raise a 400 error."""
    mapping = _load_reference_mapping()
    opensearch_client.indices.create(index=test_index_name, body=mapping)

    doc = {
        "chunk_id": str(uuid4()),
        "doc_id": str(uuid4()),
        "content": "wrong dimension document",
        "embedding": [0.1, 0.2, 0.3],  # 3 dimensions — should be rejected
        "source": "smoke_test",
        "doc_type": "txt",
        "page_number": None,
        "chunk_index": 0,
        "ingested_at": "2024-01-01T00:00:00Z",
    }
    with pytest.raises(RequestError) as exc_info:
        opensearch_client.index(
            index=test_index_name,
            body=doc,
            refresh=True,
        )
    # OpenSearch returns a 400 MapperParsingException for dimension mismatches.
    assert exc_info.value.status_code == 400, (
        f"Expected HTTP 400, got: {exc_info.value.status_code}"
    )


def test_delete_index(
    opensearch_client: OpenSearch,
    test_index_name: str,
) -> None:
    """Creating then deleting an index must result in the index being absent."""
    mapping = _load_reference_mapping()
    opensearch_client.indices.create(index=test_index_name, body=mapping)
    assert opensearch_client.indices.exists(index=test_index_name)

    opensearch_client.indices.delete(index=test_index_name)
    assert not opensearch_client.indices.exists(index=test_index_name), (
        f"Index {test_index_name!r} still exists after deletion."
    )
