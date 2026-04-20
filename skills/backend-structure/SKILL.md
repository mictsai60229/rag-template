---
name: backend-structure
description: >
  Opinionated backend project structure skill for production-grade APIs and services.
  Use this skill whenever a user is setting up, scaffolding, refactoring, or asking about
  how to structure a backend project — regardless of framework or language. Trigger on phrases
  like "how should I structure my backend", "where do I put my business logic", "how do I
  organise my routes", "should I have a service layer", "how do I separate concerns",
  "what folder structure should I use", or any question about layering, project layout,
  naming conventions, or where a specific piece of code belongs. Also trigger when the user
  asks about patterns like: service layer, repository pattern, provider/adapter pattern,
  request/response models, dependency injection, config management, error handling strategy,
  or testing structure — even if they don't mention a specific framework.
---

# Backend Project Structure Skill

An opinionated, framework-agnostic guide for structuring production-grade backend projects.
The patterns here apply whether you're using FastAPI, Express, NestJS, Django, Rails, Go, or
anything else — the layer names and file names may change, the principles don't.

---

## The Core Principle: Strict Layering

Every backend, regardless of size or framework, benefits from the same layered structure:

```
Request → api/ → services/ → providers/ → Response
                    ↕
              models/ / db/
```

Each layer has **one job** and only talks to the layer directly below it.
No layer skips another. No layer reaches upward.

---

## Canonical Directory Structure

```
project/
├── src/
│   ├── main.{ext}               # App entry point + bootstrap
│   ├── config.{ext}             # Config / env loading — single source of truth
│   │
│   ├── api/                     # HTTP layer — routes only, no business logic
│   │   ├── router.{ext}         # Mounts / registers all sub-routers
│   │   ├── health.{ext}
│   │   ├── {feature}.{ext}      # One file per resource/feature
│   │   └── middlewares/         # Auth, logging, rate limiting, CORS
│   │
│   ├── schemas/                 # Request & response shapes, per endpoint
│   │   ├── {feature}.{ext}      # {Feature}Request, {Feature}Response
│   │   └── common.{ext}         # Shared types: Pagination, ErrorResponse…
│   │
│   ├── services/                # Business logic — orchestrates providers + db
│   │   └── {feature}_service.{ext}
│   │
│   ├── providers/               # External service wrappers (APIs, SDKs, queues)
│   │   └── {service}.{ext}      # One file per external dependency
│   │
│   ├── models/                  # DB / ORM entity definitions
│   │   └── {entity}.{ext}
│   │
│   ├── db/                      # DB connection, session factory, query helpers
│   │   └── session.{ext}
│   │
│   ├── repositories/            # (optional) Data access layer — DB queries
│   │   └── {entity}_repo.{ext}  # Use when services are getting DB-query-heavy
│   │
│   ├── dependencies/            # DI factories (framework-specific)
│   │   └── {feature}.{ext}      # get_{service}(), get_{repo}()…
│   │
│   ├── middleware/              # Cross-cutting HTTP concerns
│   │   └── logging.{ext}        # Request ID, structured logs
│   │
│   └── exceptions/              # Domain errors + HTTP error mapping
│       ├── domain.{ext}         # NotFoundError, ValidationError…
│       └── handlers.{ext}       # Maps domain errors → HTTP responses
│
├── tests/
│   ├── conftest.{ext}           # Shared fixtures, test app/client setup
│   ├── unit/                    # Test services and providers in isolation
│   └── integration/             # Test full request → response through the app
│
├── migrations/                  # DB schema migrations
│   └── versions/
│
├── .env
├── .env.example                 # Template with all required keys, no values
├── Dockerfile
├── docker-compose.yml           # Local dev: app + DB + any dependencies
└── {package_manifest}           # pyproject.toml / package.json / go.mod…
```

---

## Layer Responsibilities

| Layer | Owns | Never touches |
|---|---|---|
| `api/` | HTTP verbs, status codes, auth guards, request parsing | Business logic, DB |
| `schemas/` | Input validation, output serialisation, field defaults | DB models, services |
| `services/` | Business rules, orchestration, domain exceptions | HTTP, framework code |
| `providers/` | External SDK calls, retry logic, circuit breaking | Services, HTTP |
| `repositories/` | DB queries, transactions | Business logic, HTTP |
| `models/` | Table/column definitions, DB-level constraints | HTTP, API schemas |
| `dependencies/` | DI wiring, object construction | Business logic |
| `middleware/` | Cross-cutting HTTP concerns (logs, auth, tracing) | Business logic |
| `exceptions/` | Domain error types + HTTP error formatting | Business logic |

