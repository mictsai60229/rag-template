# Backend — Init Plan

## System
The Backend is the HTTP-facing component of the RAG template. It receives natural-language queries from client applications, embeds the query text, dispatches retrieval against OpenSearch using vector, keyword, or hybrid search, assembles a prompt from retrieved chunks, calls the configured LLM provider, and returns a structured answer with source attribution. It is implemented as a FastAPI application and is the only component that end-users or downstream applications interact with directly.

## Objective
Bootstrap the `systems/backend/` directory with a fully populated `CLAUDE.md` and a minimal FastAPI project scaffold — following the `backend-structure` skill's strict layering convention — so the coding-agent can safely proceed with the backend coding plan.

## Prerequisites
- [ ] `docs/prd.md` exists
- [ ] `docs/sad.md` exists

## Phase 1 — Scaffold & Document

**Objective:** Create the `systems/backend/` directory with a complete `CLAUDE.md` and minimal scaffold files sufficient to boot the application and pass a `/health` smoke test from a clean checkout.

**Files to create:**

- `systems/backend/CLAUDE.md` — full project documentation (all five required sections)
- `systems/backend/pyproject.toml` — package metadata, runtime and dev dependency declarations, and tool config (pytest, ruff, mypy)
- `systems/backend/.env.example` — every required env var with a placeholder value and an explanatory comment
- `systems/backend/Dockerfile` — multi-stage image; installs deps then copies `src/`; exposes port 8000
- `systems/backend/src/main.py` — FastAPI app factory; registers `api/router.py`; registers exception handlers from `exceptions/handlers.py`; no business logic
- `systems/backend/src/config.py` — `pydantic-settings` `Config` class; all required env vars declared as non-optional fields; crashes at startup if any required var is missing; exposed via `@lru_cache get_config()`
- `systems/backend/src/api/router.py` — top-level `APIRouter` that includes the health sub-router; other sub-routers added here in later plans
- `systems/backend/src/api/health.py` — `GET /health` returns `{"status": "ok"}`; no service call required at this stage
- `systems/backend/src/exceptions/domain.py` — base `AppError(Exception)` plus `NotFoundError`, `ExternalServiceError`, and `ConfigurationError`
- `systems/backend/src/exceptions/handlers.py` — registers `exception_handler` functions on the FastAPI app instance: `NotFoundError → 404`, `ExternalServiceError → 502`, `AppError → 500`; this is the only file that maps domain errors to HTTP status codes
- `systems/backend/tests/conftest.py` — shared `TestClient` (or `AsyncClient`) fixture that imports the app from `src.main`
- `systems/backend/tests/test_health.py` — smoke test: `GET /health` returns `200` and body `{"status": "ok"}`

**Files NOT created in Phase 1** (listed as `# planned` in the directory layout):

- `src/api/query.py` — POST /query route
- `src/schemas/query.py` — QueryRequest, QueryResponse
- `src/schemas/common.py` — ErrorResponse, shared types
- `src/services/query_service.py` — embed → retrieve → generate orchestration
- `src/providers/embedder.py` — Embedder ABC, OpenAIEmbedder, HFEmbedder
- `src/providers/opensearch_provider.py` — OpenSearch client wrapper
- `src/providers/llm_provider.py` — LLM ABC, OpenAIChatProvider
- `src/dependencies/query.py` — get_query_service(), get_embedder(), etc.

**Content required in `systems/backend/CLAUDE.md`:**

All five sections must be fully populated with no placeholders:

1. **Project Overview** — The Backend is a FastAPI (Python 3.11+) REST API that serves as the query-time component of the RAG template. It embeds incoming queries via a swappable `Embedder` provider, retrieves relevant chunks from OpenSearch (vector, keyword, or hybrid mode) via an `OpenSearchProvider`, assembles a prompt, calls a swappable `LLMProvider`, and returns a structured `QueryResponse` with source attribution. It depends on a running OpenSearch instance (populated by the Python Data Import pipeline) and on configured Embedding and LLM providers. Client applications call `POST /query` and receive a grounded answer plus ranked source chunk references. It is stateless with respect to documents — all retrieval state lives in OpenSearch.

