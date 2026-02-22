"""
Calibre database integration for ARCHILLES RAG.

Read-only access to Calibre's metadata.db for enriched metadata.
"""

import logging
import re
import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional

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

    # ── Static helpers ─────────────────────────────────────────

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

        text = re.sub(r'<[^>]+>', '', html_text)

        # Decode common HTML entities
        text = text.replace('&nbsp;', ' ')
        text = text.replace('&amp;', '&')
        text = text.replace('&lt;', '<')
        text = text.replace('&gt;', '>')
        text = text.replace('&quot;', '"')
        text = text.replace('&#39;', "'")

        text = re.sub(r'\s+', ' ', text).strip()
        return text

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

        for _ in range(5):
            if (current / "metadata.db").exists():
                return current
            if current.parent == current:
                break
            current = current.parent

        return None

    # ── Custom columns ─────────────────────────────────────────

    def get_custom_columns(self) -> Dict[int, Dict[str, Any]]:
        """
        Get all custom column definitions from Calibre database.

        Returns:
            Dictionary mapping column_id to column metadata
            {1: {'label': 'mytags', 'name': 'My Tags', 'datatype': 'text'}, ...}
        """
        cursor = self.conn.execute(
            "SELECT id, label, name, datatype, display FROM custom_columns"
        )
        return {
            row['id']: {
                'label': row['label'],
                'name': row['name'],
                'datatype': row['datatype'],
                'display': row['display'],
            }
            for row in cursor.fetchall()
        }

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
            cursor = self.conn.execute(
                f"SELECT value FROM {table_name} WHERE book = ?", (book_id,)
            )
            row = cursor.fetchone()

            if not row or row['value'] is None:
                return None

            if datatype == 'comments':
                return self.clean_html(row['value'])

            return row['value']

        except Exception as e:
            logger.debug(f"Could not read custom column {column_id}: {e}")
            return None

    # ── Book lookup ────────────────────────────────────────────

    def get_book_by_path(self, file_path: Path) -> Optional[Dict[str, Any]]:
        """
        Find book in Calibre DB by file path.

        Args:
            file_path: Absolute path to book file

        Returns:
            Dictionary with book metadata, or None if not found
        """
        try:
            rel_path = file_path.relative_to(self.library_path)
        except ValueError:
            logger.warning(f"File not in library: {file_path}")
            return None

        if len(rel_path.parts) < 2:
            return None

        # Calibre always uses forward slashes in DB, even on Windows
        book_folder = f"{rel_path.parts[0]}/{rel_path.parts[1]}"

        query = """
        SELECT
            books.id,
            books.title,
            books.path,
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

        # Get ISBN
        cursor = self.conn.execute(
            "SELECT val FROM identifiers WHERE book = ? AND type = 'isbn' LIMIT 1",
            (book_id,),
        )
        isbn_row = cursor.fetchone()

        # Get all authors (books can have multiple)
        cursor = self.conn.execute(
            """
            SELECT authors.name
            FROM authors
            INNER JOIN books_authors_link ON authors.id = books_authors_link.author
            WHERE books_authors_link.book = ?
            ORDER BY books_authors_link.id
            """,
            (book_id,),
        )
        author_rows = cursor.fetchall()
        authors = ' & '.join(r['name'] for r in author_rows) if author_rows else row['author']

        # Get tags
        cursor = self.conn.execute(
            """
            SELECT tags.name
            FROM tags
            INNER JOIN books_tags_link ON tags.id = books_tags_link.tag
            WHERE books_tags_link.book = ?
            ORDER BY tags.name
            """,
            (book_id,),
        )
        tags = [r['name'] for r in cursor.fetchall()]

        # Clean comments (stored as HTML in Calibre)
        comments_text = self.clean_html(row['comments']) if row['comments'] else None

        # Get custom fields
        custom_fields = {}
        try:
            for col_id, col_info in self.get_custom_columns().items():
                value = self.get_custom_field_value(book_id, col_id, col_info['datatype'])
                if value is not None:
                    custom_fields[col_info['label']] = {
                        'value': value,
                        'name': col_info['name'],
                        'datatype': col_info['datatype'],
                    }
        except Exception as e:
            logger.debug(f"Could not read custom fields: {e}")

        result = {
            'calibre_id': book_id,
            'title': row['title'],
            'author': authors,
            'publisher': row['publisher'],
            'language': row['language'],
            'isbn': isbn_row['val'] if isbn_row else None,
            'path': row['path'],
            'tags': tags,
            'comments': comments_text,
        }

        if custom_fields:
            result['custom_fields'] = custom_fields

        return result
