"""POST /query route handler.

The route handler is intentionally thin: it parses the request schema, calls
``QueryService.query()`` via dependency injection, and returns the response
schema. No business logic lives here.
"""

import asyncio

from fastapi import APIRouter, Depends

from src.dependencies.query import get_query_service
from src.middleware.auth import require_api_key
from src.schemas.query import QueryRequest, QueryResponse
from src.services.query_service import QueryService

router = APIRouter()


@router.post("/query", response_model=QueryResponse)
async def query_endpoint(
    request: QueryRequest,
    service: QueryService = Depends(get_query_service),
    _: None = Depends(require_api_key),
) -> QueryResponse:
    """Accept a natural-language query and return a grounded answer.

    Delegates all logic to ``QueryService.query()``. Uses ``asyncio.to_thread``
    to avoid blocking the event loop because the provider calls (embedder, LLM)
    are synchronous.

    Args:
        request: Validated ``QueryRequest`` from the request body.
        service: Injected ``QueryService`` with all providers wired in.

    Returns:
        A ``QueryResponse`` containing the answer, source chunks, retrieval mode,
        and end-to-end latency in milliseconds.
    """
    return await asyncio.to_thread(service.query, request)
