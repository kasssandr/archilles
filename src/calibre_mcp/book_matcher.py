"""
Book Matcher — maps external annotations to Calibre library entries.

Three-stage matching, in priority order:
1. ASIN: deterministic match against Calibre 'mobi-asin'/'amazon*'/'asin'
   identifiers (when the source provides one).
2. Exact: normalized title (+ optional author check).
3. Fuzzy: token_sort_ratio with configurable threshold.
Unmatched items can be written to a review-queue JSON for manual resolution.
"""

import json
import logging
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from rapidfuzz import fuzz

from src.archilles.sqlite_ro import connect_readonly

logger = logging.getLogger(__name__)

# Calibre identifier types that hold an Amazon ASIN. Order in iteration is
# unimportant; preference for 'mobi-asin' is handled below.
ASIN_IDENTIFIER_TYPES = (
    "mobi-asin", "amazon", "amazon_de", "amazon_uk", "asin",
)


def load_asin_index(library_path: Path) -> dict[str, int]:
    """Build {ASIN_uppercase: calibre_id} from a Calibre library's identifiers.

    When the same ASIN points to multiple books, prefers the row whose
    identifier type is 'mobi-asin' (Calibre sets this on Mobi imports).
    """
    db_path = Path(library_path) / "metadata.db"
    placeholders = ",".join("?" * len(ASIN_IDENTIFIER_TYPES))
    query = f"""
        SELECT i.val, i.type, i.book
          FROM identifiers i
         WHERE LOWER(i.type) IN ({placeholders})
    """
    index: dict[str, tuple[int, str]] = {}
    with connect_readonly(db_path) as con:
        for val, itype, cid in con.execute(query, ASIN_IDENTIFIER_TYPES):
            asin = (val or "").strip().upper()
            if not asin:
                continue
            existing = index.get(asin)
            if existing and existing[1] == "mobi-asin" and itype != "mobi-asin":
                continue
            index[asin] = (cid, itype)
    return {asin: cid for asin, (cid, _t) in index.items()}

_RE_PUNCT = re.compile(r"[^\w\s]")
_RE_WS = re.compile(r"\s+")
_RE_EDITION_SUFFIX = re.compile(r"\s*\([\w\s]+Edition\)\s*$", re.IGNORECASE)


@dataclass
class MatchResult:
    """Result of a book match attempt."""

    calibre_id: int
    calibre_title: str
    calibre_author: str
    score: float
    match_type: str  # "exact", "fuzzy"


def normalize(text: str) -> str:
    """Normalize text for comparison: lowercase, strip accents, collapse whitespace."""
    text = text.lower().strip()
    # Decompose unicode, strip combining marks (accents)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    # Replace punctuation with spaces, collapse whitespace
    text = _RE_PUNCT.sub(" ", text)
    text = _RE_WS.sub(" ", text).strip()
    return text


def _strip_edition_suffix(title: str) -> str:
    """Remove common suffixes like '(German Edition)', '(Kindle Edition)'."""
    return _RE_EDITION_SUFFIX.sub("", title)


