"""Request-ID logging middleware.

``RequestIDMiddleware`` is a Starlette ``BaseHTTPMiddleware`` that:
- Generates a UUID4 ``request_id`` for every inbound request.
- Stores it in a ``contextvars.ContextVar`` so structured log records emitted
  during the request include it automatically.
- Appends ``X-Request-ID`` to every response header.
- Emits a structured JSON log record at INFO level on request completion with
  ``method``, ``path``, ``status_code``, and ``latency_ms``.

Registration in ``main.py``::

    from src.middleware.logging_middleware import RequestIDMiddleware
    app.add_middleware(RequestIDMiddleware)
"""

import logging
import time
import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# Module-level context variable — holds the current request_id for each task.
_request_id_ctx_var: ContextVar[str] = ContextVar("request_id", default="")


def get_request_id() -> str:
    """Return the ``request_id`` for the currently active request.

    Returns an empty string when called outside of a request context.
    """
    return _request_id_ctx_var.get()


class _RequestIDFilter(logging.Filter):
    """Logging filter that injects the current ``request_id`` into log records."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        record.request_id = _request_id_ctx_var.get()
        return True


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Starlette middleware that injects a UUID4 request-ID into every request.

    For each request:
    1. Generates ``request_id = str(uuid.uuid4())``.
    2. Stores it in the ``_request_id_ctx_var`` context variable.
    3. Dispatches the request to the next handler.
    4. Appends ``X-Request-ID: <request_id>`` to the response.
    5. Logs ``method``, ``path``, ``status_code``, and ``latency_ms`` at INFO.
    """

    async def dispatch(self, request: Request, call_next: object) -> Response:
        """Process the request, injecting a unique request_id.

        Args:
            request: The incoming HTTP request.
            call_next: The next handler in the middleware stack (callable).

        Returns:
            The HTTP response with ``X-Request-ID`` header set.
        """
        request_id = str(uuid.uuid4())
        token = _request_id_ctx_var.set(request_id)

        start = time.monotonic()
        try:
            response: Response = await call_next(request)  # type: ignore[operator]
        finally:
            _request_id_ctx_var.reset(token)

        latency_ms = int((time.monotonic() - start) * 1000)
        response.headers["X-Request-ID"] = request_id

        logging.getLogger(__name__).info(
            "request completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "latency_ms": latency_ms,
            },
        )

        return response


def configure_json_logging(log_level: str = "INFO") -> None:
    """Configure the root logger to emit structured JSON records.

    Attaches a ``python-json-logger`` formatter and the ``_RequestIDFilter``
    to the root handler so every log record includes a ``request_id`` field.

    Args:
        log_level: Logging level string (e.g. ``"INFO"``, ``"DEBUG"``).
    """
    try:
        from pythonjsonlogger.json import JsonFormatter  # type: ignore[import-untyped]
    except ImportError:
        from pythonjsonlogger.jsonlogger import JsonFormatter  # type: ignore[import-untyped]

    handler = logging.StreamHandler()
    handler.setFormatter(
        JsonFormatter(
            fmt="%(asctime)s %(name)s %(levelname)s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    )
    handler.addFilter(_RequestIDFilter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, log_level.upper(), logging.INFO))
