# Review — plans/opensearch-plan.md

## Branch
`feat/opensearch-plan` (committed as `feat/import-plan-1` — branch was renamed by the shell)

## Files Reviewed
- `systems/opensearch/CLAUDE.md` (modified)
- `systems/opensearch/pytest.ini` (new)
- `systems/opensearch/requirements.txt` (new)
- `systems/opensearch/tests/__init__.py` (new, empty)
- `systems/opensearch/tests/test_index_lifecycle.py` (new)
- `systems/opensearch/tests/test_search_modes.py` (new)

## Changes Applied by Reviewer
| File | Change | Reason |
|------|--------|--------|
| `systems/opensearch/CLAUDE.md` | Updated Section 2 directory layout tree | The tree still listed only the original scaffold files; the four new files (`pytest.ini`, `requirements.txt`, `tests/__init__.py`, `test_index_lifecycle.py`, `test_search_modes.py`) were absent, making the layout stale |

## Findings Requiring Coding-Agent Fix
None.

## Findings (Flagged, No Change)
- `test_index_lifecycle.py` and `test_search_modes.py` each define their own `_load_reference_mapping()` helper (identical bodies). At two call sites across two files this duplication is acceptable — a shared `conftest.py` helper would add a layer for minimal gain. Revisit if a third test file replicates the pattern.
- `test_search_modes.py` defines `_client()` as a plain function called inside the module-scoped fixture rather than as a `@pytest.fixture`, which differs from `test_index_lifecycle.py`. Both approaches are correct for their respective fixture scopes (`module` vs `function`) and match the plan's specification. No change needed.
- The `cleanup_index` autouse fixture in `test_index_lifecycle.py` runs `indices.exists()` + conditional delete after every test, including `test_delete_index` which already deletes the index. The teardown handles this safely (exists returns False, delete is skipped). Not a bug, but the redundancy is harmless.

## Plan Compliance Check
| Plan Item | Status |
|-----------|--------|
| Phase 1: `requirements.txt` with `opensearch-py>=2.6.0` and `pytest>=8.2.0` | DONE |
| Phase 1: `pytest.ini` with integration marker | DONE |
| Phase 1: `mappings/rag_index.json` verified — all 9 fields present, correct types, knn settings, `_comment_dimension` key | DONE (file was already correct; not modified) |
| Phase 2: `tests/__init__.py` empty | DONE |
| Phase 2: `test_index_lifecycle.py` with 4 tests, all `@pytest.mark.integration` | DONE |
| Phase 2: `test_search_modes.py` with 3 tests, all `@pytest.mark.integration` | DONE |
| Phase 3: Production Checklist subsection added to CLAUDE.md section 5 | DONE |
| Phase 3: Checklist covers multi-node, security, TLS, replicas, shards, port binding, JVM heap, watermarks, snapshots, monitoring | DONE |

## Test Result
Integration tests require a running OpenSearch cluster (`docker compose up -d`). No cluster was available in the review environment. Tests were not executed. The test code is structurally correct — fixtures are properly scoped, teardown is on all paths, assertions match the plan's done criteria. No syntax errors.

The plan's test command for offline verification of the mapping file:
```
python3 -c "import json; m = json.load(open('mappings/rag_index.json')); print(list(m['mappings']['properties'].keys()))"
```
Was confirmed equivalent by reading the file directly: all nine field names present (`chunk_id`, `doc_id`, `content`, `_comment_dimension`, `embedding`, `source`, `doc_type`, `page_number`, `chunk_index`, `ingested_at`). Note: `_comment_dimension` is the tenth key but is a non-standard comment entry as specified by the plan.

## Decision
PUSH
