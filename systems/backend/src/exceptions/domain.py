"""Domain error hierarchy for the RAG backend.

Services raise these errors to signal what went wrong in the system.
``exceptions/handlers.py`` is the only place that maps these to HTTP status codes.
"""


class AppError(Exception):
    """Base class for all application domain errors."""


class NotFoundError(AppError):
    """Raised when a requested resource cannot be found."""


class ExternalServiceError(AppError):
    """Raised when a call to an external service (OpenSearch, LLM, Embedding) fails."""


class ConfigurationError(AppError):
    """Raised when the application is misconfigured at runtime."""
