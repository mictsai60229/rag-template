"""Smoke tests for the ingest.py CLI entry point."""

import subprocess
import sys
import tempfile
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

# Absolute path to ingest.py so the test works regardless of cwd.
INGEST_SCRIPT = Path(__file__).parent.parent / "ingest.py"


def test_help_exits_zero() -> None:
    """Invoking the CLI with --help must exit with code 0."""
    result = subprocess.run(
        [sys.executable, str(INGEST_SCRIPT), "--help"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"--help exited with code {result.returncode}.\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )


def test_main_runs_full_pipeline_with_mocked_components() -> None:
    """main() should call all five pipeline stages and not raise exceptions."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        # We need to patch sys.argv so argparse sees --source
        mock_args = MagicMock()
        mock_args.source = tmp_dir
        mock_args.config = None

        mock_settings = MagicMock()
        mock_settings.log_level = "INFO"
        mock_settings.opensearch_host = "localhost"
        mock_settings.opensearch_port = 9200
        mock_settings.opensearch_index = "rag-chunks"
        mock_settings.opensearch_username = None
        mock_settings.opensearch_password = None
        mock_settings.chunking_strategy = "recursive"
        mock_settings.chunk_size = 512
        mock_settings.chunk_overlap = 64
        mock_settings.embedding_provider = "openai"
        mock_settings.embedding_model = "text-embedding-3-small"
        mock_settings.embedding_batch_size = 32
        mock_settings.embedding_dimension = 1536

        mock_loader = MagicMock()
        mock_loader.load.return_value = []

        mock_cleaner = MagicMock()
        mock_chunker = MagicMock()
        mock_embedder = MagicMock()
        mock_embedder.embed_batch.return_value = []

        mock_provider = MagicMock()
        mock_indexer = MagicMock()
        mock_indexer.index_chunks.return_value = 0

        with (
            patch("ingest.build_parser") as mock_build_parser,
            patch("ingest.get_settings", return_value=mock_settings),
            patch("ingest.configure_logging"),
            patch("ingest.DocumentLoader", return_value=mock_loader),
            patch("ingest.TextCleaner", return_value=mock_cleaner),
            patch("ingest.Chunker", return_value=mock_chunker),
            patch("ingest.get_embedder", return_value=mock_embedder),
            patch("ingest.OpenSearchProvider", return_value=mock_provider),
            patch("ingest.Indexer", return_value=mock_indexer),
        ):
            mock_build_parser.return_value.parse_args.return_value = mock_args

            # Import and run main — should not raise
            import ingest
            ingest.main()

        # ensure_index was called on the indexer
        mock_indexer.ensure_index.assert_called_once()
