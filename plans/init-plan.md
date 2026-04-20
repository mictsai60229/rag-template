# RAG Template — Init Plan

## Project Overview
A framework-agnostic, reusable Retrieval-Augmented Generation (RAG) template that developers can drop into any project, swapping data sources, embedding models, vector stores, and LLM providers through configuration alone.

## System Inventory

| System | Purpose | Recommended Framework | Why This Framework |
|--------|---------|-----------------------|--------------------|
| Backend API | Exposes REST endpoints for query embedding, retrieval orchestration, and LLM answer generation | FastAPI (Python 3.11+) | Async-native, automatic OpenAPI docs, lightweight; consistent language with the Import pipeline |
| Python Data Import | Offline CLI pipeline that loads, cleans, chunks, embeds, and indexes documents into OpenSearch | Python 3.11+ CLI (`ingest.py`) | Matches Backend language; rich document-loader ecosystem (PyMuPDF, python-docx, BeautifulSoup) |
| OpenSearch | Sole persistence layer providing k-NN vector search, BM25 keyword search, metadata filtering, and hybrid search | OpenSearch 2.x (Docker for dev, managed for prod) | PRD-mandated; provides BM25 and k-NN in a single engine, eliminating a separate keyword search service |
| Infrastructure | Container orchestration for local development, CI/CD pipeline, and production deployment scaffolding | Docker + Docker Compose + GitHub Actions | Industry-standard; same images promoted from local to CI to production |

## Tech Stack Summary

| Layer | Technology | Notes |
|-------|------------|-------|
| Language (backend + import) | Python 3.11+ | Single language across both active systems |
| API framework | FastAPI | Async REST, automatic OpenAPI docs |
| Config validation | pydantic-settings | Env vars, `.env`, and YAML/JSON support |
| LLM abstraction | langchain-core | Prompt templates and LLM interface only; full LangChain stack is not used |
| Embedding — cloud | OpenAI Embeddings API (`text-embedding-3-small`) | Default provider; swap via config |
| Embedding — local | HuggingFace sentence-transformers | Zero-cost, privacy-preserving alternative |
| LLM provider | OpenAI Chat Completions API | Default; swappable via config |
| Vector + keyword store | OpenSearch 2.x | k-NN plugin (HNSW), BM25, metadata filtering |
| Containerisation | Docker + Docker Compose | Reproducible local/CI environment |
| CI/CD | GitHub Actions | lint → test → build → push → deploy |
| Testing | pytest + pytest-asyncio + testcontainers | Integration tests spin up real OpenSearch container |

## Open Architecture Questions
- [ ] Production cloud provider: AWS OpenSearch Service vs. self-hosted on GKE/AKS (see SAD Open Decision #1)
- [ ] Re-ranking step: none in v1 or optional cross-encoder post-retrieval re-ranker (SAD Open Decision #2)
- [ ] Async ingestion queue: defer until single-process throughput is insufficient (SAD Open Decision #3)
- [ ] Distributed tracing: OpenTelemetry + Jaeger vs. Datadog APM (SAD Open Decision #4)
- [ ] Authentication model: API Key only for v1; OAuth2 if multi-tenant use cases emerge (SAD Open Decision #5)
- [ ] Semantic chunking implementation: LangChain SemanticChunker vs. custom similarity splitter (SAD Open Decision #6)
- [ ] Index lifecycle / re-ingestion strategy: full re-index vs. upsert by chunk_id (SAD Open Decision #7)
