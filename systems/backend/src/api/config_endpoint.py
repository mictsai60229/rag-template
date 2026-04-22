"""GET /config route handler.

Returns all non-secret configuration values for introspection. Secrets are
always redacted from the response regardless of environment.

Secret fields excluded from the response:
- ``OPENAI_API_KEY``
- ``API_KEY``
- Any field whose name contains ``PASSWORD``, ``SECRET``, or ``TOKEN``
  (case-insensitive check).
"""

from fastapi import APIRouter, Depends

from src.config import Config, get_config

router = APIRouter()

# Field names that are always redacted from the /config response.
_ALWAYS_REDACTED: frozenset[str] = frozenset({"OPENAI_API_KEY", "API_KEY"})
_REDACTED_SUBSTRINGS: tuple[str, ...] = ("PASSWORD", "SECRET", "TOKEN")


def _is_secret_field(field_name: str) -> bool:
    """Return ``True`` if ``field_name`` should be excluded from the response.

    Args:
        field_name: The config field name to check.

    Returns:
        ``True`` when the field is in the always-redacted set or its upper-case
        form contains any of the redacted substrings.
    """
    if field_name in _ALWAYS_REDACTED:
        return True
    upper = field_name.upper()
    return any(sub in upper for sub in _REDACTED_SUBSTRINGS)


@router.get("/config", response_model=dict[str, object])
async def config_endpoint(
    config: Config = Depends(get_config),
) -> dict[str, object]:
    """Return active (non-secret) configuration values.

    All secret fields (``OPENAI_API_KEY``, ``API_KEY``, and any field whose
    name contains ``PASSWORD``, ``SECRET``, or ``TOKEN``) are excluded.

    Authentication is handled by the ``require_api_key`` dependency injected
    in Phase 3; this handler itself has no auth logic.

    Args:
        config: Injected application configuration.

    Returns:
        A dict mapping config field names to their current values, with all
        secret fields omitted.
    """
    raw: dict[str, object] = config.model_dump()
    return {key: value for key, value in raw.items() if not _is_secret_field(key)}
