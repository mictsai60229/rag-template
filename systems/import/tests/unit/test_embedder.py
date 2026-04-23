"""Unit tests for src/embedder.py.

All external calls (OpenAI API, SentenceTransformer) are mocked so no real
network or model inference is performed.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.embedder import HFEmbedder, OpenAIEmbedder, get_embedder


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_embedding_response(n: int, dim: int = 4) -> MagicMock:
    """Build a mock openai embeddings.create response with *n* embeddings of *dim* floats."""
    response = MagicMock()
    response.data = [MagicMock(embedding=[0.1] * dim) for _ in range(n)]
    return response


# ---------------------------------------------------------------------------
# OpenAIEmbedder tests
# ---------------------------------------------------------------------------


class TestOpenAIEmbedder:
    def test_embed_text_returns_list_of_float(self) -> None:
        """embed_text should return list[float]."""
        with patch("openai.OpenAI") as mock_openai_cls:
            mock_client = MagicMock()
            mock_openai_cls.return_value = mock_client
            mock_client.embeddings.create.return_value = _make_embedding_response(1, dim=4)

            embedder = OpenAIEmbedder(api_key="test-key", model="text-embedding-3-small")
            result = embedder.embed_text("hello world")

        assert isinstance(result, list)
        assert all(isinstance(v, float) for v in result)
        assert len(result) == 4

    def test_embed_batch_splits_into_batches(self) -> None:
        """embed_batch with batch_size=25 and 100 texts should call create 4 times."""
        with patch("openai.OpenAI") as mock_openai_cls:
            mock_client = MagicMock()
            mock_openai_cls.return_value = mock_client
            # Each create call returns 25 embeddings.
            mock_client.embeddings.create.return_value = _make_embedding_response(25, dim=4)

            embedder = OpenAIEmbedder(
                api_key="test-key", model="text-embedding-3-small", batch_size=25
            )
            texts = [f"text {i}" for i in range(100)]
            results = embedder.embed_batch(texts)

        assert mock_client.embeddings.create.call_count == 4
        assert len(results) == 100

    def test_embed_batch_smaller_than_batch_size(self) -> None:
        """embed_batch with fewer texts than batch_size makes exactly one call."""
        with patch("openai.OpenAI") as mock_openai_cls:
            mock_client = MagicMock()
            mock_openai_cls.return_value = mock_client
            mock_client.embeddings.create.return_value = _make_embedding_response(5, dim=4)

            embedder = OpenAIEmbedder(
                api_key="test-key", model="text-embedding-3-small", batch_size=32
            )
            results = embedder.embed_batch(["a", "b", "c", "d", "e"])

        assert mock_client.embeddings.create.call_count == 1
        assert len(results) == 5

    def test_exponential_backoff_raises_runtime_error_after_retries(self) -> None:
        """If RateLimitError fires 3 times, RuntimeError should be raised."""
        import openai

        with patch("openai.OpenAI") as mock_openai_cls, patch("time.sleep") as mock_sleep:
            mock_client = MagicMock()
            mock_openai_cls.return_value = mock_client
            mock_client.embeddings.create.side_effect = openai.RateLimitError(
                message="rate limit", response=MagicMock(), body={}
            )

            embedder = OpenAIEmbedder(api_key="test-key", model="text-embedding-3-small")

            with pytest.raises(RuntimeError, match="Rate limit exceeded after retries"):
                embedder.embed_batch(["test"])

        # Should have slept between the first two retries (not after the third failure).
        assert mock_client.embeddings.create.call_count == 3
        assert mock_sleep.call_count == 2  # sleeps between attempts 1→2 and 2→3

    def test_exponential_backoff_sleep_durations(self) -> None:
        """Backoff sleeps should follow 2^attempt seconds (1s, 2s)."""
        import openai

        with patch("openai.OpenAI") as mock_openai_cls, patch("time.sleep") as mock_sleep:
            mock_client = MagicMock()
            mock_openai_cls.return_value = mock_client
            mock_client.embeddings.create.side_effect = openai.RateLimitError(
                message="rate limit", response=MagicMock(), body={}
            )

            embedder = OpenAIEmbedder(api_key="test-key", model="text-embedding-3-small")

            with pytest.raises(RuntimeError):
                embedder.embed_batch(["test"])

        sleep_calls = [call.args[0] for call in mock_sleep.call_args_list]
        assert sleep_calls == [1, 2]  # 2^0=1, 2^1=2


# ---------------------------------------------------------------------------
# HFEmbedder tests
# ---------------------------------------------------------------------------


class TestHFEmbedder:
    def test_embed_batch_returns_correct_shape(self) -> None:
        """embed_batch should return list[list[float]] with correct dimensions."""
        with patch("sentence_transformers.SentenceTransformer") as mock_st_cls:
            mock_model = MagicMock()
            mock_st_cls.return_value = mock_model
            # Simulate encode returning a list of 3 vectors of dim 8.
            mock_model.encode.return_value = [[0.1] * 8 for _ in range(3)]

            embedder = HFEmbedder(model_name="all-MiniLM-L6-v2")
            results = embedder.embed_batch(["a", "b", "c"])

        assert len(results) == 3
        assert all(len(v) == 8 for v in results)
        assert all(isinstance(v, list) for v in results)
        mock_model.encode.assert_called_once_with(["a", "b", "c"], convert_to_numpy=False)

    def test_embed_text_delegates_to_embed_batch(self) -> None:
        """embed_text should return the first element of embed_batch([text])."""
        with patch("sentence_transformers.SentenceTransformer") as mock_st_cls:
            mock_model = MagicMock()
            mock_st_cls.return_value = mock_model
            mock_model.encode.return_value = [[0.5, 0.6, 0.7]]

            embedder = HFEmbedder(model_name="all-MiniLM-L6-v2")
            result = embedder.embed_text("hello")

        assert result == [0.5, 0.6, 0.7]


# ---------------------------------------------------------------------------
# get_embedder factory tests
# ---------------------------------------------------------------------------


class TestGetEmbedder:
    def test_returns_openai_embedder_when_provider_is_openai(self) -> None:
        settings = MagicMock()
        settings.embedding_provider = "openai"
        settings.openai_api_key = "key"
        settings.embedding_model = "text-embedding-3-small"
        settings.embedding_batch_size = 32

        embedder = get_embedder(settings)
        assert isinstance(embedder, OpenAIEmbedder)

    def test_returns_hf_embedder_when_provider_is_not_openai(self) -> None:
        with patch("sentence_transformers.SentenceTransformer"):
            settings = MagicMock()
            settings.embedding_provider = "huggingface"
            settings.embedding_model = "all-MiniLM-L6-v2"

            embedder = get_embedder(settings)

        assert isinstance(embedder, HFEmbedder)
