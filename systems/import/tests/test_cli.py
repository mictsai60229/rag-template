"""Smoke tests for the ingest.py CLI entry point."""

import subprocess
import sys
from pathlib import Path

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
