"""
ARCHILLES EPUB Parser

EPUB parser implementation using ebooklib.

Features:
- EPUB 2 and EPUB 3 support
- Chapter-by-chapter text extraction
- Table of contents extraction
- Metadata extraction (title, author, language)
- Fallback to manual ZIP extraction if ebooklib unavailable
"""

import time
import zipfile
from pathlib import Path
from typing import Any, Optional, List, Dict
import logging
import re

try:
    import ebooklib
    from ebooklib import epub
    EBOOKLIB_AVAILABLE = True
    try:
        EBOOKLIB_VERSION = ebooklib.__version__
    except AttributeError:
        EBOOKLIB_VERSION = "unknown"
except ImportError:
    EBOOKLIB_AVAILABLE = False
    EBOOKLIB_VERSION = "0.0.0"

try:
    from bs4 import BeautifulSoup
    BS4_AVAILABLE = True
except ImportError:
    BS4_AVAILABLE = False

from .base import (
    DocumentParser,
    DocumentType,
    ParserCapabilities,
    ParsedDocument,
    ParsedChunk,
)

logger = logging.getLogger(__name__)


class EPUBParser(DocumentParser):
    """
    EPUB parser using ebooklib and BeautifulSoup.

    Extracts text chapter-by-chapter from EPUB files with metadata
    and table of contents support. Falls back to manual ZIP extraction
    if ebooklib is not available.

    Args:
        chunk_by_chapter: If True, create one chunk per chapter (default: True)
        extract_toc: If True, extract table of contents (default: True)
        remove_formatting: If True, strip HTML formatting (default: True)
    """

    def __init__(
        self,
        chunk_by_chapter: bool = True,
        extract_toc: bool = True,
        remove_formatting: bool = True
    ):
        self._chunk_by_chapter = chunk_by_chapter
        self._should_extract_toc = extract_toc
        self._remove_formatting = remove_formatting

    @property
    def name(self) -> str:
        return "epub"

    @property
    def version(self) -> str:
        return f"1.0.0+ebooklib{EBOOKLIB_VERSION}"

    @property
    def capabilities(self) -> ParserCapabilities:
        return ParserCapabilities(
            supported_extensions={'.epub', '.EPUB'},
            supported_types={DocumentType.EPUB},
            extracts_images=False,
            extracts_tables=False,
            extracts_metadata=True,
            preserves_formatting=not self._remove_formatting,
            supports_ocr=False,
            memory_efficient=True,
            parallel_safe=True,
            quality_tier=2  # Good quality
        )

    def parse(self, file_path: Path) -> ParsedDocument:
        """
        Parse an EPUB file.

        Args:
            file_path: Path to EPUB file

        Returns:
            ParsedDocument with extracted text and metadata
        """
        file_path = Path(file_path)
        start_time = time.time()

        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        if not self.can_parse(file_path):
            raise ValueError(f"Unsupported file type: {file_path.suffix}")

        warnings = []

        # Try ebooklib first, fall back to manual extraction
        if EBOOKLIB_AVAILABLE and BS4_AVAILABLE:
            try:
                result = self._parse_with_ebooklib(file_path, warnings)
            except Exception as e:
                logger.warning(f"ebooklib extraction failed: {e}, falling back to manual")
                warnings.append(f"ebooklib failed: {e}, using fallback")
                result = self._parse_manual(file_path, warnings)
        else:
            if not EBOOKLIB_AVAILABLE:
                warnings.append("ebooklib not available, using manual extraction")
            if not BS4_AVAILABLE:
                warnings.append("BeautifulSoup not available, using basic extraction")
            result = self._parse_manual(file_path, warnings)

        # Add timing information
        duration = time.time() - start_time
        result.parse_duration_seconds = duration
        result.warnings.extend(warnings)

        return result

    def _parse_with_ebooklib(self, file_path: Path, warnings: List[str]) -> ParsedDocument:
        """Parse EPUB using ebooklib library."""
        book = epub.read_epub(str(file_path))

        # Extract metadata
        title = self._get_metadata(book, 'DC', 'title')
        authors = self._get_metadata_list(book, 'DC', 'creator')
        language = self._get_metadata(book, 'DC', 'language')

        # Extract chapters
        chapters = []
        full_text_parts = []

        for item in book.get_items():
            if item.get_type() == ebooklib.ITEM_DOCUMENT:
                try:
                    content = item.get_content()
                    soup = BeautifulSoup(content, 'html.parser')

                    # Remove scripts and styles
                    for element in soup(['script', 'style']):
                        element.decompose()

                    # Extract text
                    text = soup.get_text(separator='\n\n')
                    text = self._clean_text(text)

                    if text.strip():
                        # Try to find chapter title
                        chapter_title = None
                        h1 = soup.find('h1')
                        if h1:
                            chapter_title = h1.get_text(strip=True)

                        chapters.append({
                            'text': text,
                            'title': chapter_title or item.get_name(),
                            'file': item.get_name(),
                        })
                        full_text_parts.append(text)
                except Exception as e:
                    warnings.append(f"Failed to extract chapter {item.get_name()}: {e}")
                    continue

        if not chapters:
            raise RuntimeError("No readable content found in EPUB")

        full_text = '\n\n'.join(full_text_parts)

        # Create chunks (one per chapter if configured)
        chunks = []
        if self._chunk_by_chapter:
            for i, chapter in enumerate(chapters):
                chunk = ParsedChunk(
                    text=chapter['text'],
                    source_file=str(file_path),
                    page_number=None,  # EPUBs don't have page numbers
                    chunk_index=i,
                    chapter=chapter['title'],
                    metadata={
                        'chapter_title': chapter['title'],
                        'chapter_file': chapter['file'],
                    }
                )
                chunks.append(chunk)

        # Extract TOC if requested
        toc_data = []
        if self._should_extract_toc:
            try:
                toc_data = self._extract_toc(book)
            except Exception as e:
                warnings.append(f"Failed to extract TOC: {e}")

        # Create ParsedDocument
        doc = ParsedDocument(
            file_path=str(file_path),
            file_name=file_path.name,
            file_size_bytes=file_path.stat().st_size,
            full_text=full_text,
            chunks=chunks,
            title=title,
            authors=authors,
            language=language,
            page_count=len(chapters),  # Use chapter count as proxy
            parser_name=self.name,
            parser_version=self.version,
            metadata={
                'chapter_count': len(chapters),
                'toc': toc_data or None,
            }
        )

        return doc

    def _parse_manual(self, file_path: Path, warnings: List[str]) -> ParsedDocument:
        """
        Fallback: Manual extraction by unzipping EPUB.

        EPUB is a ZIP file containing HTML/XHTML files.
        """
        chapters_text = []
        chapters_metadata = []

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

                    if BS4_AVAILABLE:
                        soup = BeautifulSoup(content, 'html.parser')
                        for element in soup(['script', 'style']):
                            element.decompose()
                        text = soup.get_text(separator='\n\n')
                    else:
                        # Very basic HTML stripping
                        text = content.decode('utf-8', errors='ignore')
                        text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL)
                        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
                        text = re.sub(r'<[^>]+>', '', text)

                    text = self._clean_text(text)

                    if text.strip():
                        chapters_text.append(text)
                        chapters_metadata.append({
                            'file': html_file,
                            'title': Path(html_file).stem
                        })
                except Exception as e:
                    warnings.append(f"Failed to extract {html_file}: {e}")
                    continue

        if not chapters_text:
            raise RuntimeError("No readable content found in EPUB")

        full_text = '\n\n'.join(chapters_text)

        # Create chunks
        chunks = []
        if self._chunk_by_chapter:
            for i, (text, meta) in enumerate(zip(chapters_text, chapters_metadata)):
                chunk = ParsedChunk(
                    text=text,
                    source_file=str(file_path),
                    page_number=None,
                    chunk_index=i,
                    chapter=meta['title'],
                    metadata={
                        'chapter_file': meta['file'],
                    }
                )
                chunks.append(chunk)

        # Create ParsedDocument
        doc = ParsedDocument(
            file_path=str(file_path),
            file_name=file_path.name,
            file_size_bytes=file_path.stat().st_size,
            full_text=full_text,
            chunks=chunks,
            title=None,  # No metadata extraction in manual mode
            authors=[],
            language=None,
            page_count=len(chapters_text),
            parser_name=self.name,
            parser_version=self.version,
            metadata={
                'chapter_count': len(chapters_text),
                'extraction_method': 'manual_zip',
            }
        )

        return doc

    def _get_metadata(self, book, namespace: str, name: str) -> Optional[str]:
        """Extract single metadata value from EPUB."""
        try:
            values = book.get_metadata(namespace, name)
            if values:
                return values[0][0]
        except Exception:
            pass
        return None

    def _get_metadata_list(self, book, namespace: str, name: str) -> List[str]:
        """Extract list of metadata values from EPUB."""
        try:
            values = book.get_metadata(namespace, name)
            if values:
                return [v[0] for v in values if v]
        except Exception:
            pass
        return []

    def _extract_toc(self, book) -> List[Dict[str, Any]]:
        """Extract table of contents from EPUB."""
        toc = []

        def parse_toc_item(item, level=1):
            if isinstance(item, tuple):
                section = item[0]
                children = item[1] if len(item) > 1 else []

                toc.append({
                    'title': section.title if hasattr(section, 'title') else str(section),
                    'level': level,
                })

                if children:
                    for child in children:
                        parse_toc_item(child, level + 1)
            elif isinstance(item, list):
                for sub_item in item:
                    parse_toc_item(sub_item, level)
            elif hasattr(item, 'title'):
                toc.append({
                    'title': item.title,
                    'level': level,
                })

        try:
            toc_items = book.toc
            if toc_items:
                parse_toc_item(toc_items)
        except Exception:
            pass

        return toc

    def _clean_text(self, text: str) -> str:
        """Clean extracted text while preserving paragraph breaks."""
        # Collapse runs of horizontal whitespace (spaces, tabs) on each line
        text = re.sub(r'[^\S\n]+', ' ', text)
        # Collapse three or more newlines into a double newline
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()


# Test if run directly
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python epub_parser.py <path_to_epub>")
        sys.exit(1)

    parser = EPUBParser()
    test_file = Path(sys.argv[1])

    print(f"Testing EPUB Parser on: {test_file}")
    print(f"Parser: {parser}")
    print(f"Capabilities: {parser.capabilities}")
    print()

    try:
        result = parser.parse(test_file)
        print(f"Success! {result}")
        print(f"Title: {result.title}")
        print(f"Authors: {result.authors}")
        print(f"Language: {result.language}")
        print(f"Chapters: {result.page_count}")
        print(f"Total chars: {result.char_count:,}")
        print(f"Chunks: {result.chunk_count}")
        print(f"Parse time: {result.parse_duration_seconds:.2f}s")

        if result.warnings:
            print("\nWarnings:")
            for w in result.warnings:
                print(f"  - {w}")

        if result.chunks:
            print(f"\nFirst chunk preview:")
            print(f"  {result.chunks[0]}")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
