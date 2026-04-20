"""Chunker for the RAG Data Import pipeline.

Implements the strategy pattern for text chunking. The active strategy is
selected by ``settings.chunking_strategy``.

Supported strategies:
- ``fixed``     — fixed-size character windows with overlap
- ``recursive`` — LangChain RecursiveCharacterTextSplitter
- ``sentence``  — sentence-boundary splitting with configurable overlap (in sentences)
- ``semantic``  — LangChain SemanticChunker (requires embedding model; only
                  instantiated when CHUNKING_STRATEGY=semantic)
"""

import re
from abc import ABC, abstractmethod

from src.models import Chunk


class ChunkingStrategy(ABC):
    """Abstract base for all chunking strategies."""

    @abstractmethod
    def chunk(self, text: str, metadata: dict[str, object]) -> list[Chunk]:
        """Split *text* into :class:`Chunk` objects, forwarding *metadata*."""


class FixedSizeStrategy(ChunkingStrategy):
    """Splits text into fixed-size character windows with overlap.

    Args:
        chunk_size:    Maximum number of characters per window.
        chunk_overlap: Number of characters to carry over into the next window.
    """

    def __init__(self, chunk_size: int, chunk_overlap: int) -> None:
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap

    def chunk(self, text: str, metadata: dict[str, object]) -> list[Chunk]:
        chunks: list[Chunk] = []
        start = 0
        index = 0

        while start < len(text):
            end = start + self._chunk_size
            window = text[start:end]
            chunks.append(
                Chunk(
                    doc_id=str(metadata["doc_id"]),
                    content=window,
                    source=str(metadata["source"]),
                    doc_type=str(metadata["doc_type"]),
                    chunk_index=index,
                    page_number=metadata.get("page_number"),  # type: ignore[arg-type]
                )
            )
            index += 1
            # Advance by (chunk_size - overlap); always move at least 1 char.
            step = self._chunk_size - self._chunk_overlap
            if step <= 0:
                step = 1
            start += step

        return chunks


class RecursiveStrategy(ChunkingStrategy):
    """Uses LangChain's RecursiveCharacterTextSplitter.

    Args:
        chunk_size:    Maximum characters per chunk.
        chunk_overlap: Characters of overlap between consecutive chunks.
    """

    def __init__(self, chunk_size: int, chunk_overlap: int) -> None:
        from langchain_text_splitters import RecursiveCharacterTextSplitter  # noqa: PLC0415

        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size, chunk_overlap=chunk_overlap
        )

    def chunk(self, text: str, metadata: dict[str, object]) -> list[Chunk]:
        pieces = self._splitter.split_text(text)
        return [
            Chunk(
                doc_id=str(metadata["doc_id"]),
                content=piece,
                source=str(metadata["source"]),
                doc_type=str(metadata["doc_type"]),
                chunk_index=i,
                page_number=metadata.get("page_number"),  # type: ignore[arg-type]
            )
            for i, piece in enumerate(pieces)
        ]


# Regex to detect sentence-ending punctuation followed by a space or end-of-string.
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


class SentenceStrategy(ChunkingStrategy):
    """Splits on sentence boundaries and groups sentences into size-bounded chunks.

    Args:
        chunk_size:    Target maximum number of *characters* per chunk.
        chunk_overlap: Number of *sentences* to carry over into the next chunk.
    """

    def __init__(self, chunk_size: int, chunk_overlap: int) -> None:
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap

    def _split_sentences(self, text: str) -> list[str]:
        """Split *text* on sentence-ending punctuation."""
        sentences = _SENTENCE_SPLIT_RE.split(text)
        return [s.strip() for s in sentences if s.strip()]

    def chunk(self, text: str, metadata: dict[str, object]) -> list[Chunk]:
        sentences = self._split_sentences(text)
        if not sentences:
            return []

        chunks: list[Chunk] = []
        index = 0
        i = 0

        while i < len(sentences):
            group: list[str] = []
            current_len = 0

            j = i
            while j < len(sentences):
                sentence = sentences[j]
                added_len = len(sentence) + (1 if group else 0)  # +1 for space separator
                if group and current_len + added_len > self._chunk_size:
                    break
                group.append(sentence)
                current_len += added_len
                j += 1

            # Ensure we always advance at least one sentence to prevent infinite loop.
            if j == i:
                group.append(sentences[i])
                j = i + 1

            content = " ".join(group)
            chunks.append(
                Chunk(
                    doc_id=str(metadata["doc_id"]),
                    content=content,
                    source=str(metadata["source"]),
                    doc_type=str(metadata["doc_type"]),
                    chunk_index=index,
                    page_number=metadata.get("page_number"),  # type: ignore[arg-type]
                )
            )
            index += 1

            # Advance with overlap: carry over `chunk_overlap` sentences.
            advance = max(1, len(group) - self._chunk_overlap)
            i += advance

        return chunks


