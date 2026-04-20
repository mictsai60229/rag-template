# Python Data Import — Init Plan

## System
The Python Data Import pipeline is the offline ingestion component of the RAG template. It is run by developers or scheduled jobs to populate or refresh OpenSearch with document content. It owns the full ingestion lifecycle: loading raw bytes from files, URLs, and directories; cleaning and normalising text; splitting text into overlapping chunks with configurable strategies; embedding chunks in batches; and writing the resulting `ChunkDocument` objects to OpenSearch via the bulk API. It exposes a CLI entry point (`python ingest.py`) and has no HTTP interface.

## Objective
Bootstrap the `systems/import/` directory with a fully populated `CLAUDE.md` and a minimal Python CLI scaffold so the coding-agent can safely proceed with the import pipeline coding plan.

## Prerequisites
- [ ] `docs/prd.md` exists
- [ ] `docs/sad.md` exists

## Phase 1 — Scaffold & Document

**Objective:** Create the `systems/import/` directory with a complete `CLAUDE.md` and minimal scaffold files sufficient to invoke the CLI entry point and run the test suite from a clean checkout.

**Files to create:**
- `systems/import/CLAUDE.md` — full project documentation (all five required sections)
- `systems/import/pyproject.toml` — package metadata and dependency declarations with minimum required dependencies
- `systems/import/ingest.py` — minimal CLI entry point that parses `--config` and `--source` arguments and prints a "not yet implemented" message
- `systems/import/src/__init__.py` — marks `src` as a Python package
- `systems/import/src/config.py` — minimal pydantic-settings `Config` class stub with required field declarations
- `systems/import/tests/__init__.py` — marks `tests` as a Python package
- `systems/import/tests/test_cli.py` — single smoke test that invokes the CLI with `--help` and confirms it exits with code 0
- `systems/import/.env.example` — template for required environment variables (no real secrets)
- `systems/import/Dockerfile` — Docker image for running the ingestion pipeline as a container or Kubernetes Job

**Content required in `systems/import/CLAUDE.md`:**

All five sections must be fully populated with no placeholders:

1. **Project Overview** — The Python Data Import pipeline is a Python 3.11+ CLI tool (`ingest.py`) that populates OpenSearch with document content for use by the RAG Backend. It reads raw documents from files (PDF, TXT, Markdown, DOCX), URLs, or directories; cleans and normalises the text; splits it into overlapping chunks using a configurable strategy (fixed-size, recursive, sentence-level, or semantic); embeds the chunks in batches using OpenAI or a local HuggingFace model; and writes the resulting `ChunkDocument` records to OpenSearch via the bulk API. It is run as a one-off command or a scheduled Kubernetes Job and shares its config schema and `embedder.py` interface with the Backend.

2. **Directory Layout** — Annotated tree showing:
   ```
   systems/import/
   ├── ingest.py            # CLI entry point
   ├── src/
   │   ├── __init__.py
   │   ├── config.py        # pydantic-settings Config object (shared schema with backend)
   │   ├── loader.py        # RawDocument loaders: PDF, TXT, MD, DOCX, URL, directory  # planned
   │   ├── cleaner.py       # Text normalisation and cleaning  # planned
   │   ├── chunker.py       # Chunking strategies: fixed-size, recursive, sentence, semantic  # planned
   │   ├── embedder.py      # embed_text() + embed_batch() interface  # planned
   │   └── indexer.py       # OpenSearch bulk indexer + index creation  # planned
   ├── tests/
   │   ├── __init__.py
   │   ├── test_cli.py
   │   ├── unit/            # planned
   │   └── integration/     # planned
   ├── .env.example
   ├── Dockerfile
   └── pyproject.toml
   ```

3. **Tech Stack** — Python 3.11+, pydantic-settings, opensearch-py, openai SDK, sentence-transformers (local embedding), PyMuPDF (`pymupdf`) for PDF loading, python-docx for DOCX loading, BeautifulSoup4 + httpx for URL loading, langchain-core (SemanticChunker), langchain-text-splitters (RecursiveCharacterTextSplitter), python-json-logger, pytest, pytest-asyncio, testcontainers.

4. **How to Run & Test:**
   ```bash
   # Install dependencies (from systems/import/)
   pip install -e ".[dev]"

   # Copy env template and fill in real values
   cp .env.example .env

   # Run the ingestion CLI (example: ingest a directory)
   python ingest.py --source ./sample_docs/

   # Run all tests
   pytest tests/ -v --cov=src --cov-report=term-missing
   ```

