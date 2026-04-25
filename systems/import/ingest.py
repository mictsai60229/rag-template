"""CLI entry point for the RAG Data Import pipeline.

Usage:
    python ingest.py --source <path|url> [--config <path>]

The pipeline loads documents from the given source, cleans and normalises the
text, splits it into overlapping chunks, embeds the chunks in batches, and
writes the resulting ChunkDocument records to OpenSearch.
"""

import argparse
import logging
from pathlib import Path

from src.chunker import Chunker
from src.cleaner import TextCleaner
from src.config import Settings, get_settings
from src.embedder import get_embedder
from src.indexer import Indexer
from src.loader import DocumentLoader
from src.models import Chunk
from src.providers.opensearch_provider import OpenSearchProvider

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ingest",
        description=(
            "RAG Data Import pipeline — loads, cleans, chunks, embeds, and indexes documents "
            "into OpenSearch."
        ),
    )
    parser.add_argument(
        "--config",
        metavar="PATH",
        default=None,
        help="Path to a YAML config file. Environment variables take precedence over file values.",
    )
    parser.add_argument(
        "--source",
        metavar="PATH_OR_URL",
        required=True,
        help=(
            "Path to a file, directory, or URL to ingest. "
            "Supported file types: PDF, TXT, Markdown (.md), DOCX."
        ),
    )
    return parser


def configure_logging(settings: Settings) -> None:
    """Configure structured JSON logging from *settings*.

    Uses ``python-json-logger`` to emit one JSON object per log record.
    The log level is taken from ``settings.log_level`` (default ``"INFO"``).
    """
    from pythonjsonlogger import jsonlogger  # noqa: PLC0415

    log_level = getattr(settings, "log_level", "INFO").upper()
    handler = logging.StreamHandler()
    formatter = jsonlogger.JsonFormatter(
        fmt="%(asctime)s %(name)s %(levelname)s %(message)s"
    )
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(log_level)

def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    settings = get_settings()
    configure_logging(settings)

    loader = DocumentLoader()
    cleaner = TextCleaner()
    chunker = Chunker(settings)
    embedder = get_embedder(settings)
    opensearch_provider = OpenSearchProvider(
        host=settings.opensearch_host,
        port=settings.opensearch_port,
        index=settings.opensearch_index,
        username=settings.opensearch_username,
        password=settings.opensearch_password,
    )
    # mapping_path = Path(__file__).parent.parent / "opensearch" / "mappings" / "rag_index.json"
    indexer = Indexer(opensearch_provider, settings, index_name=settings.opensearch_index)

    indexer.ensure_index()

    logger.info("Loading documents from %s", args.source)
    raw_docs = loader.load(args.source)
    logger.info("Loaded %d documents", len(raw_docs))

    all_chunks: list[Chunk] = []
    for doc in raw_docs:
        cleaned = cleaner.clean_document(doc)
        chunks = chunker.chunk(cleaned.content, cleaned.source, cleaned.doc_id, cleaned.doc_type)
        all_chunks.extend(chunks)
    logger.info("Created %d chunks from %d documents", len(all_chunks), len(raw_docs))

    texts = [c.content for c in all_chunks]
    embeddings = embedder.embed_batch(texts)
    logger.info("Embedded %d chunks", len(embeddings))

    n_indexed = indexer.index_chunks(all_chunks, embeddings)
    logger.info("Ingestion complete: %d chunks indexed", n_indexed)


if __name__ == "__main__":
    main()
