# Infrastructure — CLAUDE.md

## 1. Project Overview

The Infrastructure system provides the glue that holds Backend, Python Data Import, and OpenSearch together in a single Docker Compose environment for local development and CI, and automates build, test, and release via GitHub Actions. It does not contain application logic; it owns Dockerfile references, service networking, environment variable injection, and CI workflow definitions. Developers use `docker compose up` to start the full stack locally and rely on GitHub Actions to gate every pull request with automated tests.

All three services share a single Docker network (`rag-network`) so they can address each other by service name (e.g., `http://opensearch:9200`). Environment variables are the only mechanism for passing config between services; no config files are volume-mounted in production images. The Import pipeline runs as a `docker compose run --rm` one-off command, not a long-running service.

---

## 2. Directory Layout

```
/ (project root)
├── docker-compose.yml             # Full-stack local dev environment
├── .env.example                   # Root env template for all services
├── .github/
│   └── workflows/
│       └── ci.yml                 # CI/CD pipeline
└── systems/
    ├── backend/
    │   └── Dockerfile             # (owned by backend system)
    └── import/
        └── Dockerfile             # (owned by import system)

systems/infra/
└── CLAUDE.md
```

---

## 3. Tech Stack

| Component | Version / Detail |
|-----------|-----------------|
| Docker Engine | 24+ |
| Docker Compose | v2 (`docker compose` CLI, not `docker-compose`) |
| GitHub Actions | ubuntu-latest runners |
| Python linter | `ruff` |
| Test framework | `pytest` + `testcontainers` (integration tests with real OpenSearch container) |
| Image registry | Docker Hub or GitHub Container Registry (GHCR) |

---

## 4. How to Run and Test

```bash
# Start the full stack locally (from project root)
cp .env.example .env   # fill in real values
docker compose up --build

# Run the import pipeline against the local stack
docker compose run --rm importer python ingest.py --source ./sample_docs/

# CI pipeline is triggered automatically on push/PR to main
# To validate locally using act (https://github.com/nektos/act):
act push
```

### Validate the compose file

```bash
# From project root — must exit without error
docker compose config
```

---

## 5. Conventions and Architecture Decisions

### Docker Network

All three services (`opensearch`, `backend`, `importer`) are attached to a single user-defined bridge network named `rag-network`. This allows them to address each other by service name (e.g., `http://opensearch:9200` from within the `backend` or `importer` containers). The network is defined at the top level of `docker-compose.yml`.

### Environment Variable Injection

Environment variables are the only mechanism for passing config between services. The root `.env.example` (and `.env` for local development) covers all three systems in one file with section headers. Secrets must never appear in config files committed to version control.

### Import Pipeline as One-Off Service

The `importer` service uses `profiles: ["import"]` so it does not start automatically with `docker compose up`. Run it explicitly with:

```bash
docker compose run --rm importer python ingest.py --source ./sample_docs/
```

### OpenSearch Port Binding

OpenSearch's port 9200 is bound to `127.0.0.1:9200` (localhost only) so it is not exposed on a public network interface. The same applies to the Backend's port 8000.

### Health Checks and Dependency Ordering

The `backend` and `importer` services declare `depends_on` with `condition: service_healthy` on `opensearch`. This ensures containers do not start until OpenSearch's health check passes.

### CI Integration Tests

CI integration tests start OpenSearch via `testcontainers` (not Docker Compose) to avoid port conflicts on shared GitHub Actions runners. This means each test run gets its own isolated OpenSearch instance that is torn down after the test suite.

### Docker Image Tagging

Docker images are tagged with the Git SHA (`${{ github.sha }}`) on every build. Images pushed to `main` are additionally tagged `latest`. Registry pushes happen only on `v*` tags (releases) via the `push` job in CI.

### CI Job Order

The GitHub Actions pipeline enforces this order:
1. `lint` — ruff linter on both `systems/backend/src` and `systems/import/src`
2. `test-backend` — pytest with coverage for the Backend
3. `test-import` — pytest with coverage for the Import pipeline
4. `build` — Docker image builds (after all tests pass)
5. `push` — push to GHCR (only on `v*` tags)