---

## Layer-by-Layer Guide

### api/ — The HTTP Boundary

Routes are **dumb**. They do three things only:
1. Parse and validate the incoming request (via schemas)
2. Call exactly one service method
3. Return the response schema

```python
# Python / FastAPI example
@router.post("/search", response_model=SearchResponse)
async def search(req: SearchRequest, svc: SearchService = Depends(get_search_service)):
    return await svc.search(req)
```

```typescript
// TypeScript / Express example
router.post('/search', validate(SearchRequest), async (req, res) => {
  const result = await searchService.search(req.body);
  res.json(result);
});
```

**Red flags in api/**: `if/else` business logic, direct DB calls, `try/catch` for non-HTTP errors.

---

### schemas/ — Request & Response Contracts

One file per endpoint group. **Never share a schema between two different endpoints** — even if they look the same today, they'll diverge. Shared base types (pagination, error envelopes) live in `common.{ext}`.

```python
# schemas/search.py
class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000)
    top_k: int = Field(5, ge=1, le=50)

class SearchResponse(BaseModel):
    hits: list[Hit]
    latency_ms: float
```

**Keep DB models and API schemas separate** — even when they look identical. A DB model is a storage concern; a schema is a contract with clients. They change for different reasons.

---

### services/ — Business Logic

Services orchestrate: they call providers, call repositories, apply rules, and return schemas. They know nothing about HTTP.

```python
# services/search_service.py
class SearchService:
    def __init__(self, embedder: Embedder, retriever: Retriever):
        self.embedder = embedder
        self.retriever = retriever

    async def search(self, req: SearchRequest) -> SearchResponse:
        vector = await self.embedder.embed(req.query)
        hits = await self.retriever.search(vector, top_k=req.top_k)
        return SearchResponse(hits=hits)
```

**Red flags in services/**: `status_code`, `request.headers`, framework imports.

---

### providers/ — External Dependencies

One provider per external service. Always define an **interface/abstract class** first, then implement it. This makes swapping providers (OpenAI → Anthropic, Pinecone → pgvector) and mocking in tests trivial.

```python
# providers/embedder.py
class Embedder(ABC):
    @abstractmethod
    async def embed(self, text: str) -> list[float]: ...

class OpenAIEmbedder(Embedder):
    async def embed(self, text: str) -> list[float]:
        # OpenAI SDK call here
```

Retry logic, circuit breaking, and rate limiting all live here — not in services.

---

### repositories/ — Data Access (use when needed)

Add this layer when services start containing too many raw DB queries. A repository encapsulates all queries for one entity.

```python
# repositories/document_repo.py
class DocumentRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def find_by_id(self, id: str) -> Document | None:
        return await self.db.get(Document, id)

    async def upsert(self, doc: Document) -> Document:
        ...
```

Services call repositories; repositories never call services.

---

### exceptions/ — Domain Errors

Define domain-level errors that describe *what went wrong in your system*, not HTTP codes. Map them to HTTP responses in one central place.

```python
# exceptions/domain.py
class AppError(Exception): ...
class NotFoundError(AppError): ...
class ExternalServiceError(AppError): ...

# exceptions/handlers.py — register once in main.py
NotFoundError      → 404
ValidationError    → 422
ExternalServiceError → 502
Unhandled AppError → 500
```

Services raise domain errors. Only `handlers.py` knows about HTTP status codes.

---

### config/ — Single Source of Truth

All environment variables and settings flow through one config object, validated at **startup** — not on first request. If a required env var is missing, the app must crash with a clear message before accepting traffic.

```python
# config.py — Python
class Config(BaseSettings):
    database_url: str          # required — crashes at startup if missing
    openai_api_key: str        # required
    log_level: str = "INFO"    # optional with default

@lru_cache
def get_config() -> Config:
    return Config()
```

```typescript
// config.ts — TypeScript
const config = z.object({
  DATABASE_URL: z.string(),
  OPENAI_API_KEY: z.string(),
  LOG_LEVEL: z.string().default('info'),
}).parse(process.env);     // throws at startup if invalid
```

---

## Critical Cross-Cutting Concerns

These are easy to skip early and painful to retrofit later.

### 1. Structured Logging + Request IDs

Add a middleware that injects a unique `request_id` into every log line for a request. Without this, debugging production issues across multiple log lines is nearly impossible.

```python
class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        request_id = str(uuid.uuid4())
        with bound_contextvars(request_id=request_id):
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response
```

Use a structured logger (`structlog` in Python, `pino` in Node) that outputs JSON in production — not plain text.

### 2. Async / Sync Consistency

Pick one and go all the way. Mixing sync DB calls into an async request handler will **block your event loop** and destroy throughput silently.

- Python: use `asyncpg` or SQLAlchemy async — not the sync engine
- Node: don't mix `await` with sync `fs` or blocking ORM calls

### 3. .env.example is a Contract

Every required environment variable must appear in `.env.example` with a placeholder value and a comment. This is the canonical list of what the app needs to run. Keep it current.

```bash
# .env.example
DATABASE_URL=postgresql://user:pass@localhost:5432/mydb
OPENAI_API_KEY=sk-...           # get from platform.openai.com
LOG_LEVEL=INFO                  # DEBUG | INFO | WARNING | ERROR
```

### 4. Docker Compose for Local Dev

`docker-compose.yml` should bring up the entire local environment — app, database, any queues or caches — with one command. New developers should be able to clone + `docker compose up` and have a working system.

### 5. Test Structure Mirrors Source Structure

```
src/services/search_service.py      → tests/unit/test_search_service.py
src/api/search.py                   → tests/integration/test_search_api.py
src/providers/embedder.py           → tests/unit/test_embedder.py
```

Unit tests mock providers and test services in isolation. Integration tests hit the real HTTP layer with a test client and mock only external SDKs.

```python
# tests/conftest.py — override DI to inject mocks
app.dependency_overrides[get_embedder] = lambda: MockEmbedder()
```

### 6. Tooling Config Belongs in One File

Put linter, formatter, type checker, and test runner config in the package manifest — not scattered across `.eslintrc`, `pytest.ini`, `mypy.ini`, `.prettierrc`. One file, one place.

```toml
# pyproject.toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
line-length = 100

[tool.mypy]
strict = true
```

---

## Naming Conventions

| Thing | Convention | Example |
|---|---|---|
| Route / controller file | Resource noun, singular | `search.py`, `user.ts` |
| Request schema | `{Noun}Request` | `SearchRequest` |
| Response schema | `{Noun}Response` | `SearchResponse` |
| Service class | `{Noun}Service` | `SearchService` |
| Repository class | `{Noun}Repository` | `DocumentRepository` |
| Provider class | `{Impl}{Interface}` | `OpenAIEmbedder`, `S3Storage` |
| DI factory function | `get_{thing}` | `get_search_service` |
| Domain exception | `{Context}Error` | `NotFoundError`, `SearchError` |
| Environment variables | `UPPER_SNAKE_CASE` | `DATABASE_URL` |

---

## What Goes Where — Quick Reference

| "Where do I put…" | Layer |
|---|---|
| HTTP status codes | `api/` only |
| Input validation rules | `schemas/` |
| Business rules / conditionals | `services/` |
| Retry / timeout logic for 3rd-party APIs | `providers/` |
| Raw DB queries | `repositories/` |
| ORM table/column definitions | `models/` |
| DI / object construction | `dependencies/` |
| Request ID injection | `middleware/` |
| HTTP error formatting | `exceptions/handlers` |
| All environment variables | `config.py` / `config.ts` |
| Local dev orchestration | `docker-compose.yml` |
| Tooling config (lint, test, types) | `pyproject.toml` / `package.json` |

---

## When to Add the Repository Layer

Start without it. Add `repositories/` when you notice either:
- Services contain more than 2–3 raw DB queries
- The same DB query is duplicated across multiple services

Until then, services can call the DB directly. Premature abstraction is a real cost.

---

## Adapting to Your Framework

The layer names are stable across frameworks. Only the implementation details change:

| Concern | FastAPI | Express/NestJS | Django | Go |
|---|---|---|---|---|
| Route registration | `APIRouter` | `Router` / `@Controller` | `urlpatterns` | `http.ServeMux` |
| DI | `Depends()` | Constructor injection | N/A / manual | Function args |
| Schema validation | Pydantic | Zod / class-validator | Serializers | struct tags |
| Config | pydantic-settings | dotenv + zod | `settings.py` | `os.Getenv` + validation |
| Middleware | `BaseHTTPMiddleware` | `app.use()` | Middleware classes | `http.Handler` wrap |
