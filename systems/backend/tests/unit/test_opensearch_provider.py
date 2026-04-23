"""Unit tests for src/providers/opensearch_provider.py.

All calls to ``opensearchpy.OpenSearch`` are mocked to avoid requiring a
running cluster.
"""

import sys
from types import ModuleType
from unittest.mock import MagicMock, patch

import pytest

from src.exceptions.domain import ExternalServiceError


# ---------------------------------------------------------------------------
# Helpers / shared fixtures
# ---------------------------------------------------------------------------


def _make_fake_opensearchpy() -> MagicMock:
    """Return a minimal fake ``opensearchpy`` module."""
    fake = MagicMock(name="opensearchpy")
    # Ensure exceptions sub-module exists
    fake.exceptions = MagicMock()
    fake.exceptions.OpenSearchException = type("OpenSearchException", (Exception,), {})
    return fake


def _make_provider(
    fake_opensearchpy: MagicMock,
    keyword_boost: float = 0.3,
) -> "tuple[object, MagicMock]":
    """Instantiate an OpenSearchProvider with a mocked opensearch client.

    Returns the provider instance and the mock client returned by
    ``OpenSearch(...)``.
    """
    from src.providers.opensearch_provider import OpenSearchProvider

    mock_client = MagicMock()
    fake_opensearchpy.OpenSearch.return_value = mock_client

    with patch.dict(sys.modules, {"opensearchpy": fake_opensearchpy}):
        provider = OpenSearchProvider(
            host="localhost",
            port=9200,
            index="test-index",
            keyword_boost=keyword_boost,
        )
        # Replace the stored module reference so calls inside search() resolve correctly
        provider._opensearchpy = fake_opensearchpy
        provider._client = mock_client

    return provider, mock_client


def _make_hit(
    chunk_id: str = "c1",
    score: float = 0.9,
    source: dict | None = None,
) -> dict:
    """Build a minimal OpenSearch hit dict."""
    if source is None:
        source = {
            "doc_id": "d1",
            "content": "some content",
            "source": "doc.pdf",
            "doc_type": "pdf",
            "page_number": 1,
            "chunk_index": 0,
            "ingested_at": "2024-01-01T00:00:00Z",
        }
    return {"_id": chunk_id, "_score": score, "_source": source}


def _make_search_response(hits: list[dict]) -> dict:
    return {"hits": {"hits": hits}}


# ---------------------------------------------------------------------------
# DSL construction tests (via search() with mocked client)
# ---------------------------------------------------------------------------


class TestVectorMode:
    def test_vector_mode_builds_knn_query(self) -> None:
        fake_os = _make_fake_opensearchpy()
        provider, mock_client = _make_provider(fake_os)
        mock_client.search.return_value = _make_search_response([])

        provider.search([0.1, 0.2], "query", "vector", None, 5)

        call_kwargs = mock_client.search.call_args
        body = call_kwargs.kwargs["body"] if call_kwargs.kwargs else call_kwargs[1]["body"]
        assert "knn" in body["query"]
        knn_body = body["query"]["knn"]["embedding"]
        assert knn_body["vector"] == [0.1, 0.2]
        assert knn_body["k"] == 5

    def test_vector_mode_with_filters_uses_bool_must(self) -> None:
        fake_os = _make_fake_opensearchpy()
        provider, mock_client = _make_provider(fake_os)
        mock_client.search.return_value = _make_search_response([])

        provider.search([0.1], "query", "vector", {"source": "doc.pdf"}, 3)

        body = mock_client.search.call_args[1]["body"]
        assert "bool" in body["query"]
        assert "filter" in body["query"]["bool"]
        filter_clauses = body["query"]["bool"]["filter"]
        assert {"term": {"source": "doc.pdf"}} in filter_clauses


class TestKeywordMode:
    def test_keyword_mode_builds_match_query(self) -> None:
        fake_os = _make_fake_opensearchpy()
        provider, mock_client = _make_provider(fake_os)
        mock_client.search.return_value = _make_search_response([])

        provider.search([], "what is python", "keyword", None, 5)

        body = mock_client.search.call_args[1]["body"]
        assert "match" in body["query"]
        assert body["query"]["match"]["content"]["query"] == "what is python"

    def test_keyword_mode_with_filters(self) -> None:
        fake_os = _make_fake_opensearchpy()
        provider, mock_client = _make_provider(fake_os)
        mock_client.search.return_value = _make_search_response([])

        provider.search([], "query", "keyword", {"doc_type": "pdf"}, 3)

        body = mock_client.search.call_args[1]["body"]
        assert "bool" in body["query"]
        filter_clauses = body["query"]["bool"]["filter"]
        assert {"term": {"doc_type": "pdf"}} in filter_clauses


