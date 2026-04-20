# Infrastructure — Init Plan

## System
The Infrastructure system covers the Docker Compose orchestration that wires all three application components (Backend, Python Data Import, OpenSearch) into a single reproducible local development environment, and the GitHub Actions CI/CD pipeline that enforces lint, unit tests, integration tests, Docker image builds, and registry pushes on every commit and tagged release.

## Objective
Bootstrap the `systems/infra/` directory with a fully populated `CLAUDE.md` and the root-level Docker Compose file and GitHub Actions workflow scaffolds so the coding-agent can proceed with the infrastructure coding plan.

## Prerequisites
- [ ] `docs/prd.md` exists
- [ ] `docs/sad.md` exists
- [ ] `systems/backend/Dockerfile` exists (created by backend-init-plan)
- [ ] `systems/import/Dockerfile` exists (created by import-init-plan)
- [ ] `systems/opensearch/docker-compose.yml` exists (created by opensearch-init-plan)

## Phase 1 — Scaffold & Document

**Objective:** Create the `systems/infra/` directory with a complete `CLAUDE.md`, a root-level `docker-compose.yml` that starts all three services, and a GitHub Actions workflow skeleton.

**Files to create:**
- `systems/infra/CLAUDE.md` — full project documentation (all five required sections)
- `docker-compose.yml` — root-level compose file that starts Backend, OpenSearch, and (optionally) runs the Import pipeline as a one-off service; references Dockerfiles in `systems/backend/` and `systems/import/`
- `.github/workflows/ci.yml` — GitHub Actions workflow: lint (ruff/flake8) → unit tests → integration tests (with OpenSearch testcontainer) → build Docker images → push to registry (on tag)
- `.env.example` — root-level environment variable template covering all three systems

**Content required in `systems/infra/CLAUDE.md`:**

All five sections must be fully populated with no placeholders:

1. **Project Overview** — The Infrastructure system provides the glue that holds Backend, Python Data Import, and OpenSearch together in a single Docker Compose environment for local development and CI, and automates build, test, and release via GitHub Actions. It does not contain application logic; it owns Dockerfile references, service networking, environment variable injection, and CI workflow definitions. Developers use `docker compose up` to start the full stack locally and rely on GitHub Actions to gate every pull request with automated tests.

2. **Directory Layout** — Annotated tree showing:
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
       ├── import/
       │   └── Dockerfile             # (owned by import system)
       └── opensearch/
           └── docker-compose.yml     # (OpenSearch-only compose for isolated use)
   systems/infra/
   └── CLAUDE.md
   ```

3. **Tech Stack** — Docker Engine 24+, Docker Compose v2, GitHub Actions (ubuntu-latest runners), `ruff` (Python linter), `pytest` + `testcontainers` (integration tests in CI), Docker Hub or GitHub Container Registry (GHCR) for image storage.

4. **How to Run & Test:**
   ```bash
   # Start the full stack locally (from project root)
   cp .env.example .env   # fill in real values
   docker compose up --build

   # Run only OpenSearch (for isolated backend/import dev)
   docker compose up opensearch

   # Run the import pipeline against the local stack
   docker compose run --rm importer python ingest.py --source ./sample_docs/

   # CI pipeline is triggered automatically on push/PR to main
   # To validate locally using act (https://github.com/nektos/act):
   act push
   ```

5. **Conventions & Architecture Decisions** — All three services share a single Docker network (`rag-network`) so they can address each other by service name (e.g., `http://opensearch:9200`). Environment variables are the only mechanism for passing config between services; no config files are volume-mounted in production images. The Import pipeline runs as a `docker compose run --rm` one-off command, not a long-running service. CI integration tests start OpenSearch via testcontainers (not Docker Compose) to avoid port conflicts on shared runners. Docker images are tagged with the Git SHA on every build and additionally tagged `latest` on pushes to `main`. Releases are triggered by `v*` tags; only release builds are pushed to the registry.

**Tasks:**
1. Read `docs/sad.md` sections "Infrastructure & Deployment", "Security Architecture", and the Infrastructure Diagram to gather all facts needed for the CLAUDE.md.
2. Create the `systems/infra/` directory.
3. Write `systems/infra/CLAUDE.md` with all five sections fully populated.
4. Write `docker-compose.yml` at the project root with three services:
   - `opensearch`: uses `opensearchproject/opensearch:2.13.0`, env `discovery.type=single-node`, `plugins.security.disabled=true`, port `127.0.0.1:9200:9200`, named volume, health check.
   - `backend`: builds from `systems/backend/Dockerfile`, depends on `opensearch` (health check), env file `.env`, port `127.0.0.1:8000:8000`.
   - `importer`: builds from `systems/import/Dockerfile`, depends on `opensearch` (health check), env file `.env`, `profiles: ["import"]` so it only starts when explicitly requested.
   - All services on network `rag-network`.
5. Write `.env.example` combining all env vars from `systems/backend/.env.example` and `systems/import/.env.example` into one root-level file, with a section header comment for each system.
6. Write `.github/workflows/ci.yml` with the following jobs:
   - `lint`: checkout, setup Python 3.11, `pip install ruff`, run `ruff check systems/backend/src systems/import/src`.
   - `test-backend`: checkout, setup Python 3.11, `pip install -e ".[dev]"` (in `systems/backend/`), `pytest tests/ -v --cov=src`.
   - `test-import`: checkout, setup Python 3.11, `pip install -e ".[dev]"` (in `systems/import/`), `pytest tests/ -v --cov=src`.
   - `build`: runs after all test jobs pass; builds Docker images for `backend` and `importer`, tags with `${{ github.sha }}`.
   - `push`: runs only on `v*` tags; pushes images to GHCR.

**Testing:**
- **Manual check:** Read back `systems/infra/CLAUDE.md` and verify all five sections are present with real content.
- **Scaffold check:** From the project root, run `docker compose config` — it must parse without errors. Run `docker compose up opensearch -d` and confirm OpenSearch starts.

**Done criteria:**
- [ ] `systems/infra/CLAUDE.md` exists and contains all five required sections with real content
- [ ] No placeholder text (`...`, `TODO`, `[System Name]`) remains in the CLAUDE.md
- [ ] `docker-compose.yml` exists at project root and `docker compose config` exits without error
- [ ] `.env.example` exists at project root and covers all env vars for all services
- [ ] `.github/workflows/ci.yml` exists with lint, test-backend, test-import, build, and push jobs

---

## Verification

- Read: `systems/infra/CLAUDE.md` — all five sections present with real content
- Run: `docker compose config` from project root — exits without error
- Run: `docker compose up opensearch -d` — OpenSearch container starts and health check passes
- Next step: `docs/plans/infra-plan.md` (full CI/CD wiring and production deployment configuration) can now be executed
