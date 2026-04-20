"""Query service — orchestrates the embed → retrieve → generate pipeline.

``QueryService`` is the single entry point for executing a RAG query. It has no
HTTP concerns; it only raises ``AppError`` subclasses on failure.

Usage::

    service = QueryService(embedder=..., opensearch=..., llm=..., config=...)
    response = service.query(QueryRequest(query="What is Python?"))
"""

import time

from src.config import Config
from src.providers.embedder import Embedder
from src.providers.llm_provider import LLMProvider
from src.providers.opensearch_provider import OpenSearchProvider
from src.schemas.query import QueryRequest, QueryResponse, SourceRef


class QueryService:
    """Orchestrates embed → retrieve → generate for a single query request.

    This service has no imports from ``fastapi``, ``starlette``, or any other
    HTTP framework. All errors are raised as ``AppError`` subclasses.
    """

    def __init__(
        self,
        embedder: Embedder,
        opensearch: OpenSearchProvider,
        llm: LLMProvider,
        config: Config,
    ) -> None:
        """Initialise the query service with injected dependencies.

        Args:
            embedder: Provider for embedding the incoming query.
            opensearch: Provider for searching the OpenSearch index.
            llm: Provider for generating the final answer.
            config: Application configuration (used to resolve defaults).
        """
        self._embedder = embedder
        self._opensearch = opensearch
        self._llm = llm
        self._config = config

    def query(self, request: QueryRequest) -> QueryResponse:
        """Execute the full RAG pipeline for a single query.

        Steps:
            1. Record start time.
            2. Resolve ``retrieval_mode`` and ``top_k`` (request overrides config).
            3. Embed the query text.
            4. Retrieve matching chunks from OpenSearch.
            5. Generate an answer from the LLM.
            6. Compute latency and build the response.

        Args:
            request: Validated query request from the caller.

        Returns:
            A ``QueryResponse`` with answer, sources, retrieval mode, and latency.
        """
        start = time.monotonic()

        retrieval_mode: str = request.retrieval_mode or self._config.RETRIEVAL_MODE
        top_k: int = request.top_k or self._config.TOP_K

        query_vector = self._embedder.embed_text(request.query)
        chunks = self._opensearch.search(
            query_vector=query_vector,
            query_text=request.query,
            mode=retrieval_mode,
            filters=request.filters,
            k=top_k,
        )
        answer = self._llm.generate(query=request.query, chunks=chunks)

        latency_ms = int((time.monotonic() - start) * 1000)

        sources = [
            SourceRef(
                chunk_id=c.chunk_id,
                content=c.content,
                source=c.source,
                score=c.score,
            )
            for c in chunks
        ]

        return QueryResponse(
            answer=answer,
            sources=sources,
            retrieval_mode=retrieval_mode,
            latency_ms=latency_ms,
        )
