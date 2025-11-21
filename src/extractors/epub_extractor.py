"""EPUB text extractor."""

from pathlib import Path
from typing import List, Dict, Any
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

                    chapters_metadata.append({
                        'chapter': chapter_title or item.get_name(),
                        'file': item.get_name(),
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
        """Extract table of contents from EPUB."""
        toc = []

        def parse_toc_item(item, level=1):
            if isinstance(item, tuple):
                # Simple TOC entry
                section, children = item[0], item[1] if len(item) > 1 else []
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

        try:
            toc_items = book.toc
            if toc_items:
                parse_toc_item(toc_items)
        except Exception:
            pass

        return toc

    def _create_chunks_with_chapters(
        self,
        chapters_text: List[str],
        chapters_metadata: List[Dict],
        file_path: Path,
        title: str,
        author: str
    ) -> List[Dict[str, Any]]:
        """Create chunks with chapter information."""
        chunks = []

        for chapter_text, chapter_meta in zip(chapters_text, chapters_metadata):
            base_metadata = ChunkMetadata(
                source_file=str(file_path),
                format='epub',
                title=title,
                author=author,
                chapter=chapter_meta.get('chapter'),
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
