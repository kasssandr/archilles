#!/usr/bin/env python3
"""
Text Extractor for Calibre Quote Tracker
Extracts full text from PDF and EPUB files.
"""

import fitz  # PyMuPDF
import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TextExtractor:
    """Extracts text from various ebook formats"""

    @staticmethod
    def extract_from_pdf(file_path):
        """
        Extract text from PDF file

        Args:
            file_path: Path to PDF file

        Returns:
            str: Extracted text
        """
        try:
            doc = fitz.open(file_path)
            text_parts = []

            for page_num, page in enumerate(doc, 1):
                text = page.get_text()
                if text.strip():
                    text_parts.append(text)

            doc.close()
            return "\n".join(text_parts)

        except Exception as e:
            logger.error(f"Error extracting PDF {file_path}: {e}")
            return ""

    @staticmethod
    def extract_from_epub(file_path):
        """
        Extract text from EPUB file

        Args:
            file_path: Path to EPUB file

        Returns:
            str: Extracted text
        """
        try:
            book = epub.read_epub(file_path)
            text_parts = []

            for item in book.get_items():
                try:
                    if item.get_type() == ebooklib.ITEM_DOCUMENT:
                        # Parse HTML content
                        content = item.get_content()
                        if content:
                            soup = BeautifulSoup(content, 'html.parser')

                            # Extract text from HTML
                            text = soup.get_text(separator='\n', strip=True)
                            if text:
                                text_parts.append(text)
                except Exception as item_error:
                    # Skip corrupted items, continue with others
                    logger.warning(f"Skipping corrupted EPUB item in {file_path}: {item_error}")
                    continue

            extracted_text = "\n".join(text_parts)

            # Only return if we got substantial text
            if len(extracted_text) > 100:
                return extracted_text
            else:
                logger.warning(f"EPUB {file_path} extracted text too short, might be corrupted")
                return ""

        except Exception as e:
            logger.error(f"Error extracting EPUB {file_path}: {e}")
            return ""

    @staticmethod
    def extract_text(file_path):
        """
        Extract text from file based on extension

        Args:
            file_path: Path to file (PDF or EPUB)

        Returns:
            str: Extracted text or empty string on failure
        """
        file_path = Path(file_path)

        if not file_path.exists():
            logger.error(f"File not found: {file_path}")
            return ""

        extension = file_path.suffix.lower()

        if extension == '.pdf':
            return TextExtractor.extract_from_pdf(str(file_path))
        elif extension == '.epub':
            return TextExtractor.extract_from_epub(str(file_path))
        else:
            logger.warning(f"Unsupported format: {extension}")
            return ""


class CalibreTextExtractor:
    """
    Extracts text from Calibre library books
    Integrates with Calibre metadata database
    """

    def __init__(self, calibre_library_path):
        """
        Initialize with Calibre library path

        Args:
            calibre_library_path: Path to Calibre library directory
        """
        self.library_path = Path(calibre_library_path)
        if not self.library_path.exists():
            raise FileNotFoundError(f"Calibre library not found: {calibre_library_path}")

        # Connect to Calibre metadata database
        import sqlite3
        self.metadata_db = self.library_path / "metadata.db"
        if not self.metadata_db.exists():
            raise FileNotFoundError(f"Calibre metadata.db not found: {self.metadata_db}")

        self.conn = sqlite3.connect(str(self.metadata_db))
        self.conn.row_factory = sqlite3.Row

    def get_book_file_path(self, book_id, format='pdf'):
        """
        Get the file path for a book using Calibre's database

        Args:
            book_id: Calibre book ID
            format: File format (pdf, epub, etc.)

        Returns:
            Path: Full path to book file or None if not found
        """
        format_upper = format.upper()

        # Query Calibre database for actual path
        query = """
            SELECT books.path, data.name, data.format
            FROM books
            JOIN data ON books.id = data.book
            WHERE books.id = ? AND data.format = ?
        """

        cursor = self.conn.execute(query, (book_id, format_upper))
        row = cursor.fetchone()

        if not row:
            return None

        # Construct full path: library_path / book_path / filename.format
        book_relative_path = row['path']
        filename = row['name']
        file_format = row['format']

        full_path = self.library_path / book_relative_path / f"{filename}.{file_format.lower()}"

        if full_path.exists():
            return full_path
        else:
            logger.warning(f"File not found: {full_path}")
            return None

    def extract_book_text(self, book_id, author, title, preferred_formats=None):
        """
        Extract text from a book, trying multiple formats

        Args:
            book_id: Calibre book ID
            author: Book author (unused, kept for compatibility)
            title: Book title (unused, kept for compatibility)
            preferred_formats: List of formats to try (default: ['epub', 'pdf'])

        Returns:
            tuple: (extracted_text, format_used) or (None, None) on failure
        """
        if preferred_formats is None:
            preferred_formats = ['epub', 'pdf']

        for fmt in preferred_formats:
            file_path = self.get_book_file_path(book_id, fmt)
            if file_path:
                logger.info(f"Extracting text from {file_path}")
                text = TextExtractor.extract_text(file_path)
                if text:
                    return text, fmt.upper()

        logger.error(f"Could not extract text for book {book_id}: {title}")
        return None, None

    def close(self):
        """Close database connection"""
        if hasattr(self, 'conn'):
            self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


if __name__ == '__main__':
    # Simple test
    import sys

    if len(sys.argv) < 2:
        print("Usage: python text_extractor.py <file_path>")
        sys.exit(1)

    file_path = sys.argv[1]
    text = TextExtractor.extract_text(file_path)

    if text:
        print(f"Extracted {len(text)} characters")
        print("First 500 characters:")
        print(text[:500])
    else:
        print("Failed to extract text")
