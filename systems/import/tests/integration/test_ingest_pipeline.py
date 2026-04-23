"""End-to-end integration tests for the RAG Data Import pipeline.

These tests start a real OpenSearch container via ``testcontainers`` and run
the full ingest pipeline (load → clean → chunk → embed → index) against it.
The OpenAI embedder is mocked to return zero-vectors so no real API calls are made.

Requires Docker to be running on the host machine.

Mark: integration
"""

import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.chunker import Chunker
from src.cleaner import TextCleaner
from src.indexer import Indexer
from src.loader import DocumentLoader
from src.providers.opensearch_provider import OpenSearchProvider

pytestmark = pytest.mark.integration

FIXTURE_DIR = Path(__file__).parent / "fixtures"
SAMPLE_TXT = FIXTURE_DIR / "sample.txt"

# Simplified mapping without knn_vector for integration tests.
# Using knn_vector requires the k-NN plugin to be enabled, which may or may not
# be available in the testcontainers image.  A standard float mapping allows us
# to test every other pipeline concern (index lifecycle, bulk indexing, search)
# without that dependency.
INTEGRATION_MAPPING = {
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
    },
    "mappings": {
        "properties": {
            "chunk_id": {"type": "keyword"},
            "doc_id": {"type": "keyword"},
            "content": {"type": "text", "analyzer": "standard"},
            "embedding": {"type": "float"},
            "source": {"type": "keyword"},
            "doc_type": {"type": "keyword"},
            "page_number": {"type": "integer"},
            "chunk_index": {"type": "integer"},
            "ingested_at": {"type": "date"},
        }
    },
}


def _make_settings(embedding_dimension: int = 4) -> MagicMock:
    """Return a minimal Settings mock for integration tests."""
    s = MagicMock()
    s.embedding_dimension = embedding_dimension
    s.chunking_strategy = "fixed"
    s.chunk_size = 300
    s.chunk_overlap = 0
    return s


def _run_pipeline(provider: OpenSearchProvider) -> tuple[int, int]:
    """Run the full ingest pipeline on the fixture file.

    Returns ``(n_chunks, n_indexed)``.
    """
    settings = _make_settings()

    # Load
    loader = DocumentLoader()
    raw_docs = loader.load(str(SAMPLE_TXT))

    # Clean
    cleaner = TextCleaner()
    cleaned_docs = [cleaner.clean_document(doc) for doc in raw_docs]

    # Chunk
    chunker = Chunker(settings)
    all_chunks = []
    for doc in cleaned_docs:
        chunks = chunker.chunk(doc.content, doc.source, doc.doc_id, doc.doc_type)
        all_chunks.extend(chunks)

    n_chunks = len(all_chunks)

    # Embed (mocked — return zero-vectors of dimension 4)
    embeddings = [[0.0, 0.0, 0.0, 0.0] for _ in all_chunks]

    # Index
    mapping_path = _write_integration_mapping()
    indexer = Indexer(provider=provider, settings=settings, mapping_path=mapping_path)
    indexer.ensure_index()
    n_indexed = indexer.index_chunks(all_chunks, embeddings)

    return n_chunks, n_indexed


def _write_integration_mapping() -> str:
    """Write the integration mapping to a temp file and return its path."""
    import json
    import os
    import tempfile

    fd, path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w") as fh:
        json.dump(INTEGRATION_MAPPING, fh)
    return path


def _count_documents(provider: OpenSearchProvider) -> int:
    """Return the number of documents in the provider's index."""
    # Refresh to ensure all indexed docs are visible.
    provider._client.indices.refresh(index=provider._index)
    response = provider._client.count(index=provider._index)
    return int(response["count"])


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestIngestPipeline:
    def test_ingest_creates_index(self, opensearch_provider: OpenSearchProvider) -> None:
        """After running the pipeline, the index must exist in OpenSearch."""
        assert not opensearch_provider.index_exists(), "Index should not exist before pipeline run"

        _run_pipeline(opensearch_provider)

        assert opensearch_provider.index_exists(), "Index must exist after pipeline run"

    def test_ingest_indexes_chunks(self, opensearch_provider: OpenSearchProvider) -> None:
        """Number of indexed documents must equal number of chunks produced."""
        n_chunks, n_indexed = _run_pipeline(opensearch_provider)

        assert n_chunks > 0, "Fixture file should produce at least one chunk"
        assert n_indexed == n_chunks, (
            f"Expected {n_chunks} indexed documents, got {n_indexed}"
        )

    def test_ingest_chunks_searchable(self, opensearch_provider: OpenSearchProvider) -> None:
        """After ingestion, a keyword search on 'Python' must return hits."""
        _run_pipeline(opensearch_provider)

        # Refresh so documents are visible to search.
        opensearch_provider._client.indices.refresh(index=opensearch_provider._index)

        # Short pause to ensure search is ready (usually instant after refresh).
        time.sleep(0.5)

        response = opensearch_provider._client.search(
            index=opensearch_provider._index,
            body={"query": {"match": {"content": "Python"}}},
        )
        total_hits = response["hits"]["total"]["value"]
        assert total_hits > 0, (
            f"Expected keyword search to return hits, got 0. "
            f"Index may not contain any searchable chunks."
        )

    def test_ingest_idempotent(self, opensearch_provider: OpenSearchProvider) -> None:
        """Running the pipeline twice must not increase the document count (upsert semantics)."""
        # First run.
        n_chunks, _ = _run_pipeline(opensearch_provider)
        count_after_first = _count_documents(opensearch_provider)

        # Second run with the same source.
        _run_pipeline(opensearch_provider)
        count_after_second = _count_documents(opensearch_provider)

        assert count_after_first == n_chunks, (
            f"After first run: expected {n_chunks} docs, got {count_after_first}"
        )
        assert count_after_second == count_after_first, (
            f"After second run: expected {count_after_first} docs (upsert), "
            f"got {count_after_second}"
        )
