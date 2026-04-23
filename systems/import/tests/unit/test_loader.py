"""Unit tests for src/loader.py — DocumentLoader."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.loader import DocumentLoader
from src.models import RawDocument

# Absolute path to the fixtures directory next to this test file.
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"


class TestLoadTxt:
    def test_returns_one_raw_document(self) -> None:
        loader = DocumentLoader()
        docs = loader._load_txt(str(FIXTURES_DIR / "sample.txt"))
        assert len(docs) == 1
        assert isinstance(docs[0], RawDocument)

    def test_doc_type_is_txt(self) -> None:
        loader = DocumentLoader()
        docs = loader._load_txt(str(FIXTURES_DIR / "sample.txt"))
        assert docs[0].doc_type == "txt"

    def test_content_matches_file(self) -> None:
        loader = DocumentLoader()
        fixture = FIXTURES_DIR / "sample.txt"
        expected = fixture.read_text(encoding="utf-8")
        docs = loader._load_txt(str(fixture))
        assert docs[0].content == expected

    def test_source_is_file_path(self) -> None:
        loader = DocumentLoader()
        path = str(FIXTURES_DIR / "sample.txt")
        docs = loader._load_txt(path)
        assert docs[0].source == path


class TestLoadMd:
    def test_returns_one_raw_document(self) -> None:
        loader = DocumentLoader()
        docs = loader._load_md(str(FIXTURES_DIR / "sample.md"))
        assert len(docs) == 1

    def test_doc_type_is_md(self) -> None:
        loader = DocumentLoader()
        docs = loader._load_md(str(FIXTURES_DIR / "sample.md"))
        assert docs[0].doc_type == "md"

    def test_content_matches_file(self) -> None:
        loader = DocumentLoader()
        fixture = FIXTURES_DIR / "sample.md"
        expected = fixture.read_text(encoding="utf-8")
        docs = loader._load_md(str(fixture))
        assert docs[0].content == expected


class TestLoadUnsupportedExtension:
    def test_raises_value_error_for_csv(self) -> None:
        loader = DocumentLoader()
        with pytest.raises(ValueError, match="Unsupported file extension"):
            loader.load("/some/path/file.csv")

    def test_raises_value_error_for_json(self) -> None:
        loader = DocumentLoader()
        with pytest.raises(ValueError, match="Unsupported file extension"):
            loader.load("/some/path/data.json")


class TestLoadUrl:
    def test_returns_one_raw_document_with_doc_type_url(self) -> None:
        mock_response = MagicMock()
        mock_response.text = "<html><body><p>Hello world</p></body></html>"
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.get", return_value=mock_response) as mock_get:
            loader = DocumentLoader()
            docs = loader._load_url("https://example.com")

        mock_get.assert_called_once_with(
            "https://example.com", follow_redirects=True, timeout=30
        )
        assert len(docs) == 1
        assert docs[0].doc_type == "url"
        assert docs[0].source == "https://example.com"
        assert "Hello world" in docs[0].content

    def test_dispatched_via_load_method(self) -> None:
        mock_response = MagicMock()
        mock_response.text = "<html><body><p>Test</p></body></html>"
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.get", return_value=mock_response):
            loader = DocumentLoader()
            docs = loader.load("https://example.com")

        assert len(docs) == 1
        assert docs[0].doc_type == "url"


class TestLoadPdf:
    def test_returns_one_raw_document(self) -> None:
        mock_page1 = MagicMock()
        mock_page1.get_text.return_value = "Page one content."
        mock_page2 = MagicMock()
        mock_page2.get_text.return_value = "Page two content."

        mock_doc = MagicMock()
        mock_doc.__iter__ = MagicMock(return_value=iter([mock_page1, mock_page2]))

        with patch("pymupdf.open", return_value=mock_doc):
            loader = DocumentLoader()
            docs = loader._load_pdf("/fake/path.pdf")

        assert len(docs) == 1
        assert docs[0].doc_type == "pdf"
        assert "Page one content." in docs[0].content
        assert "Page two content." in docs[0].content

    def test_source_set_to_path(self) -> None:
        mock_doc = MagicMock()
        mock_doc.__iter__ = MagicMock(return_value=iter([]))

        with patch("pymupdf.open", return_value=mock_doc):
            loader = DocumentLoader()
            docs = loader._load_pdf("/fake/path.pdf")

        assert docs[0].source == "/fake/path.pdf"


class TestLoadDocx:
    def test_returns_one_raw_document(self) -> None:
        mock_para1 = MagicMock()
        mock_para1.text = "First paragraph."
        mock_para2 = MagicMock()
        mock_para2.text = "Second paragraph."

        mock_document = MagicMock()
        mock_document.paragraphs = [mock_para1, mock_para2]

        with patch("docx.Document", return_value=mock_document):
            loader = DocumentLoader()
            docs = loader._load_docx("/fake/doc.docx")

        assert len(docs) == 1
        assert docs[0].doc_type == "docx"
        assert "First paragraph." in docs[0].content
        assert "Second paragraph." in docs[0].content

    def test_source_set_to_path(self) -> None:
        mock_document = MagicMock()
        mock_document.paragraphs = []

        with patch("docx.Document", return_value=mock_document):
            loader = DocumentLoader()
            docs = loader._load_docx("/fake/doc.docx")

        assert docs[0].source == "/fake/doc.docx"


class TestLoadDirectory:
    def test_returns_documents_from_multiple_txt_files(self, tmp_path: Path) -> None:
        (tmp_path / "a.txt").write_text("Content of file A.", encoding="utf-8")
        (tmp_path / "b.txt").write_text("Content of file B.", encoding="utf-8")

        loader = DocumentLoader()
        docs = loader._load_directory(str(tmp_path))

        assert len(docs) == 2
        contents = {d.content for d in docs}
        assert "Content of file A." in contents
        assert "Content of file B." in contents

    def test_skips_unsupported_files_with_warning(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        (tmp_path / "file.txt").write_text("Valid file.", encoding="utf-8")
        (tmp_path / "file.csv").write_text("col1,col2", encoding="utf-8")

        loader = DocumentLoader()
        import logging

        with caplog.at_level(logging.WARNING, logger="src.loader"):
            docs = loader._load_directory(str(tmp_path))

        assert len(docs) == 1
        assert any("csv" in msg for msg in caplog.messages)

    def test_mixed_extensions(self, tmp_path: Path) -> None:
        (tmp_path / "file.txt").write_text("TXT content.", encoding="utf-8")
        (tmp_path / "file.md").write_text("MD content.", encoding="utf-8")

        loader = DocumentLoader()
        docs = loader._load_directory(str(tmp_path))

        assert len(docs) == 2
        doc_types = {d.doc_type for d in docs}
        assert "txt" in doc_types
        assert "md" in doc_types

    def test_logs_warning_on_failed_file_load(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Files that raise during loading are skipped with a warning."""
        txt_file = tmp_path / "file.txt"
        txt_file.write_text("OK.", encoding="utf-8")
        bad_file = tmp_path / "bad.pdf"
        bad_file.write_bytes(b"not a real pdf")

        loader = DocumentLoader()
        import logging

        with caplog.at_level(logging.WARNING, logger="src.loader"):
            with patch("pymupdf.open", side_effect=RuntimeError("bad pdf")):
                docs = loader._load_directory(str(tmp_path))

        # TXT should be loaded; PDF should be skipped with a warning.
        assert len(docs) == 1
        assert docs[0].doc_type == "txt"
        assert any("bad.pdf" in msg or "Failed" in msg for msg in caplog.messages)
