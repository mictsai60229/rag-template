# OpenSearch — Init Plan

## System
OpenSearch is the sole persistence layer of the RAG template. It stores all indexed chunk content as `ChunkDocument` records that combine a dense k-NN vector field (for semantic similarity search), a BM25-indexed text field (for keyword search), and keyword/date metadata fields (for filtered queries). Both the Backend (at query time) and the Python Data Import pipeline (at ingestion time) communicate with OpenSearch after initial setup. No other database or search engine is used.

This system's directory (`systems/opensearch/`) is responsible for **infrastructure only**: running the cluster locally, and holding the index mapping as a reference file. It does not own index lifecycle operations at runtime — those belong to the Import pipeline.

## Objective
Bootstrap the `systems/opensearch/` directory with a fully populated `CLAUDE.md` and a minimal infrastructure scaffold — Docker Compose configuration, an index-mapping reference file, and a cluster health smoke test — so the coding-agent can safely proceed with the OpenSearch integration work in the Import pipeline and Backend plans.

## Prerequisites
- [ ] `docs/prd.md` exists
- [ ] `docs/sad.md` exists

## Phase 1 — Scaffold & Document

**Objective:** Create the `systems/opensearch/` directory with a complete `CLAUDE.md`, a Docker Compose cluster, a reference mapping file, and a pytest health smoke test. A developer should be able to start a local OpenSearch node and confirm it is ready with two commands.

**Files to create:**
- `systems/opensearch/CLAUDE.md` — full project documentation (all five required sections; see content spec below)
- `systems/opensearch/docker-compose.yml` — single-node OpenSearch 2.x container with k-NN plugin enabled, security disabled for development, named data volume, and a health check
- `systems/opensearch/mappings/rag_index.json` — reference index mapping JSON (SAD Appendix A) with an inline comment on the `dimension` field; this file is the source of truth read by the Import pipeline's `indexer.py`
- `systems/opensearch/tests/test_opensearch_health.py` — pytest smoke test that connects to a running OpenSearch instance and asserts cluster health is `green` or `yellow`

**Content required in `systems/opensearch/CLAUDE.md`:**

All five sections must be fully populated with no placeholders:

1. **Project Overview** — OpenSearch 2.x is the sole persistence layer of the RAG template. It provides three search capabilities from a single index: k-NN approximate nearest-neighbour vector search (HNSW algorithm via the bundled k-NN plugin), BM25 full-text keyword search, and metadata-filtered variants of both. It receives all writes from the Python Data Import pipeline and answers all read queries from the Backend. No other database or search engine is used. In development it runs as a single-node Docker container. In production it should be a minimum 3-node cluster or AWS OpenSearch Service. This directory owns only the cluster infrastructure (Docker Compose) and the canonical index mapping reference file (`mappings/rag_index.json`). Index lifecycle operations (create, delete, recreate) are performed exclusively by the Import pipeline's `indexer.py`.

2. **Directory Layout** — annotated tree:
   ```
   systems/opensearch/
   ├── CLAUDE.md
   ├── docker-compose.yml          # Single-node dev cluster
   ├── mappings/
   │   └── rag_index.json          # Reference index mapping (source of truth for indexer.py)
   └── tests/
       └── test_opensearch_health.py  # Cluster health smoke test (pytest)
   ```

3. **Tech Stack** — OpenSearch 2.x (Docker image `opensearchproject/opensearch:2.13.0`), k-NN plugin (bundled, enabled via `plugins.knn.enabled: true`), security plugin disabled in dev (`plugins.security.disabled: true`), Docker Compose v2, `opensearch-py` Python client (for smoke test), pytest.

4. **How to Run & Test:**
   ```bash
   # Start OpenSearch locally (run from systems/opensearch/)
   docker compose up -d

   # Confirm the cluster is ready (status will be green or yellow)
   curl -s http://localhost:9200/_cluster/health | python3 -m json.tool

   # Run the health smoke test
   export OPENSEARCH_URL=http://localhost:9200
   pytest tests/test_opensearch_health.py -v

   # Tear down (removes the data volume)
   docker compose down -v
   ```

5. **Conventions & Architecture Decisions:**
   - OpenSearch must not be exposed on a public network interface; bind to `127.0.0.1:9200` on the host in Docker Compose.
   - The k-NN plugin must be enabled (`plugins.knn.enabled: true`). The security plugin is disabled in dev (`plugins.security.disabled: true`) and must be re-enabled with TLS in production.
   - **Index lifecycle (create, delete, recreate) is managed exclusively by the Import pipeline's `indexer.py` using `opensearch-py`.** No shell scripts in this directory perform index management. The `mappings/rag_index.json` file is a reference/source-of-truth that `indexer.py` reads at runtime via the file system or bundled as a package resource.
   - The `embedding` field dimension (default 1536, matching `text-embedding-3-small`) must match the configured embedding model output. If the dimension changes the index must be deleted and recreated; this is handled by `indexer.py`, not by anything in this directory.
   - HNSW parameters (`ef_construction: 128`, `m: 16`) are the defaults; they are exposed as config values in the Import pipeline's `config.py`.
   - **Provider/repository pattern (from backend-structure skill):** consumers of OpenSearch — both the Backend and the Import pipeline — must wrap the `opensearch-py` client inside a `providers/opensearch_provider.py` in their respective `systems/` directories. Services and business logic must never import `opensearch-py` directly; they call the provider. This keeps the OpenSearch client swappable and testable in isolation.
   - Index settings: 1 shard, 1 replica for dev; tunable for production via config.
   - All `ChunkDocument` fields (`chunk_id`, `doc_id`, `content`, `embedding`, `source`, `doc_type`, `page_number`, `chunk_index`, `ingested_at`) must exactly match the SAD Data Models section. Any mapping change requires a coordinated update across the Import pipeline's `indexer.py` and the Backend's `retriever.py`.

