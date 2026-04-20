# Review — plans/import-plan-1.md

## Diff Range
7863655..HEAD

## Files Reviewed
- systems/import/src/models.py
- systems/import/src/loader.py
- systems/import/src/cleaner.py
- systems/import/src/chunker.py
- systems/import/tests/unit/test_loader.py
- systems/import/tests/unit/test_cleaner.py
- systems/import/tests/unit/test_chunker.py
- systems/import/tests/fixtures/sample.txt
- systems/import/tests/fixtures/sample.md

## Changes Applied
| File | Change | Reason |
|------|--------|--------|
| systems/import/src/chunker.py | Removed unused `from langchain_core.embeddings import Embeddings` import in `SemanticStrategy.__init__` | Import was dead code — `Embeddings` was never referenced after import; the constructor accepts `embedder: object` and passes it directly with `type: ignore` |

## Findings (Flagged, No Change)

**loader.py — coverage gaps at lines 40, 58–61, 117 (93% coverage, above 90% target)**

Three branches are not exercised via `load()` dispatch: the directory path (line 40), and the `.txt`/`.md`/`.docx` branches inside `if path.is_file()` (lines 54–59). All loader tests call private methods (`_load_txt`, `_load_md`, etc.) directly rather than routing through `load()`. This is intentional and acceptable — the direct-method approach keeps tests fast and isolated — but it means `load()` itself is only partially exercised for file types. A follow-up could add one round-trip test per type through `load()`, though coverage is already above the 90% target.

**loader.py — no-extension file falls through silently to generic ValueError (line 61)**

A path with no extension (e.g. `README`) passes the `if ext and ext not in SUPPORTED_EXTENSIONS` guard (because `ext` is `""`, which is falsy) and then falls through the `if path.is_file()` block with no matching `elif`, landing on the generic `ValueError` at line 61. The error message says "not a file, directory, or supported URL" which may be confusing for the no-extension case. Not a bug — the error is raised and the comment on lines 42–43 explains the intent — but it could produce a misleading message for callers. Flagged for awareness; not changed.

**chunker.py — SemanticStrategy coverage is 84% as expected**

`SemanticStrategy` is not covered because `langchain_experimental` is not installed in the test environment. This is explicitly called out in the plan scope note and is acceptable for this plan.

**models.py — `datetime.utcnow()` is deprecated in Python 3.12+**

Both `RawDocument.loaded_at` and `Chunk.ingested_at` use `datetime.utcnow` as their `default_factory`. `datetime.utcnow()` is deprecated since Python 3.12 (use `datetime.now(timezone.utc)` instead). The project targets Python 3.11+ so this does not break anything today, but it will produce deprecation warnings on 3.12 and above. Flagged for awareness; not changed as it matches the plan's literal spec.

## Test Result
PASS — 59 passed, 0 failed. Coverage: cleaner.py 100%, models.py 100%, loader.py 93%, chunker.py 84% (SemanticStrategy excluded per plan note). All targets met.

## Decision
PUSH
