"""Common Pydantic models shared across the API.

Provides ``ErrorResponse`` used in exception handlers and OpenAPI docs.
"""

from pydantic import BaseModel, ConfigDict, Field


class ErrorResponse(BaseModel):
    """Standard error response body returned by exception handlers."""

    model_config = ConfigDict(frozen=True)

    detail: str = Field(..., description="Human-readable description of the error.")
