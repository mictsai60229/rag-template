"""Text cleaner for the RAG Data Import pipeline.

Normalises loaded text before chunking: removes excessive whitespace, normalises
Unicode encoding, and normalises line endings. The cleaner never removes content —
it only normalises whitespace and encoding; sentence structure and punctuation are
preserved.
"""

import re
import unicodedata

from src.models import RawDocument

# Regex that matches three or more consecutive blank lines.
_EXCESS_BLANK_LINES_RE = re.compile(r"\n{3,}")


class TextCleaner:
    """Stateless text normaliser.

    Cleaning rules (applied in order):
    1. Normalise Unicode to NFC form.
    2. Replace ``\\r\\n`` and ``\\r`` with ``\\n``.
    3. Collapse runs of 3+ blank lines into at most 2 blank lines.
    4. Strip leading/trailing whitespace from each line.
    5. Strip leading/trailing whitespace from the full text.
    """

    def clean(self, text: str) -> str:
        """Return a cleaned copy of *text*.

        The original string is never mutated.
        """
        # 1. Normalise Unicode to NFC form.
        text = unicodedata.normalize("NFC", text)

        # 2. Normalise line endings to LF.
        text = text.replace("\r\n", "\n").replace("\r", "\n")

        # 3. Collapse 3+ consecutive blank lines into exactly 2 blank lines.
        #    Three newlines (\\n\\n\\n) = two blank lines; we collapse anything
        #    longer to exactly \\n\\n (one blank line separator).
        text = _EXCESS_BLANK_LINES_RE.sub("\n\n", text)

        # 4. Strip leading/trailing whitespace from each line.
        text = "\n".join(line.strip() for line in text.split("\n"))

        # 5. Strip leading/trailing whitespace from the full text.
        text = text.strip()

        return text

    def clean_document(self, doc: RawDocument) -> RawDocument:
        """Return a new :class:`RawDocument` with its content cleaned.

        All other fields (``doc_id``, ``source``, ``doc_type``, ``loaded_at``)
        are preserved unchanged.
        """
        return RawDocument(
            content=self.clean(doc.content),
            source=doc.source,
            doc_type=doc.doc_type,
            doc_id=doc.doc_id,
            loaded_at=doc.loaded_at,
        )
