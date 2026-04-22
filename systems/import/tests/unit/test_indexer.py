"""Unit tests for src/indexer.py.

OpenSearchProvider is mocked throughout; no real OpenSearch instance required.
"""

import json
import os
import tempfile
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.indexer import MAX_DOCUMENT_BYTES, Indexer
from src.models import Chunk


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

MINIMAL_MAPPING = {
    "settings": {"index.knn": True},
    "mappings": {
        "properties": {
            "_comment_dimension": "should be stripped",
            "embedding": {"type": "knn_vector", "dimension": 1536},
            "content": {"type": "text"},
        }
    },
}


def _write_mapping(mapping: dict) -> str:
    """Write *mapping* to a temp file and return its path."""
    fd, path = tempfile.mkstemp(suffix=".json")
    with os.fdopen(fd, "w") as fh:
        json.dump(mapping, fh)
    return path


def _make_settings(embedding_dimension: int = 1536) -> MagicMock:
    s = MagicMock()
    s.embedding_dimension = embedding_dimension
    return s


def _make_chunk(index: int = 0) -> Chunk:
    return Chunk(
        doc_id="doc-1",
        content=f"chunk content {index}",
        source="test.txt",
        doc_type="txt",
        chunk_index=index,
        ingested_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
    )


# ---------------------------------------------------------------------------
# ensure_index
# ---------------------------------------------------------------------------


class TestEnsureIndex:
    def test_creates_index_when_it_does_not_exist(self) -> None:
        path = _write_mapping(MINIMAL_MAPPING)
        try:
            provider = MagicMock()
            provider._index = "test-index"
            provider.index_exists.return_value = False

            indexer = Indexer(provider=provider, settings=_make_settings(), mapping_path=path)
            indexer.ensure_index()

            provider.create_index.assert_called_once()
        finally:
            os.unlink(path)

    def test_does_not_create_index_when_it_already_exists(self) -> None:
        path = _write_mapping(MINIMAL_MAPPING)
        try:
            provider = MagicMock()
            provider._index = "test-index"
            provider.index_exists.return_value = True

            indexer = Indexer(provider=provider, settings=_make_settings(), mapping_path=path)
            indexer.ensure_index()

            provider.create_index.assert_not_called()
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# _load_mapping
# ---------------------------------------------------------------------------


class TestLoadMapping:
    def test_strips_comment_dimension_key(self) -> None:
        path = _write_mapping(MINIMAL_MAPPING)
        try:
            provider = MagicMock()
            provider._index = "test-index"
            indexer = Indexer(provider=provider, settings=_make_settings(), mapping_path=path)
            mapping = indexer._load_mapping()

            assert "_comment_dimension" not in mapping["mappings"]["properties"]
        finally:
            os.unlink(path)

    def test_patches_embedding_dimension_from_settings(self) -> None:
        path = _write_mapping(MINIMAL_MAPPING)
        try:
            provider = MagicMock()
            provider._index = "test-index"
            indexer = Indexer(
                provider=provider, settings=_make_settings(embedding_dimension=768), mapping_path=path
            )
            mapping = indexer._load_mapping()

            assert mapping["mappings"]["properties"]["embedding"]["dimension"] == 768
        finally:
            os.unlink(path)


# ---------------------------------------------------------------------------
# _validate_document_size
# ---------------------------------------------------------------------------


class TestValidateDocumentSize:
    def test_returns_false_for_oversized_document(self) -> None:
        provider = MagicMock()
        provider._index = "test-index"
        indexer = Indexer(
            provider=provider,
            settings=_make_settings(),
            mapping_path="/dev/null",
        )
        # Build a document exceeding 10 MB.
        huge_doc = {"chunk_id": "x", "content": "A" * (MAX_DOCUMENT_BYTES + 1)}
        assert indexer._validate_document_size(huge_doc) is False

    def test_returns_true_for_valid_document(self) -> None:
        provider = MagicMock()
        provider._index = "test-index"
        indexer = Indexer(
            provider=provider,
            settings=_make_settings(),
            mapping_path="/dev/null",
        )
        small_doc = {"chunk_id": "x", "content": "hello"}
        assert indexer._validate_document_size(small_doc) is True


# ---------------------------------------------------------------------------
# index_chunks
# ---------------------------------------------------------------------------


class TestIndexChunks:
    def test_builds_correct_chunk_documents(self) -> None:
        provider = MagicMock()
        provider._index = "test-index"
        indexer = Indexer(
            provider=provider,
            settings=_make_settings(),
            mapping_path="/dev/null",
        )
        chunk = _make_chunk(0)
        embedding = [0.1, 0.2, 0.3]

        indexer.index_chunks([chunk], [embedding])

        call_docs = provider.bulk_index.call_args.args[0]
        assert len(call_docs) == 1
        doc = call_docs[0]
        assert doc["chunk_id"] == chunk.chunk_id
        assert doc["doc_id"] == "doc-1"
        assert doc["content"] == "chunk content 0"
        assert doc["embedding"] == [0.1, 0.2, 0.3]
        assert doc["source"] == "test.txt"
        assert doc["doc_type"] == "txt"
        assert doc["page_number"] is None
        assert doc["chunk_index"] == 0
        assert "ingested_at" in doc

    def test_skips_oversized_documents(self) -> None:
        provider = MagicMock()
        provider._index = "test-index"
        indexer = Indexer(
            provider=provider,
            settings=_make_settings(),
            mapping_path="/dev/null",
        )
        valid_chunk = _make_chunk(0)
        # Build a chunk whose content alone exceeds the limit.
        huge_chunk = Chunk(
            doc_id="doc-1",
            content="X" * (MAX_DOCUMENT_BYTES + 1),
            source="test.txt",
            doc_type="txt",
            chunk_index=1,
        )
        embeddings = [[0.1], [0.2]]

        count = indexer.index_chunks([valid_chunk, huge_chunk], embeddings)

        call_docs = provider.bulk_index.call_args.args[0]
        assert len(call_docs) == 1
        assert count == 1

    def test_returns_correct_count(self) -> None:
        provider = MagicMock()
        provider._index = "test-index"
        indexer = Indexer(
            provider=provider,
            settings=_make_settings(),
            mapping_path="/dev/null",
        )
        chunks = [_make_chunk(i) for i in range(5)]
        embeddings = [[0.1] * 4 for _ in range(5)]

        count = indexer.index_chunks(chunks, embeddings)

        assert count == 5

    def test_does_not_call_bulk_index_for_empty_input(self) -> None:
        provider = MagicMock()
        provider._index = "test-index"
        indexer = Indexer(
            provider=provider,
            settings=_make_settings(),
            mapping_path="/dev/null",
        )

        count = indexer.index_chunks([], [])

        provider.bulk_index.assert_not_called()
        assert count == 0
