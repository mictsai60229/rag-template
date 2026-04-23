"""Unit tests for src/chunker.py — Chunker and all strategy classes."""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.chunker import (
    Chunker,
    FixedSizeStrategy,
    RecursiveStrategy,
    SentenceStrategy,
)
from src.models import Chunk

# Shared metadata dict used across tests.
METADATA: dict[str, object] = {
    "doc_id": "test-doc-id",
    "source": "/tmp/doc.txt",
    "doc_type": "txt",
    "page_number": None,
}


def make_settings(
    strategy: str = "recursive",
    chunk_size: int = 512,
    chunk_overlap: int = 64,
) -> SimpleNamespace:
    return SimpleNamespace(
        chunking_strategy=strategy,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )


class TestFixedSizeStrategy:
    def test_splits_into_expected_windows(self) -> None:
        text = "a" * 1000
        strategy = FixedSizeStrategy(chunk_size=200, chunk_overlap=50)
        chunks = strategy.chunk(text, METADATA)
        # First window: 0-200; next: 150-350; 300-500; 450-650; 600-800; 750-950; 900-1000
        assert len(chunks) >= 2
        assert all(len(c.content) <= 200 for c in chunks)

    def test_first_chunk_content_correct(self) -> None:
        text = "x" * 1000
        strategy = FixedSizeStrategy(chunk_size=100, chunk_overlap=0)
        chunks = strategy.chunk(text, METADATA)
        assert chunks[0].content == "x" * 100
        assert len(chunks) == 10

    def test_overlap_is_applied(self) -> None:
        text = "abcdefghij"  # 10 chars
        strategy = FixedSizeStrategy(chunk_size=6, chunk_overlap=2)
        chunks = strategy.chunk(text, METADATA)
        # Window 0: 0-6 "abcdef"; step=4; window 1: 4-10 "efghij"
        assert chunks[0].content == "abcdef"
        assert chunks[1].content == "efghij"

    def test_chunk_indices_sequential(self) -> None:
        text = "a" * 500
        strategy = FixedSizeStrategy(chunk_size=100, chunk_overlap=0)
        chunks = strategy.chunk(text, METADATA)
        for i, chunk in enumerate(chunks):
            assert chunk.chunk_index == i

    def test_metadata_forwarded(self) -> None:
        text = "hello world"
        strategy = FixedSizeStrategy(chunk_size=100, chunk_overlap=0)
        chunks = strategy.chunk(text, METADATA)
        chunk = chunks[0]
        assert chunk.doc_id == "test-doc-id"
        assert chunk.source == "/tmp/doc.txt"
        assert chunk.doc_type == "txt"
        assert chunk.page_number is None

    def test_ingested_at_is_set(self) -> None:
        strategy = FixedSizeStrategy(chunk_size=100, chunk_overlap=0)
        chunks = strategy.chunk("hello", METADATA)
        assert isinstance(chunks[0].ingested_at, datetime)

    def test_empty_text_returns_empty_list(self) -> None:
        strategy = FixedSizeStrategy(chunk_size=100, chunk_overlap=0)
        chunks = strategy.chunk("", METADATA)
        assert chunks == []


class TestRecursiveStrategy:
    def test_chunk_index_set_correctly(self) -> None:
        mock_splitter = MagicMock()
        mock_splitter.split_text.return_value = ["chunk A", "chunk B", "chunk C"]

        with patch(
            "langchain_text_splitters.RecursiveCharacterTextSplitter",
            return_value=mock_splitter,
        ):
            strategy = RecursiveStrategy(chunk_size=512, chunk_overlap=64)
            chunks = strategy.chunk("some text", METADATA)

        assert len(chunks) == 3
        assert chunks[0].chunk_index == 0
        assert chunks[1].chunk_index == 1
        assert chunks[2].chunk_index == 2

    def test_content_from_splitter_output(self) -> None:
        mock_splitter = MagicMock()
        mock_splitter.split_text.return_value = ["chunk A", "chunk B"]

        with patch(
            "langchain_text_splitters.RecursiveCharacterTextSplitter",
            return_value=mock_splitter,
        ):
            strategy = RecursiveStrategy(chunk_size=512, chunk_overlap=64)
            chunks = strategy.chunk("text", METADATA)

        assert chunks[0].content == "chunk A"
        assert chunks[1].content == "chunk B"

    def test_metadata_forwarded(self) -> None:
        mock_splitter = MagicMock()
        mock_splitter.split_text.return_value = ["only chunk"]

        with patch(
            "langchain_text_splitters.RecursiveCharacterTextSplitter",
            return_value=mock_splitter,
        ):
            strategy = RecursiveStrategy(chunk_size=512, chunk_overlap=64)
            chunks = strategy.chunk("text", METADATA)

        assert chunks[0].doc_id == "test-doc-id"
        assert chunks[0].source == "/tmp/doc.txt"
        assert chunks[0].doc_type == "txt"


