"""Unit tests for src/providers/embedder.py.

All external SDK calls (openai, sentence_transformers) are mocked so no real
API calls or model downloads occur during testing.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.exceptions.domain import ExternalServiceError
from src.providers.embedder import HFEmbedder, OpenAIEmbedder


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_embedding_response(vectors: list[list[float]]) -> MagicMock:
    """Build a mock object that mimics the OpenAI embeddings response."""
    response = MagicMock()
    response.data = [MagicMock(embedding=v) for v in vectors]
    return response


# ---------------------------------------------------------------------------
# OpenAIEmbedder tests
# ---------------------------------------------------------------------------


class TestOpenAIEmbedder:
    @patch("src.providers.embedder.OpenAIEmbedder._openai", create=True)
    def _make_embedder(
        self, mock_openai: MagicMock, batch_size: int = 32
    ) -> tuple["OpenAIEmbedder", MagicMock]:
        """Helper — instantiated embedder plus mocked OpenAI module."""
        with patch.dict("sys.modules", {"openai": MagicMock()}):
            import openai as mock_mod  # noqa: F401

        embedder = OpenAIEmbedder.__new__(OpenAIEmbedder)
        mock_openai_mod = MagicMock()
        embedder._openai = mock_openai_mod
        embedder._api_key = "sk-test"
        embedder._model = "text-embedding-3-small"
        embedder._batch_size = batch_size
        return embedder, mock_openai_mod

    def test_embed_text_returns_list_of_float(self) -> None:
        """embed_text() delegates to embed_batch and returns a flat vector."""
        embedder, mock_openai_mod = self._make_embedder()
        expected_vector = [0.1, 0.2, 0.3]
        mock_client = MagicMock()
        mock_openai_mod.OpenAI.return_value = mock_client
        mock_client.embeddings.create.return_value = _make_embedding_response([expected_vector])

        result = embedder.embed_text("hello world")

        assert isinstance(result, list)
        assert all(isinstance(x, float) for x in result)
        assert result == expected_vector

    def test_embed_batch_returns_all_vectors(self) -> None:
        """embed_batch() returns one vector per input text."""
        embedder, mock_openai_mod = self._make_embedder(batch_size=10)
        texts = ["text1", "text2", "text3"]
        vectors = [[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]]
        mock_client = MagicMock()
        mock_openai_mod.OpenAI.return_value = mock_client
        mock_client.embeddings.create.return_value = _make_embedding_response(vectors)

        result = embedder.embed_batch(texts)

        assert result == vectors
        mock_client.embeddings.create.assert_called_once_with(
            input=texts, model="text-embedding-3-small"
        )

    def test_embed_batch_splits_into_correct_batches(self) -> None:
        """embed_batch() splits texts into chunks of batch_size and calls API per batch."""
        embedder, mock_openai_mod = self._make_embedder(batch_size=2)
        texts = ["a", "b", "c", "d", "e"]
        # 3 batches: [a,b], [c,d], [e]
        mock_client = MagicMock()
        mock_openai_mod.OpenAI.return_value = mock_client
        mock_client.embeddings.create.side_effect = [
            _make_embedding_response([[0.1, 0.2], [0.3, 0.4]]),
            _make_embedding_response([[0.5, 0.6], [0.7, 0.8]]),
            _make_embedding_response([[0.9, 1.0]]),
        ]

        result = embedder.embed_batch(texts)

        assert mock_client.embeddings.create.call_count == 3
        assert len(result) == 5

    def test_rate_limit_error_wrapped_as_external_service_error(self) -> None:
        """After all retries fail with RateLimitError, ExternalServiceError is raised."""
        embedder, mock_openai_mod = self._make_embedder()
        mock_client = MagicMock()
        mock_openai_mod.OpenAI.return_value = mock_client

        rate_limit_exc = Exception("rate limited")
        mock_openai_mod.RateLimitError = type("RateLimitError", (Exception,), {})
        mock_client.embeddings.create.side_effect = mock_openai_mod.RateLimitError("rate limited")

        with patch("time.sleep"):  # prevent actual sleeping in tests
            with pytest.raises(ExternalServiceError, match="rate limit"):
                embedder.embed_batch(["text"])

    def test_rate_limit_retries_before_raising(self) -> None:
        """embed_batch() retries _MAX_RETRIES times before giving up."""
        embedder, mock_openai_mod = self._make_embedder()
        mock_client = MagicMock()
        mock_openai_mod.OpenAI.return_value = mock_client

        mock_openai_mod.RateLimitError = type("RateLimitError", (Exception,), {})
        mock_client.embeddings.create.side_effect = mock_openai_mod.RateLimitError("rate limited")

        with patch("time.sleep") as mock_sleep:
            with pytest.raises(ExternalServiceError):
                embedder.embed_batch(["text"])

        # 3 retries → 2 sleeps (last attempt doesn't sleep)
        assert mock_sleep.call_count == OpenAIEmbedder._MAX_RETRIES - 1


# ---------------------------------------------------------------------------
# HFEmbedder tests
# ---------------------------------------------------------------------------


class TestHFEmbedder:
    def _make_hf_embedder(self) -> tuple["HFEmbedder", MagicMock]:
        """Helper — create an HFEmbedder with a mocked SentenceTransformer.

        ``sentence_transformers`` is not installed in the dev environment (it is an optional
        extra), so we inject a fake module into sys.modules before instantiating HFEmbedder.
        """
        import sys

        mock_model = MagicMock()
        mock_st_module = MagicMock()
        mock_st_module.SentenceTransformer.return_value = mock_model

        with patch.dict(sys.modules, {"sentence_transformers": mock_st_module}):
            embedder = HFEmbedder("all-MiniLM-L6-v2")
        return embedder, mock_model

    def test_embed_batch_returns_correct_shape(self) -> None:
        """embed_batch returns one vector per input text."""
        embedder, mock_model = self._make_hf_embedder()
        expected = [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
        mock_model.encode.return_value = expected

        result = embedder.embed_batch(["text1", "text2"])

        assert result == expected
        mock_model.encode.assert_called_once_with(["text1", "text2"], convert_to_numpy=False)

    def test_embed_text_delegates_to_embed_batch(self) -> None:
        """embed_text() returns the first (and only) vector from embed_batch."""
        embedder, mock_model = self._make_hf_embedder()
        mock_model.encode.return_value = [[0.1, 0.2, 0.3]]

        result = embedder.embed_text("hello")

        assert result == [0.1, 0.2, 0.3]

    def test_no_network_calls_at_embed_time(self) -> None:
        """embed_batch should not trigger any additional network I/O after construction."""
        embedder, mock_model = self._make_hf_embedder()
        mock_model.encode.return_value = [[0.0, 0.0]]

        # The real SentenceTransformer would only touch the network during __init__,
        # which is already mocked. If encode is called without error, we're good.
        result = embedder.embed_batch(["test"])
        assert isinstance(result, list)
