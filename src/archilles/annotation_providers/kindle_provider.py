"""
Kindle Annotation Provider.

Two input modes:

1. **My Clippings.txt** — the text export written by Kindle e-ink devices
   (supports English and German UI localizations).
2. **Kindle for PC** — accepts either a single ``<ASIN>_EBOK`` directory or
   the whole ``My Kindle Content`` root. Reads the per-book ``.mbpV2``
   (modern JSON variant) for highlights / notes and parses Mobi/AZW3 EXTH
   headers from ``.azw`` for title/author. KFX-format books and DRM-only
   ``.azw`` files are detected and skipped (they expose no readable
   metadata to us). For matching against Calibre, the ASIN from the
   directory name is exposed in ``Annotation.raw_metadata['asin']``.
"""

import json
import logging
import re
import struct
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


# ── Kindle for PC: per-book directory parsing ────────────────────────────

# Subset of Mobi/AZW3 EXTH record types we care about
_EXTH_LABELS = {
    100: "author",
    101: "publisher",
    113: "asin",
    503: "title",
    504: "asin2",
    524: "language",
}

# Footer Kindle appends to copied notes, always preceded by a blank line.
# Two-stage parsing: first locate the footer block, then split into fields.
_NOTE_FOOTER_RE = re.compile(
    r"\n+[^\n]*?\(S\.\s*\d+\)[^\n]*?Kindle-Version\.?\s*$"
)
_FOOTER_FIELDS_RE = re.compile(
    r"^(?P<authors>.+?)\s*\.\s*(?P<title>.+?)"
    r"(?:\s*\([^)]*\))?"
    r"\s*\(S\.\s*\d+\)"
)


def _parse_azw_metadata(azw: Path) -> dict:
    """Parse Mobi/AZW3 EXTH headers. Returns {} on failure or KFX/DRMION."""
    try:
        with open(azw, "rb") as f:
            f.seek(78)
            rec0 = struct.unpack(">I", f.read(4))[0]
            f.seek(rec0 + 16)
            if f.read(4) != b"MOBI":
                return {}
            header_len = struct.unpack(">I", f.read(4))[0]
            f.seek(rec0 + 16 + header_len)
            if f.read(4) != b"EXTH":
                return {}
            f.read(4)  # exth_len, unused
            count = struct.unpack(">I", f.read(4))[0]
            out: dict = {}
            for _ in range(count):
                rtype = struct.unpack(">I", f.read(4))[0]
                rlen = struct.unpack(">I", f.read(4))[0]
                rdata = f.read(rlen - 8)
                if rtype in _EXTH_LABELS:
                    try:
                        s = rdata.decode("utf-8")
                    except UnicodeDecodeError:
                        s = rdata.decode("latin-1", errors="replace")
                    out[_EXTH_LABELS[rtype]] = s
            return out
    except (OSError, struct.error):
        return {}


def _parse_mbpv2(mbp: Path) -> list[dict]:
    """Parse Kindle for PC ``.mbpV2`` (modern JSON variant). Returns []."""
    try:
        text = mbp.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    if not text.strip().startswith("{"):
        # Old binary mbp format or sentinel like '<ResourceNotAvailableException/>'
        return []
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    return data.get("payload", {}).get("records", [])


def _strip_footer(text: str) -> str:
    """Remove the auto-appended Kindle source footer from a note body."""
    return _NOTE_FOOTER_RE.sub("", text).strip()


def _title_author_from_notes(notes: list[dict]) -> Optional[tuple[str, str]]:
    """Fallback: extract title/author from the Kindle note source footer."""
    for r in notes:
        text = r.get("text", "") or ""
        m = _NOTE_FOOTER_RE.search(text)
        if not m:
            continue
        footer = m.group(0).lstrip("\n").strip()
        m2 = _FOOTER_FIELDS_RE.match(footer)
        if m2:
            authors = [a.strip() for a in m2.group("authors").split(";")]
            return m2.group("title").strip(), " & ".join(authors)
    return None


def _is_ebook_dir(p: Path) -> bool:
    return p.is_dir() and p.name.endswith("_EBOK")


