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

        # Detect and remove running headers (Kolumnentitel)
        running_headers = self._detect_running_headers(pages_text)
        if running_headers:
            original_lines = sum(len(p.split('\n')) for p in pages_text)
            pages_text = self._remove_running_headers(pages_text, running_headers)
            new_lines = sum(len(p.split('\n')) for p in pages_text)
            print(f"  🧹 Removed {original_lines - new_lines} header lines from {len(pages_text)} pages")

        # Create chunks with page information and section detection
        chunks = self._create_chunks_with_pages(
            pages_text,
            pages_metadata,
            file_path,
            toc=toc
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

        # Detect and remove running headers (Kolumnentitel)
        running_headers = self._detect_running_headers(pages_text)
        if running_headers:
            original_lines = sum(len(p.split('\n')) for p in pages_text)
            pages_text = self._remove_running_headers(pages_text, running_headers)
            new_lines = sum(len(p.split('\n')) for p in pages_text)
            print(f"  🧹 Removed {original_lines - new_lines} header lines from {len(pages_text)} pages")

        # Create chunks with page information and section detection
        chunks = self._create_chunks_with_pages(
            pages_text,
            pages_metadata,
            file_path,
            toc=toc
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
        file_path: Path,
        toc: List[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Create chunks while preserving page information.

        Each chunk knows which page(s) it comes from and what section type.
        """
        chunks = []
        total_pages = len(pages_text)

        for page_num, (page_text, page_meta) in enumerate(zip(pages_text, pages_metadata), start=1):
            # Detect section type (front_matter, main_content, back_matter)
            section_type = self._detect_section_type(
                page_text, page_num, total_pages, toc
            )

            # Create base metadata for this page
            base_metadata = ChunkMetadata(
                source_file=str(file_path),
                format='pdf',
                page=page_meta['page'],
                page_label=page_meta.get('page_label'),
                section_type=section_type,
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

    def _detect_running_headers(
        self,
        pages_text: List[str],
        min_occurrences: int = 3,
        similarity_threshold: float = 0.85
    ) -> List[str]:
        """
        Detect running headers (Kolumnentitel) that repeat across pages.

        Running headers are typically:
        - The first line(s) of each page
        - Repeat identically (or with only page number changes) across multiple pages
        - Often contain chapter titles or book title

        Uses fuzzy matching to handle OCR errors (e.g., "Narbonne" vs "Narbome").

        Args:
            pages_text: List of page texts
            min_occurrences: Minimum times a header must appear to be considered running
            similarity_threshold: Minimum similarity ratio for fuzzy matching (0.0-1.0)

        Returns:
            List of detected running header patterns
        """
        if len(pages_text) < min_occurrences:
            return []

        from collections import Counter
        from difflib import SequenceMatcher

        def similar(a: str, b: str) -> bool:
            """Check if two strings are similar enough (handles OCR errors)."""
            if not a or not b:
                return False
            ratio = SequenceMatcher(None, a.lower(), b.lower()).ratio()
            return ratio >= similarity_threshold

        # Extract first 3 non-empty lines from each page (potential headers)
        # Line 1 might be page number, lines 2-3 might be actual headers (verso/recto)
        first_lines = []
        for page_text in pages_text:
            lines = page_text.strip().split('\n')
            lines_checked = 0
            # Check first 3 non-empty lines for potential headers
            for line in lines:
                if lines_checked >= 3:
                    break
                if not line.strip():
                    continue
                lines_checked += 1
                # Normalize whitespace
                line_normalized = ' '.join(line.split())
                # Remove page numbers (digits at start or end)
                line_normalized = re.sub(r'^\d+\s*', '', line_normalized)
                line_normalized = re.sub(r'\s*\d+$', '', line_normalized)
                # Skip if too short or just numbers
                if line_normalized and len(line_normalized) > 5:
                    first_lines.append((line, line_normalized))

        # Group similar headers together (handles OCR variations)
        # Use the most common variant as the canonical form
        header_groups = []  # List of (canonical_header, count)

        for _, normalized in first_lines:
            found_group = False
            for i, (canonical, count) in enumerate(header_groups):
                if similar(normalized, canonical):
                    # Add to existing group, keep the longer variant as canonical
                    if len(normalized) > len(canonical):
                        header_groups[i] = (normalized, count + 1)
                    else:
                        header_groups[i] = (canonical, count + 1)
                    found_group = True
                    break

            if not found_group:
                header_groups.append((normalized, 1))

        # Headers (or header groups) that appear on multiple pages
        running_headers = [
            header for header, count in header_groups
            if count >= min_occurrences
        ]

        # Debug output - always show what was found
        print(f"  📊 Header analysis: {len(first_lines)} candidate lines from {len(pages_text)} pages")
        if header_groups:
            # Show top 5 header groups by count
            sorted_groups = sorted(header_groups, key=lambda x: x[1], reverse=True)[:5]
            print(f"  📋 Top header patterns found:")
            for h, count in sorted_groups:
                status = "✓" if count >= min_occurrences else "✗"
                h_display = f"{h[:50]}..." if len(h) > 50 else h
                print(f"     {status} ({count}x): \"{h_display}\"")

        if running_headers:
            print(f"  🧹 Will remove {len(running_headers)} running header patterns (threshold: {min_occurrences}+)")

        return running_headers

    def _remove_running_headers(
        self,
        pages_text: List[str],
        running_headers: List[str],
        similarity_threshold: float = 0.85
    ) -> List[str]:
        """
        Remove detected running headers from page texts.

        Uses fuzzy matching to handle OCR variations.

        Args:
            pages_text: List of page texts
            running_headers: List of running header patterns to remove
            similarity_threshold: Minimum similarity ratio for fuzzy matching

        Returns:
            List of page texts with running headers removed
        """
        from difflib import SequenceMatcher

        def similar(a: str, b: str) -> bool:
            """Check if two strings are similar enough."""
            if not a or not b:
                return False
            # Exact match or containment
            if a == b or b in a:
                return True
            # Fuzzy match
            ratio = SequenceMatcher(None, a.lower(), b.lower()).ratio()
            return ratio >= similarity_threshold

        cleaned_pages = []

        for page_text in pages_text:
            # Use strip().split() to match detection preprocessing exactly
            lines = page_text.strip().split('\n')
            cleaned_lines = []
            lines_checked = 0  # Track non-empty lines checked

            for line in lines:
                # Normalize the line for comparison
                line_stripped = line.strip()
                if not line_stripped:
                    cleaned_lines.append(line)
                    continue

                line_normalized = ' '.join(line_stripped.split())
                line_normalized = re.sub(r'^\d+\s*', '', line_normalized)
                line_normalized = re.sub(r'\s*\d+$', '', line_normalized)

                # Only check first 3 non-empty lines for running headers
                is_header = False
                if lines_checked < 3 and line_normalized:
                    lines_checked += 1
                    for header in running_headers:
                        if similar(line_normalized, header):
                            is_header = True
                            break

                if not is_header:
                    cleaned_lines.append(line)

            cleaned_pages.append('\n'.join(cleaned_lines))

        return cleaned_pages

    def _detect_section_type(
        self,
        page_text: str,
        page_num: int,
        total_pages: int,
        toc: List[Dict[str, Any]] = None
    ) -> str:
        """
        Detect the section type of a page.

        Returns one of:
        - 'front_matter': Title page, TOC, preface, introduction with roman numerals
        - 'main_content': Main body of the book
        - 'back_matter': Index, bibliography, appendix
        - 'unknown': Cannot determine

        Args:
            page_text: Text content of the page
            page_num: Page number (1-indexed)
            total_pages: Total number of pages
            toc: Table of contents if available

        Returns:
            Section type string
        """
        text_lower = page_text.lower()
        lines = page_text.strip().split('\n')

        # Front matter indicators
        front_matter_keywords = [
            'table of contents', 'contents', 'inhaltsverzeichnis',
            'preface', 'vorwort', 'introduction', 'einleitung',
            'acknowledgments', 'danksagung', 'copyright', 'isbn'
        ]

        # Back matter indicators
        back_matter_keywords = [
            'index', 'register', 'sachregister', 'personenregister',
            'bibliography', 'literaturverzeichnis', 'references',
            'appendix', 'anhang', 'notes', 'anmerkungen'
        ]

        # Check for index-like structure (short entries, alphabetical)
        if self._looks_like_index(page_text):
            return 'back_matter'

        # Check keywords in first few lines
        first_lines = '\n'.join(lines[:5]).lower() if lines else ''

        for keyword in back_matter_keywords:
            if keyword in first_lines:
                return 'back_matter'

        for keyword in front_matter_keywords:
            if keyword in first_lines:
                return 'front_matter'

        # Heuristic: first 5% of pages are likely front matter
        if page_num <= max(3, total_pages * 0.05):
            # Check for roman numerals
            if self._detect_roman_numerals(page_text[:100]):
                return 'front_matter'

        # Heuristic: last 10% of pages are likely back matter
        if page_num >= total_pages * 0.90:
            return 'back_matter'

        return 'main_content'

    @staticmethod
    def _looks_like_index(page_text: str) -> bool:
        """
        Detect if page looks like an index (many short entries, page numbers).

        Index pages typically have:
        - Many short lines
        - Lots of page number references (digits with commas)
        - Alphabetical structure
        """
        lines = [l.strip() for l in page_text.split('\n') if l.strip()]

        if len(lines) < 10:
            return False

        # Check for page number patterns (e.g., "123, 456, 789")
        page_ref_pattern = r'\d{1,4}(?:\s*[,;]\s*\d{1,4})+'
        page_refs = sum(1 for line in lines if re.search(page_ref_pattern, line))

        # Check for short lines (typical for index entries)
        short_lines = sum(1 for line in lines if len(line) < 80)

        # If >50% of lines have page refs and >70% are short, likely an index
        if page_refs > len(lines) * 0.5 and short_lines > len(lines) * 0.7:
            return True

        return False
