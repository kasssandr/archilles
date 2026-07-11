"""Tests for Indexer._detect_needs_ocr calibration.

PDFs shorter than OCR_WARN_MIN_PAGES must never be flagged: reference
managers routinely attach tiny scanned PDFs (Zotero stores publisher
TOC/preview scans), and a warning per attachment buries the genuine
re-index candidates in noise (user report 2026-07-11 during the Zotero
prepare run).
"""

from types import SimpleNamespace

from src.archilles.engine.indexing import Indexer, OCR_WARN_MIN_PAGES


def _extracted(fmt='pdf', pages=0, words=0, chunk_pages=()):
    return SimpleNamespace(
        metadata=SimpleNamespace(
            detected_format=fmt,
            total_pages=pages,
            total_words=words,
        ),
        chunks=[{'text': 'x', 'metadata': {'page': p}} for p in chunk_pages],
    )


def _detect(extracted) -> bool:
    # _detect_needs_ocr reads nothing from self — call it unbound.
    return Indexer._detect_needs_ocr(None, extracted)


class TestNonPdf:
    def test_epub_never_flagged(self):
        assert _detect(_extracted(fmt='epub', pages=0, words=0)) is False


class TestTinyPdfsSuppressed:
    def test_fully_scanned_toc_pdf_not_flagged(self):
        """A 3-page scanned TOC attachment yields no chunks — no warning."""
        assert _detect(_extracted(pages=3, words=0)) is False

    def test_mostly_scanned_tiny_pdf_not_flagged(self):
        """The reported wall-of-warnings case: 334w across 3p, text on 1/3."""
        assert _detect(
            _extracted(pages=3, words=334, chunk_pages=(1,))
        ) is False

    def test_threshold_boundary_below(self):
        assert _detect(_extracted(pages=OCR_WARN_MIN_PAGES - 1, words=0)) is False


class TestRealCandidatesStillFlagged:
    def test_fully_scanned_book_flagged(self):
        assert _detect(_extracted(pages=200, words=0)) is True

    def test_threshold_boundary_at_min_pages(self):
        assert _detect(_extracted(pages=OCR_WARN_MIN_PAGES, words=0)) is True

    def test_mostly_scanned_book_flagged(self):
        """Low words/page AND low page coverage on a real-sized PDF."""
        assert _detect(
            _extracted(pages=10, words=500, chunk_pages=(1, 2))
        ) is True

    def test_unknown_page_count_without_text_flagged(self):
        """total_pages=0 (unknown) must stay eligible — could be a big book."""
        assert _detect(_extracted(pages=0, words=0)) is True


class TestHealthyPdfsNotFlagged:
    def test_normal_text_pdf_not_flagged(self):
        assert _detect(
            _extracted(pages=10, words=4000, chunk_pages=range(1, 11))
        ) is False

    def test_front_matter_only_text_but_good_coverage(self):
        """Low words/page but chunks on most pages → front-matter, not scan."""
        assert _detect(
            _extracted(pages=10, words=800, chunk_pages=range(1, 9))
        ) is False
