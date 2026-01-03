"""
Calibre database integration for ARCHILLES RAG.

Read-only access to Calibre's metadata.db for enriched metadata.
"""

import sqlite3
from pathlib import Path
from typing import Optional, Dict, Any
import logging
import re

logger = logging.getLogger(__name__)


class CalibreDB:
    """Read-only interface to Calibre's metadata database."""

    @staticmethod
    def clean_html(html_text: str) -> str:
        """
        Remove HTML tags from Calibre comments field.

        Calibre stores comments as HTML, we need clean text for indexing.

        Args:
            html_text: HTML string from Calibre comments

        Returns:
            Clean text without HTML tags
        """
        if not html_text:
            return ""

        # Remove HTML tags
        text = re.sub(r'<[^>]+>', '', html_text)

        # Decode common HTML entities
        text = text.replace('&nbsp;', ' ')
        text = text.replace('&amp;', '&')
        text = text.replace('&lt;', '<')
        text = text.replace('&gt;', '>')
        text = text.replace('&quot;', '"')
        text = text.replace('&#39;', "'")

        # Clean up whitespace
        text = re.sub(r'\s+', ' ', text)
        text = text.strip()

        return text

    def get_custom_columns(self) -> Dict[int, Dict[str, Any]]:
        """
        Get all custom column definitions from Calibre database.

        Returns:
            Dictionary mapping column_id to column metadata
            {1: {'label': 'mytags', 'name': 'My Tags', 'datatype': 'text'}, ...}
        """
        query = """
        SELECT id, label, name, datatype, display
        FROM custom_columns
        """
        cursor = self.conn.execute(query)
        rows = cursor.fetchall()

        columns = {}
        for row in rows:
            columns[row['id']] = {
                'label': row['label'],  # e.g., 'mytags' (used in column name: custom_column_1)
                'name': row['name'],    # e.g., 'My Tags' (display name)
                'datatype': row['datatype'],  # text, comments, datetime, float, int, bool, rating, series, enumeration
                'display': row['display']
            }
        return columns

    def get_custom_field_value(self, book_id: int, column_id: int, datatype: str) -> Any:
        """
        Get value of a custom field for a specific book.

        Args:
            book_id: Calibre book ID
            column_id: Custom column ID
            datatype: Data type of the field (text, datetime, float, etc.)

        Returns:
            Field value (type depends on datatype)
        """
        table_name = f"custom_column_{column_id}"

        try:
            # Different query depending on datatype
            if datatype in ['text', 'comments', 'series', 'enumeration']:
                # Text-based fields: value column
                query = f"SELECT value FROM {table_name} WHERE book = ?"
            elif datatype in ['datetime', 'float', 'int', 'rating', 'bool']:
                # Numeric/date fields: value column
                query = f"SELECT value FROM {table_name} WHERE book = ?"
            else:
                # Fallback
                query = f"SELECT value FROM {table_name} WHERE book = ?"

            cursor = self.conn.execute(query, (book_id,))
            row = cursor.fetchone()

            if not row or row['value'] is None:
                return None

            # Clean HTML from 'comments' type fields
            if datatype == 'comments' and row['value']:
                return self.clean_html(row['value'])

            return row['value']

        except Exception as e:
            # Table might not exist or other error
            logger.debug(f"Could not read custom column {column_id}: {e}")
            return None

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

        # Calibre always uses forward slashes in DB, even on Windows
        book_folder = str(Path(rel_path.parts[0]) / rel_path.parts[1]).replace('\\', '/')
        filename_stem = file_path.stem

        # Query database
        query = """
        SELECT
            books.id,
            books.title,
            books.path,
            books.isbn as legacy_isbn,
            books.has_cover,
            comments.text as comments,
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
        LEFT JOIN comments ON books.id = comments.book
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

        # Get all authors (books can have multiple authors)
        authors_query = """
        SELECT authors.name
        FROM authors
        INNER JOIN books_authors_link ON authors.id = books_authors_link.author
        WHERE books_authors_link.book = ?
        ORDER BY books_authors_link.id
        """
        cursor = self.conn.execute(authors_query, (book_id,))
        author_rows = cursor.fetchall()
        # Join multiple authors with " & "
        authors = ' & '.join([author_row['name'] for author_row in author_rows]) if author_rows else row['author']

        # Get tags
        tags_query = """
        SELECT tags.name
        FROM tags
        INNER JOIN books_tags_link ON tags.id = books_tags_link.tag
        WHERE books_tags_link.book = ?
        ORDER BY tags.name
        """
        cursor = self.conn.execute(tags_query, (book_id,))
        tag_rows = cursor.fetchall()
        tags = [tag_row['name'] for tag_row in tag_rows] if tag_rows else []

        # Clean comments (remove HTML)
        comments_text = row['comments'] if row['comments'] else None
        if comments_text:
            comments_text = self.clean_html(comments_text)

        # Get custom fields (if any)
        custom_fields = {}
        try:
            custom_columns = self.get_custom_columns()
            for col_id, col_info in custom_columns.items():
                value = self.get_custom_field_value(book_id, col_id, col_info['datatype'])
                if value is not None:
                    # Use label as key (e.g., 'mytags', 'reading_status')
                    custom_fields[col_info['label']] = {
                        'value': value,
                        'name': col_info['name'],  # Display name
                        'datatype': col_info['datatype']
                    }
        except Exception as e:
            logger.debug(f"Could not read custom fields: {e}")

        result = {
            'calibre_id': book_id,
            'title': row['title'],
            'author': authors,  # All authors joined with " & "
            'publisher': row['publisher'],
            'language': row['language'],
            'isbn': isbn,
            'path': row['path'],
            'tags': tags,
            'comments': comments_text,
        }

        # Add custom fields to result (if any)
        if custom_fields:
            result['custom_fields'] = custom_fields

        return result