2. **Directory Layout** — Annotated tree of the expected structure after full implementation:
   ```
   systems/backend/
   ├── src/
   │   ├── main.py                        # FastAPI app factory + bootstrap
   │   ├── config.py                      # pydantic-settings Config — single source of truth
   │   ├── api/
   │   │   ├── router.py                  # mounts all sub-routers
   │   │   ├── health.py                  # GET /health
   │   │   └── query.py                   # POST /query  (planned)
   │   ├── schemas/
   │   │   ├── query.py                   # QueryRequest, QueryResponse  (planned)
   │   │   └── common.py                  # ErrorResponse, shared types  (planned)
   │   ├── services/
   │   │   └── query_service.py           # orchestrates embed → retrieve → generate  (planned)
   │   ├── providers/
   │   │   ├── embedder.py                # Embedder ABC + OpenAIEmbedder + HFEmbedder  (planned)
   │   │   ├── opensearch_provider.py     # OpenSearch client wrapper  (planned)
   │   │   └── llm_provider.py            # LLM ABC + OpenAIChatProvider  (planned)
   │   ├── dependencies/
   │   │   └── query.py                   # get_query_service(), get_embedder()…  (planned)
   │   └── exceptions/
   │       ├── domain.py                  # AppError, NotFoundError, ExternalServiceError, ConfigurationError
   │       └── handlers.py               # maps domain errors → HTTP responses
   ├── tests/
   │   ├── conftest.py                    # shared TestClient / AsyncClient fixture
   │   ├── test_health.py                 # smoke test for GET /health
   │   ├── unit/                          # (planned) test services and providers in isolation
   │   └── integration/                   # (planned) full request → response through the app
   ├── .env.example
   ├── Dockerfile
   └── pyproject.toml
   ```

3. **Tech Stack** — Python 3.11+, FastAPI, uvicorn[standard], pydantic-settings, opensearch-py, openai SDK, sentence-transformers (local embedding, optional), langchain-core (prompt templates and LLM abstractions only — not the full LangChain stack), python-json-logger, pytest, pytest-asyncio, httpx (test client), pytest-cov, testcontainers (integration tests against a real OpenSearch container).

4. **How to Run & Test:**
   ```bash
   # From systems/backend/

   # Install all dependencies including dev extras
   pip install -e ".[dev]"

   # Copy env template and fill in real values
   cp .env.example .env

   # Run the API locally (development, with auto-reload)
   uvicorn src.main:app --reload --port 8000

   # Run all tests
   pytest tests/ -v --cov=src --cov-report=term-missing
   ```

5. **Conventions & Architecture Decisions** — The project follows the `backend-structure` skill's strict layering. Specific rules for this codebase:
   - `providers/` owns all external SDK calls. Never import `opensearch-py`, `openai`, or `sentence-transformers` directly in `services/` or `api/`. Every provider must define an abstract base class first; concrete implementations follow in the same file.
   - `services/` owns all business logic (embed → retrieve → generate orchestration). Services have no HTTP concerns: no `status_code`, no `Request` imports, no framework code.
   - `api/` routes are dumb: parse the request schema → call exactly one service method → return the response schema. No `if/else` business logic, no direct provider calls.
   - `dependencies/` wires dependency injection using FastAPI `Depends()`: `get_query_service()`, `get_embedder()`, `get_opensearch_provider()`, etc.
   - `exceptions/handlers.py` is the only file that maps domain errors to HTTP status codes. Services raise `AppError` subclasses; handlers convert them to `JSONResponse`.
   - `config.py` is the single source of truth for all settings. The `Config` object is injected everywhere via `get_config()`. Required fields have no default — missing vars crash startup. Secrets (`OPENAI_API_KEY`, `API_KEY`, `OPENSEARCH_PASSWORD`) are never logged or returned by the `/config` endpoint.
   - Structured JSON logging via `python-json-logger`. All log calls must include a `request_id` context var injected by a logging middleware (middleware is planned; the pattern must be respected from the start).
   - Type hints on all public functions and class methods. `mypy --strict` must pass.
   - No full LangChain stack. `langchain-core` only for prompt templates and LLM interface abstractions.
   - All tooling config (pytest, ruff, mypy) lives in `pyproject.toml` — no separate `.ini` or `.cfg` files.

