# OpenSearch — System CLAUDE.md

## 1. Project Overview

OpenSearch 2.x is the sole persistence layer of the RAG template. It provides three search capabilities from a single index:

- **k-NN approximate nearest-neighbour vector search** — powered by the HNSW algorithm via the bundled k-NN plugin. Used when `retrieval_mode` is `vector` or `hybrid`.
- **BM25 full-text keyword search** — the standard OpenSearch inverted-index text search. Used when `retrieval_mode` is `keyword` or `hybrid`.
- **Metadata-filtered variants of both** — any search can be narrowed by `keyword` or `date` filter clauses on the metadata fields (`source`, `doc_type`, `page_number`, `chunk_index`, `ingested_at`).

All writes come from the Python Data Import pipeline's `indexer.py`. All reads come from the Backend's `retriever.py`. No other component communicates with OpenSearch.

In development OpenSearch runs as a single-node Docker container (security plugin disabled, k-NN plugin enabled). In production it should be a minimum 3-node cluster or AWS OpenSearch Service, with the security plugin re-enabled and TLS configured for node-to-node and client-to-node traffic.

**This directory owns only infrastructure:** the Docker Compose configuration that starts a local cluster, and the canonical index mapping reference file (`mappings/rag_index.json`). Index lifecycle operations — create, delete, and recreate the index — are performed exclusively by the Import pipeline's `indexer.py`, not by anything in this directory.

---

## 2. Directory Layout

```
systems/opensearch/
├── CLAUDE.md
├── docker-compose.yml              # Single-node dev cluster
├── mappings/
│   └── rag_index.json              # Reference index mapping (source of truth for indexer.py)
└── tests/
    └── test_opensearch_health.py   # Cluster health smoke test (pytest)
```

---

## 3. Tech Stack

| Component | Version / Detail |
|-----------|-----------------|
| OpenSearch | 2.x — Docker image `opensearchproject/opensearch:2.13.0` |
| k-NN plugin | Bundled with OpenSearch 2.x; enabled via `plugins.knn.enabled: true` |
| Security plugin | Disabled in dev (`plugins.security.disabled: true`); must be re-enabled with TLS in production |
| Docker Compose | v2 (`docker compose` CLI, not `docker-compose`) |
| `opensearch-py` | Python client used by the smoke test and by all consuming systems |
| pytest | Test runner for the health smoke test |

---

## 4. How to Run and Test

```bash
# Start OpenSearch locally (run from systems/opensearch/)
docker compose up -d

# Confirm the cluster is ready (status will be green or yellow for a single-node cluster)
curl -s http://localhost:9200/_cluster/health | python3 -m json.tool

# Run the health smoke test
export OPENSEARCH_URL=http://localhost:9200
pytest tests/test_opensearch_health.py -v

# Tear down (removes the data volume)
docker compose down -v
```

The cluster takes approximately 20–30 seconds to become ready after `docker compose up -d`. The smoke test will fail if run before the cluster is healthy.

---

## 5. Conventions and Architecture Decisions

### Index lifecycle ownership

**Index lifecycle — create, delete, and recreate — is managed exclusively by the Import pipeline's `indexer.py`, not by any shell script or tool in this directory.** The `mappings/rag_index.json` file is a reference document and source of truth that `indexer.py` reads at runtime from the file system (or as a package resource). No `.sh` files exist under `systems/opensearch/`.

### Provider / repository pattern

Consumers of OpenSearch — both the Backend and the Import pipeline — must wrap the `opensearch-py` client inside a `providers/opensearch_provider.py` in their respective `systems/` directories:

- `systems/backend/src/providers/opensearch_provider.py`
- `systems/import/src/providers/opensearch_provider.py`

Services and business logic (e.g., `retriever.py`, `indexer.py`) must never import `opensearch-py` directly. They call the provider. This keeps the OpenSearch client swappable and testable in isolation.

### Network exposure

OpenSearch must not be exposed on a public network interface. The Docker Compose port mapping binds to `127.0.0.1:9200` on the host so the port is only reachable from localhost. On a shared or cloud host, no additional firewall rules are required for isolation.

### k-NN and security plugin settings

The k-NN plugin must be enabled (`plugins.knn.enabled: true`) in all environments — without it, indexing or querying the `knn_vector` field will fail. The security plugin is disabled in dev (`plugins.security.disabled: true`) and must be re-enabled with proper TLS configuration in production.

### Embedding dimension

The `embedding` field dimension defaults to 1536, matching `text-embedding-3-small`. If the embedding model changes and its output dimension differs, the index must be deleted and recreated. This operation is handled by `indexer.py`, not by anything in this directory.

### HNSW parameters

The HNSW index parameters (`ef_construction: 128`, `m: 16`) are the defaults specified in the reference mapping. They are exposed as config values in the Import pipeline's `config.py` so they can be tuned without editing the mapping file.

### Index settings

The reference mapping uses 1 shard and 1 replica for development. For production, shard count and replica count should be tuned via the Import pipeline's config before the index is created; they cannot be changed on a live index without reindexing.

### ChunkDocument field contract

All `ChunkDocument` fields listed below must exactly match the SAD Data Models section. Any mapping change requires a coordinated update across the Import pipeline's `indexer.py` and the Backend's `retriever.py`.

| Field | OpenSearch Type | Notes |
|-------|----------------|-------|
| `chunk_id` | `keyword` | Primary key |
| `doc_id` | `keyword` | Parent document identifier |
| `content` | `text` (standard analyzer) | BM25 full-text search field |
| `embedding` | `knn_vector` (dim=1536) | Dense vector for k-NN search |
| `source` | `keyword` | Filterable; file path or URL |
| `doc_type` | `keyword` | Filterable; `pdf`, `txt`, `md`, `docx`, `url` |
| `page_number` | `integer` | Filterable; nullable |
| `chunk_index` | `integer` | Filterable; zero-based position in parent doc |
| `ingested_at` | `date` | Filterable; UTC timestamp of ingestion |