class SemanticStrategy(ChunkingStrategy):
    """Uses LangChain SemanticChunker for embedding-similarity-based chunking.

    Only instantiated when ``CHUNKING_STRATEGY=semantic`` to avoid loading
    embedding models by default.

    Args:
        embedder: An :class:`~src.embedder.Embedder` instance used to embed
                  text for semantic boundary detection.
    """

    def __init__(self, embedder: object) -> None:
        try:
            from langchain_experimental.text_splitter import SemanticChunker  # noqa: PLC0415
            from langchain_core.embeddings import Embeddings  # noqa: PLC0415

            self._chunker = SemanticChunker(embeddings=embedder)  # type: ignore[arg-type]
        except Exception as exc:
            raise RuntimeError(f"Failed to initialise SemanticChunker: {exc}") from exc

    def chunk(self, text: str, metadata: dict[str, object]) -> list[Chunk]:
        try:
            docs = self._chunker.create_documents([text])
        except Exception as exc:
            raise RuntimeError(f"SemanticChunker embedding failed: {exc}") from exc

        return [
            Chunk(
                doc_id=str(metadata["doc_id"]),
                content=doc.page_content,
                source=str(metadata["source"]),
                doc_type=str(metadata["doc_type"]),
                chunk_index=i,
                page_number=metadata.get("page_number"),  # type: ignore[arg-type]
            )
            for i, doc in enumerate(docs)
        ]


class Chunker:
    """Pipeline-facing chunker that selects a strategy from ``settings``.

    Args:
        settings: A :class:`~src.config.Settings` instance. The
                  ``chunking_strategy``, ``chunk_size``, and ``chunk_overlap``
                  fields are used to build the active strategy.
    """

    def __init__(self, settings: object) -> None:
        self._settings = settings
        self._strategy = self._build_strategy()

    def _build_strategy(self) -> ChunkingStrategy:
        s = self._settings
        strategy_name = getattr(s, "chunking_strategy", "recursive")
        chunk_size = getattr(s, "chunk_size", 512)
        chunk_overlap = getattr(s, "chunk_overlap", 64)

        if strategy_name == "fixed":
            return FixedSizeStrategy(chunk_size, chunk_overlap)
        elif strategy_name == "recursive":
            return RecursiveStrategy(chunk_size, chunk_overlap)
        elif strategy_name == "sentence":
            return SentenceStrategy(chunk_size, chunk_overlap)
        elif strategy_name == "semantic":
            # Lazy import to avoid loading embedding models unless needed.
            from src.embedder import get_embedder  # noqa: PLC0415

            embedder = get_embedder(s)
            return SemanticStrategy(embedder)
        else:
            raise ValueError(
                f"Unknown chunking strategy '{strategy_name}'. "
                "Valid values: fixed, recursive, sentence, semantic."
            )

    def chunk(
        self,
        text: str,
        source: str,
        doc_id: str,
        doc_type: str,
        page_number: int | None = None,
    ) -> list[Chunk]:
        """Chunk *text* and return a list of :class:`Chunk` objects.

        Args:
            text:        Cleaned text to split.
            source:      File path or URL of the parent document.
            doc_id:      UUID of the parent document.
            doc_type:    Document type (``pdf``, ``txt``, etc.).
            page_number: Page number for PDF sources; ``None`` otherwise.
        """
        metadata: dict[str, object] = {
            "source": source,
            "doc_id": doc_id,
            "doc_type": doc_type,
            "page_number": page_number,
        }
        return self._strategy.chunk(text, metadata)
