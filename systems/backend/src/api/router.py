"""Top-level API router.

Mounts all sub-routers. Add new sub-routers here as they are implemented in
subsequent plans.
"""

from fastapi import APIRouter

from src.api import health, query

router = APIRouter()

# Health check
router.include_router(health.router)

# POST /query
router.include_router(query.router)
