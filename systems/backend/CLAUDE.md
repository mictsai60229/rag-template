# Backend — CLAUDE.md

## 1. Project Overview

The Backend is a FastAPI (Python 3.11+) REST API that serves as the query-time component of the RAG template. It embeds incoming queries via a swappable `Embedder` provider, retrieves relevant chunks from OpenSearch (vector, keyword, or hybrid mode) via an `OpenSearchProvider`, assembles a prompt, calls a swappable `LLMProvider`, and returns a structured `QueryResponse` with source attribution.

It depends on a running OpenSearch instance (populated by the Python Data Import pipeline) and on configured Embedding and LLM providers. Client applications call `POST /query` and receive a grounded answer plus ranked source chunk references. It is stateless with respect to documents — all retrieval state lives in OpenSearch.

### Endpoints

- `POST /query` — accepts a `QueryRequest` (natural-language question + optional overrides); returns `QueryResponse` with answer, sources, retrieval mode, and latency.
- `GET /health` — liveness check; returns `{"status": "ok"}`.
- `GET /config` — returns active (non-secret) config values for introspection.

### External Dependencies

- **OpenSearch 2.x** — sole persistence layer for chunk vectors and BM25 index. Required at startup.
- **Embedding Provider** — OpenAI Embeddings API (default) or local HuggingFace `sentence-transformers`. Required at query time.
- **LLM Provider** — OpenAI Chat Completions API (default). Required at query time.

---

## 2. Directory Layout

Annotated tree of the expected structure after full implementation:

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

---

## 3. Tech Stack

| Layer | Technology | Notes |
|-------|------------|-------|
| API framework | FastAPI (Python 3.11+) | Async-native, automatic OpenAPI docs |
| Server | uvicorn[standard] | ASGI server with auto-reload in dev |
| Config | pydantic-settings | Validates env vars at startup; crashes if required vars are missing |
| Vector store client | opensearch-py | Connects to OpenSearch 2.x cluster |
| LLM provider | openai SDK | Chat completions API; abstracted behind `LLMProvider` ABC |
| Prompt / LLM abstractions | langchain-core | Used for prompt templates and LLM interface only; NOT the full LangChain stack |
| Embedding — cloud | openai SDK | `text-embedding-3-small` or `-large` via `OpenAIEmbedder` |
| Embedding — local | sentence-transformers | HuggingFace local models via `HFEmbedder`; optional extra |
| Logging | python-json-logger | Structured JSON logging; `request_id` injected by logging middleware |
| Testing | pytest, pytest-asyncio, httpx, pytest-cov | `AsyncClient` for async test client; `testcontainers` for integration tests |
| Linting | ruff | Line length 100 |
| Type checking | mypy (strict) | All public functions and class methods must be typed |

---

## 4. How to Run and Test

```bash
# From systems/backend/

# Pin Python version (uses pyenv)
zsh -i -c 'pyenv local 3.11.9'

# Create venv and install all dependencies including dev extras
zsh -i -c 'uv venv --python $(pyenv which python) && uv pip install -e ".[dev]"'

# Copy env template and fill in real values
cp .env.example .env

# Run the API locally (development, with auto-reload)
zsh -i -c 'uv run uvicorn src.main:app --reload --port 8000'

# Run all tests
zsh -i -c 'uv run pytest tests/ -v --cov=src --cov-report=term-missing'
```

### Import check (CI smoke test)

```bash
# From systems/backend/ with .env populated
zsh -i -c 'uv run python -c "from src.main import app; print(app.routes)"'
```

### Docker build

```bash
# From systems/backend/
docker build -t rag-backend .
docker run --env-file .env -p 8000:8000 rag-backend
```

---

## 5. Conventions and Architecture Decisions

This project follows the `backend-structure` skill's strict layering convention. The layer rules are:

### Layer Rules

1. **`providers/` owns all external SDK calls.** Never import `opensearch-py`, `openai`, or `sentence-transformers` directly in `services/` or `api/`. Every provider must define an abstract base class (ABC) first; concrete implementations follow in the same file.

2. **`services/` owns all business logic** (embed → retrieve → generate orchestration). Services have no HTTP concerns: no `status_code`, no `Request` imports, no framework code. Services raise `AppError` subclasses; they never return HTTP responses.

3. **`api/` routes are dumb:** parse the request schema → call exactly one service method → return the response schema. No `if/else` business logic in routes, no direct provider calls.

4. **`dependencies/` wires dependency injection** using FastAPI `Depends()`: `get_query_service()`, `get_embedder()`, `get_opensearch_provider()`, etc. This is the only place where providers and services are instantiated for injection.

5. **`exceptions/handlers.py` is the only file that maps domain errors to HTTP status codes.** Services raise `AppError` subclasses; handlers convert them to `JSONResponse`. No other file may import `HTTPException` for domain-error mapping.

### Config Rules

- `config.py` is the single source of truth for all settings. The `Config` object is injected everywhere via `get_config()`.
- Required fields have no default — a missing env var crashes startup with a clear `ValidationError`.
- Secrets (`OPENAI_API_KEY`, `API_KEY`, `OPENSEARCH_PASSWORD`) are never logged or returned by any endpoint.

### Logging Rules

- Structured JSON logging via `python-json-logger`. All log calls must include a `request_id` context variable injected by a logging middleware (middleware is planned; the pattern must be respected from the start).
- Log level is controlled by `LOG_LEVEL` config field.

### Type and Style Rules

- Type hints on all public functions and class methods. `mypy --strict` must pass.
- Line length 100 (`ruff`).
- No full LangChain stack. `langchain-core` only for prompt templates and LLM interface abstractions.
- All tooling config (pytest, ruff, mypy) lives in `pyproject.toml` — no separate `.ini` or `.cfg` files.

### Security Rules

- The Backend API supports an `X-API-Key` header for request authentication. The key is loaded from the `API_KEY` env var.
- In development mode (`ENV=dev`), authentication is disabled.
- OpenSearch must not be exposed on a public network interface.
- The `/config` endpoint must redact all secret fields before returning the response.
