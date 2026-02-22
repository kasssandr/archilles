"""PDF text extractor with support for complex layouts."""

import re
import time
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional

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

from .base import BaseExtractor
from .exceptions import PDFExtractionError
from .models import ChunkMetadata, ExtractedText
from .ocr_extractor import (
    OCRBackend,
    detect_scanned_pdf,
    get_ocr_extractor,
)


def _strings_are_similar(a: str, b: str, threshold: float = 0.85) -> bool:
    """Check if two strings are similar enough (handles OCR errors)."""
    if not a or not b:
        return False
    if a == b or b in a:
        return True
    return SequenceMatcher(None, a.lower(), b.lower()).ratio() >= threshold


def _normalize_header_line(line: str) -> str:
    """Normalize a line for header comparison: collapse whitespace, strip page numbers."""
    normalized = ' '.join(line.split())
    normalized = re.sub(r'^\d+\s*', '', normalized)
    normalized = re.sub(r'\s*\d+$', '', normalized)
    return normalized


class PDFExtractor(BaseExtractor):
    """
    Extract text from PDF files with robust fallback chain.

    Features:
    - Multi-library support (PyMuPDF -> pdfplumber -> OCR)
    - Page number tracking (including roman numerals)
    - Footnote detection and separation
    - Table of contents extraction
    - Running header detection and removal
    """

    SUPPORTED_EXTENSIONS = {'.pdf'}

    def __init__(
        self,
        *args,
        enable_ocr: bool = False,
        force_ocr: bool = False,
        ocr_backend: OCRBackend = OCRBackend.AUTO,
        ocr_language: str = "deu+eng",
        **kwargs
    ):
        """
        Initialize PDF extractor.

        Args:
            enable_ocr: Whether to use OCR for scanned pages (auto-detect)
            force_ocr: Force OCR even for digital PDFs (skip text extraction)
            ocr_backend: Which OCR backend to use (AUTO, TESSERACT, LIGHTON, OLMOCR)
            ocr_language: Language codes for Tesseract (e.g., "deu+eng")
            *args, **kwargs: Passed to BaseExtractor
        """
        super().__init__(*args, **kwargs)
        self.enable_ocr = enable_ocr
        self.force_ocr = force_ocr
        self.ocr_backend = ocr_backend
        self.ocr_language = ocr_language

    def supports(self, file_path: Path) -> bool:
        """Check if file is PDF."""
        return file_path.suffix.lower() in self.SUPPORTED_EXTENSIONS

    def extract(self, file_path: Path) -> ExtractedText:
        """
        Extract text from PDF using best available method.

        Tries in order:
        1. If force_ocr: Use OCR directly
        2. PyMuPDF (best word boundaries, especially for German block-set text)
        3. pdfplumber (fallback, better for some table-heavy layouts)
        4. If enable_ocr and result is empty/scanned: Use OCR

        Raises:
            PDFExtractionError: If all extraction methods fail
        """
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        if self.force_ocr:
            print("  [OCR] Force OCR enabled, skipping text extraction", flush=True)
            return self._extract_with_ocr(file_path)

        if self.enable_ocr and detect_scanned_pdf(file_path):
            print("  [OCR] Scanned PDF detected, using OCR", flush=True)
            return self._extract_with_ocr(file_path)

        errors = []

        # Try text-based extraction methods, falling back to OCR if result is sparse
        for name, available, method in [
            ("PyMuPDF", PYMUPDF_AVAILABLE, self._extract_with_pymupdf),
            ("pdfplumber", PDFPLUMBER_AVAILABLE, self._extract_with_pdfplumber),
        ]:
            if not available:
                continue
            try:
                result = method(file_path)
                if self.enable_ocr and self._is_extraction_empty(result):
                    print("  [OCR] Text extraction yielded little text, trying OCR", flush=True)
                    return self._extract_with_ocr(file_path)
                return result
            except Exception as e:
                errors.append(f"{name} failed: {e}")

        # Last resort: OCR
        if self.enable_ocr:
            try:
                return self._extract_with_ocr(file_path)
            except Exception as e:
                errors.append(f"OCR failed: {e}")

        error_msg = "All PDF extraction methods failed:\n" + "\n".join(errors)
        raise PDFExtractionError(error_msg)

    def _is_extraction_empty(self, result: ExtractedText, min_chars: int = 500) -> bool:
        """Check if extraction result has too little text (likely scanned)."""
        if not result.full_text:
            return True
        return len(result.full_text.strip()) < min_chars

    # ------------------------------------------------------------------
    # Backend-specific page extraction
    # ------------------------------------------------------------------

    def _extract_with_pdfplumber(self, file_path: Path) -> ExtractedText:
        """Extract using pdfplumber (best for complex layouts)."""
        pages_text = []
        pages_metadata = []
        footnotes = []
        toc = []  # pdfplumber has no built-in TOC; would need bookmark parsing

        with pdfplumber.open(file_path) as pdf:
            for page_num, page in enumerate(pdf.pages, start=1):
                text = page.extract_text()
                if not text or not text.strip():
                    continue

                pages_text.append(text)
                pages_metadata.append({
                    'page': page_num,
                    'page_label': str(page.page_number),
                    'height': page.height,
                    'width': page.width,
                })

        return self._build_extraction_result(
            pages_text, pages_metadata, file_path,
            toc=toc,
            footnotes=footnotes,
            method_label="pdfplumber",
        )

    def _extract_with_pymupdf(self, file_path: Path) -> ExtractedText:
        """Extract using PyMuPDF (faster, better word boundaries)."""
        doc = fitz.open(file_path)
        pages_text = []
        pages_metadata = []
        toc = []

        # Extract TOC
        try:
            toc = [
                {'level': level, 'title': title, 'page': page}
                for level, title, page in doc.get_toc()
            ]
        except Exception:
            pass

        # Get page labels (printed page numbers like "xiv", "1", "62")
        try:
            page_labels = doc.get_page_labels()
        except Exception:
            page_labels = None

        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text()
            if not text.strip():
                continue

            # Use PDF page label if available; dict means raw PageLabel spec, not resolved
            if page_labels and page_num < len(page_labels):
                raw_label = page_labels[page_num]
                page_label = str(page_num + 1) if isinstance(raw_label, dict) else str(raw_label)
            else:
                page_label = str(page_num + 1)

            pages_text.append(text)
            pages_metadata.append({
                'page': page_num + 1,       # Physical page (for navigation)
                'page_label': page_label,    # Printed page label (for citation)
            })

        doc.close()

        return self._build_extraction_result(
            pages_text, pages_metadata, file_path,
            toc=toc,
            method_label="PyMuPDF",
        )

    def _extract_with_ocr(self, file_path: Path) -> ExtractedText:
        """Extract using OCR (for scanned PDFs)."""
        start_time = time.time()

        try:
            from .ocr_extractor import TesseractExtractor
            ocr = get_ocr_extractor(self.ocr_backend)
            if isinstance(ocr, TesseractExtractor):
                ocr.language = self.ocr_language
        except RuntimeError as e:
            raise PDFExtractionError(f"OCR not available: {e}")

        print(f"  [OCR] Using {ocr.name} backend", flush=True)
        ocr_result = ocr.extract(file_path)
        print(
            f"  [OCR] Processed {ocr_result.successful_pages}/{ocr_result.total_pages} pages "
            f"in {ocr_result.processing_time_seconds:.1f}s "
            f"(avg confidence: {ocr_result.average_confidence:.0%})",
            flush=True,
        )

        pages_text = []
        pages_metadata = []
        for page in ocr_result.pages:
            if page.text.strip():
                pages_text.append(page.text)
                pages_metadata.append({
                    'page': page.page_number,
                    'page_label': str(page.page_number),
                    'ocr_confidence': page.confidence,
                })

        if not pages_text:
            raise PDFExtractionError("OCR extracted no text from document")

        full_text = '\n\n'.join(pages_text)
        chunks = self._create_chunks_with_pages(pages_text, pages_metadata, file_path, toc=[])

        extraction_metadata = self._create_extraction_metadata(
            file_path=file_path,
            format_name='pdf',
            extraction_time=time.time() - start_time,
            total_pages=ocr_result.total_pages,
            total_chars=len(full_text),
            total_words=len(full_text.split()),
            total_chunks=len(chunks),
        )
        extraction_metadata.warnings.append(f"Extracted with OCR ({ocr.name})")
        extraction_metadata.warnings.append(f"Average OCR confidence: {ocr_result.average_confidence:.0%}")
        extraction_metadata.warnings.extend(ocr_result.warnings)

        return ExtractedText(
            full_text=full_text,
            chunks=chunks,
            metadata=extraction_metadata,
            toc=[],
        )

    # ------------------------------------------------------------------
    # Shared post-processing (page labels, header removal, chunking)
    # ------------------------------------------------------------------

    def _build_extraction_result(
        self,
        pages_text: List[str],
        pages_metadata: List[Dict[str, Any]],
        file_path: Path,
        *,
        toc: List[Dict[str, Any]] = None,
        footnotes: List[Dict[str, Any]] = None,
        method_label: str = "unknown",
    ) -> ExtractedText:
        """
        Shared post-processing for PyMuPDF and pdfplumber backends.

        1. Extract page labels from headers (before header removal)
        2. Detect and remove running headers
        3. Create chunks and metadata
        """
        if toc is None:
            toc = []
        if footnotes is None:
            footnotes = []

        # Update page labels from printed headers/footers (fallback when PDF metadata is absent)
        self._update_page_labels(pages_text, pages_metadata)

        # Detect and remove running headers (Kolumnentitel)
        running_headers = self._detect_running_headers(pages_text)
        if running_headers:
            original_lines = sum(len(p.split('\n')) for p in pages_text)
            pages_text = self._remove_running_headers(pages_text, running_headers)
            removed = original_lines - sum(len(p.split('\n')) for p in pages_text)
            print(f"  Removed {removed} header lines from {len(pages_text)} pages", flush=True)

        full_text = '\n\n'.join(pages_text)
        chunks = self._create_chunks_with_pages(pages_text, pages_metadata, file_path, toc=toc)

        extraction_metadata = self._create_extraction_metadata(
            file_path=file_path,
            format_name='pdf',
            extraction_time=0,
            total_pages=len(pages_text),
            total_chars=len(full_text),
            total_words=len(full_text.split()),
            total_chunks=len(chunks),
        )
        extraction_metadata.warnings.append(f"Extracted with {method_label}")

        return ExtractedText(
            full_text=full_text,
            chunks=chunks,
            metadata=extraction_metadata,
            toc=toc,
            footnotes=footnotes,
        )

    def _update_page_labels(
        self,
        pages_text: List[str],
        pages_metadata: List[Dict[str, Any]],
    ) -> None:
        """Update pages_metadata in-place with labels extracted from headers/footers."""
        extracted_labels = self._extract_page_labels_from_headers(pages_text)
        for i, label in enumerate(extracted_labels):
            if not label or i >= len(pages_metadata):
                continue
            current_label = pages_metadata[i].get('page_label', '')
            # Only update if PDF did not provide a meaningful label
            if not current_label or current_label == str(pages_metadata[i].get('page', '')):
                pages_metadata[i]['page_label'] = label

    # ------------------------------------------------------------------
    # Chunking
    # ------------------------------------------------------------------

    def _create_chunks_with_pages(
        self,
        pages_text: List[str],
        pages_metadata: List[Dict],
        file_path: Path,
        toc: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """Create chunks while preserving page information and section type."""
        chunks = []
        total_pages = len(pages_text)

        for page_num, (page_text, page_meta) in enumerate(zip(pages_text, pages_metadata), start=1):
            section_type = self._detect_section_type(page_text, page_num, total_pages, toc)

            base_metadata = ChunkMetadata(
                source_file=str(file_path),
                format='pdf',
                page=page_meta['page'],
                page_label=page_meta.get('page_label'),
                section_type=section_type,
            )

            chunks.extend(self._create_chunks(page_text, base_metadata))

        return chunks

    # ------------------------------------------------------------------
    # Running header detection and removal
    # ------------------------------------------------------------------

    def _detect_running_headers(
        self,
        pages_text: List[str],
        min_occurrences: int = 3,
        similarity_threshold: float = 0.85,
    ) -> List[str]:
        """
        Detect running headers (Kolumnentitel) that repeat across pages.

        Extracts the first 3 non-empty lines per page, normalizes them,
        and groups by fuzzy similarity.  Headers appearing on at least
        *min_occurrences* pages are returned.
        """
        if len(pages_text) < min_occurrences:
            return []

        # Extract first 3 non-empty lines from each page (potential headers)
        first_lines = []
        for page_text in pages_text:
            lines_checked = 0
            for line in page_text.strip().split('\n'):
                if lines_checked >= 3:
                    break
                if not line.strip():
                    continue
                lines_checked += 1
                normalized = _normalize_header_line(line)
                if normalized and len(normalized) > 5:
                    first_lines.append(normalized)

        # Group similar headers; keep the longest variant as canonical
        header_groups: List[tuple] = []  # (canonical, count)

        for normalized in first_lines:
            matched = False
            for i, (canonical, count) in enumerate(header_groups):
                if _strings_are_similar(normalized, canonical, similarity_threshold):
                    best = normalized if len(normalized) > len(canonical) else canonical
                    header_groups[i] = (best, count + 1)
                    matched = True
                    break
            if not matched:
                header_groups.append((normalized, 1))

        running_headers = [
            header for header, count in header_groups
            if count >= min_occurrences
        ]

        # Diagnostic output
        print(f"  Header analysis: {len(first_lines)} candidate lines from {len(pages_text)} pages", flush=True)
        if header_groups:
            sorted_groups = sorted(header_groups, key=lambda x: x[1], reverse=True)[:5]
            print("  Top header patterns found:", flush=True)
            for h, count in sorted_groups:
                status = "Y" if count >= min_occurrences else "N"
                h_display = f"{h[:50]}..." if len(h) > 50 else h
                print(f"     [{status}] ({count}x): \"{h_display}\"", flush=True)

        if running_headers:
            print(f"  Will remove {len(running_headers)} running header patterns (threshold: {min_occurrences}+)", flush=True)

        return running_headers

    def _remove_running_headers(
        self,
        pages_text: List[str],
        running_headers: List[str],
        similarity_threshold: float = 0.85,
    ) -> List[str]:
        """Remove detected running headers from the first 3 non-empty lines of each page."""
        cleaned_pages = []

        for page_text in pages_text:
            lines = page_text.strip().split('\n')
            cleaned_lines = []
            lines_checked = 0

            for line in lines:
                if not line.strip():
                    cleaned_lines.append(line)
                    continue

                normalized = _normalize_header_line(line)

                is_header = False
                if lines_checked < 3 and normalized:
                    lines_checked += 1
                    for header in running_headers:
                        if _strings_are_similar(normalized, header, similarity_threshold):
                            is_header = True
                            break

                if not is_header:
                    cleaned_lines.append(line)

            cleaned_pages.append('\n'.join(cleaned_lines))

        return cleaned_pages

    # ------------------------------------------------------------------
    # Roman numeral utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _roman_to_int(roman: str) -> int:
        """Convert Roman numeral to integer."""
        values = {'I': 1, 'V': 5, 'X': 10, 'L': 50, 'C': 100, 'D': 500, 'M': 1000}
        result = 0
        prev = 0
        for char in reversed(roman.upper()):
            curr = values.get(char, 0)
            if curr < prev:
                result -= curr
            else:
                result += curr
            prev = curr
        return result

    _ROMAN_RE = re.compile(
        r'^(M{0,3})(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})$',
        re.IGNORECASE,
    )

    @classmethod
    def _is_roman(cls, s: str) -> bool:
        """Check if string is a valid Roman numeral."""
        return len(s) > 0 and bool(cls._ROMAN_RE.match(s))

    @staticmethod
    def _detect_roman_numerals(text: str) -> bool:
        """Detect if text contains roman numeral page numbers."""
        roman_pattern = r'\b(i{1,3}|iv|v|vi{0,3}|ix|x|xi{0,3}|xiv|xv|xvi{0,3}|xix|xx)\b'
        return bool(re.search(roman_pattern, text.lower()))

    # ------------------------------------------------------------------
    # Page label extraction from headers/footers
    # ------------------------------------------------------------------

    def _is_likely_footnote_line(self, line: str) -> bool:
        """
        Check if a line looks like a footnote rather than a page number.

        A standalone number is treated as a page number.  A small number (<=20)
        followed by text is treated as a footnote marker.  Multiple numbers
        separated by commas/dashes are footnote references.
        """
        line = line.strip()
        if not line or line.isdigit():
            return False

        # Small number + text = likely footnote
        match = re.match(r'^(\d+)[\.\)\s]\s*[A-Za-z\u00C4\u00D6\u00DC\u00E4\u00F6\u00FC\u00DF]', line)
        if match and int(match.group(1)) <= 20:
            return True

        # Multiple numbers with separators = footnote references
        return bool(re.search(r'\d+\s*[,\-]\s*\d+', line))

    def _extract_page_number_from_lines(
        self,
        lines: List[str],
        check_first: bool = True,
    ) -> str:
        """
        Extract page number from header (check_first=True) or footer lines.

        Returns the extracted page label or empty string.
        """
        non_empty = [line.strip() for line in lines if line.strip()]
        if not non_empty:
            return ""

        lines_to_check = non_empty[:3] if check_first else non_empty[-3:]

        for line in lines_to_check:
            if not check_first and self._is_likely_footnote_line(line):
                continue

            # Standalone number (most reliable)
            if line.isdigit():
                return line

            # Standalone Roman numeral
            if self._is_roman(line):
                return line.lower()

            # Number at start followed by header text
            match = re.match(r'^(\d+)\s+', line)
            if match:
                num = int(match.group(1))
                if not check_first and num <= 20 and len(line) > 10:
                    continue
                return match.group(1)

            # Number at end of header line
            match = re.search(r'\s(\d+)$', line)
            if match:
                return match.group(1)

            # Roman numerals at start or end
            parts = line.split()
            if parts:
                for candidate in [parts[0], parts[-1]]:
                    if self._is_roman(candidate):
                        return candidate.lower()

        return ""

    def _extract_page_labels_from_headers(
        self,
        pages_text: List[str],
    ) -> List[str]:
        """
        Extract printed page numbers from running headers/footers with validation.

        Steps:
        1. Raw extraction from headers and footers
        2. Convert to numeric for validation
        3. Validate sequence, remove outliers
        4. Interpolate missing values
        5. Convert back to strings (preserving Roman numerals in front matter)
        """
        # Step 1: Raw extraction
        raw_labels = []
        header_count = 0
        footer_count = 0

        for page_text in pages_text:
            lines = page_text.strip().split('\n')

            page_label = self._extract_page_number_from_lines(lines[:10], check_first=True)
            if page_label:
                header_count += 1
            else:
                page_label = self._extract_page_number_from_lines(lines[-10:], check_first=False)
                if page_label:
                    footer_count += 1

            raw_labels.append(page_label)

        # Step 2: Convert to numeric
        numeric_labels: List[Optional[int]] = []
        is_roman_sequence = False

        for label in raw_labels:
            if not label:
                numeric_labels.append(None)
            elif label.isdigit():
                numeric_labels.append(int(label))
            elif self._is_roman(label):
                numeric_labels.append(self._roman_to_int(label))
                is_roman_sequence = True
            else:
                numeric_labels.append(None)

        # Step 3: Validate sequence -- outliers differ >5 from neighbor-based expectation
        validated = numeric_labels.copy()

        for i in range(len(validated)):
            if validated[i] is None:
                continue

            neighbors = [
                (j, validated[j])
                for j in range(max(0, i - 3), min(len(validated), i + 4))
                if j != i and validated[j] is not None
            ]

            if len(neighbors) >= 2:
                avg_expected = sum(val + (i - j) for j, val in neighbors) / len(neighbors)
                if abs(validated[i] - avg_expected) > 5:
                    validated[i] = None

        # Step 4: Interpolate missing values
        interpolated = validated.copy()

        for i in range(len(interpolated)):
            if interpolated[i] is not None:
                continue

            prev_idx, prev_val = self._find_nearest_valid(interpolated, i, direction=-1)
            next_idx, next_val = self._find_nearest_valid(interpolated, i, direction=1)

            if prev_val is not None and next_val is not None:
                if next_val > prev_val:
                    step = (next_val - prev_val) / (next_idx - prev_idx)
                    interpolated[i] = int(prev_val + step * (i - prev_idx))
            elif prev_val is not None:
                interpolated[i] = prev_val + (i - prev_idx)
            elif next_val is not None:
                interpolated[i] = next_val - (next_idx - i)

        # Step 5: Convert back to strings
        final_labels = []
        front_matter_cutoff = len(interpolated) // 4

        for i, val in enumerate(interpolated):
            if val is None:
                final_labels.append("")
            elif is_roman_sequence and i < front_matter_cutoff:
                original = raw_labels[i]
                if original and self._is_roman(original):
                    final_labels.append(original.lower())
                else:
                    final_labels.append(str(val))
            else:
                final_labels.append(str(val))

        # Log results
        raw_found = sum(1 for label in raw_labels if label)
        final_found = sum(1 for label in final_labels if label)
        interpolated_count = final_found - raw_found

        if final_found > 0:
            sources = []
            if header_count > 0:
                sources.append(f"{header_count} header")
            if footer_count > 0:
                sources.append(f"{footer_count} footer")
            msg = f"  Page labels: {raw_found} extracted"
            if sources:
                msg += f" ({', '.join(sources)})"
            if interpolated_count > 0:
                msg += f", {interpolated_count} interpolated"
            msg += f" -> total: {final_found}/{len(pages_text)}"
            print(msg, flush=True)

        return final_labels

    @staticmethod
    def _find_nearest_valid(
        values: List[Optional[int]],
        index: int,
        direction: int,
    ) -> tuple:
        """Find the nearest non-None value in the given direction (-1 or +1)."""
        step = direction
        j = index + step
        while 0 <= j < len(values):
            if values[j] is not None:
                return j, values[j]
            j += step
        return None, None

    # ------------------------------------------------------------------
    # Section classification
    # ------------------------------------------------------------------

    _FRONT_MATTER_KEYWORDS = [
        'table of contents', 'contents', 'inhaltsverzeichnis',
        'preface', 'vorwort', 'introduction', 'einleitung',
        'acknowledgments', 'danksagung', 'copyright', 'isbn',
    ]

    _BACK_MATTER_KEYWORDS = [
        'index', 'register', 'sachregister', 'personenregister',
        'bibliography', 'literaturverzeichnis', 'references',
        'appendix', 'anhang', 'notes', 'anmerkungen',
    ]

    def _detect_section_type(
        self,
        page_text: str,
        page_num: int,
        total_pages: int,
        toc: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        """
        Classify a page as front_matter, main_content, or back_matter.

        Uses keyword matching in the first 5 lines, index-like structure
        detection, positional heuristics, and roman numeral presence.
        """
        if self._looks_like_index(page_text):
            return 'back_matter'

        lines = page_text.strip().split('\n')
        first_lines_lower = '\n'.join(lines[:5]).lower() if lines else ''

        for keyword in self._BACK_MATTER_KEYWORDS:
            if keyword in first_lines_lower:
                return 'back_matter'

        for keyword in self._FRONT_MATTER_KEYWORDS:
            if keyword in first_lines_lower:
                return 'front_matter'

        # First ~5% of pages with roman numerals are likely front matter
        if page_num <= max(3, total_pages * 0.05):
            if self._detect_roman_numerals(page_text[:100]):
                return 'front_matter'

        # Last 10% of pages are likely back matter
        if page_num >= total_pages * 0.90:
            return 'back_matter'

        return 'main_content'

    @staticmethod
    def _looks_like_index(page_text: str) -> bool:
        """
        Detect if page looks like an index (many short entries with page references).
        """
        lines = [line.strip() for line in page_text.split('\n') if line.strip()]
        if len(lines) < 10:
            return False

        page_ref_pattern = r'\d{1,4}(?:\s*[,;]\s*\d{1,4})+'
        page_refs = sum(1 for line in lines if re.search(page_ref_pattern, line))
        short_lines = sum(1 for line in lines if len(line) < 80)

        return page_refs > len(lines) * 0.5 and short_lines > len(lines) * 0.7
