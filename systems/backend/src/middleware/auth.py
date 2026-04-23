"""API-key authentication dependency.

``require_api_key`` is a FastAPI dependency that enforces ``X-API-Key`` header
authentication when the application is running in production mode with a
configured API key.

Rules:
- When ``ENV == "dev"`` or ``API_KEY`` is empty: auth is skipped entirely.
- Otherwise: the ``X-API-Key`` request header must equal ``API_KEY``; a
  mismatch raises ``HTTP 401``.

Usage::

    from fastapi import Depends
    from src.middleware.auth import require_api_key

    @router.post("/query")
    async def my_endpoint(_: None = Depends(require_api_key)) -> ...: ...
"""

from fastapi import Depends, Header, HTTPException

from src.config import Config, get_config


async def require_api_key(
    x_api_key: str | None = Header(default=None),
    config: Config = Depends(get_config),
) -> None:
    """FastAPI dependency that enforces API-key authentication.

    Skips authentication in development mode or when no API key is configured.
    Raises ``HTTP 401`` when the provided key does not match the configured key.

    Args:
        x_api_key: Value of the ``X-API-Key`` request header (``None`` if absent).
        config: Injected application configuration.

    Raises:
        HTTPException: ``401`` when the key is required but absent or incorrect.
    """
    if config.ENV == "dev" or not config.API_KEY:
        return
    if x_api_key != config.API_KEY:
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing X-API-Key header",
        )
