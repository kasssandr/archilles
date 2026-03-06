"""
Calibre adapter — wraps the existing ``calibre_db.CalibreDB`` behind SourceAdapter.

This is a **wrapper**, not a replacement.  ``calibre_db.py`` stays untouched
and continues to do the actual SQLite work.
"""

import logging
import os
from pathlib import Path
from typing import Optional

from src.adapters.base import (
    DocumentAnnotation,
    DocumentMetadata,
    DocumentTimestamps,
    SourceAdapter,
)
from src.calibre_db import CalibreDB

logger = logging.getLogger(__name__)

# Format priority when a book has multiple files in Calibre
_FORMAT_PRIORITY = ("pdf", "epub", "mobi", "azw3", "djvu", "txt", "md", "html")


class CalibreAdapter(SourceAdapter):
    """Adapter for Calibre libraries (``metadata.db``)."""

    def __init__(self, library_path: Path):
        self._library_path = Path(library_path)
        if not (self._library_path / "metadata.db").exists():
            raise FileNotFoundError(
                f"No metadata.db in {self._library_path} — not a Calibre library"
            )

    # ── Properties ──────────────────────────────────────────────

    @property
    def adapter_type(self) -> str:
        return "calibre"

    @property
    def library_path(self) -> Path:
        return self._library_path

    # ── Core interface ──────────────────────────────────────────

    def list_documents(
        self,
        tag_filter: Optional[str] = None,
        exclude_tag: Optional[str] = None,
    ) -> list[DocumentMetadata]:
        import sqlite3

        db_path = self._library_path / "metadata.db"
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row

        query = "SELECT id, title, path FROM books ORDER BY id"
        rows = conn.execute(query).fetchall()

        results: list[DocumentMetadata] = []
        for row in rows:
            book_id = row["id"]
            book_path = row["path"]

            # Resolve tags for filtering
            tag_rows = conn.execute(
                """
                SELECT tags.name FROM tags
                INNER JOIN books_tags_link ON tags.id = books_tags_link.tag
                WHERE books_tags_link.book = ?
                """,
                (book_id,),
            ).fetchall()
            tags = [t["name"] for t in tag_rows]

            if tag_filter and tag_filter not in tags:
                continue
            if exclude_tag and exclude_tag in tags:
                continue

            # Find the primary file
            file_path = self._find_primary_file(book_path)
            if file_path is None:
                continue

            meta = self._row_to_metadata(conn, book_id, row["title"], book_path, tags, file_path)
            results.append(meta)

        conn.close()
        return results

    def get_metadata(self, doc_id: str) -> Optional[DocumentMetadata]:
        with CalibreDB(self._library_path) as db:
            # Look up by Calibre book id
            import sqlite3

            conn = sqlite3.connect(self._library_path / "metadata.db")
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT id, title, path FROM books WHERE id = ?",
                (int(doc_id),),
            ).fetchone()
            if not row:
                conn.close()
                return None

            tag_rows = conn.execute(
                """
                SELECT tags.name FROM tags
                INNER JOIN books_tags_link ON tags.id = books_tags_link.tag
                WHERE books_tags_link.book = ?
                """,
                (int(doc_id),),
            ).fetchall()
            tags = [t["name"] for t in tag_rows]

            file_path = self._find_primary_file(row["path"])
            if file_path is None:
                conn.close()
                return None

            meta = self._row_to_metadata(conn, int(doc_id), row["title"], row["path"], tags, file_path)
            conn.close()
            return meta

    def get_file_path(self, doc_id: str) -> Optional[Path]:
        import sqlite3

        conn = sqlite3.connect(self._library_path / "metadata.db")
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT path FROM books WHERE id = ?", (int(doc_id),)
        ).fetchone()
        conn.close()
        if not row:
            return None
        return self._find_primary_file(row["path"])

    def get_annotations(self, doc_id: str) -> list[DocumentAnnotation]:
        file_path = self.get_file_path(doc_id)
        if not file_path:
            return []

        try:
            from src.calibre_mcp.annotations import get_combined_annotations

            result = get_combined_annotations(str(file_path))
            annotations = result.get("annotations", [])
            return [
                DocumentAnnotation(
                    text=a.get("highlighted_text", ""),
                    note=a.get("notes", ""),
                    annotation_type=a.get("type", "highlight"),
                    page=a.get("page"),
                    created=a.get("timestamp", ""),
                )
                for a in annotations
            ]
        except Exception as e:
            logger.debug(f"Could not read annotations for {doc_id}: {e}")
            return []

    def get_comments(self, doc_id: str) -> str:
        with CalibreDB(self._library_path) as db:
            import sqlite3

            conn = sqlite3.connect(self._library_path / "metadata.db")
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT text FROM comments WHERE book = ?", (int(doc_id),)
            ).fetchone()
            conn.close()
            if row and row["text"]:
                return CalibreDB.clean_html(row["text"])
            return ""

    def get_metadata_by_path(self, file_path: Path) -> Optional[DocumentMetadata]:
        """Efficient path-based lookup via CalibreDB."""
        file_path = Path(file_path).resolve()
        library_path = CalibreDB.find_library_path(file_path)
        if not library_path or library_path.resolve() != self._library_path.resolve():
            return None

        with CalibreDB(self._library_path) as db:
            book_data = db.get_book_by_path(file_path)
            if not book_data:
                return None
            return self._book_data_to_metadata(book_data, file_path)

    # ── Internal helpers ────────────────────────────────────────

    def _find_primary_file(self, calibre_book_path: str) -> Optional[Path]:
        """Find the best available file for a Calibre book folder."""
        book_dir = self._library_path / calibre_book_path
        if not book_dir.is_dir():
            return None

        files_by_ext: dict[str, Path] = {}
        for f in book_dir.iterdir():
            if f.is_file() and f.suffix:
                files_by_ext[f.suffix.lower().lstrip(".")] = f

        for fmt in _FORMAT_PRIORITY:
            if fmt in files_by_ext:
                return files_by_ext[fmt]

        # Fallback: any file
        for f in files_by_ext.values():
            return f
        return None

    def _row_to_metadata(
        self,
        conn,
        book_id: int,
        title: str,
        book_path: str,
        tags: list[str],
        file_path: Path,
    ) -> DocumentMetadata:
        """Build DocumentMetadata from a SQLite row + resolved file."""
        # Authors
        author_rows = conn.execute(
            """
            SELECT authors.name FROM authors
            INNER JOIN books_authors_link ON authors.id = books_authors_link.author
            WHERE books_authors_link.book = ?
            ORDER BY books_authors_link.id
            """,
            (book_id,),
        ).fetchall()
        authors = [r["name"] for r in author_rows] if author_rows else []

        # Publisher
        pub_row = conn.execute(
            """
            SELECT publishers.name FROM publishers
            INNER JOIN books_publishers_link ON publishers.id = books_publishers_link.publisher
            WHERE books_publishers_link.book = ?
            """,
            (book_id,),
        ).fetchone()
        publisher = pub_row["name"] if pub_row else ""

        # Language
        lang_row = conn.execute(
            """
            SELECT languages.lang_code FROM languages
            INNER JOIN books_languages_link ON languages.id = books_languages_link.lang_code
            WHERE books_languages_link.book = ?
            """,
            (book_id,),
        ).fetchone()
        language = lang_row["lang_code"] if lang_row else ""

        # ISBN
        isbn_row = conn.execute(
            "SELECT val FROM identifiers WHERE book = ? AND type = 'isbn' LIMIT 1",
            (book_id,),
        ).fetchone()
        identifiers = {}
        if isbn_row:
            identifiers["isbn"] = isbn_row["val"]

        # Comments
        comment_row = conn.execute(
            "SELECT text FROM comments WHERE book = ?", (book_id,)
        ).fetchone()
        comments = ""
        if comment_row and comment_row["text"]:
            comments = CalibreDB.clean_html(comment_row["text"])

        # Timestamps from Calibre
        ts_row = conn.execute(
            "SELECT timestamp, pubdate, last_modified FROM books WHERE id = ?",
            (book_id,),
        ).fetchone()
        timestamps = DocumentTimestamps()
        if ts_row:
            if ts_row["pubdate"]:
                timestamps.created_at = str(ts_row["pubdate"])
            if ts_row["last_modified"]:
                timestamps.modified_at = str(ts_row["last_modified"])

        return DocumentMetadata(
            doc_id=str(book_id),
            title=title,
            authors=authors,
            file_path=file_path,
            file_format=file_path.suffix.lower().lstrip("."),
            tags=tags,
            comments=comments,
            language=language,
            publisher=publisher,
            identifiers=identifiers,
            timestamps=timestamps,
        )

    def _book_data_to_metadata(
        self, book_data: dict, file_path: Path
    ) -> DocumentMetadata:
        """Convert a ``CalibreDB.get_book_by_path()`` dict to DocumentMetadata."""
        # Split author string back to list
        author_str = book_data.get("author", "")
        authors = [a.strip() for a in author_str.split("&")] if author_str else []

        identifiers = {}
        if book_data.get("isbn"):
            identifiers["isbn"] = book_data["isbn"]

        return DocumentMetadata(
            doc_id=str(book_data["calibre_id"]),
            title=book_data.get("title", ""),
            authors=authors,
            file_path=file_path,
            file_format=file_path.suffix.lower().lstrip("."),
            tags=book_data.get("tags", []),
            comments=book_data.get("comments", "") or "",
            language=book_data.get("language", "") or "",
            publisher=book_data.get("publisher", "") or "",
            identifiers=identifiers,
            custom_fields=book_data.get("custom_fields", {}),
        )
