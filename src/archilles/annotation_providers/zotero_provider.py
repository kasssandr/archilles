"""
Zotero Annotation Provider.

Reads annotations and notes stored in Zotero's SQLite database.

Two annotation types are extracted:
  itemAnnotations  — PDF highlights/underlines/notes made in the Zotero PDF viewer
  itemNotes        — standalone notes attached to a Zotero item

CRITICAL: The database is opened in read-only mode.
"""

import logging
import re
import sqlite3
from datetime import datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Optional

from src.archilles.sqlite_ro import connect_readonly
from .base import Annotation, AnnotationProvider

logger = logging.getLogger(__name__)

# Zotero annotation type → unified type
_ANNOT_TYPE_MAP = {
    "highlight": "highlight",
    "underline": "highlight",
    "note": "note",
    "image": "bookmark",
    "ink": "bookmark",
}

# sortIndex format: "PPPPP|CCCCC|LLLLL"
_SORT_INDEX_RE = re.compile(r"^(\d+)\|")


class _HTMLStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self._parts.append(data)

    def get_text(self) -> str:
        return " ".join(self._parts).strip()


def _strip_html(html: str) -> str:
    if not html:
        return ""
    s = _HTMLStripper()
    s.feed(html)
    return re.sub(r"\s+", " ", s.get_text()).strip()


def _parse_sort_index_page(sort_index: str) -> Optional[int]:
    """Extract the 0-based page number from Zotero's sortIndex."""
    m = _SORT_INDEX_RE.match(sort_index or "")
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            pass
    return None


def _parse_zotero_date(date_str: str) -> Optional[datetime]:
    """Parse Zotero's ISO-ish timestamp (e.g. '2024-03-15 14:22:33')."""
    if not date_str:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(date_str[:19], fmt)
        except ValueError:
            continue
    return None


class ZoteroAnnotationProvider(AnnotationProvider):
    """Extract annotations and notes from a Zotero SQLite database.

    Parameters
    ----------
    path:
        Path to ``zotero.sqlite``. Passed either via constructor or as the
        ``path`` argument to :meth:`extract`.
    """

    def __init__(self, path: Optional[str] = None):
        self._default_path = path

    @property
    def name(self) -> str:
        return "zotero"

    def can_handle(self, path: str) -> bool:
        return Path(path).name == "zotero.sqlite" and Path(path).is_file()

    def extract(self, path: str, **kwargs) -> list[Annotation]:
        db_path = Path(path or self._default_path or "")
        if not db_path.is_file():
            logger.error("zotero.sqlite not found: %s", db_path)
            return []

        # Live DB: no immutable (Zotero may be writing) — mode=ro reads a
        # consistent WAL snapshot, busy_timeout absorbs a brief lock (4.4).
        conn = connect_readonly(db_path, row_factory=sqlite3.Row)
        try:
            return self._extract_all(conn)
        finally:
            conn.close()

    # ── Internal ────────────────────────────────────────────────────

    def _item_title_author(
        self, conn: sqlite3.Connection, item_id: int
    ) -> tuple[str, str]:
        """Return (title, first_author) for an item."""
        title_row = conn.execute(
            """
            SELECT idv.value FROM itemData id
            JOIN itemDataValues idv ON id.valueID = idv.valueID
            JOIN fields f ON id.fieldID = f.fieldID
            WHERE id.itemID = ? AND f.fieldName = 'title'
            """,
            (item_id,),
        ).fetchone()
        title = title_row[0] if title_row else ""

        author_row = conn.execute(
            """
            SELECT c.firstName, c.lastName FROM itemCreators ic
            JOIN creators c ON ic.creatorID = c.creatorID
            JOIN creatorTypes ct ON ic.creatorTypeID = ct.creatorTypeID
            WHERE ic.itemID = ? AND ct.creatorType = 'author'
            ORDER BY ic.orderIndex LIMIT 1
            """,
            (item_id,),
        ).fetchone()
        if author_row:
            first, last = author_row[0] or "", author_row[1] or ""
            author = f"{first} {last}".strip() if first else last
        else:
            author = ""

        return title, author

    def _item_key(self, conn: sqlite3.Connection, item_id: int) -> str:
        row = conn.execute("SELECT key FROM items WHERE itemID = ?", (item_id,)).fetchone()
        return row[0] if row else ""

    def _extract_all(self, conn: sqlite3.Connection) -> list[Annotation]:
        annotations: list[Annotation] = []
        annotations.extend(self._extract_pdf_annotations(conn))
        annotations.extend(self._extract_notes(conn))
        return annotations

    def _extract_pdf_annotations(self, conn: sqlite3.Connection) -> list[Annotation]:
        """Read itemAnnotations (highlights/notes in Zotero PDF viewer)."""
        rows = conn.execute(
            """
            SELECT
                ia.itemID,
                ia.parentItemID    AS attachment_id,
                ia.type,
                ia.text,
                ia.comment,
                ia.sortIndex,
                ia.pageLabel,
                ia.dateModified,
                att.parentItemID   AS parent_item_id
            FROM itemAnnotations ia
            JOIN itemAttachments att ON ia.parentItemID = att.itemID
            WHERE ia.itemID     NOT IN (SELECT itemID FROM deletedItems)
            AND   att.itemID    NOT IN (SELECT itemID FROM deletedItems)
            AND   att.parentItemID NOT IN (SELECT itemID FROM deletedItems)
            """
        ).fetchall()

        annotations = []
        for row in rows:
            unified_type = _ANNOT_TYPE_MAP.get(row["type"] or "", "highlight")
            text = row["text"] or ""
            comment = row["comment"] or ""
            if not text and not comment:
                continue

            page_from_index = _parse_sort_index_page(row["sortIndex"] or "")
            page_label = row["pageLabel"] or ""
            page_number = page_from_index + 1 if page_from_index is not None else None

            parent_item_id = row["parent_item_id"]
            if parent_item_id:
                title, author = self._item_title_author(conn, parent_item_id)
                doc_id = self._item_key(conn, parent_item_id)
            else:
                title, author, doc_id = "", "", ""

            annotations.append(
                Annotation(
                    source="zotero",
                    type=unified_type,
                    text=text,
                    note=comment or None,
                    location=f"page:{page_label or page_number or ''}",
                    page_number=page_number,
                    created_at=_parse_zotero_date(row["dateModified"]),
                    book_title=title or None,
                    book_author=author or None,
                    source_doc_id=doc_id or None,
                )
            )
        return annotations

    def _extract_notes(self, conn: sqlite3.Connection) -> list[Annotation]:
        """Read itemNotes (standalone HTML notes attached to Zotero items)."""
        rows = conn.execute(
            """
            SELECT n.itemID, n.parentItemID, n.note, i.dateModified
            FROM itemNotes n
            JOIN items i ON n.itemID = i.itemID
            WHERE n.parentItemID IS NOT NULL
            AND n.itemID NOT IN (SELECT itemID FROM deletedItems)
            """
        ).fetchall()

        annotations = []
        for row in rows:
            text = _strip_html(row["note"] or "")
            if not text:
                continue

            parent_item_id = row["parentItemID"]
            title, author = self._item_title_author(conn, parent_item_id)
            doc_id = self._item_key(conn, parent_item_id)

            annotations.append(
                Annotation(
                    source="zotero",
                    type="note",
                    text=text,
                    created_at=_parse_zotero_date(row["dateModified"]),
                    book_title=title or None,
                    book_author=author or None,
                    source_doc_id=doc_id or None,
                )
            )
        return annotations
