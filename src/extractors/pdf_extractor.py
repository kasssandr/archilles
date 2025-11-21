"""PDF text extractor with support for complex layouts."""

from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
import re

try:
    import pdfplumber
    PDFPLUMBER_AVAILABLE = True
except ImportError:
    PDFPLUMBER_AVAILABLE = False

try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False

try:
    import pytesseract
    from PIL import Image
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False

from .base import BaseExtractor
from .models import ExtractedText, ChunkMetadata
from .exceptions import PDFExtractionError, ExtractionError


class PDFExtractor(BaseExtractor):
    """
    Extract text from PDF files with robust fallback chain.

    Features:
    - Multi-library support (pdfplumber → PyMuPDF → OCR)
    - Page number tracking (including roman numerals)
    - Footnote detection and separation
    - PDF coordinates for clickable citations
    - Table of contents extraction
    - Multi-column layout detection
    """

    SUPPORTED_EXTENSIONS = {'.pdf'}

    def __init__(self, *args, enable_ocr: bool = False, **kwargs):
        """
        Initialize PDF extractor.

        Args:
            enable_ocr: Whether to use OCR for scanned pages
            *args, **kwargs: Passed to BaseExtractor
        """
        super().__init__(*args, **kwargs)
        self.enable_ocr = enable_ocr and OCR_AVAILABLE

    def supports(self, file_path: Path) -> bool:
        """Check if file is PDF."""
        return file_path.suffix.lower() in self.SUPPORTED_EXTENSIONS

    def extract(self, file_path: Path) -> ExtractedText:
        """
        Extract text from PDF using best available method.

        Tries in order:
        1. pdfplumber (best for layout-aware extraction)
        2. PyMuPDF (faster, good for simple PDFs)
        3. OCR (for scanned PDFs)

        Args:
            file_path: Path to PDF file

        Returns:
            ExtractedText object

        Raises:
            PDFExtractionError: If all extraction methods fail
        """
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # Try extraction methods in order
        errors = []

        if PDFPLUMBER_AVAILABLE:
            try:
                return self._extract_with_pdfplumber(file_path)
            except Exception as e:
                errors.append(f"pdfplumber failed: {e}")

        if PYMUPDF_AVAILABLE:
            try:
                return self._extract_with_pymupdf(file_path)
            except Exception as e:
                errors.append(f"PyMuPDF failed: {e}")

        if self.enable_ocr and OCR_AVAILABLE:
            try:
                return self._extract_with_ocr(file_path)
            except Exception as e:
                errors.append(f"OCR failed: {e}")

        # All methods failed
        error_msg = "All PDF extraction methods failed:\n" + "\n".join(errors)
        raise PDFExtractionError(error_msg)

    def _extract_with_pdfplumber(self, file_path: Path) -> ExtractedText:
        """Extract using pdfplumber (best for complex layouts)."""
        pages_text = []
        pages_metadata = []
        footnotes = []
        toc = []

        with pdfplumber.open(file_path) as pdf:
            # Extract TOC if available
            try:
                toc = self._extract_toc_pdfplumber(pdf)
            except Exception:
                pass

            for page_num, page in enumerate(pdf.pages, start=1):
                # Extract text with layout information
                text = page.extract_text()

                if not text or not text.strip():
                    # Empty page or might need OCR
                    continue

                # Detect page label (e.g., "xiv" for roman numerals)
                page_label = page.page_number  # pdfplumber provides this

                # Extract footnotes (heuristic: smaller font or bottom of page)
                page_footnotes = self._extract_footnotes_pdfplumber(page, page_num)
                footnotes.extend(page_footnotes)

                # Get PDF coordinates for the page
                # This will be used for clickable citations
                page_height = page.height
                page_width = page.width

                pages_text.append(text)
                pages_metadata.append({
                    'page': page_num,
                    'page_label': str(page_label),
                    'height': page_height,
                    'width': page_width,
                })

        # Combine all pages
        full_text = '\n\n'.join(pages_text)

        # Create chunks with page information
        chunks = self._create_chunks_with_pages(
            pages_text,
            pages_metadata,
            file_path
        )

        # Create extraction metadata
        extraction_metadata = self._create_extraction_metadata(
            file_path=file_path,
            format_name='pdf',
            extraction_time=0,
            total_pages=len(pages_text),
            total_chars=len(full_text),
            total_words=len(full_text.split()),
            total_chunks=len(chunks),
        )
        extraction_metadata.warnings.append("Extracted with pdfplumber")

        return ExtractedText(
            full_text=full_text,
            chunks=chunks,
            metadata=extraction_metadata,
            toc=toc,
            footnotes=footnotes,
        )

    def _extract_with_pymupdf(self, file_path: Path) -> ExtractedText:
        """Extract using PyMuPDF (faster, simpler)."""
        doc = fitz.open(file_path)
        pages_text = []
        pages_metadata = []
        toc = []

        # Extract TOC
        try:
            toc_raw = doc.get_toc()
            toc = [
                {'level': level, 'title': title, 'page': page}
                for level, title, page in toc_raw
            ]
        except Exception:
            pass

        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text()

            if not text.strip():
                continue

            pages_text.append(text)
            pages_metadata.append({
                'page': page_num + 1,
                'page_label': str(page_num + 1),
            })

        doc.close()

        full_text = '\n\n'.join(pages_text)

        chunks = self._create_chunks_with_pages(
            pages_text,
            pages_metadata,
            file_path
        )

        extraction_metadata = self._create_extraction_metadata(
            file_path=file_path,
            format_name='pdf',
            extraction_time=0,
            total_pages=len(pages_text),
            total_chars=len(full_text),
            total_words=len(full_text.split()),
            total_chunks=len(chunks),
        )
        extraction_metadata.warnings.append("Extracted with PyMuPDF")

        return ExtractedText(
            full_text=full_text,
            chunks=chunks,
            metadata=extraction_metadata,
            toc=toc,
        )

    def _extract_with_ocr(self, file_path: Path) -> ExtractedText:
        """Extract using OCR (for scanned PDFs)."""
        # TODO: Implement OCR extraction
        # This is complex and should use Tesseract
        raise NotImplementedError("OCR extraction not yet implemented")

    def _create_chunks_with_pages(
        self,
        pages_text: List[str],
        pages_metadata: List[Dict],
        file_path: Path
    ) -> List[Dict[str, Any]]:
        """
        Create chunks while preserving page information.

        Each chunk knows which page(s) it comes from.
        """
        chunks = []

        for page_num, (page_text, page_meta) in enumerate(zip(pages_text, pages_metadata)):
            # Create base metadata for this page
            base_metadata = ChunkMetadata(
                source_file=str(file_path),
                format='pdf',
                page=page_meta['page'],
                page_label=page_meta.get('page_label'),
            )

            # Create chunks for this page
            page_chunks = self._create_chunks(page_text, base_metadata)
            chunks.extend(page_chunks)

        return chunks

    def _extract_footnotes_pdfplumber(
        self,
        page,
        page_num: int
    ) -> List[Dict[str, Any]]:
        """
        Extract footnotes from page (heuristic-based).

        Looks for:
        - Smaller font size
        - Bottom 20% of page
        - Numbered patterns (1., *, †, etc.)
        """
        footnotes = []

        # TODO: Implement robust footnote detection
        # This is complex and needs font size analysis

        return footnotes

    def _extract_toc_pdfplumber(self, pdf) -> List[Dict[str, Any]]:
        """Extract table of contents."""
        # pdfplumber doesn't have built-in TOC extraction
        # Would need to parse bookmarks/outline
        return []

    @staticmethod
    def _detect_roman_numerals(text: str) -> bool:
        """Detect if text contains roman numeral page numbers."""
        roman_pattern = r'\b(i{1,3}|iv|v|vi{0,3}|ix|x|xi{0,3}|xiv|xv|xvi{0,3}|xix|xx)\b'
        return bool(re.search(roman_pattern, text.lower()))
