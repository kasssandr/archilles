"""
OCR-Modul for ARCHILLES.

Supports multiple OCR backends with unified interface:
- Tesseract: Classic OCR, fast, simple documents
- LightOnOCR-2: Vision-Language model, complex layouts (future)
- olmOCR-2: Alternative VLM for academic documents (future)

All processing is fully local - no data leaves the system.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Dict, Any
from enum import Enum
import time
import logging

logger = logging.getLogger(__name__)


class OCRBackend(Enum):
    """Available OCR backends."""
    TESSERACT = "tesseract"      # Classic, fast, simple documents
    LIGHTON = "lighton"          # State-of-the-art VLM (future)
    OLMOCR = "olmocr"            # Alternative VLM (future)
    AUTO = "auto"                # Automatic selection


class OCROutputFormat(Enum):
    """Output format for OCR results.

    VLM backends (LightOnOCR-2, GOT-OCR 2.0) can produce structured Markdown
    with headings, lists, and tables. The chunking pipeline uses this to
    determine whether Markdown headings can serve as chunk boundaries.
    """
    PLAINTEXT = "plaintext"
    MARKDOWN = "markdown"
    HTML = "html"


@dataclass
class OCRPage:
    """Result of OCR processing for a single page."""
    page_number: int
    text: str
    confidence: float = 0.0
    output_format: OCROutputFormat = OCROutputFormat.PLAINTEXT
    layout_blocks: Optional[List[Dict[str, Any]]] = None  # For structured VLM output
    processing_time: float = 0.0


@dataclass
class OCRResult:
    """Complete OCR result for a document."""
    pages: List[OCRPage]
    backend_used: OCRBackend
    processing_time_seconds: float
    total_pages: int = 0
    successful_pages: int = 0
    average_confidence: float = 0.0
    warnings: List[str] = field(default_factory=list)

    def __post_init__(self):
        self.total_pages = len(self.pages)
        self.successful_pages = sum(1 for p in self.pages if p.text.strip())
        if self.pages:
            confidences = [p.confidence for p in self.pages if p.confidence > 0]
            self.average_confidence = sum(confidences) / len(confidences) if confidences else 0.0


class OCRExtractor(ABC):
    """Abstract interface for OCR backends."""

    @abstractmethod
    def extract(self, pdf_path: Path, pages: Optional[List[int]] = None) -> OCRResult:
        """
        Extract text from PDF via OCR.

        Args:
            pdf_path: Path to PDF file
            pages: Optional list of page numbers to process (1-indexed).
                   If None, process all pages.

        Returns:
            OCRResult with extracted text and metadata
        """
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this backend is available (dependencies installed)."""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name of this backend."""
        pass


class TesseractExtractor(OCRExtractor):
    """
    Tesseract-based OCR (classic, reliable fallback).

    Uses PyMuPDF for PDF-to-image rendering and pytesseract for OCR.
    Best for simple, single-column documents with clear typography.
    """

    def __init__(
        self,
        language: str = "deu+eng",
        dpi: int = 300,
        psm: int = 3  # Page Segmentation Mode: 3 = fully automatic
    ):
        """
        Initialize Tesseract extractor.

        Args:
            language: Tesseract language codes (e.g., "deu+eng" for German + English)
            dpi: Resolution for PDF rendering (higher = better quality, slower)
            psm: Page Segmentation Mode (3 = auto, 6 = single block)
        """
        self.language = language
        self.dpi = dpi
        self.psm = psm

    @property
    def name(self) -> str:
        return "Tesseract OCR"

    def is_available(self) -> bool:
        """Check if Tesseract and required libraries are installed."""
        try:
            import pytesseract
            import fitz  # PyMuPDF for rendering
            from PIL import Image

            # Try to get Tesseract version (fails if not installed)
            pytesseract.get_tesseract_version()
            return True
        except Exception as e:
            logger.debug(f"Tesseract not available: {e}")
            return False

    def extract(self, pdf_path: Path, pages: Optional[List[int]] = None) -> OCRResult:
        """
        Extract text from PDF using Tesseract OCR.

        Args:
            pdf_path: Path to PDF file
            pages: Optional list of page numbers (1-indexed)

        Returns:
            OCRResult with extracted text
        """
        import pytesseract
        import fitz
        from PIL import Image
        import io

        start_time = time.time()
        ocr_pages = []
        warnings = []

        doc = fitz.open(pdf_path)
        total_pages = len(doc)

        # Determine which pages to process
        if pages:
            page_indices = [p - 1 for p in pages if 0 < p <= total_pages]
        else:
            page_indices = range(total_pages)

        logger.info(f"OCR processing {len(page_indices)} pages from {pdf_path.name}")

        for page_idx in page_indices:
            page_start = time.time()
            page_num = page_idx + 1

            try:
                page = doc[page_idx]

                # Render page to image
                # Higher DPI = better quality but slower
                mat = fitz.Matrix(self.dpi / 72, self.dpi / 72)
                pix = page.get_pixmap(matrix=mat)

                # Convert to PIL Image
                img_data = pix.tobytes("png")
                img = Image.open(io.BytesIO(img_data))

                # Run Tesseract OCR
                # Config: psm for page segmentation, oem for OCR engine mode
                config = f"--psm {self.psm} --oem 3"

                # Get text and confidence in a single Tesseract call
                data = pytesseract.image_to_data(
                    img,
                    lang=self.language,
                    config=config,
                    output_type=pytesseract.Output.DICT
                )

                # Reconstruct text from data (avoids a second Tesseract call)
                text = ' '.join(
                    w for w, c in zip(data['text'], data['conf']) if w.strip()
                )

                # Calculate average confidence (filter out -1 values)
                confidences = [c for c in data['conf'] if c > 0]
                avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

                ocr_pages.append(OCRPage(
                    page_number=page_num,
                    text=text.strip(),
                    confidence=avg_confidence / 100.0,  # Normalize to 0-1
                    processing_time=time.time() - page_start
                ))

                logger.debug(f"  Page {page_num}: {len(text)} chars, confidence {avg_confidence:.1f}%")

            except Exception as e:
                warnings.append(f"Page {page_num} failed: {e}")
                logger.warning(f"OCR failed for page {page_num}: {e}")
                ocr_pages.append(OCRPage(
                    page_number=page_num,
                    text="",
                    confidence=0.0,
                    processing_time=time.time() - page_start
                ))

        doc.close()

        return OCRResult(
            pages=ocr_pages,
            backend_used=OCRBackend.TESSERACT,
            processing_time_seconds=time.time() - start_time,
            warnings=warnings
        )


class _PlaceholderVLMExtractor(OCRExtractor):
    """
    Base class for VLM-based OCR backends not yet implemented.

    Subclasses only need to set _NAME and _DESCRIPTION.
    """

    _NAME: str = "Placeholder"
    _DESCRIPTION: str = "Not yet implemented"

    def __init__(
        self,
        model_path: Optional[Path] = None,
        device: str = "auto"
    ):
        self.model_path = model_path
        self.device = device

    @property
    def name(self) -> str:
        return self._NAME

    def is_available(self) -> bool:
        # TODO: Check for model weights and dependencies
        return False

    def extract(self, pdf_path: Path, pages: Optional[List[int]] = None) -> OCRResult:
        raise NotImplementedError(
            f"{self._NAME} integration is planned for future release. "
            "Use Tesseract backend for now."
        )


class LightOnOCRExtractor(_PlaceholderVLMExtractor):
    """LightOnOCR-2: State-of-the-art VLM for complex layouts (planned)."""
    _NAME = "LightOnOCR-2"
    _DESCRIPTION = "Vision-Language model for complex layouts (planned)"


class OlmOCRExtractor(_PlaceholderVLMExtractor):
    """olmOCR-2: Alternative VLM optimized for academic documents (planned)."""
    _NAME = "olmOCR-2"
    _DESCRIPTION = "VLM for academic documents (planned)"


def get_ocr_extractor(backend: OCRBackend = OCRBackend.AUTO) -> OCRExtractor:
    """
    Factory function for OCR backend selection.

    Args:
        backend: Which OCR backend to use (AUTO = best available)

    Returns:
        Configured OCRExtractor instance

    Raises:
        RuntimeError: If no OCR backend is available
    """
    if backend == OCRBackend.AUTO:
        # Priority: VLM (better quality) > Tesseract (fallback)
        lighton = LightOnOCRExtractor()
        if lighton.is_available():
            logger.info("Using LightOnOCR-2 backend")
            return lighton

        olmocr = OlmOCRExtractor()
        if olmocr.is_available():
            logger.info("Using olmOCR-2 backend")
            return olmocr

        tesseract = TesseractExtractor()
        if tesseract.is_available():
            logger.info("Using Tesseract backend")
            return tesseract

        raise RuntimeError(
            "No OCR backend available. Please install Tesseract:\n"
            "  Windows: Download from https://github.com/UB-Mannheim/tesseract/wiki\n"
            "  Linux: sudo apt install tesseract-ocr tesseract-ocr-deu\n"
            "  macOS: brew install tesseract tesseract-lang"
        )

    # Explicit backend selection
    backends = {
        OCRBackend.TESSERACT: TesseractExtractor,
        OCRBackend.LIGHTON: LightOnOCRExtractor,
        OCRBackend.OLMOCR: OlmOCRExtractor,
    }

    extractor_class = backends.get(backend)
    if not extractor_class:
        raise ValueError(f"Unknown OCR backend: {backend}")

    extractor = extractor_class()
    if not extractor.is_available():
        raise RuntimeError(f"OCR backend '{backend.value}' is not available")

    return extractor


def detect_scanned_pdf(pdf_path: Path, sample_pages: int = 5) -> bool:
    """
    Detect if a PDF is scanned (image-based) or digital (text-based).

    Samples a few pages and checks for extractable text.
    If most sampled pages have little/no text, it's likely scanned.

    Args:
        pdf_path: Path to PDF file
        sample_pages: Number of pages to sample

    Returns:
        True if PDF appears to be scanned, False if digital
    """
    try:
        import fitz
    except ImportError:
        logger.warning("PyMuPDF not available, assuming PDF is digital")
        return False

    doc = fitz.open(pdf_path)
    total_pages = len(doc)

    if total_pages == 0:
        doc.close()
        return False

    # Sample pages evenly distributed through document
    if total_pages <= sample_pages:
        sample_indices = range(total_pages)
    else:
        step = total_pages // sample_pages
        sample_indices = [i * step for i in range(sample_pages)]

    pages_with_text = 0
    min_chars_threshold = 100  # Minimum characters to consider "has text"

    for idx in sample_indices:
        page = doc[idx]
        text = page.get_text().strip()

        if len(text) >= min_chars_threshold:
            pages_with_text += 1

    doc.close()

    # If less than 30% of sampled pages have text, likely scanned
    text_ratio = pages_with_text / len(sample_indices)
    is_scanned = text_ratio < 0.3

    logger.debug(
        f"PDF scan detection: {pages_with_text}/{len(sample_indices)} pages have text "
        f"({text_ratio:.0%}) -> {'scanned' if is_scanned else 'digital'}"
    )

    return is_scanned


def get_ocr_status() -> Dict[str, Any]:
    """
    Get status of available OCR backends.

    Returns:
        Dictionary with availability status for each backend
    """
    # Priority order: best quality first
    backends = [
        ("lighton", LightOnOCRExtractor(), "Vision-Language model for complex layouts (planned)"),
        ("olmocr", OlmOCRExtractor(), "VLM for academic documents (planned)"),
        ("tesseract", TesseractExtractor(), "Classic OCR, best for simple documents"),
    ]

    status: Dict[str, Any] = {}
    recommended = None

    for key, extractor, description in backends:
        available = extractor.is_available()
        status[key] = {
            "available": available,
            "name": extractor.name,
            "description": description,
        }
        if available and recommended is None:
            recommended = key

    status["recommended"] = recommended
    return status
