"""EPUB text extractor."""

import logging
import re
import zipfile
from pathlib import Path
from typing import List, Dict, Any, Optional

try:
    import ebooklib
    from ebooklib import epub
    from bs4 import BeautifulSoup
    EBOOKLIB_AVAILABLE = True
except ImportError:
    EBOOKLIB_AVAILABLE = False

from .base import BaseExtractor
from .models import ExtractedText, ChunkMetadata
from .exceptions import EPUBExtractionError

logger = logging.getLogger(__name__)

# Compiled patterns for section number extraction
_SECTION_NUM_START = re.compile(r'^(\d+(?:\.\d+)*)\s+')
_SECTION_NUM_LABEL = re.compile(r'(?:Chapter|Section)\s+(\d+(?:\.\d+)*)', re.IGNORECASE)

# Section type classification patterns
_FRONT_MATTER_PATTERNS = frozenset([
    'preface', 'foreword', 'introduction', 'acknowledgments', 'acknowledgements',
    'dedication', 'table of contents', 'contents', 'toc', 'about the author',
    'about this book', 'prologue', 'copyright', 'title page',
    'half title', 'frontispiece', 'list of illustrations', 'list of maps',
])
_BACK_MATTER_PATTERNS = frozenset([
    'index', 'bibliography', 'references', 'glossary',
    'appendix', 'notes', 'endnotes', 'epilogue',
    'afterword', 'about the publisher', 'colophon',
])


