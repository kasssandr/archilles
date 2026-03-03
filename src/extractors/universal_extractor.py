"""
Universal text extractor that handles all e-book formats.

Uses a multi-tier fallback strategy:
1. Native extractors (fast, precise)
2. Calibre conversion (reliable, slower)
3. Pandoc fallback (for exotic formats)
"""

from pathlib import Path
from typing import Optional, List
import logging

from .models import ExtractedText
from .exceptions import (
    UnsupportedFormatError,
    ExtractionError,
    CalibreNotFoundError,
)
from .format_detector import FormatDetector
from .pdf_extractor import PDFExtractor
from .epub_extractor import EPUBExtractor
from .txt_extractor import TXTExtractor
from .html_extractor import HTMLExtractor
from .calibre_converter import CalibreConverter
from .ocr_extractor import OCRBackend


logger = logging.getLogger(__name__)


class UniversalExtractor:
    """
    Extract text from any e-book format.

    Automatically selects the best extraction method:
    - PDF → PDFExtractor (pdfplumber/PyMuPDF)
    - EPUB → EPUBExtractor (ebooklib)
    - TXT → TXTExtractor (native)
    - HTML → HTMLExtractor (BeautifulSoup)
    - MOBI/DJVU/DOC/etc. → Calibre → EPUB/PDF → Extract

    Features:
    - Automatic format detection (magic bytes, not just extension)
    - Robust fallback chain
    - Detailed error reporting
    - Support for 20+ formats
    """

    def __init__(
        self,
        chunk_size: int = 512,
        overlap: int = 128,
        enable_ocr: bool = False,
        force_ocr: bool = False,
        ocr_backend: OCRBackend = OCRBackend.AUTO,
        ocr_language: str = "deu+eng",
        calibre_path: Optional[str] = None,
    ):
        """
        Initialize universal extractor.

        Args:
            chunk_size: Target chunk size in tokens
            overlap: Overlap between chunks in tokens
            enable_ocr: Enable OCR for scanned PDFs (auto-detect)
            force_ocr: Force OCR even for digital PDFs
            ocr_backend: OCR backend to use (AUTO, TESSERACT, LIGHTON, OLMOCR)
            ocr_language: Language codes for Tesseract (e.g., "deu+eng")
            calibre_path: Path to Calibre's ebook-convert (if not in PATH)
        """
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.enable_ocr = enable_ocr
        self.force_ocr = force_ocr
        self.ocr_backend = ocr_backend
        self.ocr_language = ocr_language

        # Initialize extractors
        self.pdf_extractor = PDFExtractor(
            chunk_size=chunk_size,
            overlap=overlap,
            enable_ocr=enable_ocr,
            force_ocr=force_ocr,
            ocr_backend=ocr_backend,
            ocr_language=ocr_language
        )
        self.epub_extractor = EPUBExtractor(
            chunk_size=chunk_size,
            overlap=overlap
        )
        self.txt_extractor = TXTExtractor(
            chunk_size=chunk_size,
            overlap=overlap
        )
        self.html_extractor = HTMLExtractor(
            chunk_size=chunk_size,
            overlap=overlap
        )

        # Initialize Calibre converter
        try:
            self.calibre_converter = CalibreConverter(calibre_path=calibre_path)
            self.calibre_available = True
        except CalibreNotFoundError:
            self.calibre_converter = None
            self.calibre_available = False
            logger.warning("Calibre not available. Exotic formats won't be supported.")

    def extract(self, file_path: Path | str) -> ExtractedText:
        """
        Extract text from file (any supported format).

        Args:
            file_path: Path to file

        Returns:
            ExtractedText object

        Raises:
            UnsupportedFormatError: If format not supported
            ExtractionError: If extraction fails
        """
        file_path = Path(file_path)

        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # Detect format
        detected_format, detection_method = FormatDetector.detect(file_path)

        logger.info(
            f"Processing {file_path.name}: "
            f"format={detected_format} (via {detection_method})"
        )

        # Try native extractors first
        extractor = self._get_native_extractor(detected_format)
        if extractor:
            try:
                logger.info(f"Using native extractor: {extractor.__class__.__name__}")
                return extractor.extract(file_path)
            except Exception as e:
                logger.warning(
                    f"Native extraction failed for {file_path.name}: {e}. "
                    f"Trying Calibre conversion..."
                )

        # Try Calibre conversion
        if self.calibre_available and self.calibre_converter.supports(file_path):
            try:
                logger.info(f"Converting {detected_format} via Calibre")
                target_format = CalibreConverter.get_optimal_target_format(detected_format)
                return self.calibre_converter.convert_and_extract(
                    file_path,
                    target_format=target_format
                )
            except Exception as e:
                logger.error(f"Calibre conversion failed: {e}")
                raise ExtractionError(
                    f"Failed to extract {file_path.name}: "
                    f"Native extraction failed, Calibre conversion failed"
                ) from e

        # No extraction method worked
        raise UnsupportedFormatError(
            f"Unsupported format: {detected_format} ({file_path.suffix})\n"
            f"Native extractors failed, and Calibre is "
            f"{'not available' if not self.calibre_available else 'unable to convert this format'}"
        )

    def extract_batch(
        self,
        file_paths: List[Path | str],
        skip_errors: bool = True
    ) -> List[tuple[Path, Optional[ExtractedText], Optional[Exception]]]:
        """
        Extract text from multiple files.

        Args:
            file_paths: List of file paths
            skip_errors: If True, continue on errors; if False, raise

        Returns:
            List of (file_path, extracted_text, error) tuples
            If successful: (path, ExtractedText, None)
            If failed: (path, None, Exception)
        """
        results = []

        for file_path in file_paths:
            file_path = Path(file_path)
            try:
                extracted = self.extract(file_path)
                results.append((file_path, extracted, None))
                logger.info(f"✓ Extracted: {file_path.name}")
            except Exception as e:
                results.append((file_path, None, e))
                logger.error(f"✗ Failed: {file_path.name} - {e}")
                if not skip_errors:
                    raise

        # Summary
        successful = sum(1 for _, ext, _ in results if ext is not None)
        failed = len(results) - successful
        logger.info(
            f"Batch extraction complete: {successful} successful, {failed} failed"
        )

        return results

    def get_supported_formats(self) -> dict:
        """
        Get information about supported formats.

        Returns:
            Dictionary with format support information
        """
        native_formats = {
            'pdf': 'Native PDF extraction (pdfplumber/PyMuPDF)',
            'epub': 'Native EPUB extraction (ebooklib)',
            'txt': 'Native text extraction',
            'html': 'Native HTML extraction (BeautifulSoup)',
            'htm': 'Native HTML extraction',
            'xhtml': 'Native HTML extraction',
            'md': 'Native text extraction (Markdown)',
            'markdown': 'Native text extraction (Markdown)',
            'rst': 'Native text extraction (reStructuredText)',
        }

        calibre_formats = {}
        if self.calibre_available:
            for fmt in CalibreConverter.CONVERTIBLE_FORMATS:
                calibre_formats[fmt] = 'Calibre conversion (to EPUB/PDF)'

        return {
            'native': native_formats,
            'calibre': calibre_formats,
            'total_supported': len(native_formats) + len(calibre_formats),
            'calibre_available': self.calibre_available,
        }

    # Map detected format names to the extractor attribute that handles them.
    _FORMAT_TO_EXTRACTOR = {
        'pdf': 'pdf_extractor',
        'epub': 'epub_extractor',
        'txt': 'txt_extractor',
        'text': 'txt_extractor',
        'log': 'txt_extractor',
        'md': 'txt_extractor',
        'markdown': 'txt_extractor',
        'rst': 'txt_extractor',
        'txtz': 'txt_extractor',
        'html': 'html_extractor',
        'htm': 'html_extractor',
        'xhtml': 'html_extractor',
        'xml': 'html_extractor',
    }

    def _get_native_extractor(self, format_name: str):
        """Get appropriate native extractor for format."""
        attr = self._FORMAT_TO_EXTRACTOR.get(format_name)
        if attr:
            return getattr(self, attr)
        return None

    def __repr__(self):
        """String representation."""
        supported = self.get_supported_formats()
        return (
            f"UniversalExtractor("
            f"native_formats={len(supported['native'])}, "
            f"calibre_formats={len(supported['calibre'])}, "
            f"calibre_available={self.calibre_available})"
        )