class BookMatcher:
    """Match external book titles/authors to Calibre library entries."""

    def __init__(
        self,
        books: list[dict],
        fuzzy_threshold: float = 80.0,
        asin_index: Optional[dict[str, int]] = None,
    ):
        """
        Args:
            books: List of dicts with 'calibre_id', 'title', 'author'
                   (from CalibreDB.get_all_books_brief)
            fuzzy_threshold: Minimum score (0-100) for fuzzy matches
            asin_index: Optional {ASIN_uppercase: calibre_id} for the ASIN
                        match stage. Build with ``load_asin_index(library)``.
        """
        self._books = books
        self._threshold = fuzzy_threshold
        self._asin_index = asin_index or {}
        # Pre-compute normalized titles for fast lookup
        self._normalized = [
            {
                "calibre_id": b["calibre_id"],
                "title": b["title"],
                "author": b["author"],
                "norm_title": normalize(b["title"]),
                "norm_author": normalize(b["author"]),
            }
            for b in books
        ]
        # calibre_id → book row for ASIN lookups
        self._by_id = {b["calibre_id"]: b for b in books}

    def match(
        self,
        title: str,
        author: Optional[str] = None,
        asin: Optional[str] = None,
    ) -> Optional[MatchResult]:
        """
        Find the best matching Calibre book.

        Args:
            title: Book title from external source
            author: Author from external source (optional but improves accuracy)
            asin: Amazon ASIN from external source (optional). When given and
                  found in the matcher's ASIN index, returns immediately
                  with match_type='asin'.

        Returns:
            MatchResult if match found above threshold, None otherwise
        """
        # Stage 0: deterministic ASIN match
        if asin:
            cid = self._asin_index.get(asin.upper())
            if cid is not None:
                row = self._by_id.get(cid)
                if row:
                    return MatchResult(
                        calibre_id=cid,
                        calibre_title=row["title"],
                        calibre_author=row["author"],
                        score=100.0,
                        match_type="asin",
                    )

        title_clean = _strip_edition_suffix(title or "")
        norm_title = normalize(title_clean)
        norm_author = normalize(author) if author else ""

        if not norm_title:
            return None

        # Stage 1: Exact title match
        for b in self._normalized:
            if b["norm_title"] == norm_title:
                # If author provided, verify it's compatible
                if not norm_author or self._author_compatible(
                    norm_author, b["norm_author"]
                ):
                    return MatchResult(
                        calibre_id=b["calibre_id"],
                        calibre_title=b["title"],
                        calibre_author=b["author"],
                        score=100.0,
                        match_type="exact",
                    )

        # Stage 2: Fuzzy title match
        best_score = 0.0
        best_match = None
        for b in self._normalized:
            title_score = fuzz.token_sort_ratio(norm_title, b["norm_title"])

            # Boost score if author also matches
            if norm_author and b["norm_author"]:
                author_score = fuzz.token_sort_ratio(norm_author, b["norm_author"])
                combined = title_score * 0.7 + author_score * 0.3
            else:
                combined = title_score

            if combined > best_score:
                best_score = combined
                best_match = b

        if best_match and best_score >= self._threshold:
            return MatchResult(
                calibre_id=best_match["calibre_id"],
                calibre_title=best_match["title"],
                calibre_author=best_match["author"],
                score=best_score,
                match_type="fuzzy",
            )

        return None

    @staticmethod
    def _author_compatible(query_author: str, calibre_author: str) -> bool:
        """Check if author names are compatible (one contains the other)."""
        return query_author in calibre_author or calibre_author in query_author

    def match_batch(
        self, items: list[dict], unmatched_path: Optional[Path] = None
    ) -> tuple[list[dict], list[dict]]:
        """
        Match a batch of items (annotations grouped by book).

        Args:
            items: List of dicts with 'title' and optionally 'author'
            unmatched_path: If given, write unmatched items to this JSON file

        Returns:
            (matched, unmatched) — matched items get calibre_id/match_score/match_type added
        """
        matched = []
        unmatched = []

        for item in items:
            result = self.match(
                item.get("title", ""),
                item.get("author"),
                asin=item.get("asin"),
            )
            if result:
                item["calibre_id"] = result.calibre_id
                item["match_score"] = result.score
                item["match_type"] = result.match_type
                item["calibre_title"] = result.calibre_title
                item["calibre_author"] = result.calibre_author
                matched.append(item)
            else:
                unmatched.append(item)

        if unmatched_path and unmatched:
            unmatched_path.parent.mkdir(parents=True, exist_ok=True)
            with open(unmatched_path, "w", encoding="utf-8") as f:
                json.dump(unmatched, f, indent=2, ensure_ascii=False, default=str)
            logger.info(
                f"Wrote {len(unmatched)} unmatched annotations to {unmatched_path}"
            )

        return matched, unmatched
