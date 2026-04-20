"""Configuration for the RAG Data Import pipeline.

All settings are loaded from environment variables (or a .env file via
pydantic-settings). Required fields have no default — a missing env var
causes a clear ValidationError at startup.

Secrets (OPENAI_API_KEY) are never logged or returned by any code path.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Import pipeline configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Embedding provider ---
    openai_api_key: str | None = None  # Required when embedding_provider="openai"
    embedding_provider: str = "openai"
    embedding_model: str = "text-embedding-3-small"
    embedding_batch_size: int = 32

    # --- OpenSearch ---
    opensearch_host: str = "localhost"
    opensearch_port: int = 9200
    opensearch_index: str = "rag-chunks"

    # --- Chunking ---
    chunking_strategy: str = "recursive"
    chunk_size: int = 512
    chunk_overlap: int = 64

    # --- Environment ---
    env: str = "dev"


def get_settings() -> Settings:
    """Return a validated Settings instance loaded from the environment."""
    return Settings()
