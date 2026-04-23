# Review — plans/backend-plan-1.md

## Diff Range
21b7b5321282c15d7208c7b289bbfd10d9b2d470..HEAD

## Files Reviewed
- systems/backend/src/schemas/query.py
- systems/backend/src/schemas/common.py
- systems/backend/src/models.py
- systems/backend/src/providers/embedder.py
- systems/backend/src/providers/opensearch_provider.py
- systems/backend/src/providers/llm_provider.py
- systems/backend/src/services/query_service.py
- systems/backend/src/dependencies/query.py
- systems/backend/tests/unit/test_schemas.py
- systems/backend/tests/unit/test_embedder.py
- systems/backend/tests/unit/test_opensearch_provider.py
- systems/backend/tests/unit/test_llm_provider.py
- systems/backend/tests/unit/test_query_service.py

## Changes Applied

| File | Change | Reason |
|------|--------|--------|
| `src/providers/embedder.py` | Replaced `range(0, max(len(texts), 1), self._batch_size)` with `range(0, len(texts), self._batch_size)` and removed the `if not batch: continue` guard | `max(...,1)` made the loop execute once on an empty list but the inner guard would skip it anyway — net effect was zero, but the pattern was misleading. `range(0, 0, n)` is already empty; no guard needed. |
| `src/providers/llm_provider.py` | Moved `from langchain_core.prompts import ChatPromptTemplate` from inside `__init__` to the module top-level alongside other first-class imports | `langchain-core` is a hard declared dependency (not optional), so there was no reason to defer the import. Placing it inside `__init__` falsely implied it was an optional lazy import like `openai`. |
| `src/providers/llm_provider.py` | Replaced `m.type if m.type != "human" else "user"` with a `_role_map = {"human": "user", "ai": "assistant"}` dict lookup | The conditional only handled `"human"→"user"` and would pass any other LangChain role type through unmodified (e.g., `"ai"` instead of `"assistant"`). A dict map is both clearer in intent and handles the `"ai"` case correctly. |
| `src/services/query_service.py` | Replaced `request.top_k or self._config.TOP_K` and `request.retrieval_mode or self._config.RETRIEVAL_MODE` with explicit `is not None` guards | The `or` operator treats `0` as falsy, so `top_k=0` would silently fall through to the config default. An empty-string `retrieval_mode` would also be bypassed. Using `is not None` is the correct sentinel check for optional Pydantic fields. |

## Findings Requiring Coding-Agent Fix

None.

## Findings (Flagged, No Change)

- `src/dependencies/query.py` line 0%: The dependency module has 0% test coverage because no unit tests construct or call the `get_*` dependency functions directly. This is noted by the coverage report as `16-105` uncovered. This is expected for plan 1 (route wiring is deferred to backend-plan-2), but a minimal smoke test for `get_embedder` branch selection (openai vs. huggingface) would be valuable in plan 2.

- `src/providers/embedder.py` lines 69-74 (uncovered): The `OpenAIEmbedder.__init__` body (the `import openai` lazy-import block and the field assignments) is not exercised by the test suite because tests construct the embedder via `__new__` and manually assign `_openai`. This is a pragmatic testing tradeoff given the lazy-import pattern; acceptable for now.

- `src/providers/llm_provider.py` lines 60-66 (uncovered): Same pattern — `OpenAIChatProvider.__init__` is bypassed in tests via `__new__`. Acceptable for the same reason.

## Test Result

PASS — 53/53 tests, 86% overall coverage (unchanged from pre-review run).

## Decision

PUSH