def _is_kindle_root(p: Path) -> bool:
    if not p.is_dir():
        return False
    try:
        return any(_is_ebook_dir(d) for d in p.iterdir())
    except OSError:
        return False


class KindleProvider(AnnotationProvider):
    """Parse Kindle annotations from My Clippings.txt or Kindle for PC.

    Accepts three path types:

    - file ending in 'clippings' → ``My Clippings.txt`` parser
    - directory ending in ``_EBOK`` → single-book .mbpV2 parser
    - directory containing one or more ``*_EBOK/`` subdirectories →
      whole-library scan (typically ``My Kindle Content``)
    """

    @property
    def name(self) -> str:
        return "kindle"

    def can_handle(self, path: str) -> bool:
        p = Path(path)
        if p.is_file():
            return p.suffix.lower() == ".txt" and "clipping" in p.stem.lower()
        if _is_ebook_dir(p) or _is_kindle_root(p):
            return True
        return False

    def extract(self, path: str, **kwargs) -> list[Annotation]:
        p = Path(path)
        if not p.exists():
            logger.error(f"Kindle source not found: {path}")
            return []

        if _is_ebook_dir(p):
            return self._extract_from_ebook_dir(p)
        if _is_kindle_root(p):
            results: list[Annotation] = []
            for d in sorted(p.iterdir()):
                if _is_ebook_dir(d):
                    results.extend(self._extract_from_ebook_dir(d))
            return results

        # File path → My Clippings.txt
        try:
            content = p.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            content = p.read_text(encoding="latin-1")
        return self._parse_clippings(content)

    def _extract_from_ebook_dir(self, ebook_dir: Path) -> list[Annotation]:
        """Read .mbpV2 + .azw of one ``<ASIN>_EBOK/`` directory."""
        asin = ebook_dir.name.removesuffix("_EBOK")
        azw = next(ebook_dir.glob("*_EBOK.azw"), None)
        mbp = next(ebook_dir.glob("*_EBOK.mbpV2"), None)
        if mbp is None:
            return []

        records = _parse_mbpv2(mbp)
        if not records:
            return []

        meta = _parse_azw_metadata(azw) if azw else {}
        title = meta.get("title") or ""
        author = meta.get("author") or ""
        if not title:
            fallback = _title_author_from_notes(
                [r for r in records if r.get("type") == "kindle.note"]
            )
            if fallback:
                title, author = fallback

        out: list[Annotation] = []
        for r in records:
            rtype = r.get("type", "")
            if rtype == "kindle.note":
                text = _strip_footer(r.get("text", "") or "")
                if not text:
                    continue
                annot_type = "note"
            elif rtype == "kindle.highlight":
                # Highlights store only byte positions in the DRM'd .azw,
                # not the underlying text. Surface them as annotations
                # without text so callers can decide whether to keep them.
                text = ""
                annot_type = "highlight"
            else:
                # Skip kindle.most_recent_read and unknown types
                continue

            out.append(
                Annotation(
                    source="kindle",
                    type=annot_type,
                    text=text,
                    location=f"pos:{r.get('startPosition')}-{r.get('endPosition')}",
                    book_title=title or None,
                    book_author=author or None,
                    raw_metadata={
                        "asin": asin,
                        "kfx_or_drm_only": not bool(meta),
                        "color": r.get("metadata", {}).get("mchl_color"),
                        "start_position": r.get("startPosition"),
                        "end_position": r.get("endPosition"),
                    },
                )
            )
        return out

    def _parse_clippings(self, content: str) -> list[Annotation]:
        """Parse the full My Clippings.txt content."""
        entries = content.split(_SEPARATOR)
        annotations = []

        for entry in entries:
            lines = [line for line in entry.strip().splitlines() if line.strip()]
            if len(lines) < 2:
                continue

            title_match = _TITLE_RE.match(lines[0].strip())
            if not title_match:
                book_title = lines[0].strip()
                book_author = None
            else:
                book_title = title_match.group(1).strip()
                book_author = title_match.group(2).strip()

            meta = _parse_meta_line(lines[1])
            if meta is None:
                logger.debug(f"Skipping unparseable clipping metadata: {lines[1]}")
                continue

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
