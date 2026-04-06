"""
Kindle Annotation Provider.

Parses Amazon Kindle 'My Clippings.txt' files (supports English and German localization).
"""

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from .base import Annotation, AnnotationProvider

logger = logging.getLogger(__name__)

_SEPARATOR = "=========="

# Title line: "Book Title (Author Name)"
_TITLE_RE = re.compile(r"^(.+?)\s*\(([^)]+)\)\s*$")

# Metadata line patterns (English + German)
_META_PATTERNS = [
    # English
    re.compile(
        r"- Your (?P<type>Highlight|Note|Bookmark) on "
        r"(?:page (?P<page>\d+) \| )?Location (?P<loc>[\d-]+)"
        r" \| Added on .+?,\s*(?P<date>.+)$",
        re.IGNORECASE,
    ),
    # German
    re.compile(
        r"- Ihre (?P<type>Markierung|Notiz|Lesezeichen) "
        r"(?:auf Seite (?P<page>\d+) \| )?bei Position (?P<loc>[\d-]+)"
        r" \| Hinzugefügt am .+?,\s*(?P<date>.+)$",
        re.IGNORECASE,
    ),
]

_TYPE_MAP = {
    "highlight": "highlight",
    "markierung": "highlight",
    "note": "note",
    "notiz": "note",
    "bookmark": "bookmark",
    "lesezeichen": "bookmark",
}

# Date formats to try
_DATE_FORMATS = [
    "%B %d, %Y %I:%M:%S %p",  # English: March 15, 2026 10:23:45 AM
    "%d. %B %Y %H:%M:%S",  # German: 15. März 2026 10:23:45
]

# German month names for parsing
_GERMAN_MONTHS = {
    "Januar": "January",
    "Februar": "February",
    "März": "March",
    "April": "April",
    "Mai": "May",
    "Juni": "June",
    "Juli": "July",
    "August": "August",
    "September": "September",
    "Oktober": "October",
    "November": "November",
    "Dezember": "December",
}


def _parse_clipping_date(date_str: str) -> Optional[datetime]:
    """Parse date string from Kindle clipping (English or German)."""
    date_str = date_str.strip()
    # Replace German month names with English for uniform parsing
    for de, en in _GERMAN_MONTHS.items():
        date_str = date_str.replace(de, en)
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue
    logger.debug(f"Could not parse Kindle date: {date_str}")
    return None


def _parse_meta_line(line: str) -> Optional[dict]:
    """Parse the metadata line (type, location, date)."""
    for pattern in _META_PATTERNS:
        m = pattern.match(line.strip())
        if m:
            raw_type = m.group("type").lower()
            return {
                "type": _TYPE_MAP.get(raw_type, "highlight"),
                "location": m.group("loc"),
                "page": int(m.group("page")) if m.group("page") else None,
                "date": _parse_clipping_date(m.group("date")),
            }
    return None


class KindleProvider(AnnotationProvider):
    """Parse Kindle 'My Clippings.txt' files."""

    @property
    def name(self) -> str:
        return "kindle"

    def can_handle(self, path: str) -> bool:
        p = Path(path)
        return p.suffix.lower() == ".txt" and "clipping" in p.stem.lower()

    def extract(self, path: str, **kwargs) -> list[Annotation]:
        filepath = Path(path)
        if not filepath.exists():
            logger.error(f"Kindle clippings file not found: {path}")
            return []

        try:
            content = filepath.read_text(encoding="utf-8-sig")  # Handle BOM
        except UnicodeDecodeError:
            content = filepath.read_text(encoding="latin-1")

        return self._parse_clippings(content)

    def _parse_clippings(self, content: str) -> list[Annotation]:
        """Parse the full My Clippings.txt content."""
        entries = content.split(_SEPARATOR)
        annotations = []

        for entry in entries:
            lines = [line for line in entry.strip().splitlines() if line.strip()]
            if len(lines) < 2:
                continue

            # Line 1: Title (Author)
            title_match = _TITLE_RE.match(lines[0].strip())
            if not title_match:
                book_title = lines[0].strip()
                book_author = None
            else:
                book_title = title_match.group(1).strip()
                book_author = title_match.group(2).strip()

            # Line 2: Metadata (type, location, date)
            meta = _parse_meta_line(lines[1])
            if meta is None:
                logger.debug(f"Skipping unparseable clipping metadata: {lines[1]}")
                continue

            # Lines 3+: Content (may be empty for bookmarks)
            text = "\n".join(lines[2:]).strip() if len(lines) > 2 else ""

            annotations.append(
                Annotation(
                    source="kindle",
                    type=meta["type"],
                    text=text,
                    location=f"loc:{meta['location']}",
                    page_number=meta.get("page"),
                    created_at=meta["date"],
                    book_title=book_title,
                    book_author=book_author,
                    raw_metadata={"original_entry": entry.strip()},
                )
            )

        return annotations
