"""OpenSearch provider for the RAG Data Import pipeline.

This is the *only* file in the Import pipeline that imports ``opensearch-py``
directly. All other modules interact with OpenSearch through this wrapper.

Responsibilities:
- Index lifecycle management: ``index_exists``, ``create_index``, ``delete_index``.
- Bulk document indexing: ``bulk_index``.
- Translate ``opensearchpy.exceptions.OpenSearchException`` into :class:`RuntimeError`.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class OpenSearchProvider:
    """Wraps the opensearch-py client and exposes a clean interface for the Import pipeline.

    Args:
        host:     OpenSearch host (e.g. ``"localhost"``).
        port:     OpenSearch port (default ``9200``).
        index:    Name of the target index.
        username: Optional basic-auth username.
        password: Optional basic-auth password.
    """

    def __init__(
        self,
        host: str,
        port: int,
        index: str,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        import opensearchpy  # noqa: PLC0415

        http_auth = (username, password) if username and password else None
        self._client = opensearchpy.OpenSearch(
            hosts=[{"host": host, "port": port}],
            http_auth=http_auth,
            use_ssl=False,
            verify_certs=False,
        )
        self._index = index

    # ------------------------------------------------------------------
    # Index lifecycle
    # ------------------------------------------------------------------

    def index_exists(self) -> bool:
        """Return ``True`` if the index already exists in OpenSearch."""
        try:
            return bool(self._client.indices.exists(index=self._index))
        except Exception as exc:
            self._reraise(exc)

    def create_index(self, mapping: dict[str, Any]) -> None:
        """Create the index with the given *mapping*.

        Raises:
            RuntimeError: If OpenSearch does not acknowledge the creation.
        """
        try:
            response = self._client.indices.create(index=self._index, body=mapping)
        except Exception as exc:
            self._reraise(exc)

        if not response.get("acknowledged"):
            raise RuntimeError(
                f"Index creation not acknowledged by OpenSearch. Response: {response}"
            )
        logger.info("Created index '%s'", self._index)

    def delete_index(self) -> None:
        """Delete the index.

        Logs a warning if the index does not exist rather than raising.
        """
        try:
            self._client.indices.delete(index=self._index)
            logger.info("Deleted index '%s'", self._index)
        except Exception as exc:
            import opensearchpy  # noqa: PLC0415

            if isinstance(exc, opensearchpy.exceptions.NotFoundError):
                logger.warning("Index '%s' does not exist; skipping delete.", self._index)
            else:
                self._reraise(exc)

    # ------------------------------------------------------------------
    # Bulk indexing
    # ------------------------------------------------------------------

    def bulk_index(self, documents: list[dict[str, Any]]) -> dict[str, Any]:
        """Bulk-index *documents* into the configured index.

        Builds the NDJSON body with alternating ``{"index": ...}`` action lines
        and document body lines, then calls the OpenSearch bulk API.

        Args:
            documents: List of document dicts.  Each dict must have a
                       ``"chunk_id"`` key used as the document ``_id``.

        Returns:
            The raw OpenSearch bulk response dict.

        Raises:
            RuntimeError: If any documents failed to index.
        """
        if not documents:
            logger.info("No documents to index into '%s'.", self._index)
            return {"errors": False, "items": []}

        ndjson: list[dict[str, Any]] = []
        for doc in documents:
            ndjson.append({"index": {"_index": self._index, "_id": doc["chunk_id"]}})
            ndjson.append(doc)

        try:
            response: dict[str, Any] = self._client.bulk(body=ndjson)
        except Exception as exc:
            self._reraise(exc)

        if response.get("errors"):
            failed_items = [
                item
                for item in response.get("items", [])
                if item.get("index", {}).get("error")
            ]
            n_failed = len(failed_items)
            for item in failed_items:
                logger.error("Bulk indexing error for item: %s", item)
            raise RuntimeError(f"Bulk indexing completed with errors: {n_failed} failed")

        n = len(documents)
        logger.info("Indexed %d documents to index '%s'", n, self._index)
        return response  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _reraise(exc: Exception) -> None:
        """Re-raise *exc* as :class:`RuntimeError` if it is an OpenSearch exception."""
        import opensearchpy  # noqa: PLC0415

        if isinstance(exc, opensearchpy.exceptions.OpenSearchException):
            raise RuntimeError(f"OpenSearch error: {exc}") from exc
        raise exc