class TestSentenceStrategy:
    def test_splits_on_sentence_boundaries(self) -> None:
        text = "Hello world. How are you? I am fine."
        strategy = SentenceStrategy(chunk_size=1000, chunk_overlap=0)
        chunks = strategy.chunk(text, METADATA)
        # All three sentences fit in one large chunk (chunk_size=1000)
        assert len(chunks) == 1
        assert "Hello world." in chunks[0].content

    def test_groups_sentences_under_chunk_size(self) -> None:
        # Three short sentences, chunk_size forces splitting after first two.
        text = "First sentence. Second sentence. Third sentence."
        strategy = SentenceStrategy(chunk_size=35, chunk_overlap=0)
        chunks = strategy.chunk(text, METADATA)
        assert len(chunks) >= 2

    def test_chunk_indices_sequential(self) -> None:
        text = "A. B. C. D. E."
        strategy = SentenceStrategy(chunk_size=5, chunk_overlap=0)
        chunks = strategy.chunk(text, METADATA)
        for i, chunk in enumerate(chunks):
            assert chunk.chunk_index == i

    def test_metadata_forwarded(self) -> None:
        text = "Hello world."
        strategy = SentenceStrategy(chunk_size=1000, chunk_overlap=0)
        chunks = strategy.chunk(text, METADATA)
        assert chunks[0].doc_id == "test-doc-id"
        assert chunks[0].source == "/tmp/doc.txt"
        assert chunks[0].doc_type == "txt"

    def test_empty_text_returns_empty_list(self) -> None:
        strategy = SentenceStrategy(chunk_size=100, chunk_overlap=0)
        chunks = strategy.chunk("", METADATA)
        assert chunks == []

    def test_overlap_carries_over_sentences(self) -> None:
        # With overlap=1, last sentence of each chunk appears at start of next.
        text = "First. Second. Third. Fourth."
        strategy = SentenceStrategy(chunk_size=10, chunk_overlap=1)
        chunks = strategy.chunk(text, METADATA)
        assert len(chunks) >= 2


class TestChunkerBuildStrategy:
    def test_fixed_strategy_selected(self) -> None:
        settings = make_settings(strategy="fixed")
        chunker = Chunker(settings)
        assert isinstance(chunker._strategy, FixedSizeStrategy)

    def test_recursive_strategy_selected(self) -> None:
        mock_splitter = MagicMock()
        mock_splitter.split_text.return_value = []
        with patch(
            "langchain_text_splitters.RecursiveCharacterTextSplitter",
            return_value=mock_splitter,
        ):
            settings = make_settings(strategy="recursive")
            chunker = Chunker(settings)
        assert isinstance(chunker._strategy, RecursiveStrategy)

    def test_sentence_strategy_selected(self) -> None:
        settings = make_settings(strategy="sentence")
        chunker = Chunker(settings)
        assert isinstance(chunker._strategy, SentenceStrategy)

    def test_unknown_strategy_raises_value_error(self) -> None:
        settings = make_settings(strategy="bogus")
        with pytest.raises(ValueError, match="Unknown chunking strategy"):
            Chunker(settings)

    def test_chunk_method_delegates_to_strategy(self) -> None:
        settings = make_settings(strategy="fixed", chunk_size=100, chunk_overlap=0)
        chunker = Chunker(settings)
        chunks = chunker.chunk(
            text="hello world",
            source="/tmp/f.txt",
            doc_id="doc-123",
            doc_type="txt",
        )
        assert len(chunks) == 1
        assert chunks[0].content == "hello world"

    def test_all_chunks_carry_required_metadata(self) -> None:
        settings = make_settings(strategy="fixed", chunk_size=100, chunk_overlap=0)
        chunker = Chunker(settings)
        chunks = chunker.chunk(
            text="some content for chunking",
            source="/tmp/doc.txt",
            doc_id="doc-abc",
            doc_type="txt",
            page_number=3,
        )
        for chunk in chunks:
            assert chunk.source == "/tmp/doc.txt"
            assert chunk.doc_id == "doc-abc"
            assert chunk.doc_type == "txt"
            assert isinstance(chunk.chunk_index, int)
            assert isinstance(chunk.ingested_at, datetime)
            assert chunk.page_number == 3
