"""Embedder abstract base class and concrete implementations.

This is the only file in ``src/`` that imports ``openai`` or ``sentence_transformers``.
All other modules depend only on the ``Embedder`` ABC.

Usage::

    embedder = OpenAIEmbedder(api_key="sk-...", model="text-embedding-3-small", batch_size=32)
    vector = embedder.embed_text("What is Python?")
"""

import time
from abc import ABC, abstractmethod

from src.exceptions.domain import ExternalServiceError


class Embedder(ABC):
    """Abstract base class for text embedding providers.

    Concrete implementations must be swappable via config without any other
    code change. Both methods must return ``list[float]`` vectors of consistent
    dimensionality for a given model.
    """

    @abstractmethod
    def embed_text(self, text: str) -> list[float]:
        """Embed a single string and return a dense vector.

        Args:
            text: The input text to embed.

        Returns:
            A list of floats representing the embedding vector.
        """
        ...

    @abstractmethod
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of strings and return a list of dense vectors.

        Args:
            texts: The input texts to embed.

        Returns:
            A list of embedding vectors, one per input text.
        """
        ...


class OpenAIEmbedder(Embedder):
    """Embedder backed by the OpenAI Embeddings API.

    Splits ``embed_batch`` requests into chunks of ``batch_size`` to stay within
    API limits. Retries on ``RateLimitError`` with exponential back-off (2^n
    seconds, up to ``_MAX_RETRIES`` attempts) before raising ``ExternalServiceError``.
    """

    _MAX_RETRIES = 3

    def __init__(self, api_key: str, model: str, batch_size: int = 32) -> None:
        """Initialise the OpenAI embedder.

        Args:
            api_key: OpenAI API key.
            model: Embeddings model name (e.g. ``"text-embedding-3-small"``).
            batch_size: Maximum number of texts per API call.
        """
        import openai  # lazy import — keeps sentence-transformers optional

        self._openai = openai
        self._api_key = api_key
        self._model = model
        self._batch_size = batch_size

    def embed_text(self, text: str) -> list[float]:
        """Embed a single string."""
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of strings, splitting into batches of ``batch_size``.

        Args:
            texts: Input texts.

        Returns:
            List of embedding vectors in the same order as ``texts``.

        Raises:
            ExternalServiceError: When all retries on ``RateLimitError`` are exhausted
                or on any other API-level error after retries.
        """
        results: list[list[float]] = []
        client = self._openai.OpenAI(api_key=self._api_key)

        for batch_start in range(0, len(texts), self._batch_size):
            batch = texts[batch_start : batch_start + self._batch_size]
            for attempt in range(self._MAX_RETRIES):
                try:
                    response = client.embeddings.create(input=batch, model=self._model)
                    results.extend([item.embedding for item in response.data])
                    break
                except self._openai.RateLimitError as exc:
                    if attempt == self._MAX_RETRIES - 1:
                        raise ExternalServiceError(
                            f"OpenAI rate limit exceeded after {self._MAX_RETRIES} retries: {exc}"
                        ) from exc
                    sleep_seconds = 2 ** (attempt + 1)
                    time.sleep(sleep_seconds)

        return results


class HFEmbedder(Embedder):
    """Embedder backed by a local HuggingFace ``sentence-transformers`` model.

    The model is loaded once at construction time and never makes network calls
    at embed time (assuming the model is already cached locally).
    """

    def __init__(self, model_name: str) -> None:
        """Initialise the HuggingFace embedder by loading the model.

        Args:
            model_name: Name or path of the sentence-transformers model.
        """
        from sentence_transformers import SentenceTransformer  # lazy import — optional dep

        self._model = SentenceTransformer(model_name)

    def embed_text(self, text: str) -> list[float]:
        """Embed a single string."""
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of strings using the loaded model.

        Args:
            texts: Input texts.

        Returns:
            List of embedding vectors.
        """
        vectors = self._model.encode(texts, convert_to_numpy=False)
        return [list(v) for v in vectors]
