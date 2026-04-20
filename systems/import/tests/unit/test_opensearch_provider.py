"""Unit tests for src/providers/opensearch_provider.py.

All opensearch-py calls are mocked so no real OpenSearch instance is required.
"""

from typing import Any
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_provider(mock_os_cls: MagicMock) -> Any:
    """Instantiate OpenSearchProvider with a mocked opensearch-py client."""
    from src.providers.opensearch_provider import OpenSearchProvider

    mock_client = MagicMock()
    mock_os_cls.return_value = mock_client
    provider = OpenSearchProvider(host="localhost", port=9200, index="test-index")
    return provider, mock_client


# ---------------------------------------------------------------------------
# index_exists
# ---------------------------------------------------------------------------


class TestIndexExists:
    def test_returns_true_when_index_exists(self) -> None:
        with patch("opensearchpy.OpenSearch") as mock_os_cls:
            provider, mock_client = _make_provider(mock_os_cls)
            mock_client.indices.exists.return_value = True

            assert provider.index_exists() is True
            mock_client.indices.exists.assert_called_once_with(index="test-index")

    def test_returns_false_when_index_does_not_exist(self) -> None:
        with patch("opensearchpy.OpenSearch") as mock_os_cls:
            provider, mock_client = _make_provider(mock_os_cls)
            mock_client.indices.exists.return_value = False

            assert provider.index_exists() is False


# ---------------------------------------------------------------------------
# create_index
# ---------------------------------------------------------------------------


class TestCreateIndex:
    def test_calls_indices_create_with_mapping(self) -> None:
        with patch("opensearchpy.OpenSearch") as mock_os_cls:
            provider, mock_client = _make_provider(mock_os_cls)
            mock_client.indices.create.return_value = {"acknowledged": True}

            mapping = {"settings": {}, "mappings": {"properties": {}}}
            provider.create_index(mapping)

            mock_client.indices.create.assert_called_once_with(
                index="test-index", body=mapping
            )

    def test_raises_if_not_acknowledged(self) -> None:
        with patch("opensearchpy.OpenSearch") as mock_os_cls:
            provider, mock_client = _make_provider(mock_os_cls)
            mock_client.indices.create.return_value = {"acknowledged": False}

            with pytest.raises(RuntimeError, match="not acknowledged"):
                provider.create_index({})


# ---------------------------------------------------------------------------
# delete_index
# ---------------------------------------------------------------------------


class TestDeleteIndex:
    def test_deletes_index_successfully(self) -> None:
        with patch("opensearchpy.OpenSearch") as mock_os_cls:
            provider, mock_client = _make_provider(mock_os_cls)
            mock_client.indices.delete.return_value = {"acknowledged": True}

            provider.delete_index()  # Should not raise
            mock_client.indices.delete.assert_called_once_with(index="test-index")

    def test_logs_warning_when_index_not_found(self) -> None:
        import opensearchpy

        with patch("opensearchpy.OpenSearch") as mock_os_cls:
            provider, mock_client = _make_provider(mock_os_cls)
            mock_client.indices.delete.side_effect = opensearchpy.exceptions.NotFoundError(
                404, "index_not_found_exception", {"_index": "test-index"}
            )

            # Should not raise — just log a warning.
            provider.delete_index()


# ---------------------------------------------------------------------------
# bulk_index
# ---------------------------------------------------------------------------


class TestBulkIndex:
    def test_builds_correct_ndjson(self) -> None:
        """bulk_index should alternate action/doc lines in the body."""
        with patch("opensearchpy.OpenSearch") as mock_os_cls:
            provider, mock_client = _make_provider(mock_os_cls)
            mock_client.bulk.return_value = {"errors": False, "items": []}

            docs = [
                {"chunk_id": "id-1", "content": "hello"},
                {"chunk_id": "id-2", "content": "world"},
            ]
            provider.bulk_index(docs)

            call_args = mock_client.bulk.call_args
            body = call_args.kwargs.get("body") or call_args.args[0]

            assert body[0] == {"index": {"_index": "test-index", "_id": "id-1"}}
            assert body[1] == {"chunk_id": "id-1", "content": "hello"}
            assert body[2] == {"index": {"_index": "test-index", "_id": "id-2"}}
            assert body[3] == {"chunk_id": "id-2", "content": "world"}

    def test_raises_runtime_error_when_response_has_errors(self) -> None:
        with patch("opensearchpy.OpenSearch") as mock_os_cls:
            provider, mock_client = _make_provider(mock_os_cls)
            mock_client.bulk.return_value = {
                "errors": True,
                "items": [
                    {"index": {"_id": "id-1", "error": {"type": "mapper_exception"}}},
                ],
            }

            with pytest.raises(RuntimeError, match="Bulk indexing completed with errors"):
                provider.bulk_index([{"chunk_id": "id-1", "content": "bad"}])

    def test_returns_empty_response_for_empty_documents(self) -> None:
        with patch("opensearchpy.OpenSearch") as mock_os_cls:
            provider, mock_client = _make_provider(mock_os_cls)

            result = provider.bulk_index([])

            mock_client.bulk.assert_not_called()
            assert result == {"errors": False, "items": []}


# ---------------------------------------------------------------------------
# OpenSearchException handling
# ---------------------------------------------------------------------------


class TestOpenSearchExceptionHandling:
    def test_opensearch_exception_reraised_as_runtime_error(self) -> None:
        import opensearchpy

        with patch("opensearchpy.OpenSearch") as mock_os_cls:
            provider, mock_client = _make_provider(mock_os_cls)
            mock_client.indices.exists.side_effect = opensearchpy.exceptions.ConnectionError(
                "E", "connection refused", {}
            )

            with pytest.raises(RuntimeError, match="OpenSearch error"):
                provider.index_exists()

    def test_non_opensearch_exception_propagates_unchanged(self) -> None:
        with patch("opensearchpy.OpenSearch") as mock_os_cls:
            provider, mock_client = _make_provider(mock_os_cls)
            mock_client.indices.exists.side_effect = ValueError("unexpected")

            with pytest.raises(ValueError, match="unexpected"):
                provider.index_exists()
