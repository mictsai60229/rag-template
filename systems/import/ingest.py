"""CLI entry point for the RAG Data Import pipeline.

Usage:
    python ingest.py --source <path|url> [--config <path>]

The pipeline loads documents from the given source, cleans and normalises the
text, splits it into overlapping chunks, embeds the chunks in batches, and
writes the resulting ChunkDocument records to OpenSearch.
"""

import argparse
import sys


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


def main() -> None:
    parser = build_parser()
    parser.parse_args()
    print("Import pipeline not yet implemented.")
    sys.exit(0)


if __name__ == "__main__":
    main()
