"""Unit tests for src/models.py — RawDocument and Chunk dataclasses."""

import uuid

from src.models import Chunk, RawDocument


class TestRawDocument:
    def test_auto_generates_doc_id(self) -> None:
        doc = RawDocument(content="hello", source="/tmp/file.txt", doc_type="txt")
        # Should be a valid UUID4 string
        parsed = uuid.UUID(doc.doc_id, version=4)
        assert str(parsed) == doc.doc_id

    def test_two_instances_have_different_doc_ids(self) -> None:
        doc1 = RawDocument(content="hello", source="/tmp/a.txt", doc_type="txt")
        doc2 = RawDocument(content="world", source="/tmp/b.txt", doc_type="txt")
        assert doc1.doc_id != doc2.doc_id

    def test_loaded_at_is_set(self) -> None:
        doc = RawDocument(content="hello", source="/tmp/file.txt", doc_type="txt")
        assert doc.loaded_at is not None


class TestChunk:
    def test_auto_generates_chunk_id(self) -> None:
        chunk = Chunk(
            doc_id="some-doc-id",
            content="some content",
            source="/tmp/file.txt",
            doc_type="txt",
            chunk_index=0,
        )
        parsed = uuid.UUID(chunk.chunk_id, version=4)
        assert str(parsed) == chunk.chunk_id

    def test_two_chunks_have_different_chunk_ids(self) -> None:
        chunk1 = Chunk(
            doc_id="doc-id",
            content="content 1",
            source="/tmp/file.txt",
            doc_type="txt",
            chunk_index=0,
        )
        chunk2 = Chunk(
            doc_id="doc-id",
            content="content 2",
            source="/tmp/file.txt",
            doc_type="txt",
            chunk_index=1,
        )
        assert chunk1.chunk_id != chunk2.chunk_id

    def test_page_number_defaults_to_none(self) -> None:
        chunk = Chunk(
            doc_id="doc-id",
            content="content",
            source="/tmp/file.txt",
            doc_type="txt",
            chunk_index=0,
        )
        assert chunk.page_number is None
