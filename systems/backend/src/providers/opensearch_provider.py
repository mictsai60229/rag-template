"""OpenSearch provider — the sole place in the Backend that imports ``opensearch-py``.

Wraps the OpenSearch client and exposes a single ``search()`` method that
supports three retrieval modes (vector, keyword, hybrid) and optional metadata
filtering.

Usage::

    provider = OpenSearchProvider(
        host="localhost", port=9200, index="rag", keyword_boost=0.3
    )
    chunks = provider.search(
        query_vector=[0.1, ...],
        query_text="What is Python?",
        mode="hybrid",
        filters={"source": "guide.pdf"},
        k=5,
    )
"""

from src.exceptions.domain import ExternalServiceError
from src.models import Chunk


class OpenSearchProvider:
    """Thin wrapper around the ``opensearch-py`` client.

    Only this class may import ``opensearchpy`` in the Backend codebase.
    """

    def __init__(
        self,
        host: str,
        port: int,
        index: str,
        username: str | None = None,
        password: str | None = None,
        keyword_boost: float = 0.3,
    ) -> None:
        """Initialise the OpenSearch client.

        Args:
            host: OpenSearch host name or IP.
            port: OpenSearch port number.
            index: Target index name for all search calls.
            username: Optional basic-auth username.
            password: Optional basic-auth password.
            keyword_boost: Boost weight applied to the ``match`` clause in hybrid mode.
        """
        import opensearchpy  # lazy import — only this file imports opensearch-py

        self._opensearchpy = opensearchpy
        self._index = index
        self._keyword_boost = keyword_boost

        http_auth = (username, password) if username and password else None
        self._client = opensearchpy.OpenSearch(
            hosts=[{"host": host, "port": port}],
            http_auth=http_auth,
            use_ssl=False,
            verify_certs=False,
        )

    def search(
        self,
        query_vector: list[float],
        query_text: str,
        mode: str,
        filters: dict[str, str] | None,
        k: int,
    ) -> list[Chunk]:
        """Run a search query against OpenSearch and return matched chunks.

        Args:
            query_vector: Dense embedding vector for the query.
            query_text: Original query text (used in keyword and hybrid modes).
            mode: Retrieval mode — ``"vector"``, ``"keyword"``, or ``"hybrid"``.
            filters: Optional metadata filter map (e.g. ``{"source": "doc.pdf"}``).
                     Only applied when non-empty.
            k: Maximum number of results to return.

        Returns:
            List of ``Chunk`` objects ranked by relevance score.

        Raises:
            ExternalServiceError: If the OpenSearch request fails.
        """
        dsl = self._build_dsl(query_vector, query_text, mode, filters, k)
        try:
            response = self._client.search(index=self._index, body=dsl, size=k)
        except self._opensearchpy.exceptions.OpenSearchException as exc:
            raise ExternalServiceError(f"OpenSearch search failed: {exc}") from exc

        return [self._hit_to_chunk(hit) for hit in response["hits"]["hits"]]

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_dsl(
        self,
        query_vector: list[float],
        query_text: str,
        mode: str,
        filters: dict[str, str] | None,
        k: int,
    ) -> dict:  # type: ignore[type-arg]
        """Build the OpenSearch DSL query body.

        Args:
            query_vector: Dense query vector.
            query_text: Raw query string.
            mode: ``"vector"``, ``"keyword"``, or ``"hybrid"``.
            filters: Optional metadata filter map.
            k: Number of results.

        Returns:
            A dict suitable for passing as the ``body`` argument to ``client.search()``.
        """
        filter_clauses = self._build_filter_clauses(filters)

        if mode == "vector":
            knn_clause: dict = {  # type: ignore[type-arg]
                "knn": {"embedding": {"vector": query_vector, "k": k}}
            }
            if filter_clauses:
                query: dict = {  # type: ignore[type-arg]
                    "bool": {"must": [knn_clause], "filter": filter_clauses}
                }
            else:
                query = knn_clause

        elif mode == "keyword":
            match_clause: dict = {"match": {"content": {"query": query_text}}}  # type: ignore[type-arg]
            if filter_clauses:
                query = {"bool": {"must": [match_clause], "filter": filter_clauses}}
            else:
                query = match_clause

        else:  # hybrid
            knn_should: dict = {"knn": {"embedding": {"vector": query_vector, "k": k}}}  # type: ignore[type-arg]
            match_should: dict = {  # type: ignore[type-arg]
                "match": {"content": {"query": query_text, "boost": self._keyword_boost}}
            }
            bool_query: dict = {"should": [knn_should, match_should]}  # type: ignore[type-arg]
            if filter_clauses:
                bool_query["filter"] = filter_clauses
            query = {"bool": bool_query}

        return {"query": query}

    @staticmethod
    def _build_filter_clauses(
        filters: dict[str, str] | None,
    ) -> list[dict]:  # type: ignore[type-arg]
        """Convert a metadata filter map to a list of OpenSearch ``term`` clauses.

        Args:
            filters: Metadata filter map or ``None``.

        Returns:
            A (possibly empty) list of ``{"term": {field: value}}`` dicts.
        """
        if not filters:
            return []
        return [{"term": {field: value}} for field, value in filters.items()]

    @staticmethod
    def _hit_to_chunk(hit: dict) -> Chunk:  # type: ignore[type-arg]
        """Map a raw OpenSearch hit dict to a ``Chunk`` dataclass.

        Args:
            hit: A single element from ``response["hits"]["hits"]``.

        Returns:
            A populated ``Chunk`` instance.
        """
        source = hit["_source"]
        return Chunk(
            chunk_id=hit["_id"],
            doc_id=source.get("doc_id", ""),
            content=source.get("content", ""),
            source=source.get("source", ""),
            doc_type=source.get("doc_type", ""),
            page_number=source.get("page_number"),
            chunk_index=source.get("chunk_index", 0),
            ingested_at=source.get("ingested_at", ""),
            score=hit.get("_score", 0.0),
        )
