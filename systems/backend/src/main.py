"""FastAPI application factory.

Creates the ``app`` instance, registers all sub-routers via ``api/router.py``,
and installs domain-error → HTTP exception handlers via ``exceptions/handlers.py``.

No inline route definitions live here. No business logic lives here.
"""

from fastapi import FastAPI

from src.api.router import router
from src.exceptions.handlers import add_exception_handlers

app = FastAPI(
    title="RAG Backend",
    description=(
        "REST API for query embedding, retrieval from OpenSearch, and LLM response generation."
    ),
    version="0.1.0",
)

# Mount all API sub-routers
app.include_router(router)

# Register domain-error → HTTP response handlers
add_exception_handlers(app)
