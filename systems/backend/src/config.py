"""Application configuration loaded from environment variables.

``Config`` is the single source of truth for all settings. Required fields have
no default value — if any are missing the application crashes at startup with a
clear ``ValidationError`` before accepting any traffic.

Secrets (``OPENAI_API_KEY``, ``API_KEY``) are never logged or returned by any
endpoint.

Usage::

    from src.config import get_config
    config = get_config()
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    """All application settings, validated from environment variables at startup."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # --- OpenSearch ---
    OPENSEARCH_HOST: str  # required
    OPENSEARCH_PORT: int  # required
    OPENSEARCH_INDEX: str  # required

    # --- Embedding ---
    EMBEDDING_PROVIDER: str  = 'huggingface' #; "openai" | "huggingface"
    EMBEDDING_MODEL: str = 'all-MiniLM-L6-v2' # e.g. "text-embedding-3-small"

    # --- Optional fields with defaults ---
    API_KEY: str = ""  # empty string disables auth check
    ENV: str = "dev"  # "dev" | "production"
    TOP_K: int = 5
    RETRIEVAL_MODE: str = "hybrid"  # "vector" | "keyword" | "hybrid"
    KEYWORD_BOOST: float = 0.3
    EMBEDDING_BATCH_SIZE: int = 32
    LOG_LEVEL: str = "INFO"


@lru_cache
def get_config() -> Config:
    """Return the singleton ``Config`` instance (cached after first call)."""
    return Config()
