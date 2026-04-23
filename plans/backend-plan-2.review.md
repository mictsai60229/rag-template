# Review — plans/backend-plan-2.md

## Diff Range
60e9e66..b0dbd9a

## Files Reviewed
- `systems/backend/src/api/query.py`
- `systems/backend/src/api/config_endpoint.py`
- `systems/backend/src/api/router.py`
- `systems/backend/src/main.py`
- `systems/backend/src/middleware/__init__.py`
- `systems/backend/src/middleware/auth.py`
- `systems/backend/src/middleware/logging_middleware.py`
- `systems/backend/pyproject.toml`
- `systems/backend/tests/unit/test_query_route.py`
- `systems/backend/tests/unit/test_config_endpoint.py`
- `systems/backend/tests/unit/test_auth_middleware.py`
- `systems/backend/tests/unit/test_logging_middleware.py`
- `systems/backend/tests/integration/conftest.py`
- `systems/backend/tests/integration/test_query_endpoint.py`
- `systems/backend/tests/integration/fixtures/chunks.json`

## Changes Applied

| File | Change | Reason |
|------|--------|--------|
| `src/middleware/logging_middleware.py` | Moved `_request_id_ctx_var.reset(token)` to after the log call; exception path resets via a bare `except … raise` block | The original `finally` block reset the context var before the "request completed" log record was emitted. The `_RequestIDFilter` therefore read an empty string from the context var for that record, defeating the filter's purpose. The new structure resets the var after logging on the happy path and immediately on the exception path. |
| `tests/integration/test_query_endpoint.py` | Changed `assert response.json()["latency_ms"] >= 0` to `> 0` | The plan specifies `test_query_latency_ms_positive: latency_ms > 0`; the test docstring also says "positive". A real request against OpenSearch always takes at least 1 ms. |

## Findings Requiring Coding-Agent Fix

None.

## Findings (Flagged, No Change)

- `src/dependencies/query.py` lines 26–32: A local `get_config()` wrapper is defined that does nothing but call `src.config.get_config()`. Both `auth.py` and `config_endpoint.py` import `get_config` directly from `src.config`, so the wrapper is only used internally within `dependencies/query.py` as the `Depends()` target for provider factories. This is harmless — FastAPI de-duplicates dependency calls within a request — but the wrapper adds one extra function object that never appears as an override key in any test. It could be simplified by having the provider factories depend on `src.config.get_config` directly, but this is a style judgement rather than a bug.

- `src/middleware/logging_middleware.py` lines 103–107: The `configure_json_logging` function handles a two-path import (`pythonjsonlogger.json` falling back to `pythonjsonlogger.jsonlogger`) to support different versions of `python-json-logger`. This is a pragmatic compatibility shim. The installed version is pinned to `>=2.0.7` in `pyproject.toml`; if the minimum is ever tightened, one import path can be removed.

## Test Result

PASS — 81 unit tests, 91% line coverage. Integration tests were not executed (require Docker); they are correctly marked with `pytest.mark.integration` and excluded from the unit test run. Coverage exceeds the 85% target.

## Decision

PUSH