class EPUBExtractor(BaseExtractor):
    """
    Extract text from EPUB files.

    Handles:
    - EPUB 2 and EPUB 3
    - Table of contents extraction
    - Chapter/section preservation
    - Metadata extraction (author, title, etc.)
    """

    SUPPORTED_EXTENSIONS = {'.epub'}

    def supports(self, file_path: Path) -> bool:
        """Check if file is EPUB."""
        return file_path.suffix.lower() in self.SUPPORTED_EXTENSIONS

    def extract(self, file_path: Path) -> ExtractedText:
        """
        Extract text from EPUB file.

        Args:
            file_path: Path to EPUB file

        Returns:
            ExtractedText object

        Raises:
            EPUBExtractionError: If extraction fails
        """
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        if not EBOOKLIB_AVAILABLE:
            return self._extract_manual(file_path)

        try:
            return self._extract_with_ebooklib(file_path)
        except Exception as e:
            try:
                return self._extract_manual(file_path)
            except Exception as e2:
                raise EPUBExtractionError(
                    f"EPUB extraction failed: {e}\nFallback also failed: {e2}"
                ) from e

    def _extract_with_ebooklib(self, file_path: Path) -> ExtractedText:
        """Extract using ebooklib library."""
        book = epub.read_epub(str(file_path))

        title = self._get_dc_metadata(book, 'title')
        author = self._get_dc_metadata(book, 'creator')
        language = self._get_dc_metadata(book, 'language')

        toc = self._extract_toc_ebooklib(book)
        toc_map = self._build_toc_map(toc)

        # Extract text from all document items
        chapters_text = []
        chapters_metadata = []

        for item in book.get_items():
            if item.get_type() != ebooklib.ITEM_DOCUMENT:
                continue

            text = self._extract_html_text(item.get_content())
            if not text.strip():
                continue

            chapters_text.append(text)

            # Determine chapter title from first <h1> if present
            soup = BeautifulSoup(item.get_content(), 'html.parser')
            h1 = soup.find('h1')
            chapter_title = h1.get_text(strip=True) if h1 else None

            item_name = item.get_name()
            toc_info = toc_map.get(item_name, {})

            chapters_metadata.append({
                'chapter': chapter_title or item_name,
                'section': toc_info.get('section'),
                'section_title': toc_info.get('title'),
                'section_type': self._detect_section_type(chapter_title or item_name),
                'file': item_name,
            })

        full_text = '\n\n---\n\n'.join(chapters_text)

        chunks = self._create_chunks_with_chapters(
            chapters_text, chapters_metadata, file_path, title, author
        )

        extraction_metadata = self._create_extraction_metadata(
            file_path=file_path,
            format_name='epub',
            extraction_time=0,
            total_chars=len(full_text),
            total_words=len(full_text.split()),
            total_chunks=len(chunks),
        )
        extraction_metadata.warnings.append("Extracted with ebooklib")

        return ExtractedText(
            full_text=full_text,
            chunks=chunks,
            metadata=extraction_metadata,
            toc=toc,
        )

    def _extract_manual(self, file_path: Path) -> ExtractedText:
        """
        Fallback: Manual extraction by unzipping EPUB.

        EPUB is a ZIP file containing HTML/XHTML files.
        """
        chapters_text = []

        with zipfile.ZipFile(file_path, 'r') as zip_ref:
            html_files = [
                name for name in zip_ref.namelist()
                if name.endswith(('.html', '.xhtml', '.htm'))
                and not name.startswith('__MACOSX')
            ]

            for html_file in sorted(html_files):
                try:
                    text = self._extract_html_text(zip_ref.read(html_file))
                    if text.strip():
                        chapters_text.append(text)
                except Exception:
                    continue

        if not chapters_text:
            raise EPUBExtractionError("No readable content found in EPUB")

        full_text = '\n\n---\n\n'.join(chapters_text)

        base_metadata = ChunkMetadata(
            source_file=str(file_path),
            format='epub',
        )
        chunks = self._create_chunks(full_text, base_metadata)

        extraction_metadata = self._create_extraction_metadata(
            file_path=file_path,
            format_name='epub',
            extraction_time=0,
            total_chars=len(full_text),
            total_words=len(full_text.split()),
            total_chunks=len(chunks),
        )
        extraction_metadata.warnings.append("Extracted with manual ZIP method (fallback)")

        return ExtractedText(
            full_text=full_text,
            chunks=chunks,
            metadata=extraction_metadata,
        )

    def _extract_toc_ebooklib(self, book) -> List[Dict[str, Any]]:
        """
        Extract table of contents from EPUB.

        Returns list of TOC entries with:
        - title: Chapter/section title
        - level: Nesting level (1, 2, 3...)
        - section: Section number if present (e.g., "19.20")
        - href: Link to file in EPUB
        """
        toc = []

        def make_toc_entry(title: str, href: Optional[str], level: int) -> Dict[str, Any]:
            """Build a TOC entry dict, including section number if found."""
            entry = {'title': title, 'level': level, 'href': href}
            section_num = self._extract_section_number(title)
            if section_num:
                entry['section'] = section_num
            return entry

        def parse_toc_item(item, level=1, parent_section=''):
            if isinstance(item, tuple):
                section_obj = item[0]
                children = item[1] if len(item) > 1 else []

                title = section_obj.title if hasattr(section_obj, 'title') else str(section_obj)
                href = section_obj.href if hasattr(section_obj, 'href') else None

                entry = make_toc_entry(title, href, level)
                toc.append(entry)

                section_num = entry.get('section', parent_section)
                for child in children:
                    parse_toc_item(child, level + 1, section_num)

            elif isinstance(item, list):
                for sub_item in item:
                    parse_toc_item(sub_item, level, parent_section)

        try:
            toc_items = book.toc
            if not toc_items:
                return toc

            if isinstance(toc_items, list):
                for item in toc_items:
                    if hasattr(item, 'href') and hasattr(item, 'title'):
                        # Link object (most common format)
                        title = item.title if item.title else str(item)
                        href = item.href if item.href else None
                        toc.append(make_toc_entry(title, href, level=1))
                    elif isinstance(item, tuple):
                        parse_toc_item(item, 1, '')
            elif isinstance(toc_items, tuple):
                parse_toc_item(toc_items, 1, '')
        except Exception as e:
            logger.warning("TOC extraction failed: %s: %s", type(e).__name__, e)

        return toc

    @staticmethod
    def _get_dc_metadata(book, field: str) -> Optional[str]:
        """Extract a Dublin Core metadata field from an EPUB book."""
        values = book.get_metadata('DC', field)
        return values[0][0] if values else None

    @staticmethod
    def _build_toc_map(toc: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
        """Build a mapping from href (without anchor) to TOC entry info."""
        toc_map = {}
        for entry in toc:
            href = entry.get('href')
            if href:
                href_base = href.split('#')[0]
                toc_map[href_base] = {
                    'section': entry.get('section'),
                    'title': entry.get('title'),
                    'level': entry.get('level', 1),
                }
        return toc_map

    @staticmethod
    def _extract_section_number(title: str) -> Optional[str]:
        """
        Extract section number from TOC title.

        Handles formats like:
        - "19.20 Land Warfare" -> "19.20"
        - "Chapter 3" -> "3"
        - "3.4.2 Tactics" -> "3.4.2"
        """
        match = _SECTION_NUM_START.match(title)
        if match:
            return match.group(1)

        match = _SECTION_NUM_LABEL.search(title)
        if match:
            return match.group(1)

        return None

    @staticmethod
    def _detect_section_type(title: str) -> str:
        """
        Detect if section is front matter, main content, or back matter.

        Returns:
            'front_matter', 'main_content', or 'back_matter'
        """
        title_lower = title.lower()

        if any(pattern in title_lower for pattern in _FRONT_MATTER_PATTERNS):
            return 'front_matter'
        if any(pattern in title_lower for pattern in _BACK_MATTER_PATTERNS):
            return 'back_matter'
        return 'main_content'

    def _extract_html_text(self, content: bytes) -> str:
        """Extract and clean text from HTML/XHTML content."""
        soup = BeautifulSoup(content, 'html.parser')
        for element in soup(['script', 'style']):
            element.decompose()
        text = soup.get_text(separator='\n\n')
        return self._clean_text(text)

    def _create_chunks_with_chapters(
        self,
        chapters_text: List[str],
        chapters_metadata: List[Dict],
        file_path: Path,
        title: str,
        author: str
    ) -> List[Dict[str, Any]]:
        """Create chunks with chapter and section information."""
        chunks = []

        for chapter_text, chapter_meta in zip(chapters_text, chapters_metadata):
            base_metadata = ChunkMetadata(
                source_file=str(file_path),
                format='epub',
                title=title,
                author=author,
                chapter=chapter_meta.get('chapter'),
                section=chapter_meta.get('section'),
                section_title=chapter_meta.get('section_title'),
                section_type=chapter_meta.get('section_type', 'main_content'),
            )

            chapter_chunks = self._create_chunks(chapter_text, base_metadata)
            chunks.extend(chapter_chunks)

        return chunks

    @staticmethod
    def _clean_text(text: str) -> str:
        """Clean extracted text by collapsing whitespace and blank lines."""
        lines = [line.strip() for line in text.split('\n')]
        lines = [line for line in lines if line]
        return '\n\n'.join(lines)
