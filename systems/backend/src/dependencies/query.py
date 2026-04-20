"""FastAPI dependency functions for the query pipeline.

This is the only place in the codebase where providers and services are
instantiated for dependency injection. Route handlers call these functions
via ``Depends()`` — they never construct provider objects directly.

Usage::

    @router.post("/query")
    async def query_endpoint(
        request: QueryRequest,
        service: QueryService = Depends(get_query_service),
    ) -> QueryResponse: ...
"""

from fastapi import Depends

from src.config import Config
from src.config import get_config as config_module_get_config
from src.providers.embedder import Embedder, HFEmbedder, OpenAIEmbedder
from src.providers.llm_provider import LLMProvider, OpenAIChatProvider
from src.providers.opensearch_provider import OpenSearchProvider
from src.services.query_service import QueryService


def get_config() -> Config:
    """Return the singleton application configuration.

    Returns:
        The validated ``Config`` instance.
    """
    return config_module_get_config()


def get_embedder(config: Config = Depends(get_config)) -> Embedder:
    """Construct and return the configured embedder provider.

    Selects between ``OpenAIEmbedder`` and ``HFEmbedder`` based on
    ``config.EMBEDDING_PROVIDER``.

    Args:
        config: Injected application configuration.

    Returns:
        An ``Embedder`` instance ready for use.
    """
    if config.EMBEDDING_PROVIDER == "openai":
        return OpenAIEmbedder(
            api_key=config.OPENAI_API_KEY,
            model=config.EMBEDDING_MODEL,
            batch_size=config.EMBEDDING_BATCH_SIZE,
        )
    return HFEmbedder(model_name=config.EMBEDDING_MODEL)


def get_opensearch_provider(config: Config = Depends(get_config)) -> OpenSearchProvider:
    """Construct and return an ``OpenSearchProvider`` from config.

    Args:
        config: Injected application configuration.

    Returns:
        An ``OpenSearchProvider`` connected to the configured cluster.
    """
    return OpenSearchProvider(
        host=config.OPENSEARCH_HOST,
        port=config.OPENSEARCH_PORT,
        index=config.OPENSEARCH_INDEX,
        keyword_boost=config.KEYWORD_BOOST,
    )


def get_llm_provider(config: Config = Depends(get_config)) -> LLMProvider:
    """Construct and return an ``OpenAIChatProvider`` from config.

    Args:
        config: Injected application configuration.

    Returns:
        An ``LLMProvider`` instance ready for use.
    """
    return OpenAIChatProvider(
        api_key=config.OPENAI_API_KEY,
        model=config.LLM_MODEL,
    )


def get_query_service(
    embedder: Embedder = Depends(get_embedder),
    opensearch: OpenSearchProvider = Depends(get_opensearch_provider),
    llm: LLMProvider = Depends(get_llm_provider),
    config: Config = Depends(get_config),
) -> QueryService:
    """Construct and return a ``QueryService`` with all providers injected.

    Args:
        embedder: Injected embedder provider.
        opensearch: Injected OpenSearch provider.
        llm: Injected LLM provider.
        config: Injected application configuration.

    Returns:
        A fully-wired ``QueryService`` instance.
    """
    return QueryService(
        embedder=embedder,
        opensearch=opensearch,
        llm=llm,
        config=config,
    )
