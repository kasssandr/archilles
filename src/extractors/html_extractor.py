"""HTML text extractor."""

from pathlib import Path
from bs4 import BeautifulSoup
import chardet

from .base import BaseExtractor
from .models import ExtractedText, ChunkMetadata
from .exceptions import ExtractionError


class HTMLExtractor(BaseExtractor):
    """Extract text from HTML files, preserving structure."""

    SUPPORTED_EXTENSIONS = {'.html', '.htm', '.xhtml', '.xml'}

    def supports(self, file_path: Path) -> bool:
        """Check if file is HTML."""
        return file_path.suffix.lower() in self.SUPPORTED_EXTENSIONS

    def extract(self, file_path: Path) -> ExtractedText:
        """
        Extract text from HTML file.

        Features:
        - Removes scripts, styles, and other non-content elements
        - Preserves paragraph structure
        - Extracts headings for TOC
        - Handles encoding detection

        Args:
            file_path: Path to HTML file

        Returns:
            ExtractedText object
        """
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        try:
            # Read and detect encoding
            with open(file_path, 'rb') as f:
                raw_data = f.read()

            detected = chardet.detect(raw_data)
            encoding = detected.get('encoding', 'utf-8')

            try:
                html_content = raw_data.decode(encoding)
            except UnicodeDecodeError:
                # Fallback to utf-8
                html_content = raw_data.decode('utf-8', errors='ignore')

            # Parse HTML
            soup = BeautifulSoup(html_content, 'html.parser')

            # Remove non-content elements
            for element in soup(['script', 'style', 'nav', 'footer', 'header']):
                element.decompose()

            # Extract table of contents from headings
            toc = self._extract_toc(soup)

            # Extract text, preserving paragraph structure
            text_parts = []

            for element in soup.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'li']):
                text = element.get_text(strip=True)
                if text:
                    text_parts.append(text)

            # If no paragraphs found, get all text
            if not text_parts:
                text_parts = [soup.get_text(separator='\n\n')]

            full_text = '\n\n'.join(text_parts)

            # Create base metadata
            base_metadata = ChunkMetadata(
                source_file=str(file_path),
                format='html',
            )

            # Try to extract title
            title_tag = soup.find('title')
            if title_tag:
                base_metadata.title = title_tag.get_text(strip=True)

            # Create chunks
            chunks = self._create_chunks(full_text, base_metadata)

            # Create extraction metadata
            extraction_metadata = self._create_extraction_metadata(
                file_path=file_path,
                format_name='html',
                extraction_time=0,
                total_chars=len(full_text),
                total_words=len(full_text.split()),
                total_chunks=len(chunks),
            )

            return ExtractedText(
                full_text=full_text,
                chunks=chunks,
                metadata=extraction_metadata,
                toc=toc,
            )

        except Exception as e:
            raise ExtractionError(f"Failed to extract HTML: {e}") from e

    def _extract_toc(self, soup: BeautifulSoup) -> list:
        """Extract table of contents from headings."""
        toc = []
        for heading in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
            level = int(heading.name[1])  # h1 -> 1, h2 -> 2, etc.
            title = heading.get_text(strip=True)
            if title:
                toc.append({
                    'title': title,
                    'level': level,
                })
        return toc
