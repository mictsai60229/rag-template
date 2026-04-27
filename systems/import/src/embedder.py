"""Embedder for the RAG Data Import pipeline.

Defines the :class:`Embedder` abstract base class and two concrete
implementations:

- :class:`OpenAIEmbedder` — calls the OpenAI Embeddings API in configurable
  batch sizes with exponential-backoff retry on rate-limit errors.
- :class:`HFEmbedder` — runs a local HuggingFace ``sentence-transformers``
  model (zero API cost, privacy-preserving).

The public interface (``embed_text``, ``embed_batch``) is identical to the
Backend's ``embedder.py`` so that both systems always produce vectors with the
same shape. Divergence causes silent k-NN dimension mismatches.
"""

import logging
import time
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class Embedder(ABC):
    """Abstract base for all embedding providers."""

    @abstractmethod
    def embed_text(self, text: str) -> list[float]:
        """Embed a single *text* string and return a vector."""

    @abstractmethod
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of *texts* and return a list of vectors."""


class OpenAIEmbedder(Embedder):
    """Embeds text via the OpenAI Embeddings API.

    Args:
        api_key:    OpenAI API key.
        model:      Model name (e.g. ``"text-embedding-3-small"``).
        batch_size: Maximum number of texts per API request (default 32).
    """

    def __init__(self, api_key: str, model: str, batch_size: int = 32) -> None:
        self._api_key = api_key
        self._model = model
        self._batch_size = batch_size

    def embed_text(self, text: str) -> list[float]:
        """Embed a single text string."""
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed *texts* in batches of ``batch_size``.

        Implements exponential back-off (up to 3 retries, sleeping ``2^retry``
        seconds) on :class:`openai.RateLimitError`.  If the rate limit is still
        hit after three retries the error is re-raised as :class:`RuntimeError`.
        """
        import openai  # noqa: PLC0415

        client = openai.OpenAI(api_key=self._api_key)
        all_embeddings: list[list[float]] = []

        for i in range(0, len(texts), self._batch_size):
            batch = texts[i : i + self._batch_size]
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    response = client.embeddings.create(input=batch, model=self._model)
                    batch_embeddings = [item.embedding for item in response.data]
                    all_embeddings.extend(batch_embeddings)
                    break
                except openai.RateLimitError:
                    if attempt < max_retries - 1:
                        sleep_time = 2 ** attempt
                        logger.warning(
                            "OpenAI rate limit hit; retrying in %s seconds (attempt %d/%d)",
                            sleep_time,
                            attempt + 1,
                            max_retries,
                        )
                        time.sleep(sleep_time)
                    else:
                        raise RuntimeError("Rate limit exceeded after retries")

        return all_embeddings


class HFEmbedder(Embedder):
    """Embeds text using a local HuggingFace ``sentence-transformers`` model.

    Args:
        model_name: HuggingFace model name (e.g. ``"all-MiniLM-L6-v2"``).
    """

    def __init__(self, model_name: str) -> None:
        from sentence_transformers import SentenceTransformer  # noqa: PLC0415

        self._model = SentenceTransformer(model_name)

    def embed_text(self, text: str) -> list[float]:
        """Embed a single text string."""
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of texts and return a list of float vectors."""
        vectors = self._model.encode(texts, convert_to_numpy=False)
        return [v.tolist() for v in vectors]


def get_embedder(settings: object) -> Embedder:
    """Factory that returns the correct :class:`Embedder` for *settings*.

    Returns:
        :class:`OpenAIEmbedder` when ``settings.embedding_provider == "openai"``,
        otherwise :class:`HFEmbedder` using ``settings.embedding_model``.
    """
    provider = getattr(settings, "embedding_provider", "openai")
    if provider == "openai":
        api_key = getattr(settings, "openai_api_key", None) or ""
        model = getattr(settings, "embedding_model", "text-embedding-3-small")
        batch_size = getattr(settings, "embedding_batch_size", 32)
        return OpenAIEmbedder(api_key=api_key, model=model, batch_size=batch_size)
    else:
        model_name = getattr(settings, "embedding_model", "all-MiniLM-L6-v2")
        return HFEmbedder(model_name=model_name)