5. **Conventions & Architecture Decisions** — All six sub-modules (`loader`, `cleaner`, `chunker`, `embedder`, `indexer`) are independent and testable in isolation. The `embedder.py` interface (`embed_text(str) -> list[float]`, `embed_batch(list[str]) -> list[list[float]]`) is the same abstract class used in the Backend — do not diverge. The `chunker.py` uses the strategy pattern; the active strategy is selected by the `CHUNKING_STRATEGY` config key. Every chunk carries metadata: `source`, `page_number`, `chunk_index`, `doc_type`, `ingested_at` (UTC). The `indexer.py` uses the OpenSearch bulk API; it must create the index with the correct k-NN mapping if it does not exist (reference mapping in SAD Appendix A). Batch size for embedding calls is configurable (`EMBEDDING_BATCH_SIZE`). Document size is validated before bulk submission to prevent OOM in OpenSearch. Structured JSON logging. No secrets in committed files.

**Tasks:**
1. Read `docs/sad.md` sections "Python Data Import", "Data Models", "OpenSearch Index API", "Ingest Flow", "Technology Stack", and Appendix A (index mapping) to gather all facts needed for the CLAUDE.md.
2. Create the `systems/import/` directory hierarchy.
3. Write `systems/import/CLAUDE.md` with all five sections fully populated.
4. Write `systems/import/pyproject.toml` declaring the project name `rag-import`, Python `>=3.11`, and minimum runtime dependencies: `pydantic-settings`, `opensearch-py`, `openai`, `pymupdf`, `python-docx`, `beautifulsoup4`, `httpx`, `langchain-core`, `langchain-text-splitters`, `sentence-transformers`, `python-json-logger`. Declare a `[dev]` optional group with `pytest`, `pytest-asyncio`, `pytest-cov`, `testcontainers`.
5. Write `systems/import/ingest.py` as a minimal CLI using `argparse` with `--config` (optional, path to YAML config), `--source` (required, path or URL), and `--help`. On invocation without `--help`, print `"Import pipeline not yet implemented."` and exit 0.
6. Write `systems/import/src/__init__.py` (empty) and `systems/import/src/config.py` with a minimal `pydantic-settings` `Settings` class that declares the fields listed in `.env.example` with appropriate types and defaults.
7. Write `systems/import/tests/__init__.py` (empty) and `systems/import/tests/test_cli.py` with a `subprocess.run` test that calls `python ingest.py --help` and asserts `returncode == 0`.
8. Write `systems/import/.env.example` listing all required env vars: `OPENAI_API_KEY`, `OPENSEARCH_HOST`, `OPENSEARCH_PORT`, `OPENSEARCH_INDEX`, `EMBEDDING_PROVIDER`, `EMBEDDING_MODEL`, `EMBEDDING_BATCH_SIZE`, `CHUNKING_STRATEGY`, `CHUNK_SIZE`, `CHUNK_OVERLAP`, `ENV`.
9. Write `systems/import/Dockerfile` using `python:3.11-slim` base, copy `pyproject.toml`, install deps, copy `src/` and `ingest.py`, set `ENTRYPOINT ["python", "ingest.py"]`.

**Testing:**
- **Manual check:** Read back `systems/import/CLAUDE.md` and verify all five sections are present with real content (no `...` or placeholder text).
- **Scaffold check:** From `systems/import/`, run `pip install -e ".[dev]"` then `pytest tests/test_cli.py -v`. The test must be collected and pass.

**Done criteria:**
- [ ] `systems/import/CLAUDE.md` exists and contains all five required sections with real content
- [ ] No placeholder text (`...`, `TODO`, `[System Name]`) remains in the CLAUDE.md
- [ ] `systems/import/pyproject.toml` exists and `pip install -e ".[dev]"` completes without error
- [ ] `systems/import/ingest.py` exists and `python ingest.py --help` exits with code 0
- [ ] `systems/import/tests/test_cli.py` exists and is collected by pytest

---

## Verification

- Read: `systems/import/CLAUDE.md` — all five sections present with real content
- Run: `pip install -e ".[dev]" && pytest tests/test_cli.py -v` from `systems/import/`
- Next step: `docs/plans/import-plan-1.md` (loader + cleaner + chunker) can now be executed