**Tasks:**
1. Read `docs/sad.md` sections "OpenSearch", "Data Models" (ChunkDocument), "OpenSearch Index API", "OpenSearch Search API", "Infrastructure & Deployment", Appendix A (index mapping), and Appendix B (hybrid search DSL) to gather all facts for the CLAUDE.md.
2. Create the `systems/opensearch/` directory hierarchy (including `mappings/` and `tests/` subdirectories).
3. Write `systems/opensearch/CLAUDE.md` with all five sections fully populated as specified above.
4. Write `systems/opensearch/docker-compose.yml` with:
   - Service `opensearch` using image `opensearchproject/opensearch:2.13.0`
   - Environment: `discovery.type=single-node`, `plugins.security.disabled=true`, `plugins.knn.enabled=true`, `OPENSEARCH_JAVA_OPTS=-Xms512m -Xmx512m`
   - Port mapping: `127.0.0.1:9200:9200`
   - Named volume `opensearch-data` mounted at `/usr/share/opensearch/data`
   - Health check: `curl -s http://localhost:9200/_cluster/health` with 30s interval, 10s timeout, 5 retries
5. Write `systems/opensearch/mappings/rag_index.json` exactly as specified in SAD Appendix A. Add an inline JSON comment field (e.g. `"_comment_dimension"`) immediately before the `embedding` field noting: "dimension must match the configured embedding model output size; default 1536 matches text-embedding-3-small; recreate the index if this value changes".
6. Write `systems/opensearch/tests/test_opensearch_health.py` as a pytest test that:
   - Reads `OPENSEARCH_URL` from the environment (default `http://localhost:9200`)
   - Uses `opensearch-py` (`from opensearchpy import OpenSearch`) to connect
   - Calls `client.cluster.health()` and asserts `response["status"]` is in `["green", "yellow"]`
   - Has a module-level `pytestmark = pytest.mark.integration` so it can be excluded from unit test runs

**Testing:**
- **Manual check:** Read back `systems/opensearch/CLAUDE.md` and verify all five sections are present with real content (no `...` or placeholder text), and that the Conventions section explicitly states index lifecycle is owned by `indexer.py`.
- **Scaffold check:** Run `docker compose up -d` from `systems/opensearch/`, wait ~30 seconds, then `curl -s http://localhost:9200/_cluster/health`. The response must contain `"status":"green"` or `"status":"yellow"`.
- **Smoke test:** With the cluster running, execute `OPENSEARCH_URL=http://localhost:9200 pytest tests/test_opensearch_health.py -v`. The test must pass.
- **Negative check:** Confirm there are no `.sh` files anywhere under `systems/opensearch/`. Index management scripts must not exist here.

**Done criteria:**
- [ ] `systems/opensearch/CLAUDE.md` exists and contains all five required sections with real content
- [ ] No placeholder text (`...`, `TODO`, `[System Name]`) remains in the CLAUDE.md
- [ ] The CLAUDE.md Conventions section explicitly states that index lifecycle (create/delete/recreate) is managed by the Import pipeline's `indexer.py`, not by any shell script in this directory
- [ ] The CLAUDE.md Conventions section documents the provider pattern: `opensearch-py` client is wrapped in `providers/opensearch_provider.py` in each consuming system
- [ ] `systems/opensearch/docker-compose.yml` exists and `docker compose up -d` starts the container without error
- [ ] `systems/opensearch/mappings/rag_index.json` exists, matches SAD Appendix A, and includes a comment on the `dimension` field
- [ ] `systems/opensearch/tests/test_opensearch_health.py` exists, is collected by pytest, and passes against a running cluster
- [ ] No shell scripts exist under `systems/opensearch/`

---

## Verification

- Read: `systems/opensearch/CLAUDE.md` — all five sections present, no placeholders, Conventions section states index lifecycle ownership
- Run: `docker compose up -d && sleep 30 && curl -s http://localhost:9200/_cluster/health` from `systems/opensearch/` — response status is `green` or `yellow`
- Run: `OPENSEARCH_URL=http://localhost:9200 pytest tests/test_opensearch_health.py -v` — 1 test passes
- Confirm: `find systems/opensearch -name "*.sh"` returns no results
- Next step: the Import pipeline's `indexer.py` coding plan can now read `systems/opensearch/mappings/rag_index.json` and implement index lifecycle management using `opensearch-py` with an `OpenSearchProvider` in `systems/import/src/providers/opensearch_provider.py`
