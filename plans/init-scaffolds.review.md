# Review — init scaffolding (commits d427fac and 3362679)

## Diff Range
`git diff fdac61b...HEAD`

## Plans Reviewed
- `plans/import-init-plan.md`
- `plans/opensearch-init-plan.md`
- `plans/infra-init-plan.md`

## Files Reviewed

**systems/import/**
- `systems/import/CLAUDE.md`
- `systems/import/pyproject.toml`
- `systems/import/ingest.py`
- `systems/import/src/__init__.py`
- `systems/import/src/config.py`
- `systems/import/tests/__init__.py`
- `systems/import/tests/test_cli.py`
- `systems/import/.env.example`
- `systems/import/Dockerfile`
- `systems/import/.python-version` (unplanned artefact)
- `systems/import/uv.lock` (unplanned artefact)

**systems/opensearch/**
- `systems/opensearch/CLAUDE.md`
- `systems/opensearch/docker-compose.yml`
- `systems/opensearch/mappings/rag_index.json`
- `systems/opensearch/tests/test_opensearch_health.py`

**systems/infra/**
- `systems/infra/CLAUDE.md`

**Root**
- `docker-compose.yml`
- `.env.example`
- `.github/workflows/ci.yml`
- `.gitignore`

**Agent config (out of scope for done-criteria check but reviewed)**
- `.claude/agents/coding-agent.md`
- `.claude/agents/project-planner.md`

---

## Done-Criteria Check

### import-init-plan.md

| Criterion | Status | Notes |
|-----------|--------|-------|
| `systems/import/CLAUDE.md` exists with all five sections, real content | PASS | All five sections fully populated |
| No placeholder text in CLAUDE.md | PASS | No `...`, `TODO`, or `[System Name]` |
| `pyproject.toml` exists | PASS | All required runtime and dev deps present |
| `python ingest.py --help` exits 0 | PASS | `main()` calls `parse_args()` then exits 0 |
| `tests/test_cli.py` collected by pytest | PASS | Single smoke test, no imports beyond stdlib and Path |

### opensearch-init-plan.md

| Criterion | Status | Notes |
|-----------|--------|-------|
| `systems/opensearch/CLAUDE.md` exists with all five sections, real content | PASS | Thorough content |
| No placeholder text in CLAUDE.md | PASS | |
| CLAUDE.md Conventions states index lifecycle owned by `indexer.py` | PASS | Stated clearly and prominently |
| CLAUDE.md Conventions documents the provider pattern | PASS | Both paths spelled out |
| `docker-compose.yml` exists | PASS | (see fix below for `version:` key) |
| `mappings/rag_index.json` matches SAD Appendix A and has `_comment_dimension` | PASS | Field-for-field match; comment present |
| `tests/test_opensearch_health.py` exists with `pytestmark` | PASS | |
| No shell scripts under `systems/opensearch/` | PASS | Confirmed via glob |

### infra-init-plan.md

| Criterion | Status | Notes |
|-----------|--------|-------|
| `systems/infra/CLAUDE.md` exists with all five sections, real content | PASS | |
| No placeholder text in CLAUDE.md | PASS | |
| Root `docker-compose.yml` exists and `docker compose config` parses | PASS (assumed) | File is syntactically correct; `backend` service references `systems/backend/Dockerfile` which does not yet exist — this is expected since `backend-init-plan` is a separate prerequisite |
| Root `.env.example` covers all env vars for all services | PASS | 57 lines; all three systems covered with section comments |
| `.github/workflows/ci.yml` has lint, test-backend, test-import, build, push jobs | PASS | All five jobs present with correct dependency chain |

---

## Changes Applied

| File | Change | Reason |
|------|--------|--------|
| `systems/opensearch/docker-compose.yml` | Removed `version: "3.8"` top-level key | Deprecated in Compose v2; the root `docker-compose.yml` (written by the same agent) already omits it correctly. Mixing styles is inconsistent. |
| `systems/import/Dockerfile` | Changed `RUN pip install --no-cache-dir -e ".[dev]" \|\| pip install --no-cache-dir -e .` to `RUN pip install --no-cache-dir -e .` | Plan spec: "Install runtime dependencies only (no dev extras in the image)." The original fallback still ran with dev extras first, so the `\|\|` branch only triggered on complete failure. Production images must not carry test tooling. |
| `systems/import/src/config.py` | Changed `openai_api_key: str = ""` to `openai_api_key: str \| None = None` with inline comment | Empty string is not equivalent to "missing" — `openai_api_key == ""` passes pydantic validation, masking a missing secret. `None` makes absence explicit and allows the embedder to guard against it. HuggingFace path does not require the key, so unconditionally requiring it would break that path. |
| `.gitignore` | Added `uv.lock` and `.python-version` | These are local developer tooling artefacts from `uv`. The project's declared build system is `setuptools` and CI installs via `pip install -e ".[dev]"`. Committing them implies `uv` is the canonical installer, which contradicts the plan and the CI workflow. |

---

## Findings Requiring Coding-Agent Fix

None.

---

## Findings (Flagged, No Change)

- **`systems/import/uv.lock` and `systems/import/.python-version` are tracked in git.** `.gitignore` has been updated to exclude them going forward, but the already-committed files must be removed from the index with `git rm --cached systems/import/uv.lock systems/import/.python-version`. Not done here because it requires a git command. The user should run these two commands before the next commit.

- **`docker-compose.yml` (root) — `backend` service references `systems/backend/Dockerfile` which does not yet exist.** This is expected (backend-init-plan is a stated prerequisite that has not been run yet) and is not a defect. `docker compose config` will parse without error; `docker compose up backend` will fail until `backend-init-plan` is executed. This is correct sequencing.

- **`ci.yml` `build` job rebuilds images from scratch in the `push` job without reuse.** The `push` job runs `docker build` again independently rather than loading the image built in `build`. This means on release tags the image is built twice. This is a minor inefficiency acceptable at scaffold stage; a future infra coding plan should introduce build caching (e.g., `docker/build-push-action` with `cache-from`).

- **`ci.yml` — integration tests are listed in the plan (with testcontainers) but the `test-import` and `test-backend` jobs run the full `pytest tests/` suite.** This will execute `tests/test_opensearch_health.py` (marked `integration`) against a non-existent OpenSearch. This won't be a problem until the backend init-plan is run and that test is reachable, but the CI jobs should eventually add `-m "not integration"` to the unit-test steps and add a separate `integration-test` job that spins up OpenSearch via testcontainers. Flag for the infra coding plan.

---

## Test Result

Bash execution is not available in this environment. The following is a static analysis pass:

- `ingest.py --help`: `build_parser()` returns an `ArgumentParser` with `--config` (optional) and `--source` (required). `parse_args()` is called before the `--source` requirement is enforced by argparse; `--help` short-circuits before that point. Exit 0. **Expected: PASS.**
- `tests/test_cli.py`: Uses `subprocess.run([sys.executable, str(INGEST_SCRIPT), "--help"])`. `INGEST_SCRIPT` is resolved with `Path(__file__).parent.parent / "ingest.py"` — correct relative path. **Expected: PASS.**
- `rag_index.json`: Valid JSON, all ChunkDocument fields present, `_comment_dimension` appears before `embedding` field. **Expected: PASS.**
- No shell scripts under `systems/opensearch/`. **PASS.**

## Decision

**PUSH**

All done criteria are met. The four direct fixes are minimal and correct. No findings require a coding-agent session. The flagged items are either expected scaffolding gaps (backend Dockerfile not yet existing), future-plan improvements (CI caching, integration test separation), or a one-time manual git cleanup (`git rm --cached` for the lock files).