**Tasks:**

1. Read `docs/sad.md` sections "Backend", "Data Models", "API Contracts", "Technology Stack", and "Security Architecture" to collect all facts needed for the CLAUDE.md five sections.
2. Create the `systems/backend/` directory hierarchy including `src/api/`, `src/exceptions/`, and `tests/`.
3. Write `systems/backend/CLAUDE.md` with all five sections fully populated from the documents above. No placeholder text, no `...`, no `TODO`.
4. Write `systems/backend/pyproject.toml` declaring:
   - Project name `rag-backend`, Python `>=3.11`
   - Runtime dependencies: `fastapi`, `uvicorn[standard]`, `pydantic-settings`, `opensearch-py`, `openai`, `langchain-core`, `python-json-logger`
   - Optional `[dev]` group: `pytest`, `pytest-asyncio`, `httpx`, `pytest-cov`, `ruff`, `mypy`
   - Tool config sections: `[tool.pytest.ini_options]` with `asyncio_mode = "auto"` and `testpaths = ["tests"]`; `[tool.ruff]` with `line-length = 100`; `[tool.mypy]` with `strict = true`
5. Write `systems/backend/src/config.py` with a `pydantic-settings` `Config` class. Required fields (no default, crashes at startup if missing): `OPENAI_API_KEY: str`, `OPENSEARCH_HOST: str`, `OPENSEARCH_PORT: int`, `OPENSEARCH_INDEX: str`, `EMBEDDING_PROVIDER: str`, `EMBEDDING_MODEL: str`, `LLM_MODEL: str`. Optional fields with defaults: `API_KEY: str = ""` (empty string disables auth check), `ENV: str = "dev"`, `TOP_K: int = 5`, `RETRIEVAL_MODE: str = "hybrid"`, `KEYWORD_BOOST: float = 0.3`, `EMBEDDING_BATCH_SIZE: int = 32`, `LOG_LEVEL: str = "INFO"`. Expose via `@lru_cache def get_config() -> Config`.
6. Write `systems/backend/src/exceptions/domain.py` defining `AppError(Exception)`, `NotFoundError(AppError)`, `ExternalServiceError(AppError)`, and `ConfigurationError(AppError)`.
7. Write `systems/backend/src/exceptions/handlers.py` that exports an `add_exception_handlers(app: FastAPI) -> None` function registering handlers: `NotFoundError → 404`, `ExternalServiceError → 502`, unhandled `AppError → 500`. Each handler returns a `JSONResponse` with `{"detail": str(exc)}`.
8. Write `systems/backend/src/api/health.py` with an `APIRouter` and a single `GET /health` route returning `{"status": "ok"}`.
9. Write `systems/backend/src/api/router.py` with a top-level `APIRouter` that includes the health router. Add a comment placeholder marking where the query router will be included in a later plan.
10. Write `systems/backend/src/main.py` as the app factory: instantiate `FastAPI`, include `api/router.py`, call `add_exception_handlers(app)` from `exceptions/handlers.py`. No inline route definitions in `main.py`.
11. Write `systems/backend/.env.example` with every required env var, a placeholder value, and a single-line comment explaining its purpose (see `.env.example` specification below).
12. Write `systems/backend/Dockerfile` using a two-stage build: `python:3.11-slim` builder stage installs deps from `pyproject.toml` via `pip install -e .`; final stage copies installed packages and `src/`; exposes port 8000; `CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]`.
13. Write `systems/backend/tests/conftest.py` with a `client` fixture that creates an `httpx.AsyncClient` (or `TestClient`) pointed at the app from `src.main`.
14. Write `systems/backend/tests/test_health.py` with one test that calls `GET /health` and asserts `status_code == 200` and `response.json() == {"status": "ok"}`.