class TestHybridMode:
    def test_hybrid_mode_includes_knn_and_match_should_clauses(self) -> None:
        fake_os = _make_fake_opensearchpy()
        provider, mock_client = _make_provider(fake_os, keyword_boost=0.3)
        mock_client.search.return_value = _make_search_response([])

        provider.search([0.5, 0.6], "what is python", "hybrid", None, 5)

        body = mock_client.search.call_args[1]["body"]
        assert "bool" in body["query"]
        should = body["query"]["bool"]["should"]
        assert len(should) == 2
        clause_types = {list(c.keys())[0] for c in should}
        assert "knn" in clause_types
        assert "match" in clause_types

    def test_hybrid_match_clause_has_keyword_boost(self) -> None:
        fake_os = _make_fake_opensearchpy()
        provider, mock_client = _make_provider(fake_os, keyword_boost=0.5)
        mock_client.search.return_value = _make_search_response([])

        provider.search([0.1], "query", "hybrid", None, 5)

        body = mock_client.search.call_args[1]["body"]
        should = body["query"]["bool"]["should"]
        match_clause = next(c for c in should if "match" in c)
        assert match_clause["match"]["content"]["boost"] == 0.5

    def test_hybrid_mode_with_filters(self) -> None:
        fake_os = _make_fake_opensearchpy()
        provider, mock_client = _make_provider(fake_os)
        mock_client.search.return_value = _make_search_response([])

        provider.search([0.1], "query", "hybrid", {"source": "a.pdf", "doc_type": "pdf"}, 3)

        body = mock_client.search.call_args[1]["body"]
        filter_clauses = body["query"]["bool"]["filter"]
        assert len(filter_clauses) == 2


class TestFilterClauses:
    def test_no_filters_does_not_add_filter_key(self) -> None:
        fake_os = _make_fake_opensearchpy()
        provider, mock_client = _make_provider(fake_os)
        mock_client.search.return_value = _make_search_response([])

        provider.search([0.1], "query", "keyword", None, 5)

        body = mock_client.search.call_args[1]["body"]
        # When no filters, keyword mode returns plain match (no bool wrapper)
        assert "bool" not in body["query"]

    def test_empty_filters_dict_treated_as_no_filters(self) -> None:
        fake_os = _make_fake_opensearchpy()
        provider, mock_client = _make_provider(fake_os)
        mock_client.search.return_value = _make_search_response([])

        provider.search([0.1], "query", "keyword", {}, 5)

        body = mock_client.search.call_args[1]["body"]
        assert "bool" not in body["query"]


class TestHitMapping:
    def test_hits_mapped_to_chunks(self) -> None:
        fake_os = _make_fake_opensearchpy()
        provider, mock_client = _make_provider(fake_os)
        hit = _make_hit(chunk_id="abc123", score=0.75)
        mock_client.search.return_value = _make_search_response([hit])

        chunks = provider.search([0.1], "query", "vector", None, 1)

        assert len(chunks) == 1
        chunk = chunks[0]
        assert chunk.chunk_id == "abc123"
        assert chunk.score == 0.75
        assert chunk.content == "some content"
        assert chunk.source == "doc.pdf"

    def test_nullable_page_number(self) -> None:
        fake_os = _make_fake_opensearchpy()
        provider, mock_client = _make_provider(fake_os)
        src = {
            "doc_id": "d1",
            "content": "text",
            "source": "x.pdf",
            "doc_type": "pdf",
            "chunk_index": 0,
            "ingested_at": "2024-01-01",
        }
        hit = {"_id": "c1", "_score": 1.0, "_source": src}
        mock_client.search.return_value = _make_search_response([hit])

        chunks = provider.search([0.1], "q", "vector", None, 1)

        assert chunks[0].page_number is None


class TestErrorHandling:
    def test_opensearch_exception_wrapped_as_external_service_error(self) -> None:
        fake_os = _make_fake_opensearchpy()
        provider, mock_client = _make_provider(fake_os)
        mock_client.search.side_effect = fake_os.exceptions.OpenSearchException("connection failed")

        with pytest.raises(ExternalServiceError, match="OpenSearch search failed"):
            provider.search([0.1], "query", "vector", None, 5)
