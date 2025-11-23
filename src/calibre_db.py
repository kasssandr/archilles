"""
Calibre database integration for Achilles RAG.

Read-only access to Calibre's metadata.db for enriched metadata.
"""

import sqlite3
from pathlib import Path
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


class CalibreDB:
    """Read-only interface to Calibre's metadata database."""

    def __init__(self, library_path: Path):
        """
        Initialize connection to Calibre library.

        Args:
            library_path: Path to Calibre library root (contains metadata.db)
        """
        self.library_path = Path(library_path)
        self.db_path = self.library_path / "metadata.db"

        if not self.db_path.exists():
            raise FileNotFoundError(f"Calibre database not found: {self.db_path}")

        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    @staticmethod
    def find_library_path(file_path: Path) -> Optional[Path]:
        """
        Find Calibre library path from a book file path.

        Calibre structure:
          Library/
            metadata.db
            Author Name/
              Book Title (ID)/
                book.epub

        Args:
            file_path: Path to book file

        Returns:
            Path to library root, or None if not in Calibre library
        """
        current = file_path.parent

        # Go up max 5 levels looking for metadata.db
        for _ in range(5):
            if (current / "metadata.db").exists():
                return current
            if current.parent == current:  # Reached root
                break
            current = current.parent

        return None

    def get_book_by_path(self, file_path: Path) -> Optional[Dict[str, Any]]:
        """
        Find book in Calibre DB by file path.

        Args:
            file_path: Absolute path to book file

        Returns:
            Dictionary with book metadata, or None if not found
        """
        # Make path relative to library
        try:
            rel_path = file_path.relative_to(self.library_path)
        except ValueError:
            logger.warning(f"File not in library: {file_path}")
            return None

        # Extract book folder path (e.g., "Author/Book Title (123)")
        # File structure: Author/Book (ID)/file.epub
        if len(rel_path.parts) < 2:
            return None

        book_folder = str(Path(rel_path.parts[0]) / rel_path.parts[1])
        filename_stem = file_path.stem

        # Query database
        query = """
        SELECT
            books.id,
            books.title,
            books.path,
            books.isbn as legacy_isbn,
            authors.name as author,
            publishers.name as publisher,
            languages.lang_code as language
        FROM books
        LEFT JOIN books_authors_link ON books.id = books_authors_link.book
        LEFT JOIN authors ON books_authors_link.author = authors.id
        LEFT JOIN books_publishers_link ON books.id = books_publishers_link.book
        LEFT JOIN publishers ON books_publishers_link.publisher = publishers.id
        LEFT JOIN books_languages_link ON books.id = books_languages_link.book
        LEFT JOIN languages ON books_languages_link.lang_code = languages.id
        WHERE books.path = ?
        """

        cursor = self.conn.execute(query, (book_folder,))
        row = cursor.fetchone()

        if not row:
            return None

        book_id = row['id']

        # Get ISBN from identifiers table
        isbn_query = """
        SELECT val FROM identifiers
        WHERE book = ? AND type = 'isbn'
        LIMIT 1
        """
        cursor = self.conn.execute(isbn_query, (book_id,))
        isbn_row = cursor.fetchone()
        isbn = isbn_row['val'] if isbn_row else row['legacy_isbn']

        return {
            'calibre_id': book_id,
            'title': row['title'],
            'author': row['author'],
            'publisher': row['publisher'],
            'language': row['language'],
            'isbn': isbn,
            'path': row['path'],
        }
