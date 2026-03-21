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

        # Detect and remove running footers (Verlagsnamen, URLs, etc.)
        running_footers = self._detect_running_footers(pages_text)
        if running_footers:
            original_lines = sum(len(p.split('\n')) for p in pages_text)
            pages_text = self._remove_running_footers(pages_text, running_footers)
            removed = original_lines - sum(len(p.split('\n')) for p in pages_text)
            print(f"  Removed {removed} footer lines from {len(pages_text)} pages", flush=True)

        # Strip standalone page numbers that survived header/footer removal
        pages_text = self._strip_standalone_page_numbers(pages_text, pages_metadata)

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

    @staticmethod
    def _strip_standalone_page_numbers(
        pages_text: List[str],
        pages_metadata: List[Dict[str, Any]],
    ) -> List[str]:
        """Remove standalone page numbers from the beginning/end of each page.

        After header/footer removal, some pages still start or end with a
        bare number that matches the page label.  These are printed page
        numbers that weren't part of a detected running header pattern.

        Also strips page numbers embedded at the start of the first content
        line (e.g. "119 Nachbarschaft..." → "Nachbarschaft...").
        """
        cleaned = []
        for i, page_text in enumerate(pages_text):
            if i >= len(pages_metadata):
                cleaned.append(page_text)
                continue

            label = str(pages_metadata[i].get('page_label', ''))
            page_num = str(pages_metadata[i].get('page', ''))
            if not label and not page_num:
                cleaned.append(page_text)
                continue

            candidates = {label, page_num}
            candidates.discard('')

            lines = page_text.split('\n')
            new_lines = []
            for j, line in enumerate(lines):
                stripped = line.strip()

                # Only check first 3 and last 2 lines
                if j < 3 or j >= len(lines) - 2:
                    # Standalone number matching page label
                    if stripped in candidates:
                        continue

                    # Number at start of line: "119 Nachbarschaft..."
                    if j < 3 and stripped:
                        for cand in candidates:
                            prefix = cand + ' '
                            if stripped.startswith(prefix) and len(stripped) > len(prefix) + 2:
                                # Only strip if remainder starts with a letter
                                remainder = stripped[len(prefix):]
                                if remainder[0].isalpha():
                                    line = remainder
                                    break

                new_lines.append(line)
            cleaned.append('\n'.join(new_lines))
        return cleaned

    # ------------------------------------------------------------------
    # Chunking
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # TOC-to-page mapping
    # ------------------------------------------------------------------

    @staticmethod
    def _build_page_toc_map(
        toc: List[Dict[str, Any]],
    ) -> Dict[int, Dict[str, str]]:
        """
        Build a mapping from physical page number to chapter/section info.

        Returns {page_number: {chapter, section_title, toc_section_type}}
        where toc_section_type is derived from TOC title keywords.
        """
        if not toc or len(toc) < 3:
            return {}

        # Filter out junk TOCs (scanner artifacts, all pointing to page 1, etc.)
        pages_referenced = {e['page'] for e in toc}
        if len(pages_referenced) <= 1:
            return {}
        junk_pattern = re.compile(r'^(scan\s*\d+|z\s*-\s*|page\s*\d+$|\d+$)', re.IGNORECASE)
        junk_count = sum(1 for e in toc if junk_pattern.match(e['title'].strip()))
        if junk_count > len(toc) * 0.5:
            return {}

        # Sort by page, preserving original order for same-page entries
        sorted_toc = sorted(toc, key=lambda e: e['page'])

        # Build page ranges: each entry covers from its page to next entry's page - 1
        # Track current level-1 heading as "chapter", deeper levels as "section_title"
        current_chapter = ''
        entries_with_ranges = []
        for i, entry in enumerate(sorted_toc):
            end_page = sorted_toc[i + 1]['page'] - 1 if i + 1 < len(sorted_toc) else 999999
            entries_with_ranges.append({
                'level': entry['level'],
                'title': entry['title'],
                'start': entry['page'],
                'end': end_page,
            })

        # Assign chapter/section_title per page
        page_map: Dict[int, Dict[str, str]] = {}
        current_chapter = ''
        current_section = ''

        for entry in entries_with_ranges:
            if entry['level'] == 1:
                current_chapter = entry['title']
                current_section = ''
            else:
                current_section = entry['title']

            for p in range(entry['start'], entry['end'] + 1):
                # Only set if not already set by a more specific (deeper) entry
                if p not in page_map:
                    page_map[p] = {
                        'chapter': current_chapter,
                        'section_title': current_section,
                    }
                elif entry['level'] > 1:
                    # Deeper entry overrides section_title but keeps chapter
                    page_map[p]['section_title'] = current_section

        return page_map

    _FRONT_MATTER_TOC_KEYWORDS = frozenset([
        'preface', 'vorwort', 'foreword', 'geleitwort',
        'acknowledgments', 'acknowledgements', 'danksagung',
        'table of contents', 'contents', 'inhaltsverzeichnis', 'inhalt',
        'dedication', 'widmung', 'about the author', 'über den autor',
        'prologue', 'prolog', 'copyright', 'isbn',
        # NB: "introduction/einleitung" bewusst NICHT hier —
        # Einleitungen sind inhaltlich relevant und gehören zu main_content.
    ])

    _BACK_MATTER_TOC_KEYWORDS = frozenset([
        'index', 'register', 'sachregister', 'personenregister', 'namenregister',
        'bibliography', 'bibliographie', 'literaturverzeichnis', 'literatur',
        'references', 'quellenverzeichnis',
        'glossary', 'glossar',
        'appendix', 'anhang',
        'notes', 'endnotes', 'anmerkungen', 'endnoten',
        'epilogue', 'epilog', 'nachwort', 'afterword',
        'abbreviations', 'abkürzungen', 'abkürzungsverzeichnis',
    ])

    @classmethod
    def _section_type_from_toc_title(cls, title: str) -> Optional[str]:
        """Derive section_type from a TOC entry title, or None if unclear."""
        t = title.strip().lower()
        for kw in cls._BACK_MATTER_TOC_KEYWORDS:
            if kw in t:
                return 'back_matter'
        for kw in cls._FRONT_MATTER_TOC_KEYWORDS:
            if kw in t:
                return 'front_matter'
        return None

    def _create_chunks_with_pages(
        self,
        pages_text: List[str],
        pages_metadata: List[Dict],
        file_path: Path,
        toc: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """Create chunks across page boundaries while preserving page metadata.

        Builds a flat list of (paragraph, page_metadata) across all pages,
        then aggregates paragraphs into chunks up to ``chunk_size`` — exactly
        like ``_create_chunks`` but without stopping at page boundaries.
        Each chunk inherits the metadata of its first paragraph's page.
        """
        total_pages = len(pages_text)
        page_toc_map = self._build_page_toc_map(toc or [])

        # Phase 1: collect all paragraphs with their page metadata
        all_paragraphs: List[tuple] = []  # (text, ChunkMetadata)

        for page_num, (page_text, page_meta) in enumerate(
            zip(pages_text, pages_metadata), start=1
        ):
            phys_page = page_meta['page']
            toc_info = page_toc_map.get(phys_page, {})

            toc_section_type = None
            chapter = toc_info.get('chapter', '')
            section_title = toc_info.get('section_title', '')
            if chapter:
                toc_section_type = self._section_type_from_toc_title(chapter)
            if toc_section_type is None and section_title:
                toc_section_type = self._section_type_from_toc_title(section_title)

            if toc_section_type is not None:
                section_type = toc_section_type
            elif chapter:
                # TOC entry exists but title doesn't match front/back keywords
                # → default to main_content (don't fall through to heuristic)
                section_type = 'main_content'
            else:
                section_type = self._detect_section_type(
                    page_text, page_num, total_pages, toc
                )

            meta = ChunkMetadata(
                source_file=str(file_path),
                format='pdf',
                page=page_meta['page'],
                page_label=page_meta.get('page_label'),
                chapter=chapter or None,
                section_title=section_title or None,
                section_type=section_type,
            )

            page_text = self._detect_paragraph_breaks(page_text)
            for raw in page_text.split('\n\n'):
                raw = raw.strip()
                if not raw:
                    continue
                all_paragraphs.append((raw, meta))

        if not all_paragraphs:
            return []

        # Phase 2: aggregate paragraphs into chunks (mirrors _create_chunks)
        chunks: List[Dict[str, Any]] = []
        current_paras: List[tuple] = []  # (text, meta)
        current_size = 0.0
        overlap_prefix = ""  # sentence-aligned overlap text from previous chunk

        for para_text, para_meta in all_paragraphs:
            para_tokens = len(para_text.split()) * 1.3

            if current_size + para_tokens > self.chunk_size and current_paras:
                chunk_text = '\n\n'.join(t for t, _ in current_paras)
                chunk_meta = self._copy_metadata(current_paras[0][1])
                chunks.append({
                    'text': chunk_text,
                    'metadata': chunk_meta.__dict__,
                })

                if self.overlap > 0:
                    # Build sentence-aligned overlap from end of chunk
                    overlap_prefix = self._extract_overlap_tail(chunk_text, self.overlap)

                # Start new chunk, optionally prepending overlap text
                if overlap_prefix:
                    overlap_tokens = len(overlap_prefix.split()) * 1.3
                    # Use last paragraph's meta for the overlap context
                    current_paras = [(overlap_prefix, current_paras[-1][1]),
                                     (para_text, para_meta)]
                    current_size = overlap_tokens + para_tokens
                    overlap_prefix = ""
                else:
                    current_paras = [(para_text, para_meta)]
                    current_size = para_tokens
            else:
                current_paras.append((para_text, para_meta))
                current_size += para_tokens

        if current_paras:
            chunk_text = '\n\n'.join(t for t, _ in current_paras)
            chunk_meta = self._copy_metadata(current_paras[0][1])
            chunks.append({
                'text': chunk_text,
                'metadata': chunk_meta.__dict__,
            })

        # Phase 3: window text (Small-to-Big context)
        full_text = '\n\n'.join(t for t, _ in all_paragraphs)
        char_pos = 0
        for chunk in chunks:
            # Skip overlap prefix when searching — overlap text duplicates
            # content from the previous chunk and won't match at char_pos.
            # Search for a unique snippet from later in the chunk instead.
            search_text = chunk['text']
            parts = search_text.split('\n\n', 1)
            if len(parts) > 1:
                # Try finding the second paragraph (post-overlap)
                found = full_text.find(parts[1], char_pos)
                if found >= 0:
                    # Extend start back to include overlap
                    overlap_len = len(parts[0]) + 2  # +2 for \n\n
                    chunk['metadata']['char_start'] = max(0, found - overlap_len)
                    chunk['metadata']['char_end'] = found + len(parts[1])
                    char_pos = found
                    continue

            found = full_text.find(search_text, char_pos)
            if found >= 0:
                chunk['metadata']['char_start'] = found
                chunk['metadata']['char_end'] = found + len(search_text)
                char_pos = found
            else:
                chunk['metadata']['char_start'] = char_pos
                chunk['metadata']['char_end'] = char_pos + len(search_text)
        self._add_window_text(chunks, full_text, 500)

        return chunks

    # ------------------------------------------------------------------
    # Sentence-aligned overlap
    # ------------------------------------------------------------------

    _SENTENCE_END_RE = re.compile(r'[.!?:»"]\s')

    @classmethod
    def _extract_overlap_tail(cls, text: str, target_tokens: int) -> str:
        """Extract the last ~target_tokens from text, aligned to a sentence boundary.

        Scans backward from the end of *text* to find a sentence-ending
        punctuation mark (. ! ? : ») followed by whitespace.  Returns the
        text from the nearest sentence start that fits within
        *target_tokens*.  If no sentence boundary is found, falls back to
        the last *target_tokens* words.
        """
        words = text.split()
        if len(words) <= target_tokens:
            return text

        # Take roughly target_tokens words from the end
        tail = ' '.join(words[-target_tokens:])

        # Find the first sentence boundary in the tail to align the start
        match = cls._SENTENCE_END_RE.search(tail)
        if match:
            # Start after the sentence-ending punctuation + space
            aligned = tail[match.end():].strip()
            # Only use aligned version if it retains at least 40% of target
            if len(aligned.split()) >= target_tokens * 0.4:
                return aligned

        return tail

    # ------------------------------------------------------------------
    # Paragraph break detection
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_paragraph_breaks(text: str) -> str:
        """Upgrade single newlines to double newlines at likely paragraph boundaries.

        PyMuPDF yields only ``\\n`` between lines.  The downstream chunker
        splits on ``\\n\\n``, so without this step an entire page is treated
        as one paragraph — leading to near-duplicate chunks when the text
        exceeds ``max_tokens``.

        Heuristics (applied per consecutive line pair):
        1. Short previous line (< 65 % of avg length) NOT ending with
           hyphen, followed by a line starting with an uppercase letter.
        2. Previous line ends with sentence-terminal punctuation AND is
           short, next line starts uppercase.
        3. Next line is indented (4+ spaces or tab) while previous is not.

        Suppression rules:
        - Lines ending with ``-`` (hyphenation) never trigger a break.
        - Footnote zone (bottom half of page): continuation lines inside a
          footnote entry are kept together; a new footnote number starts a
          new paragraph.
        """
        # Early exit: text already contains paragraph separators
        if '\n\n' in text:
            return text

        lines = text.split('\n')
        if len(lines) < 2:
            return text

        # Compute average non-empty line length for "short line" threshold
        lengths = [len(l) for l in lines if l.strip()]
        if not lengths:
            return text
        avg_len = sum(lengths) / len(lengths)
        short_threshold = avg_len * 0.65

        # Footnote zone heuristic: bottom half of the lines
        footnote_zone_start = len(lines) // 2
        fn_number_re = re.compile(r'^\d{1,3}[\s\.]')

        result_lines: list[str] = [lines[0]]
        in_footnote = False

        for i in range(1, len(lines)):
            prev = lines[i - 1]
            curr = lines[i]
            prev_stripped = prev.rstrip()
            curr_stripped = curr.lstrip()

            is_break = False

            # --- Suppression: hyphenation --------------------------------
            if prev_stripped.endswith('-'):
                result_lines.append(curr)
                continue

            # --- Suppression / special handling: footnote zone -----------
            if i >= footnote_zone_start:
                if fn_number_re.match(curr_stripped):
                    # New footnote entry → paragraph break
                    is_break = True
                    in_footnote = True
                elif in_footnote:
                    # Continuation inside a footnote → no break
                    result_lines.append(curr)
                    continue

            # --- Heuristic 3: indentation --------------------------------
            if not is_break:
                prev_indent = len(prev) - len(prev.lstrip())
                curr_indent = len(curr) - len(curr.lstrip())
                if curr_indent >= 4 and prev_indent < 4:
                    is_break = True

            # --- Heuristic 1+2: short prev line + sentence end ----------
            if not is_break and len(prev_stripped) < short_threshold:
                if (prev_stripped and prev_stripped[-1] in '.?!:'
                        and curr_stripped and curr_stripped[0].isupper()):
                    is_break = True

            if is_break:
                result_lines.append('\n' + curr)  # extra \n → \n\n when joined
            else:
                result_lines.append(curr)

        return '\n'.join(result_lines)

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
    # Running footer detection and removal
    # ------------------------------------------------------------------

    def _detect_running_footers(
        self,
        pages_text: List[str],
        min_occurrences: Optional[int] = None,
        similarity_threshold: float = 0.85,
    ) -> List[str]:
        """
        Detect running footers that repeat across pages.

        Mirrors _detect_running_headers but checks the last 3 non-empty
        lines of each page. Uses a higher default threshold than headers
        (5% of pages, minimum 10) to avoid false positives from repeated
        footnotes.
        """
        if min_occurrences is None:
            min_occurrences = max(10, len(pages_text) // 20)
        if len(pages_text) < min_occurrences:
            return []

        last_lines = []
        for page_text in pages_text:
            lines = page_text.strip().split('\n')
            lines_checked = 0
            for line in reversed(lines):
                if lines_checked >= 3:
                    break
                if not line.strip():
                    continue
                lines_checked += 1
                normalized = _normalize_header_line(line)
                if normalized and len(normalized) > 5:
                    last_lines.append(normalized)

        # Group similar footers
        footer_groups: List[tuple] = []
        for normalized in last_lines:
            matched = False
            for i, (canonical, count) in enumerate(footer_groups):
                if _strings_are_similar(normalized, canonical, similarity_threshold):
                    best = normalized if len(normalized) > len(canonical) else canonical
                    footer_groups[i] = (best, count + 1)
                    matched = True
                    break
            if not matched:
                footer_groups.append((normalized, 1))

        running_footers = [
            footer for footer, count in footer_groups
            if count >= min_occurrences
        ]

        if running_footers:
            print(f"  Footer analysis: {len(running_footers)} running footer pattern(s) found", flush=True)
            for f in running_footers[:5]:
                f_display = f"{f[:50]}..." if len(f) > 50 else f
                print(f"     \"{f_display}\"", flush=True)

        return running_footers

    def _remove_running_footers(
        self,
        pages_text: List[str],
        running_footers: List[str],
        similarity_threshold: float = 0.85,
    ) -> List[str]:
        """Remove detected running footers from the last 3 non-empty lines of each page."""
        cleaned_pages = []

        for page_text in pages_text:
            lines = page_text.strip().split('\n')

            # Identify footer lines by scanning from the end
            footer_indices = set()
            lines_checked = 0
            for idx in range(len(lines) - 1, -1, -1):
                if lines_checked >= 3:
                    break
                if not lines[idx].strip():
                    continue
                lines_checked += 1
                normalized = _normalize_header_line(lines[idx])
                if normalized:
                    for footer in running_footers:
                        if _strings_are_similar(normalized, footer, similarity_threshold):
                            footer_indices.add(idx)
                            break

            cleaned_lines = [
                line for idx, line in enumerate(lines)
                if idx not in footer_indices
            ]
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
