"""Unit tests for src/cleaner.py — TextCleaner."""

from src.cleaner import TextCleaner
from src.models import RawDocument


class TestClean:
    def test_normalises_crlf_to_lf(self) -> None:
        cleaner = TextCleaner()
        result = cleaner.clean("line1\r\nline2\r\nline3")
        assert "\r" not in result
        assert result == "line1\nline2\nline3"

    def test_normalises_cr_to_lf(self) -> None:
        cleaner = TextCleaner()
        result = cleaner.clean("line1\rline2")
        assert "\r" not in result
        assert result == "line1\nline2"

    def test_collapses_five_blank_lines_to_two(self) -> None:
        cleaner = TextCleaner()
        # 5 blank lines = 6 consecutive newlines
        text = "paragraph one\n\n\n\n\nparagraph two"
        result = cleaner.clean(text)
        # Should have at most 2 consecutive newlines (one blank line) between paragraphs.
        assert "\n\n\n" not in result
        assert "paragraph one" in result
        assert "paragraph two" in result

    def test_collapses_three_blank_lines_to_two(self) -> None:
        cleaner = TextCleaner()
        # 3 blank lines = 4 newlines in a row
        text = "a\n\n\n\nb"
        result = cleaner.clean(text)
        assert "\n\n\n" not in result

    def test_strips_leading_trailing_whitespace_per_line(self) -> None:
        cleaner = TextCleaner()
        text = "  hello world  \n  foo bar  "
        result = cleaner.clean(text)
        lines = result.split("\n")
        for line in lines:
            assert line == line.strip()

    def test_strips_leading_trailing_whitespace_full_text(self) -> None:
        cleaner = TextCleaner()
        text = "   \nsome content\n   "
        result = cleaner.clean(text)
        assert result == result.strip()

    def test_leaves_normal_prose_unchanged(self) -> None:
        cleaner = TextCleaner()
        prose = "The quick brown fox jumps over the lazy dog. It was a sunny day."
        result = cleaner.clean(prose)
        assert result == prose

    def test_preserves_sentence_structure_and_punctuation(self) -> None:
        cleaner = TextCleaner()
        prose = "Hello, world! How are you? I'm fine, thanks."
        result = cleaner.clean(prose)
        assert result == prose

    def test_unicode_normalisation_nfc(self) -> None:
        cleaner = TextCleaner()
        # "é" as NFD (e + combining accent) should be normalised to NFC.
        nfd_e = "e\u0301"  # NFD form of é
        nfc_e = "\xe9"  # NFC form of é
        result = cleaner.clean(nfd_e)
        assert result == nfc_e


class TestCleanDocument:
    def test_returns_new_raw_document(self) -> None:
        cleaner = TextCleaner()
        doc = RawDocument(content="  hello  \r\n  world  ", source="/tmp/f.txt", doc_type="txt")
        cleaned = cleaner.clean_document(doc)
        assert isinstance(cleaned, RawDocument)
        assert cleaned is not doc

    def test_content_is_cleaned(self) -> None:
        cleaner = TextCleaner()
        doc = RawDocument(content="  hello  \r\n  world  ", source="/tmp/f.txt", doc_type="txt")
        cleaned = cleaner.clean_document(doc)
        assert cleaned.content == "hello\nworld"

    def test_other_fields_preserved(self) -> None:
        cleaner = TextCleaner()
        doc = RawDocument(content="  hello  ", source="/tmp/file.txt", doc_type="txt")
        cleaned = cleaner.clean_document(doc)
        assert cleaned.doc_id == doc.doc_id
        assert cleaned.source == doc.source
        assert cleaned.doc_type == doc.doc_type
        assert cleaned.loaded_at == doc.loaded_at
