"""Health check endpoint.

Returns a simple liveness response with no external service calls required.
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter()


@router.get("/health")
async def health_check() -> JSONResponse:
    """Liveness check — returns 200 with ``{"status": "ok"}``."""
    return JSONResponse(content={"status": "ok"})
