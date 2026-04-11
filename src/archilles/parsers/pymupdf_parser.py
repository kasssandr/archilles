"""
ARCHILLES PyMuPDF Parser — Adapter around PDFExtractor.

Delegates all extraction to the battle-tested PDFExtractor (src/extractors/)
and converts its ExtractedText output to the ParsedDocument format expected
by the ModularPipeline.
"""

import time
from pathlib import Path
import logging

try:
    import fitz  # PyMuPDF — only needed to report availability & version
    PYMUPDF_AVAILABLE = True
    PYMUPDF_VERSION = fitz.version[0]
except ImportError:
    PYMUPDF_AVAILABLE = False
    PYMUPDF_VERSION = "0.0.0"

from .base import (
    DocumentParser,
    DocumentType,
    ParserCapabilities,
    ParsedDocument,
    ParsedChunk,
)

logger = logging.getLogger(__name__)


class PyMuPDFParser(DocumentParser):
    """
    PDF parser that delegates to PDFExtractor.

    Provides the DocumentParser interface for the ModularPipeline while
    reusing all extraction logic (OCR fallback, TOC-aware chunking,
    running-header removal, page-label detection) from PDFExtractor.

    Args:
        enable_ocr: Enable OCR for scanned PDFs
        force_ocr: Force OCR even for digital PDFs
        ocr_backend: OCR backend (auto, tesseract, lighton, olmocr)
        ocr_language: Language codes for Tesseract
    """

    def __init__(
        self,
        enable_ocr: bool = False,
        force_ocr: bool = False,
        ocr_backend: str = "auto",
        ocr_language: str = "deu+eng",
    ):
        if not PYMUPDF_AVAILABLE:
            raise ImportError(
                "PyMuPDF is not installed. Install with: pip install pymupdf"
            )
        self._enable_ocr = enable_ocr
        self._force_ocr = force_ocr
        self._ocr_backend = ocr_backend
        self._ocr_language = ocr_language

    @property
    def name(self) -> str:
        return "pymupdf"

    @property
    def version(self) -> str:
        return f"1.0.0+pymupdf{PYMUPDF_VERSION}"

    @property
    def capabilities(self) -> ParserCapabilities:
        return ParserCapabilities(
            supported_extensions={'.pdf'},
            supported_types={DocumentType.PDF},
            extracts_images=False,
            extracts_tables=False,
            extracts_metadata=True,
            preserves_formatting=False,
            supports_ocr=self._enable_ocr or self._force_ocr,
            memory_efficient=True,
            parallel_safe=True,
            quality_tier=2,
        )

    def parse(self, file_path: Path) -> ParsedDocument:
        """Parse a PDF via PDFExtractor and convert to ParsedDocument."""
        file_path = Path(file_path)
        start_time = time.time()

        from src.extractors.pdf_extractor import PDFExtractor

        extractor = PDFExtractor(
            enable_ocr=self._enable_ocr,
            force_ocr=self._force_ocr,
            ocr_backend=self._ocr_backend,
            ocr_language=self._ocr_language,
        )
        extracted = extractor.extract(file_path)

        # Convert ExtractedText chunks → ParsedChunks (page-level)
        chunks = []
        for i, chunk_dict in enumerate(extracted.chunks):
            meta = chunk_dict.get('metadata', {})
            chunks.append(ParsedChunk(
                text=chunk_dict.get('text', ''),
                source_file=str(file_path),
                page_number=meta.get('page'),
                chunk_index=i,
                section_title=meta.get('section_title'),
                chapter=meta.get('chapter'),
                metadata=meta,
            ))

        duration = time.time() - start_time
        ext_meta = extracted.metadata

        return ParsedDocument(
            file_path=str(file_path),
            file_name=file_path.name,
            file_size_bytes=file_path.stat().st_size,
            full_text=extracted.full_text,
            chunks=chunks,
            title=ext_meta.file_path.stem if ext_meta else None,
            authors=[],
            language=None,
            page_count=ext_meta.total_pages if ext_meta else None,
            parser_name=self.name,
            parser_version=self.version,
            parse_duration_seconds=duration,
            metadata={
                'toc': extracted.toc or [],
                'extraction_method': ext_meta.extraction_method if ext_meta else 'unknown',
            },
            warnings=[w for w in (ext_meta.warnings if ext_meta else [])],
        )
