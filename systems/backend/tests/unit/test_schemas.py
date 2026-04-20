"""Unit tests for src/schemas/query.py and src/schemas/common.py."""

import pytest
from pydantic import ValidationError

from src.schemas.common import ErrorResponse
from src.schemas.query import QueryRequest, QueryResponse, SourceRef


class TestSourceRef:
    def test_valid_construction(self) -> None:
        ref = SourceRef(chunk_id="c1", content="some text", source="doc.pdf", score=0.9)
        assert ref.chunk_id == "c1"
        assert ref.content == "some text"
        assert ref.source == "doc.pdf"
        assert ref.score == 0.9

    def test_is_frozen(self) -> None:
        ref = SourceRef(chunk_id="c1", content="text", source="doc.pdf", score=0.5)
        with pytest.raises(Exception):
            ref.chunk_id = "changed"  # type: ignore[misc]

    def test_missing_field_raises(self) -> None:
        with pytest.raises(ValidationError):
            SourceRef(chunk_id="c1", content="text", source="doc.pdf")  # type: ignore[call-arg]


class TestQueryRequest:
    def test_valid_minimal(self) -> None:
        req = QueryRequest(query="What is Python?")
        assert req.query == "What is Python?"
        assert req.retrieval_mode is None
        assert req.top_k is None
        assert req.filters is None

    def test_valid_full(self) -> None:
        req = QueryRequest(
            query="What is Python?",
            retrieval_mode="hybrid",
            top_k=10,
            filters={"source": "report.pdf"},
        )
        assert req.retrieval_mode == "hybrid"
        assert req.top_k == 10
        assert req.filters == {"source": "report.pdf"}

    def test_empty_query_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError):
            QueryRequest(query="")

    def test_missing_query_raises_validation_error(self) -> None:
        with pytest.raises(ValidationError):
            QueryRequest()  # type: ignore[call-arg]


class TestQueryResponse:
    def _make_source(self) -> SourceRef:
        return SourceRef(chunk_id="c1", content="text", source="doc.pdf", score=0.8)

    def test_valid_construction(self) -> None:
        resp = QueryResponse(
            answer="The answer is 42.",
            sources=[self._make_source()],
            retrieval_mode="vector",
            latency_ms=120,
        )
        assert resp.answer == "The answer is 42."
        assert len(resp.sources) == 1
        assert resp.retrieval_mode == "vector"
        assert resp.latency_ms == 120

    def test_is_frozen(self) -> None:
        resp = QueryResponse(
            answer="A",
            sources=[],
            retrieval_mode="hybrid",
            latency_ms=50,
        )
        with pytest.raises(Exception):
            resp.answer = "B"  # type: ignore[misc]

    def test_empty_sources_allowed(self) -> None:
        resp = QueryResponse(answer="No context.", sources=[], retrieval_mode="keyword", latency_ms=10)
        assert resp.sources == []


class TestErrorResponse:
    def test_valid_construction(self) -> None:
        err = ErrorResponse(detail="Something went wrong.")
        assert err.detail == "Something went wrong."

    def test_is_frozen(self) -> None:
        err = ErrorResponse(detail="error")
        with pytest.raises(Exception):
            err.detail = "changed"  # type: ignore[misc]

    def test_missing_detail_raises(self) -> None:
        with pytest.raises(ValidationError):
            ErrorResponse()  # type: ignore[call-arg]
