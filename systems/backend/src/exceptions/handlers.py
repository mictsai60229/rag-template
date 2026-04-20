"""Exception handlers that map domain errors to HTTP responses.

This is the ONLY file in the codebase that converts domain errors to HTTP status
codes. All other code raises ``AppError`` subclasses; this module translates them.

Usage::

    from src.exceptions.handlers import add_exception_handlers
    add_exception_handlers(app)
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.exceptions.domain import AppError, ExternalServiceError, NotFoundError


def add_exception_handlers(app: FastAPI) -> None:
    """Register all domain-error → HTTP-response handlers on the FastAPI app."""

    @app.exception_handler(NotFoundError)
    async def not_found_handler(request: Request, exc: NotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(ExternalServiceError)
    async def external_service_handler(
        request: Request, exc: ExternalServiceError
    ) -> JSONResponse:
        return JSONResponse(status_code=502, content={"detail": str(exc)})

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=500, content={"detail": str(exc)})
