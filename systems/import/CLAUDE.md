# Python Data Import — CLAUDE.md

## 1. Project Overview

The Python Data Import pipeline is a Python 3.11+ CLI tool (`ingest.py`) that populates OpenSearch with document content for use by the RAG Backend. It reads raw documents from files (PDF, TXT, Markdown, DOCX), URLs, or directories; cleans and normalises the text; splits it into overlapping chunks using a configurable strategy (fixed-size, recursive, sentence-level, or semantic); embeds the chunks in batches using OpenAI or a local HuggingFace model; and writes the resulting `ChunkDocument` records to OpenSearch via the bulk API. It is run as a one-off command or a scheduled Kubernetes Job and shares its config schema and `embedder.py` interface with the Backend.

### Data Flow

1. **Load** — `loader.py` reads raw bytes from any supported source and returns `RawDocument` objects.
2. **Clean** — `cleaner.py` strips headers, footers, excess whitespace, and normalises encoding.
3. **Chunk** — `chunker.py` splits cleaned text into overlapping chunks using the configured strategy and attaches metadata.
4. **Embed** — `embedder.py` calls the configured embedding provider in configurable batch sizes.
5. **Index** — `indexer.py` writes `ChunkDocument` objects to OpenSearch via the bulk API, creating the index with the correct k-NN mapping if it does not exist.

### External Dependencies

- **OpenSearch 2.x** — sole persistence layer for chunk vectors and BM25 index. Required at run time.
- **Embedding Provider** — OpenAI Embeddings API (default) or local HuggingFace `sentence-transformers`. Required at run time.

---

## 2. Directory Layout

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

---

## 3. Tech Stack

| Layer | Technology | Notes |
|-------|------------|-------|
| Runtime | Python 3.11+ | Matches Backend language |
| Config | pydantic-settings | Validates env vars at startup; crashes if required vars are missing |
| Vector store client | opensearch-py | Connects to OpenSearch 2.x; bulk API for indexing |
| Embedding — cloud | openai SDK | `text-embedding-3-small` or `-large` via `OpenAIEmbedder` |
| Embedding — local | sentence-transformers | HuggingFace local models via `HFEmbedder`; zero-cost, privacy-preserving |
| PDF loading | PyMuPDF (`pymupdf`) | Extracts text with page numbers from PDF files |
| DOCX loading | python-docx | Extracts text from Microsoft Word `.docx` files |
| URL loading | BeautifulSoup4 + httpx | Fetches and parses HTML content from URLs |
| Chunking (recursive) | langchain-text-splitters | `RecursiveCharacterTextSplitter` for recursive character chunking |
| Chunking (semantic) | langchain-core | `SemanticChunker` for embedding-similarity chunking |
| Logging | python-json-logger | Structured JSON logging with phase-level latency |
| Testing | pytest, pytest-asyncio, pytest-cov, testcontainers | Integration tests spin up a real OpenSearch container |

---

## 4. How to Run and Test

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

### Docker build

```bash
# From systems/import/
docker build -t rag-import .
docker run --env-file .env rag-import --source /data/docs/
```

---

## 5. Conventions and Architecture Decisions

### Module Independence

All six sub-modules (`loader`, `cleaner`, `chunker`, `embedder`, `indexer`) are independent and testable in isolation. No sub-module may import from another sub-module directly — they communicate only through data model objects (`RawDocument`, `Chunk`, `ChunkDocument`).

### Shared Embedder Interface

The `embedder.py` interface (`embed_text(str) -> list[float]`, `embed_batch(list[str]) -> list[list[float]]`) is the same abstract class used in the Backend — do not diverge. Both the Backend and the Import pipeline must use the same embedding model and dimension; divergence causes silent k-NN dimension mismatches that corrupt retrieval results.

### Chunking Strategy Pattern

The `chunker.py` uses the strategy pattern; the active strategy is selected by the `CHUNKING_STRATEGY` config key. Valid values: `fixed`, `recursive`, `sentence`, `semantic`. Each strategy implements the same `chunk(text: str, metadata: dict) -> list[Chunk]` interface.

### Chunk Metadata

Every chunk carries the following metadata fields, all required:
- `source` — file path or URL from which the parent document was loaded
- `page_number` — page number (integer, nullable; set only for PDF sources)
- `chunk_index` — zero-based position of this chunk within the parent document
- `doc_type` — one of `pdf`, `txt`, `md`, `docx`, `url`
- `ingested_at` — UTC timestamp of ingestion (ISO 8601 format)

### OpenSearch Index Mapping

The `indexer.py` must create the index with the correct k-NN mapping if it does not exist. Reference mapping from SAD Appendix A:

```json
{
  "settings": {
    "index.knn": true,
    "number_of_shards": 1,
    "number_of_replicas": 1
  },
  "mappings": {
    "properties": {
      "chunk_id":    { "type": "keyword" },
      "doc_id":      { "type": "keyword" },
      "content":     { "type": "text", "analyzer": "standard" },
      "embedding":   { "type": "knn_vector", "dimension": 1536,
                       "method": { "name": "hnsw", "space_type": "cosinesimil",
                                   "engine": "nmslib",
                                   "parameters": { "ef_construction": 128, "m": 16 } } },
      "source":      { "type": "keyword" },
      "doc_type":    { "type": "keyword" },
      "page_number": { "type": "integer" },
      "chunk_index": { "type": "integer" },
      "ingested_at": { "type": "date" }
    }
  }
}
```

The `dimension` value must match the configured embedding model output size (`EMBEDDING_DIMENSION` config key). The index must be recreated if the dimension changes.

### Batch Embedding

The `embedder.py` accepts `embed_batch(list[str])` with configurable `EMBEDDING_BATCH_SIZE`. If rate limit errors occur, the embedder must implement exponential backoff and retry before propagating the error.

### Document Size Validation

Document size must be validated before bulk submission to prevent OOM in OpenSearch. The `indexer.py` must check individual document size and log a warning (and skip) any document exceeding the configured limit.

### Config Rules

- `config.py` is the single source of truth for all settings. The `Settings` object is loaded from environment variables at startup.
- Required fields have no default — a missing env var causes a clear `ValidationError` at startup.
- Secrets (`OPENAI_API_KEY`, `OPENSEARCH_PASSWORD`) are never logged.

### Logging Rules

- Structured JSON logging via `python-json-logger`. Phase-level latency must be logged for each step (load, clean, chunk, embed, index).
- Log level is controlled by the `LOG_LEVEL` config field (not in the required env vars but can be added as needed).

### Security Rules

- No secrets in committed files. The `.env.example` contains only placeholder values.
- All secrets are injected as environment variables at run time.
- OpenSearch credentials (`OPENSEARCH_USER`, `OPENSEARCH_PASSWORD`) are optional and used only when provided.
