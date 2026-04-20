"""Top-level API router.

Mounts all sub-routers. Add new sub-routers here as they are implemented in
subsequent plans.
"""

from fastapi import APIRouter

from src.api import health

router = APIRouter()

# Health check (implemented in Phase 1)
router.include_router(health.router)

# POST /query sub-router — planned (backend-plan-1)
# from src.api import query
# router.include_router(query.router)