**.env.example specification:**

```bash
# --- OpenSearch ---
OPENSEARCH_HOST=localhost          # Hostname or IP of the OpenSearch node
OPENSEARCH_PORT=9200               # OpenSearch REST API port
OPENSEARCH_INDEX=rag-chunks        # Name of the index that stores ChunkDocuments
# OPENSEARCH_USERNAME=admin        # Optional: basic-auth username (leave blank for no-auth dev)
# OPENSEARCH_PASSWORD=changeme     # Optional: basic-auth password

# --- Embedding ---
EMBEDDING_PROVIDER=openai          # openai | huggingface
EMBEDDING_MODEL=text-embedding-3-small  # Model name passed to the embedding provider
EMBEDDING_BATCH_SIZE=32            # Max texts per batch when calling the embedding API

# --- LLM ---
LLM_MODEL=gpt-4o-mini              # Chat completion model name

# --- OpenAI (used by both OpenAI embedder and OpenAI LLM provider) ---
OPENAI_API_KEY=sk-...              # Get from platform.openai.com — never commit a real value

# --- Retrieval ---
RETRIEVAL_MODE=hybrid              # vector | keyword | hybrid
TOP_K=5                            # Number of chunks to retrieve per query
KEYWORD_BOOST=0.3                  # Weight of the BM25 keyword clause in hybrid mode

# --- API Security ---
API_KEY=                           # Request auth header value (X-API-Key); leave blank to disable in dev
ENV=dev                            # dev | production — disables auth checks when set to dev

# --- Logging ---
LOG_LEVEL=INFO                     # DEBUG | INFO | WARNING | ERROR
```

**Testing:**

- **Manual check:** Read back `systems/backend/CLAUDE.md` and confirm all five sections are present with real content. Confirm no `...`, `TODO`, or `[placeholder]` text remains.
- **Import check:** From `systems/backend/`, run `pip install -e ".[dev]"` then `python -c "from src.main import app"`. Must complete without errors.
- **Smoke test:** Run `pytest tests/test_health.py -v`. The test must be collected and pass.

**Done criteria:**

- [ ] `systems/backend/CLAUDE.md` exists and contains all five required sections with real content and no placeholder text
- [ ] `systems/backend/pyproject.toml` exists and `pip install -e ".[dev]"` completes without error
- [ ] `systems/backend/src/main.py`, `src/config.py`, `src/api/router.py`, `src/api/health.py`, `src/exceptions/domain.py`, `src/exceptions/handlers.py` all exist
- [ ] `from src.main import app` executes without `ImportError`
- [ ] `systems/backend/tests/conftest.py` and `tests/test_health.py` exist
- [ ] `pytest tests/test_health.py -v` passes
- [ ] `systems/backend/.env.example` lists every env var consumed by `config.py` with a comment
- [ ] `systems/backend/Dockerfile` exists and `docker build` completes without error

---

## Verification

- Read: `systems/backend/CLAUDE.md` — all five sections present, conventions section explicitly names all five layer rules (`providers/`, `services/`, `api/`, `dependencies/`, `exceptions/handlers.py`)
- Run: `pip install -e ".[dev]" && pytest tests/test_health.py -v` from `systems/backend/` — must exit 0
- Run: `python -c "from src.main import app; print(app.routes)"` — must print the registered routes including `/health`
- Next step: `plans/backend-plan-1.md` (config + providers + query service) can now be executed
