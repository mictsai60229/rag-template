"""Unit tests for src/services/query_service.py.

All providers are mocked so no real external calls are made.
"""

from unittest.mock import MagicMock

import pytest

from src.models import Chunk
from src.schemas.query import QueryRequest
from src.services.query_service import QueryService


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _make_config(
    retrieval_mode: str = "hybrid",
    top_k: int = 5,
) -> MagicMock:
    config = MagicMock()
    config.RETRIEVAL_MODE = retrieval_mode
    config.TOP_K = top_k
    return config


def _make_chunk(
    chunk_id: str = "c1",
    content: str = "chunk content",
    source: str = "doc.pdf",
    score: float = 0.8,
) -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        doc_id="d1",
        content=content,
        source=source,
        doc_type="pdf",
        page_number=None,
        chunk_index=0,
        ingested_at="2024-01-01",
        score=score,
    )


def _make_service(
    chunks: list[Chunk] | None = None,
    config: MagicMock | None = None,
) -> "tuple[QueryService, MagicMock, MagicMock]":
    """Create a QueryService with all mocked dependencies.

    Returns: (service, mock_embedder, mock_opensearch)
    """
    if chunks is None:
        chunks = [_make_chunk()]
    if config is None:
        config = _make_config()

    mock_embedder = MagicMock()
    mock_embedder.embed_text.return_value = [0.1, 0.2, 0.3]

    mock_opensearch = MagicMock()
    mock_opensearch.search.return_value = chunks

    service = QueryService(
        embedder=mock_embedder,
        opensearch=mock_opensearch,
        config=config,
    )
    return service, mock_embedder, mock_opensearch


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestQueryServiceOrchestration:
    @pytest.mark.asyncio
    async def test_calls_embed_then_search_in_order(self) -> None:
        """query() calls embed → search exactly once, in order."""
        service, mock_embedder, mock_opensearch = _make_service()
        request = QueryRequest(query="What is Python?")
        call_order: list[str] = []

        mock_embedder.embed_text.side_effect = lambda t: (
            call_order.append("embed") or [0.1, 0.2]
        )
        mock_opensearch.search.side_effect = lambda **_kw: (
            call_order.append("search") or [_make_chunk()]
        )

        await service.query(request)

        assert call_order == ["embed", "search"]

    @pytest.mark.asyncio
    async def test_embed_text_called_with_query_string(self) -> None:
        service, mock_embedder, _ = _make_service()
        request = QueryRequest(query="What is Python?")

        await service.query(request)

        mock_embedder.embed_text.assert_called_once_with("What is Python?")

    @pytest.mark.asyncio
    async def test_opensearch_search_called_with_correct_args(self) -> None:
        service, _, mock_opensearch = _make_service()
        request = QueryRequest(query="query text", retrieval_mode="vector", top_k=3)

        await service.query(request)

        mock_opensearch.search.assert_called_once_with(
            query_vector=[0.1, 0.2, 0.3],
            query_text="query text",
            mode="vector",
            filters=None,
            k=3,
        )


class TestRetrievalModeAndTopKFallback:
    @pytest.mark.asyncio
    async def test_retrieval_mode_falls_back_to_config_when_request_is_none(self) -> None:
        """When request.retrieval_mode is None, config.RETRIEVAL_MODE is used."""
        config = _make_config(retrieval_mode="keyword")
        service, _, mock_opensearch = _make_service(config=config)
        request = QueryRequest(query="query")  # retrieval_mode defaults to None

        await service.query(request)

        call_kwargs = mock_opensearch.search.call_args.kwargs
        assert call_kwargs["mode"] == "keyword"

    @pytest.mark.asyncio
    async def test_retrieval_mode_request_overrides_config(self) -> None:
        """When request.retrieval_mode is set, it overrides config."""
        config = _make_config(retrieval_mode="keyword")
        service, _, mock_opensearch = _make_service(config=config)
        request = QueryRequest(query="query", retrieval_mode="vector")

        await service.query(request)

        call_kwargs = mock_opensearch.search.call_args.kwargs
        assert call_kwargs["mode"] == "vector"

    @pytest.mark.asyncio
    async def test_top_k_falls_back_to_config_when_request_is_none(self) -> None:
        """When request.top_k is None, config.TOP_K is used."""
        config = _make_config(top_k=7)
        service, _, mock_opensearch = _make_service(config=config)
        request = QueryRequest(query="query")  # top_k defaults to None

        await service.query(request)

        call_kwargs = mock_opensearch.search.call_args.kwargs
        assert call_kwargs["k"] == 7

    @pytest.mark.asyncio
    async def test_top_k_request_overrides_config(self) -> None:
        """When request.top_k is set, it overrides config."""
        config = _make_config(top_k=7)
        service, _, mock_opensearch = _make_service(config=config)
        request = QueryRequest(query="query", top_k=3)

        await service.query(request)

        call_kwargs = mock_opensearch.search.call_args.kwargs
        assert call_kwargs["k"] == 3


class TestQueryResponseShape:
    @pytest.mark.asyncio
    async def test_response_retrieval_mode_set_correctly(self) -> None:
        config = _make_config(retrieval_mode="vector")
        service, _, _ = _make_service(config=config)
        response = await service.query(QueryRequest(query="q"))
        assert response.retrieval_mode == "vector"

    @pytest.mark.asyncio
    async def test_latency_ms_is_non_negative_integer(self) -> None:
        service, _, _ = _make_service()
        response = await service.query(QueryRequest(query="q"))
        assert isinstance(response.latency_ms, int)
        assert response.latency_ms >= 0

    @pytest.mark.asyncio
    async def test_sources_list_maps_chunk_fields_correctly(self) -> None:
        chunk = _make_chunk(chunk_id="abc", content="text", source="file.pdf", score=0.75)
        service, _, _ = _make_service(chunks=[chunk])

        response = await service.query(QueryRequest(query="q"))

        assert len(response.sources) == 1
        src = response.sources[0]
        assert src.chunk_id == "abc"
        assert src.content == "text"
        assert src.source == "file.pdf"
        assert src.score == 0.75

    @pytest.mark.asyncio
    async def test_sources_empty_when_no_chunks_returned(self) -> None:
        service, _, _ = _make_service(chunks=[])
        response = await service.query(QueryRequest(query="q"))
        assert response.sources == []

    def test_no_fastapi_imports_in_service(self) -> None:
        """QueryService must not import FastAPI or starlette at the module level."""
        import ast
        import pathlib

        service_path = pathlib.Path(__file__).parents[2] / "src" / "services" / "query_service.py"
        tree = ast.parse(service_path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module or ""]
                for name in names:
                    assert not name.startswith("fastapi"), (
                        f"QueryService must not import fastapi; found: {name}"
                    )
                    assert not name.startswith("starlette"), (
                        f"QueryService must not import starlette; found: {name}"
                    )
