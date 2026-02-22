"""
ARCHILLES PyMuPDF Parser

PDF parser implementation using PyMuPDF (fitz).

Features:
- Fast, memory-efficient PDF parsing
- Page-by-page text extraction
- Metadata extraction (title, author, etc.)
- Optional page-level chunking
"""

import time
from pathlib import Path
from typing import Optional
import logging

try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
    PYMUPDF_VERSION = fitz.version[0]
except ImportError:
    PYMUPDF_AVAILABLE = False
    PYMUPDF_VERSION = "0.0.0"

from .base import (
    DocumentParser,
    DocumentType,
    ParserCapabilities,
    ParsedDocument,
    ParsedChunk,
)

logger = logging.getLogger(__name__)


class PyMuPDFParser(DocumentParser):
    """
    PDF parser using PyMuPDF (fitz).

    PyMuPDF is a fast, lightweight PDF library that provides
    excellent text extraction with minimal dependencies.

    Args:
        chunk_by_page: If True, create one chunk per page (default: True)
        extract_images: If True, note image locations (default: False)
        preserve_whitespace: If True, keep original spacing (default: False)
    """

    def __init__(
        self,
        chunk_by_page: bool = True,
        extract_images: bool = False,
        preserve_whitespace: bool = False
    ):
        if not PYMUPDF_AVAILABLE:
            raise ImportError(
                "PyMuPDF is not installed. Install with: pip install pymupdf"
            )

        self._chunk_by_page = chunk_by_page
        self._extract_images = extract_images
        self._preserve_whitespace = preserve_whitespace

    @property
    def name(self) -> str:
        return "pymupdf"

    @property
    def version(self) -> str:
        return f"1.0.0+pymupdf{PYMUPDF_VERSION}"

    @property
    def capabilities(self) -> ParserCapabilities:
        return ParserCapabilities(
            supported_extensions={'.pdf', '.PDF'},
            supported_types={DocumentType.PDF},
            extracts_images=self._extract_images,
            extracts_tables=False,
            extracts_metadata=True,
            preserves_formatting=False,
            supports_ocr=False,
            memory_efficient=True,
            parallel_safe=True,
            quality_tier=2  # Good quality, fast
        )

    def parse(self, file_path: Path) -> ParsedDocument:
        """
        Parse a PDF file.

        Args:
            file_path: Path to PDF file

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
        chunks = []
        full_text_parts = []

        try:
            doc = fitz.open(str(file_path))
        except Exception as e:
            raise RuntimeError(f"Failed to open PDF: {e}")

        try:
            # Extract metadata
            metadata = doc.metadata or {}
            title = metadata.get('title') or None
            author = metadata.get('author') or None
            authors = [a.strip() for a in author.split(',')] if author else []

            # Get page count
            page_count = len(doc)

            # Extract text page by page
            for page_num in range(page_count):
                try:
                    page = doc[page_num]

                    text = page.get_text("text")

                    if not self._preserve_whitespace:
                        lines = text.split('\n')
                        lines = [' '.join(line.split()) for line in lines]
                        text = '\n'.join(line for line in lines if line)

                    full_text_parts.append(text)

                    # Create chunk for this page if requested
                    if self._chunk_by_page and text.strip():
                        chunk_metadata = {
                            'width': page.rect.width,
                            'height': page.rect.height,
                        }

                        # Note image locations if requested
                        if self._extract_images:
                            images = page.get_images()
                            if images:
                                chunk_metadata['image_count'] = len(images)

                        chunk = ParsedChunk(
                            text=text.strip(),
                            source_file=str(file_path),
                            page_number=page_num + 1,  # 1-indexed
                            chunk_index=len(chunks),
                            metadata=chunk_metadata,
                        )
                        chunks.append(chunk)

                except Exception as e:
                    warnings.append(f"Error on page {page_num + 1}: {str(e)[:100]}")
                    logger.warning(f"Error extracting page {page_num + 1} from {file_path}: {e}")

            full_text = '\n\n'.join(full_text_parts)

        finally:
            doc.close()

        duration = time.time() - start_time

        return ParsedDocument(
            file_path=str(file_path),
            file_name=file_path.name,
            file_size_bytes=file_path.stat().st_size,
            full_text=full_text,
            chunks=chunks,
            title=title,
            authors=authors,
            language=metadata.get('language'),
            page_count=page_count,
            parser_name=self.name,
            parser_version=self.version,
            parse_duration_seconds=duration,
            metadata={
                'producer': metadata.get('producer'),
                'creator': metadata.get('creator'),
                'creation_date': metadata.get('creationDate'),
                'modification_date': metadata.get('modDate'),
                'pdf_format': metadata.get('format'),
            },
            warnings=warnings
        )


def create_pymupdf_parser(**kwargs) -> Optional[PyMuPDFParser]:
    """
    Factory function to create PyMuPDF parser if available.

    Returns:
        PyMuPDFParser instance or None if PyMuPDF not installed
    """
    if not PYMUPDF_AVAILABLE:
        logger.warning("PyMuPDF not available, parser not created")
        return None
    return PyMuPDFParser(**kwargs)


# Auto-register if PyMuPDF is available
def _auto_register():
    """Auto-register parser with global registry."""
    if PYMUPDF_AVAILABLE:
        from .registry import register_parser
        try:
            register_parser(PyMuPDFParser())
            logger.debug("Auto-registered PyMuPDF parser")
        except ValueError:
            pass  # Already registered


# Quick test
if __name__ == "__main__":
    import sys

    if not PYMUPDF_AVAILABLE:
        print("PyMuPDF not installed!")
        sys.exit(1)

    parser = PyMuPDFParser()
    print(f"Parser: {parser}")
    print(f"Capabilities: {parser.capabilities}")

    # Test with a file if provided
    if len(sys.argv) > 1:
        pdf_path = Path(sys.argv[1])
        if pdf_path.exists():
            print(f"\nParsing: {pdf_path}")
            result = parser.parse(pdf_path)
            print(f"Result: {result}")
            print(f"Title: {result.title}")
            print(f"Authors: {result.authors}")
            print(f"Pages: {result.page_count}")
            print(f"Chunks: {result.chunk_count}")
            print(f"Duration: {result.parse_duration_seconds:.2f}s")
            if result.warnings:
                print(f"Warnings: {result.warnings}")
