"""EPUB text extractor."""

from pathlib import Path
from typing import List, Dict, Any, Optional
import zipfile
import xml.etree.ElementTree as ET

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
            # Fallback to manual ZIP extraction
            return self._extract_manual(file_path)

        try:
            return self._extract_with_ebooklib(file_path)
        except Exception as e:
            # Try fallback
            try:
                return self._extract_manual(file_path)
            except Exception as e2:
                raise EPUBExtractionError(
                    f"EPUB extraction failed: {e}\nFallback also failed: {e2}"
                ) from e

    def _extract_with_ebooklib(self, file_path: Path) -> ExtractedText:
        """Extract using ebooklib library."""
        book = epub.read_epub(str(file_path))

        # Extract metadata
        title = book.get_metadata('DC', 'title')
        title = title[0][0] if title else None

        author = book.get_metadata('DC', 'creator')
        author = author[0][0] if author else None

        language = book.get_metadata('DC', 'language')
        language = language[0][0] if language else None

        # Extract TOC
        toc = self._extract_toc_ebooklib(book)
        print(f"  DEBUG: Extracted {len(toc)} TOC entries")
        if toc and len(toc) > 0:
            print(f"  DEBUG: First TOC entry: {toc[0]}")

        # Build href -> TOC mapping for section numbers
        toc_map = {}
        for toc_entry in toc:
            if toc_entry.get('href'):
                # Strip anchor from href (e.g., "chapter3.xhtml#section2" -> "chapter3.xhtml")
                href_base = toc_entry['href'].split('#')[0]
                toc_map[href_base] = {
                    'section': toc_entry.get('section'),
                    'title': toc_entry.get('title'),
                    'level': toc_entry.get('level', 1),
                }
        print(f"  DEBUG: Built toc_map with {len(toc_map)} entries")
        if len(toc_map) > 0:
            print(f"  DEBUG: toc_map keys (first 3): {list(toc_map.keys())[:3]}")

        # Extract text from all chapters
        chapters_text = []
        chapters_metadata = []

        for item in book.get_items():
            if item.get_type() == ebooklib.ITEM_DOCUMENT:
                # Extract text from HTML content
                content = item.get_content()
                soup = BeautifulSoup(content, 'html.parser')

                # Remove scripts and styles
                for element in soup(['script', 'style']):
                    element.decompose()

                text = soup.get_text(separator='\n\n')
                text = self._clean_text(text)

                if text.strip():
                    chapters_text.append(text)

                    # Try to find chapter title
                    chapter_title = None
                    h1 = soup.find('h1')
                    if h1:
                        chapter_title = h1.get_text(strip=True)

                    # Get section info from TOC if available
                    item_name = item.get_name()
                    toc_info = toc_map.get(item_name, {})

                    # Detect section type (front_matter, main_content, back_matter)
                    section_type = self._detect_section_type(chapter_title or item_name)

                    # DEBUG: Print first few chapters
                    if len(chapters_metadata) < 3:
                        print(f"  DEBUG Chapter {len(chapters_metadata)}: {chapter_title or item_name}")
                        print(f"         Item name: {item_name}")
                        print(f"         Section type: {section_type}")
                        print(f"         TOC info: {toc_info}")

                    chapters_metadata.append({
                        'chapter': chapter_title or item_name,
                        'section': toc_info.get('section'),
                        'section_title': toc_info.get('title'),
                        'section_type': section_type,
                        'file': item_name,
                    })

        full_text = '\n\n---\n\n'.join(chapters_text)

        # Create chunks with chapter information
        chunks = self._create_chunks_with_chapters(
            chapters_text,
            chapters_metadata,
            file_path,
            title,
            author
        )

        # Create extraction metadata
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
            # Find all HTML/XHTML files
            html_files = [
                name for name in zip_ref.namelist()
                if name.endswith(('.html', '.xhtml', '.htm'))
                and not name.startswith('__MACOSX')
            ]

            for html_file in sorted(html_files):
                try:
                    content = zip_ref.read(html_file)
                    soup = BeautifulSoup(content, 'html.parser')

                    for element in soup(['script', 'style']):
                        element.decompose()

                    text = soup.get_text(separator='\n\n')
                    text = self._clean_text(text)

                    if text.strip():
                        chapters_text.append(text)
                except Exception:
                    continue

        if not chapters_text:
            raise EPUBExtractionError("No readable content found in EPUB")

        full_text = '\n\n---\n\n'.join(chapters_text)

        # Create simple chunks (no chapter metadata in fallback mode)
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
        section_counters = [0, 0, 0, 0, 0]  # Track section numbers at each level

        def parse_toc_item(item, level=1, parent_section=''):
            if isinstance(item, tuple):
                # TOC entry with possible children
                section, children = item[0], item[1] if len(item) > 1 else []

                # Extract title and href
                title = section.title if hasattr(section, 'title') else str(section)
                href = section.href if hasattr(section, 'href') else None

                # Try to extract section number from title
                section_num = self._extract_section_number(title, level, parent_section, section_counters)

                toc_entry = {
                    'title': title,
                    'level': level,
                    'href': href,
                }
                if section_num:
                    toc_entry['section'] = section_num

                toc.append(toc_entry)

                # Parse children
                if children:
                    for child in children:
                        parse_toc_item(child, level + 1, section_num or parent_section)
            elif isinstance(item, list):
                for sub_item in item:
                    parse_toc_item(sub_item, level, parent_section)

        try:
            toc_items = book.toc
            print(f"  DEBUG: book.toc type: {type(toc_items)}")
            print(f"  DEBUG: book.toc length: {len(toc_items) if toc_items else 0}")
            if toc_items:
                print(f"  DEBUG: First item type: {type(toc_items[0]) if len(toc_items) > 0 else 'N/A'}")
                if len(toc_items) > 0 and hasattr(toc_items[0], '__dict__'):
                    print(f"  DEBUG: First item attributes: {toc_items[0].__dict__}")
                parse_toc_item(toc_items)
        except Exception as e:
            print(f"  DEBUG: TOC extraction failed with error: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()

        return toc

    def _extract_section_number(self, title: str, level: int, parent_section: str, counters: List[int]) -> Optional[str]:
        """
        Extract section number from TOC title or generate based on hierarchy.

        Handles formats like:
        - "19.20 Land Warfare" -> "19.20"
        - "Chapter 3" -> "3"
        - "3.4.2 Tactics" -> "3.4.2"
        """
        import re

        # Pattern 1: Number(s) at start: "19.20 Title" or "3 Title"
        match = re.match(r'^(\d+(?:\.\d+)*)\s+', title)
        if match:
            return match.group(1)

        # Pattern 2: "Chapter X" or "Section X.Y"
        match = re.search(r'(?:Chapter|Section)\s+(\d+(?:\.\d+)*)', title, re.IGNORECASE)
        if match:
            return match.group(1)

        # If no explicit number found, return None (we won't auto-generate)
        # Better to have no section number than an incorrect one
        return None

    def _detect_section_type(self, title: str) -> str:
        """
        Detect if section is front matter, main content, or back matter.

        Returns:
            'front_matter', 'main_content', or 'back_matter'
        """
        title_lower = title.lower()

        # Front matter patterns
        front_patterns = [
            'preface', 'foreword', 'introduction', 'acknowledgments', 'acknowledgements',
            'dedication', 'table of contents', 'contents', 'toc', 'about the author',
            'about this book', 'prologue', 'copyright', 'title page',
            'half title', 'frontispiece', 'list of illustrations', 'list of maps'
        ]
        for pattern in front_patterns:
            if pattern in title_lower:
                return 'front_matter'

        # Back matter patterns
        back_patterns = [
            'index', 'bibliography', 'references', 'glossary',
            'appendix', 'notes', 'endnotes', 'epilogue',
            'afterword', 'about the publisher', 'colophon'
        ]
        for pattern in back_patterns:
            if pattern in title_lower:
                return 'back_matter'

        # Default to main content
        return 'main_content'

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
        """Clean extracted text."""
        # Remove excessive whitespace
        lines = [line.strip() for line in text.split('\n')]
        lines = [line for line in lines if line]
        text = '\n\n'.join(lines)

        # Remove multiple consecutive newlines
        while '\n\n\n' in text:
            text = text.replace('\n\n\n', '\n\n')

        return text.strip()
