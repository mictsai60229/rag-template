"""Indexer for the RAG Data Import pipeline.

Reads the reference mapping from ``systems/opensearch/mappings/rag_index.json``,
patches in the configured embedding dimension, creates the OpenSearch index if it
does not already exist, validates each chunk document size before submission, and
bulk-writes :class:`~src.models.Chunk` objects via :class:`OpenSearchProvider`.

The only module that imports opensearch-py is
:mod:`src.providers.opensearch_provider`.  This module never does so directly.
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any

from src.models import Chunk
from src.providers.opensearch_provider import OpenSearchProvider

logger = logging.getLogger(__name__)

# Maximum allowed size (in bytes) for a single document sent to OpenSearch.
MAX_DOCUMENT_BYTES = 10 * 1024 * 1024  # 10 MB


class Indexer:
    """Manages index lifecycle and bulk-writes :class:`~src.models.Chunk` objects.

    Args:
        provider:     An :class:`OpenSearchProvider` instance.
        settings:     A :class:`~src.config.Settings` instance; the
                      ``embedding_dimension`` field is used to patch the mapping.
        mapping_path: Absolute path to ``rag_index.json``.
    """

    def __init__(
        self,
        provider: OpenSearchProvider,
        settings: object,
        index_name: str
    ) -> None:
        self._provider = provider
        self._settings = settings
        self.index_name = index_name

    # ------------------------------------------------------------------
    # Index lifecycle
    # ------------------------------------------------------------------

    def ensure_index(self) -> None:
        """Create the index if it does not already exist.

        Logs the outcome at INFO level in both cases.
        """
        if not self._provider.index_exists():
            self._provider.create_index(self.index_name)
            logger.info("Created index '%s'", self.index_name)
        else:
            logger.info("Index '%s' already exists, skipping creation", self.index_name)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate_document_size(self, doc: dict[str, Any]) -> bool:
        """Return ``True`` if *doc* is within the size limit.

        If the document exceeds :data:`MAX_DOCUMENT_BYTES` a WARNING is logged
        and ``False`` is returned.
        """
        size = len(json.dumps(doc).encode("utf-8"))
        if size > MAX_DOCUMENT_BYTES:
            logger.warning(
                "Document '%s' exceeds maximum size (%d bytes); skipping.",
                doc.get("chunk_id", "<unknown>"),
                size,
            )
            return False
        return True

    # ------------------------------------------------------------------
    # Bulk indexing
    # ------------------------------------------------------------------

    def index_chunks(
        self,
        chunks: list[Chunk],
        embeddings: list[list[float]],
    ) -> int:
        """Pair each :class:`~src.models.Chunk` with its embedding, build a
        :class:`ChunkDocument` dict, and bulk-index valid documents.

        Args:
            chunks:     Chunk objects produced by :class:`~src.chunker.Chunker`.
            embeddings: Parallel list of embedding vectors; must be the same
                        length as *chunks*.

        Returns:
            The number of documents successfully indexed.
        """
        valid_docs: list[dict[str, Any]] = []

        for chunk, embedding in zip(chunks, embeddings):
            ingested_at: str
            if isinstance(chunk.ingested_at, datetime):
                # Ensure UTC and format as ISO 8601.
                ts = chunk.ingested_at
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                ingested_at = ts.isoformat()
            else:
                ingested_at = str(chunk.ingested_at)

            doc: dict[str, Any] = {
                "chunk_id": chunk.chunk_id,
                "doc_id": chunk.doc_id,
                "content": chunk.content,
                "embedding": embedding,
                "source": chunk.source,
                "doc_type": chunk.doc_type,
                "page_number": chunk.page_number,
                "chunk_index": chunk.chunk_index,
                "ingested_at": ingested_at,
            }

            if self._validate_document_size(doc):
                valid_docs.append(doc)

        if valid_docs:
            self._provider.bulk_index(valid_docs)

        n = len(valid_docs)
        logger.info("Indexed %d chunks", n)
        return n
