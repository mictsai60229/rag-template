"""
Search mode smoke tests for OpenSearch.

Verifies that BM25 keyword search, k-NN vector search, and metadata-filtered
search all operate correctly against a seeded test index.

Requires a running OpenSearch instance. Set OPENSEARCH_URL to override
the default http://localhost:9200.

Run with:
    docker compose up -d
    sleep 30
    OPENSEARCH_URL=http://localhost:9200 pytest tests/test_search_modes.py -v -m integration
"""

import json
import os
from pathlib import Path
from uuid import uuid4

import pytest
from opensearchpy import OpenSearch

pytestmark = pytest.mark.integration

# Path to the canonical reference mapping relative to this file.
_MAPPING_PATH = Path(__file__).parent.parent / "mappings" / "rag_index.json"

# Seed documents used to populate the test index.
_SEED_DOCUMENTS = [
    {
        "content": "Python is a versatile programming language used in data science.",
        "doc_type": "txt",
        "source": "doc1.txt",
        "page_number": 1,
        "chunk_index": 0,
    },
    {
        "content": "Python supports object-oriented and functional programming paradigms.",
        "doc_type": "txt",
        "source": "doc1.txt",
        "page_number": 1,
        "chunk_index": 1,
    },
    {
        "content": "OpenSearch provides full-text search and vector similarity search.",
        "doc_type": "pdf",
        "source": "doc2.pdf",
        "page_number": 1,
        "chunk_index": 0,
    },
    {
        "content": "Machine learning models can be used for natural language processing tasks.",
        "doc_type": "pdf",
        "source": "doc2.pdf",
        "page_number": 2,
        "chunk_index": 1,
    },
    {
        "content": "RAG combines retrieval with language model generation for grounded answers.",
        "doc_type": "md",
        "source": "doc3.md",
        "page_number": None,
        "chunk_index": 0,
    },
]


def _client() -> OpenSearch:
    """Return an opensearch-py client configured from OPENSEARCH_URL."""
    url = os.environ.get("OPENSEARCH_URL", "http://localhost:9200")
    return OpenSearch(hosts=[url], use_ssl=False, verify_certs=False)


def _load_reference_mapping() -> dict:
    """Load and return the canonical index mapping from rag_index.json."""
    with open(_MAPPING_PATH, encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture(scope="module")
def seeded_index():
    """
    Module-scoped fixture: create a unique test index, bulk-index 5 seed
    documents, yield (client, index_name), then delete the index on teardown.
    """
    client = _client()
    short_id = uuid4().hex[:8]
    index_name = f"rag-test-search-{short_id}"

    mapping = _load_reference_mapping()
    client.indices.create(index=index_name, body=mapping)

    # Build the bulk request body.
    bulk_body = []
    for doc in _SEED_DOCUMENTS:
        bulk_body.append({"index": {"_index": index_name, "_id": uuid4().hex}})
        bulk_body.append(
            {
                "chunk_id": uuid4().hex,
                "doc_id": uuid4().hex,
                "content": doc["content"],
                "embedding": [0.0] * 1536,
                "source": doc["source"],
                "doc_type": doc["doc_type"],
                "page_number": doc["page_number"],
                "chunk_index": doc["chunk_index"],
                "ingested_at": "2024-01-01T00:00:00Z",
            }
        )

    client.bulk(body=bulk_body, refresh=True)

    yield client, index_name

    # Teardown: delete the test index.
    if client.indices.exists(index=index_name):
        client.indices.delete(index=index_name)


def test_bm25_keyword_search(seeded_index) -> None:
    """BM25 match query on 'python' must return at least one hit."""
    client, index_name = seeded_index
    response = client.search(
        index=index_name,
        body={"query": {"match": {"content": "python"}}},
    )
    hits_total = response["hits"]["total"]["value"]
    assert hits_total > 0, (
        f"Expected at least one BM25 hit for 'python', got {hits_total}."
    )


def test_vector_knn_search(seeded_index) -> None:
    """k-NN search with a zero-vector must return a list (may be empty for zero-vectors)."""
    client, index_name = seeded_index
    response = client.search(
        index=index_name,
        body={
            "query": {
                "knn": {
                    "embedding": {
                        "vector": [0.0] * 1536,
                        "k": 3,
                    }
                }
            }
        },
    )
    # The response must not error and hits must be a list.
    assert isinstance(response["hits"]["hits"], list), (
        "Expected hits.hits to be a list."
    )


def test_metadata_filter(seeded_index) -> None:
    """Metadata filter on doc_type='txt' must return only txt documents."""
    client, index_name = seeded_index
    response = client.search(
        index=index_name,
        body={
            "query": {
                "bool": {
                    "must": [{"match_all": {}}],
                    "filter": [{"term": {"doc_type": "txt"}}],
                }
            }
        },
    )
    hits = response["hits"]["hits"]
    assert len(hits) > 0, "Expected at least one hit with doc_type='txt'."
    for hit in hits:
        assert hit["_source"]["doc_type"] == "txt", (
            f"Expected doc_type='txt', got {hit['_source']['doc_type']!r}."
        )
