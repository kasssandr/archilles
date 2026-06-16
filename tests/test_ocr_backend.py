"""
Tests for OCR backend string→enum conversion (Befund 2.16).

The modular pipeline's PyMuPDFParser used to pass ocr_backend as a raw
string to PDFExtractor, which expects an OCRBackend enum — a latent
KeyError. A single from_string() classmethod is the canonical converter.
"""

import pytest

from src.extractors.ocr_extractor import OCRBackend
from src.archilles.parsers.pymupdf_parser import PyMuPDFParser, PYMUPDF_AVAILABLE


class TestOCRBackendFromString:
    def test_known_backends(self):
        assert OCRBackend.from_string("auto") is OCRBackend.AUTO
        assert OCRBackend.from_string("tesseract") is OCRBackend.TESSERACT
        assert OCRBackend.from_string("lighton") is OCRBackend.LIGHTON
        assert OCRBackend.from_string("olmocr") is OCRBackend.OLMOCR

    def test_case_insensitive(self):
        assert OCRBackend.from_string("AUTO") is OCRBackend.AUTO
        assert OCRBackend.from_string("Tesseract") is OCRBackend.TESSERACT

    def test_unknown_falls_back_to_auto(self):
        assert OCRBackend.from_string("does-not-exist") is OCRBackend.AUTO
        assert OCRBackend.from_string("") is OCRBackend.AUTO

    def test_enum_passes_through(self):
        """Passing an enum instance returns it unchanged (idempotent)."""
        assert OCRBackend.from_string(OCRBackend.LIGHTON) is OCRBackend.LIGHTON


@pytest.mark.skipif(not PYMUPDF_AVAILABLE, reason="PyMuPDF not installed")
class TestPyMuPDFParserBackend:
    def test_string_backend_stored_as_enum(self):
        """Parser must hold an OCRBackend enum, not a raw string —
        otherwise PDFExtractor.get_ocr_extractor() would KeyError."""
        parser = PyMuPDFParser(ocr_backend="auto")
        assert parser._ocr_backend is OCRBackend.AUTO

    def test_named_string_backend(self):
        parser = PyMuPDFParser(ocr_backend="lighton")
        assert parser._ocr_backend is OCRBackend.LIGHTON

    def test_enum_backend_accepted(self):
        parser = PyMuPDFParser(ocr_backend=OCRBackend.TESSERACT)
        assert parser._ocr_backend is OCRBackend.TESSERACT
