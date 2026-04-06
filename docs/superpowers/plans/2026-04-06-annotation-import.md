# Annotation Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend ARCHILLES to import annotations (highlights, notes, bookmarks) from Kindle, Kobo, and other reading apps, matching them to Calibre books via fuzzy title/author matching.

**Architecture:** Extract existing PDF/Calibre-Viewer annotation code into a provider-based architecture (ABC + registry, matching the existing Parser/Chunker/Embedder pattern). Add a book-matching service for mapping external annotations to Calibre IDs. Implement Kindle My Clippings.txt as the first external provider.

**Tech Stack:** Python 3.11+, rapidfuzz (fuzzy matching), PyMuPDF (existing), sqlite3 (existing), dataclasses

---

## File Structure

### New files
```
src/calibre_mcp/annotation_providers/
├── __init__.py              # Package init, convenience re-exports
├── base.py                  # Annotation dataclass + AnnotationProvider ABC
├── registry.py              # AnnotationProviderRegistry
├── pdf_provider.py          # Migrated from annotations.py:get_pdf_annotations
├── calibre_provider.py      # Migrated from annotations.py:get_book_annotations
└── kindle_provider.py       # NEW: My Clippings.txt parser

src/calibre_mcp/book_matcher.py  # Fuzzy title+author matching against CalibreDB

tests/
├── conftest.py
├── test_annotation_providers.py
├── test_book_matcher.py
└── test_kindle_provider.py

tests/fixtures/
├── my_clippings_en.txt      # English Kindle clippings sample
├── my_clippings_de.txt      # German Kindle clippings sample
└── my_clippings_mixed.txt   # Mixed language + edge cases
```

### Modified files
```
src/calibre_mcp/annotations.py    # Refactored to use providers (facade)
src/calibre_mcp/server.py         # Add import_annotations MCP tool
src/calibre_db.py                 # Add get_all_books_metadata() for matcher
scripts/rag_demo.py               # Add import-annotations subcommand
requirements.txt                  # Add rapidfuzz
```

---

## Task 1: Annotation dataclass + Provider ABC

**Files:**
- Create: `src/calibre_mcp/annotation_providers/__init__.py`
- Create: `src/calibre_mcp/annotation_providers/base.py`
- Test: `tests/test_annotation_providers.py`

- [ ] **Step 1: Create the package and base module**

```python
# src/calibre_mcp/annotation_providers/__init__.py
from .base import Annotation, AnnotationProvider

__all__ = ["Annotation", "AnnotationProvider"]
```

```python
# src/calibre_mcp/annotation_providers/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Annotation:
    """Unified annotation from any reading source."""
    source: str                    # "kindle", "kobo", "apple_books", "pdf", "calibre_viewer"
    type: str                      # "highlight", "note", "bookmark"
    text: str                      # The highlighted text
    note: Optional[str] = None     # User note attached to highlight
    location: str = ""             # Source-specific: Kindle Location, EPUB CFI, PDF page
    page_number: Optional[int] = None  # Page number if available
    chapter: Optional[str] = None  # Chapter name if available
    created_at: Optional[datetime] = None
    book_title: Optional[str] = None   # Title as reported by source (for matching)
    book_author: Optional[str] = None  # Author as reported by source (for matching)
    calibre_id: Optional[int] = None   # Calibre book ID (set after matching)
    raw_metadata: dict = field(default_factory=dict)

    def to_chunk_dict(self) -> dict:
        """Convert to dict compatible with LanceDB chunk schema."""
        return {
            "text": self._build_text(),
            "chunk_type": "annotation",
            "annotation_type": self.type,
            "annotation_source": self.source,
            "page_number": self.page_number or 0,
            "chapter": self.chapter or "",
        }

    def _build_text(self) -> str:
        """Build searchable text from highlight + note."""
        parts = []
        if self.text:
            parts.append(self.text)
        if self.note:
            parts.append(f"[Note: {self.note}]")
        return "\n".join(parts)


class AnnotationProvider(ABC):
    """Base class for annotation source providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique provider name (e.g. 'kindle', 'pdf')."""
        ...

    @abstractmethod
    def extract(self, path: str, **kwargs) -> list[Annotation]:
        """
        Extract annotations from the given path.

        Args:
            path: Path to the annotation source (file, directory, or database)

        Returns:
            List of Annotation objects
        """
        ...

    def can_handle(self, path: str) -> bool:
        """Check if this provider can handle the given path. Override for auto-detection."""
        return False
```

- [ ] **Step 2: Write tests**

```python
# tests/test_annotation_providers.py
from src.calibre_mcp.annotation_providers.base import Annotation, AnnotationProvider


def test_annotation_build_text_highlight_only():
    a = Annotation(source="kindle", type="highlight", text="Important passage")
    assert a._build_text() == "Important passage"


def test_annotation_build_text_with_note():
    a = Annotation(source="kindle", type="highlight", text="Important", note="My thoughts")
    assert a._build_text() == "Important\n[Note: My thoughts]"


def test_annotation_to_chunk_dict():
    a = Annotation(source="pdf", type="highlight", text="Hello", page_number=42, chapter="Ch1")
    d = a.to_chunk_dict()
    assert d["chunk_type"] == "annotation"
    assert d["annotation_type"] == "highlight"
    assert d["annotation_source"] == "pdf"
    assert d["page_number"] == 42
    assert d["chapter"] == "Ch1"


def test_provider_is_abstract():
    """AnnotationProvider cannot be instantiated directly."""
    import pytest
    with pytest.raises(TypeError):
        AnnotationProvider()
```

- [ ] **Step 3: Run tests**

Run: `python -m pytest tests/test_annotation_providers.py -v`
Expected: All 4 tests PASS

- [ ] **Step 4: Commit**

```bash
git add src/calibre_mcp/annotation_providers/ tests/
git commit -m "feat(annotations): add Annotation dataclass and AnnotationProvider ABC"
```

---

## Task 2: Provider Registry

**Files:**
- Create: `src/calibre_mcp/annotation_providers/registry.py`
- Update: `src/calibre_mcp/annotation_providers/__init__.py`
- Test: `tests/test_annotation_providers.py`

- [ ] **Step 1: Create registry**

```python
# src/calibre_mcp/annotation_providers/registry.py
import logging
from typing import Optional
from .base import Annotation, AnnotationProvider

logger = logging.getLogger(__name__)


class AnnotationProviderRegistry:
    """Registry for annotation source providers."""

    def __init__(self):
        self._providers: dict[str, AnnotationProvider] = {}

    def register(self, provider: AnnotationProvider) -> None:
        if provider.name in self._providers:
            raise ValueError(f"Provider '{provider.name}' is already registered")
        self._providers[provider.name] = provider
        logger.debug(f"Registered annotation provider: {provider.name}")

    def get(self, name: str) -> Optional[AnnotationProvider]:
        return self._providers.get(name)

    def detect(self, path: str) -> Optional[AnnotationProvider]:
        """Auto-detect which provider can handle a path."""
        for provider in self._providers.values():
            if provider.can_handle(path):
                return provider
        return None

    def extract_all(self, path: str, source: Optional[str] = None) -> list[Annotation]:
        """Extract annotations using specified or auto-detected provider."""
        if source:
            provider = self.get(source)
            if not provider:
                raise ValueError(f"Unknown annotation provider: '{source}'. Available: {list(self._providers.keys())}")
            return provider.extract(path)

        provider = self.detect(path)
        if not provider:
            raise ValueError(f"No provider can handle: {path}")
        return provider.extract(path)

    @property
    def available(self) -> list[str]:
        return list(self._providers.keys())
```

- [ ] **Step 2: Update __init__.py**

```python
# src/calibre_mcp/annotation_providers/__init__.py
from .base import Annotation, AnnotationProvider
from .registry import AnnotationProviderRegistry

__all__ = ["Annotation", "AnnotationProvider", "AnnotationProviderRegistry"]
```

- [ ] **Step 3: Write registry tests**

Add to `tests/test_annotation_providers.py`:

```python
from src.calibre_mcp.annotation_providers.registry import AnnotationProviderRegistry


class DummyProvider(AnnotationProvider):
    @property
    def name(self) -> str:
        return "dummy"

    def extract(self, path, **kwargs):
        return [Annotation(source="dummy", type="highlight", text=f"from {path}")]

    def can_handle(self, path):
        return path.endswith(".dummy")


def test_registry_register_and_get():
    reg = AnnotationProviderRegistry()
    reg.register(DummyProvider())
    assert reg.get("dummy") is not None
    assert reg.get("nonexistent") is None


def test_registry_duplicate_raises():
    import pytest
    reg = AnnotationProviderRegistry()
    reg.register(DummyProvider())
    with pytest.raises(ValueError, match="already registered"):
        reg.register(DummyProvider())


def test_registry_detect():
    reg = AnnotationProviderRegistry()
    reg.register(DummyProvider())
    assert reg.detect("file.dummy") is not None
    assert reg.detect("file.txt") is None


def test_registry_extract_all():
    reg = AnnotationProviderRegistry()
    reg.register(DummyProvider())
    results = reg.extract_all("test.dummy")
    assert len(results) == 1
    assert results[0].text == "from test.dummy"
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_annotation_providers.py -v`
Expected: All 8 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/calibre_mcp/annotation_providers/registry.py tests/test_annotation_providers.py
git commit -m "feat(annotations): add AnnotationProviderRegistry"
```

---

## Task 3: PDF Provider (migrate from annotations.py)

**Files:**
- Create: `src/calibre_mcp/annotation_providers/pdf_provider.py`
- Test: `tests/test_annotation_providers.py`

- [ ] **Step 1: Create PDF provider**

Migrate `get_pdf_annotations()` and `_parse_pdf_date()` from `annotations.py` into a provider class:

```python
# src/calibre_mcp/annotation_providers/pdf_provider.py
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional
from .base import Annotation, AnnotationProvider

logger = logging.getLogger(__name__)


def _parse_pdf_date(mod_date: str) -> Optional[datetime]:
    """Parse a PDF date string (D:YYYYMMDDHHmmSS) into datetime."""
    if not mod_date:
        return None
    try:
        if mod_date.startswith("D:"):
            date_str = mod_date[2:16]
            return datetime.strptime(date_str, "%Y%m%d%H%M%S")
    except (ValueError, IndexError):
        pass
    return None


class PdfAnnotationProvider(AnnotationProvider):
    """Extract annotations embedded in PDF files via PyMuPDF."""

    @property
    def name(self) -> str:
        return "pdf"

    def can_handle(self, path: str) -> bool:
        return Path(path).suffix.lower() == ".pdf"

    def extract(self, path: str, **kwargs) -> list[Annotation]:
        try:
            import fitz
        except ImportError:
            logger.warning("PyMuPDF not installed, cannot extract PDF annotations")
            return []

        pdf_path = Path(path)
        if not pdf_path.exists() or pdf_path.suffix.lower() != ".pdf":
            return []

        annotations = []
        try:
            doc = fitz.open(str(pdf_path))
            total_pages = len(doc)

            for page_num in range(total_pages):
                page = doc[page_num]
                for annot in page.annots():
                    if annot is None:
                        continue

                    annot_type_raw = annot.type[1] if annot.type else "Unknown"

                    text = ""
                    if annot_type_raw in ("Highlight", "Underline", "StrikeOut", "Squiggly"):
                        text = page.get_textbox(annot.rect).strip()

                    note_content = annot.info.get("content", "").strip()
                    timestamp = _parse_pdf_date(annot.info.get("modDate", ""))

                    if annot_type_raw in ("Highlight", "Underline"):
                        anno_type = "highlight"
                    elif annot_type_raw in ("Text", "FreeText"):
                        anno_type = "note"
                    else:
                        anno_type = "bookmark"

                    annotations.append(Annotation(
                        source="pdf",
                        type=anno_type,
                        text=text,
                        note=note_content or None,
                        location=f"page:{page_num + 1}",
                        page_number=page_num + 1,
                        created_at=timestamp,
                        raw_metadata={
                            "annot_type_raw": annot_type_raw,
                            "pos_frac": (page_num + 1) / total_pages if total_pages > 0 else 0,
                            "spine_index": page_num,
                        },
                    ))

            doc.close()
        except Exception as e:
            logger.error(f"Error extracting PDF annotations from {path}: {e}")

        return annotations
```

- [ ] **Step 2: Write test**

```python
def test_pdf_provider_can_handle():
    from src.calibre_mcp.annotation_providers.pdf_provider import PdfAnnotationProvider
    p = PdfAnnotationProvider()
    assert p.name == "pdf"
    assert p.can_handle("book.pdf")
    assert p.can_handle("BOOK.PDF")
    assert not p.can_handle("book.epub")


def test_pdf_provider_nonexistent_file():
    from src.calibre_mcp.annotation_providers.pdf_provider import PdfAnnotationProvider
    p = PdfAnnotationProvider()
    assert p.extract("/nonexistent/file.pdf") == []
```

- [ ] **Step 3: Run tests, commit**

Run: `python -m pytest tests/test_annotation_providers.py -v`

```bash
git add src/calibre_mcp/annotation_providers/pdf_provider.py tests/
git commit -m "feat(annotations): add PdfAnnotationProvider"
```

---

## Task 4: Calibre Viewer Provider (migrate from annotations.py)

**Files:**
- Create: `src/calibre_mcp/annotation_providers/calibre_provider.py`
- Test: `tests/test_annotation_providers.py`

- [ ] **Step 1: Create Calibre provider**

Migrate `get_book_annotations()`, `compute_book_hash()`, `get_annotations_dir()` from `annotations.py`:

```python
# src/calibre_mcp/annotation_providers/calibre_provider.py
import hashlib
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional
from .base import Annotation, AnnotationProvider

logger = logging.getLogger(__name__)


def compute_book_hash(book_path: str) -> str:
    """Calibre hashes the FILE PATH (not content) for annotation filenames."""
    return hashlib.sha256(book_path.encode("utf-8")).hexdigest()


def get_default_annotations_dir() -> Path:
    """Get the default Calibre viewer annotations directory."""
    if os.name == "nt":
        appdata = os.environ.get("APPDATA", "")
        return Path(appdata) / "calibre" / "viewer" / "annots"
    return Path.home() / ".local" / "share" / "calibre" / "viewer" / "annots"


class CalibreViewerProvider(AnnotationProvider):
    """Read annotations from Calibre's viewer annotation store."""

    def __init__(self, annotations_dir: Optional[str] = None):
        self._annotations_dir = Path(annotations_dir) if annotations_dir else None

    @property
    def name(self) -> str:
        return "calibre_viewer"

    @property
    def annotations_dir(self) -> Path:
        return self._annotations_dir or get_default_annotations_dir()

    def can_handle(self, path: str) -> bool:
        """Can handle any book path that has a corresponding annotation file."""
        book_hash = compute_book_hash(path)
        annotation_file = self.annotations_dir / f"{book_hash}.json"
        return annotation_file.exists()

    def extract(self, path: str, **kwargs) -> list[Annotation]:
        book_hash = compute_book_hash(path)
        annotation_file = self.annotations_dir / f"{book_hash}.json"

        if not annotation_file.exists():
            return []

        try:
            with open(annotation_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Error reading Calibre annotations: {e}")
            return []

        raw_list = data if isinstance(data, list) else data.get("annotations", [])

        annotations = []
        for raw in raw_list:
            annot_type = raw.get("type", "highlight")
            text = raw.get("highlighted_text", "")
            notes = raw.get("notes", "")
            timestamp_str = raw.get("timestamp", "")

            created_at = None
            if timestamp_str:
                try:
                    created_at = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                except (ValueError, AttributeError):
                    pass

            annotations.append(Annotation(
                source="calibre_viewer",
                type=annot_type,
                text=text,
                note=notes or None,
                location=raw.get("cfi", ""),
                page_number=raw.get("spine_index"),
                created_at=created_at,
                raw_metadata=raw,
            ))

        return annotations
```

- [ ] **Step 2: Write test**

```python
def test_calibre_provider_name():
    from src.calibre_mcp.annotation_providers.calibre_provider import CalibreViewerProvider
    p = CalibreViewerProvider()
    assert p.name == "calibre_viewer"


def test_calibre_provider_nonexistent_dir():
    from src.calibre_mcp.annotation_providers.calibre_provider import CalibreViewerProvider
    p = CalibreViewerProvider(annotations_dir="/nonexistent/path")
    assert p.extract("somebook.epub") == []
```

- [ ] **Step 3: Run tests, commit**

Run: `python -m pytest tests/test_annotation_providers.py -v`

```bash
git add src/calibre_mcp/annotation_providers/calibre_provider.py tests/
git commit -m "feat(annotations): add CalibreViewerProvider"
```

---

## Task 5: Wire providers into annotations.py (facade refactor)

**Files:**
- Modify: `src/calibre_mcp/annotations.py`
- Modify: `src/calibre_mcp/annotation_providers/__init__.py`

- [ ] **Step 1: Update annotations.py to use providers internally**

Keep the existing public API (`get_combined_annotations`, `get_pdf_annotations`, etc.) but delegate to providers internally. This ensures `server.py` and any other callers continue working without changes.

Key change in `get_combined_annotations()`:
```python
# Instead of directly calling get_book_annotations() and get_pdf_annotations(),
# use the providers:
from .annotation_providers import PdfAnnotationProvider, CalibreViewerProvider

# ... inside get_combined_annotations():
calibre_provider = CalibreViewerProvider(annotations_dir)
calibre_annots = calibre_provider.extract(book_path)

if include_pdf and book_path.lower().endswith('.pdf'):
    pdf_provider = PdfAnnotationProvider()
    pdf_annots = pdf_provider.extract(book_path)
```

Convert Annotation objects back to dicts for backward compatibility with existing filter/format functions.

- [ ] **Step 2: Verify existing MCP tools still work**

Run: `python -c "from src.calibre_mcp.annotations import get_combined_annotations, get_pdf_annotations, search_annotations; print('OK')"`

- [ ] **Step 3: Commit**

```bash
git add src/calibre_mcp/annotations.py src/calibre_mcp/annotation_providers/
git commit -m "refactor(annotations): delegate to provider classes internally"
```

---

## Task 6: Book-Matcher Service

**Files:**
- Create: `src/calibre_mcp/book_matcher.py`
- Modify: `src/calibre_db.py` (add `get_all_books_brief()`)
- Modify: `requirements.txt`
- Test: `tests/test_book_matcher.py`

- [ ] **Step 1: Add rapidfuzz to requirements**

Add to `requirements.txt`:
```
rapidfuzz>=3.0.0  # Fuzzy string matching for annotation import
```

- [ ] **Step 2: Add get_all_books_brief() to CalibreDB**

```python
# Add to src/calibre_db.py class CalibreDB:
def get_all_books_brief(self) -> list[dict]:
    """Get id, title, author for all books (used by book matcher)."""
    cursor = self.conn.execute("""
        SELECT books.id, books.title,
               GROUP_CONCAT(authors.name, ' & ') as authors
        FROM books
        LEFT JOIN books_authors_link ON books.id = books_authors_link.book
        LEFT JOIN authors ON books_authors_link.author = authors.id
        GROUP BY books.id
        ORDER BY books.title
    """)
    return [{"calibre_id": row[0], "title": row[1], "author": row[2] or ""} for row in cursor.fetchall()]
```

- [ ] **Step 3: Create book_matcher.py**

```python
# src/calibre_mcp/book_matcher.py
import json
import logging
import re
import unicodedata
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

from rapidfuzz import fuzz

logger = logging.getLogger(__name__)


@dataclass
class MatchResult:
    calibre_id: int
    calibre_title: str
    calibre_author: str
    score: float
    match_type: str  # "exact", "fuzzy"


def normalize(text: str) -> str:
    """Normalize text for comparison: lowercase, strip accents, collapse whitespace."""
    text = text.lower().strip()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _strip_edition_suffix(title: str) -> str:
    """Remove common suffixes like '(German Edition)', '(Kindle Edition)'."""
    return re.sub(r"\s*\([\w\s]+Edition\)\s*$", "", title, flags=re.IGNORECASE)


class BookMatcher:
    """Match external book titles/authors to Calibre library entries."""

    def __init__(self, books: list[dict], fuzzy_threshold: float = 80.0):
        """
        Args:
            books: List of dicts with 'calibre_id', 'title', 'author' (from CalibreDB.get_all_books_brief)
            fuzzy_threshold: Minimum score (0-100) for fuzzy matches
        """
        self._books = books
        self._threshold = fuzzy_threshold
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

    def match(self, title: str, author: Optional[str] = None) -> Optional[MatchResult]:
        """
        Find the best matching Calibre book.

        Args:
            title: Book title from external source
            author: Author from external source (optional but improves accuracy)

        Returns:
            MatchResult if match found above threshold, None otherwise
        """
        title_clean = _strip_edition_suffix(title)
        norm_title = normalize(title_clean)
        norm_author = normalize(author) if author else ""

        # Stage 1: Exact title match
        for b in self._normalized:
            if b["norm_title"] == norm_title:
                if not norm_author or norm_author in b["norm_author"] or b["norm_author"] in norm_author:
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

    def match_batch(
        self, items: list[dict], unmatched_path: Optional[Path] = None
    ) -> tuple[list[dict], list[dict]]:
        """
        Match a batch of annotations.

        Args:
            items: List of dicts with 'title' and optionally 'author'
            unmatched_path: If given, write unmatched items to this JSON file

        Returns:
            (matched, unmatched) — matched items get a 'calibre_id' field added
        """
        matched = []
        unmatched = []

        for item in items:
            result = self.match(item.get("title", ""), item.get("author"))
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
            logger.info(f"Wrote {len(unmatched)} unmatched annotations to {unmatched_path}")

        return matched, unmatched
```

- [ ] **Step 4: Write tests**

```python
# tests/test_book_matcher.py
from src.calibre_mcp.book_matcher import BookMatcher, normalize, _strip_edition_suffix

SAMPLE_BOOKS = [
    {"calibre_id": 1, "title": "Die Blechtrommel", "author": "Günter Grass"},
    {"calibre_id": 2, "title": "Der Prozess", "author": "Franz Kafka"},
    {"calibre_id": 3, "title": "Faust: Der Tragödie erster Teil", "author": "Johann Wolfgang von Goethe"},
    {"calibre_id": 4, "title": "The Structure of Scientific Revolutions", "author": "Thomas S. Kuhn"},
]


def test_normalize():
    assert normalize("  Günter Grass  ") == "gunter grass"
    assert normalize("François") == "francois"


def test_strip_edition_suffix():
    assert _strip_edition_suffix("Die Blechtrommel (German Edition)") == "Die Blechtrommel"
    assert _strip_edition_suffix("The Process (Kindle Edition)") == "The Process"
    assert _strip_edition_suffix("Normal Title") == "Normal Title"


def test_exact_match():
    m = BookMatcher(SAMPLE_BOOKS)
    result = m.match("Die Blechtrommel", "Günter Grass")
    assert result is not None
    assert result.calibre_id == 1
    assert result.match_type == "exact"
    assert result.score == 100.0


def test_exact_match_case_insensitive():
    m = BookMatcher(SAMPLE_BOOKS)
    result = m.match("die blechtrommel")
    assert result is not None
    assert result.calibre_id == 1


def test_fuzzy_match_edition_suffix():
    m = BookMatcher(SAMPLE_BOOKS)
    result = m.match("Die Blechtrommel (German Edition)", "Grass, Günter")
    assert result is not None
    assert result.calibre_id == 1


def test_no_match_below_threshold():
    m = BookMatcher(SAMPLE_BOOKS, fuzzy_threshold=95.0)
    result = m.match("Completely Different Book")
    assert result is None


def test_match_batch():
    m = BookMatcher(SAMPLE_BOOKS)
    items = [
        {"title": "Die Blechtrommel", "author": "Günter Grass", "text": "highlight1"},
        {"title": "Unknown Book XYZ", "author": "Nobody", "text": "highlight2"},
    ]
    matched, unmatched = m.match_batch(items)
    assert len(matched) == 1
    assert matched[0]["calibre_id"] == 1
    assert len(unmatched) == 1
```

- [ ] **Step 5: Install rapidfuzz, run tests**

Run: `pip install rapidfuzz>=3.0.0`
Run: `python -m pytest tests/test_book_matcher.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/calibre_mcp/book_matcher.py src/calibre_db.py requirements.txt tests/test_book_matcher.py
git commit -m "feat(annotations): add BookMatcher for fuzzy title+author matching"
```

---

## Task 7: Kindle Provider (My Clippings.txt)

**Files:**
- Create: `src/calibre_mcp/annotation_providers/kindle_provider.py`
- Create: `tests/fixtures/my_clippings_en.txt`
- Create: `tests/fixtures/my_clippings_de.txt`
- Test: `tests/test_kindle_provider.py`

- [ ] **Step 1: Create test fixtures**

```
# tests/fixtures/my_clippings_en.txt
The Structure of Scientific Revolutions (Thomas S. Kuhn)
- Your Highlight on Location 234-240 | Added on Monday, March 15, 2026 10:23:45 AM

Normal science, the activity in which most scientists inevitably spend almost all their time, is predicated on the assumption that the scientific community knows what the world is like.
==========
The Structure of Scientific Revolutions (Thomas S. Kuhn)
- Your Note on Location 234 | Added on Monday, March 15, 2026 10:24:00 AM

This is the key definition of normal science
==========
The Structure of Scientific Revolutions (Thomas S. Kuhn)
- Your Bookmark on Location 500 | Added on Tuesday, March 16, 2026 02:15:00 PM

==========
```

```
# tests/fixtures/my_clippings_de.txt
Die Blechtrommel (Günter Grass)
- Ihre Markierung bei Position 1234-1256 | Hinzugefügt am Montag, 15. März 2026 10:23:45

Zugegeben: ich bin Insasse einer Heil- und Pflegeanstalt, mein Pfleger beobachtet mich, lässt mich kaum aus dem Auge.
==========
Die Blechtrommel (Günter Grass)
- Ihre Notiz bei Position 1234 | Hinzugefügt am Montag, 15. März 2026 10:24:00

Berühmter erster Satz
==========
```

- [ ] **Step 2: Create Kindle provider**

```python
# src/calibre_mcp/annotation_providers/kindle_provider.py
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Optional
from .base import Annotation, AnnotationProvider

logger = logging.getLogger(__name__)

# Patterns for the separator and metadata lines
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
    "%B %d, %Y %I:%M:%S %p",    # English: March 15, 2026 10:23:45 AM
    "%d. %B %Y %H:%M:%S",        # German: 15. März 2026 10:23:45
]

# German month names for parsing
_GERMAN_MONTHS = {
    "Januar": "January", "Februar": "February", "März": "March",
    "April": "April", "Mai": "May", "Juni": "June",
    "Juli": "July", "August": "August", "September": "September",
    "Oktober": "October", "November": "November", "Dezember": "December",
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
            lines = [l for l in entry.strip().splitlines() if l.strip()]
            if len(lines) < 2:
                continue

            # Line 1: Title (Author)
            title_match = _TITLE_RE.match(lines[0].strip())
            if not title_match:
                # Fallback: use entire first line as title
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

            annotations.append(Annotation(
                source="kindle",
                type=meta["type"],
                text=text,
                location=f"loc:{meta['location']}",
                page_number=meta.get("page"),
                created_at=meta["date"],
                book_title=book_title,
                book_author=book_author,
                raw_metadata={"original_entry": entry.strip()},
            ))

        return annotations
```

- [ ] **Step 3: Write tests**

```python
# tests/test_kindle_provider.py
import os
from pathlib import Path
from src.calibre_mcp.annotation_providers.kindle_provider import (
    KindleProvider, _parse_clipping_date, _parse_meta_line,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_english_date():
    dt = _parse_clipping_date("March 15, 2026 10:23:45 AM")
    assert dt is not None
    assert dt.year == 2026
    assert dt.month == 3
    assert dt.day == 15


def test_parse_german_date():
    dt = _parse_clipping_date("15. März 2026 10:23:45")
    assert dt is not None
    assert dt.year == 2026
    assert dt.month == 3


def test_parse_meta_line_english():
    result = _parse_meta_line("- Your Highlight on Location 234-240 | Added on Monday, March 15, 2026 10:23:45 AM")
    assert result is not None
    assert result["type"] == "highlight"
    assert result["location"] == "234-240"


def test_parse_meta_line_german():
    result = _parse_meta_line("- Ihre Markierung bei Position 1234-1256 | Hinzugefügt am Montag, 15. März 2026 10:23:45")
    assert result is not None
    assert result["type"] == "highlight"
    assert result["location"] == "1234-1256"


def test_kindle_provider_can_handle():
    p = KindleProvider()
    assert p.can_handle("My Clippings.txt")
    assert p.can_handle("my clippings.txt")
    assert p.can_handle("/mnt/kindle/My Clippings.txt")
    assert not p.can_handle("notes.txt")
    assert not p.can_handle("book.epub")


def test_kindle_provider_english_fixture():
    p = KindleProvider()
    results = p.extract(str(FIXTURES / "my_clippings_en.txt"))
    assert len(results) == 3
    # First entry: highlight
    assert results[0].type == "highlight"
    assert results[0].book_title == "The Structure of Scientific Revolutions"
    assert results[0].book_author == "Thomas S. Kuhn"
    assert "Normal science" in results[0].text
    # Second entry: note
    assert results[1].type == "note"
    assert "key definition" in results[1].text
    # Third entry: bookmark
    assert results[2].type == "bookmark"
    assert results[2].text == ""


def test_kindle_provider_german_fixture():
    p = KindleProvider()
    results = p.extract(str(FIXTURES / "my_clippings_de.txt"))
    assert len(results) == 2
    assert results[0].type == "highlight"
    assert results[0].book_title == "Die Blechtrommel"
    assert results[0].book_author == "Günter Grass"
    assert "Insasse" in results[0].text
    assert results[1].type == "note"


def test_kindle_provider_nonexistent():
    p = KindleProvider()
    assert p.extract("/nonexistent/My Clippings.txt") == []
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_kindle_provider.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/calibre_mcp/annotation_providers/kindle_provider.py tests/fixtures/ tests/test_kindle_provider.py
git commit -m "feat(annotations): add KindleProvider for My Clippings.txt"
```

---

## Task 8: CLI import-annotations subcommand

**Files:**
- Modify: `scripts/rag_demo.py`
- Update: `src/calibre_mcp/annotation_providers/__init__.py`

- [ ] **Step 1: Register all providers in __init__.py**

```python
# src/calibre_mcp/annotation_providers/__init__.py
from .base import Annotation, AnnotationProvider
from .registry import AnnotationProviderRegistry
from .pdf_provider import PdfAnnotationProvider
from .calibre_provider import CalibreViewerProvider
from .kindle_provider import KindleProvider


def create_default_registry(**kwargs) -> AnnotationProviderRegistry:
    """Create registry with all built-in providers."""
    reg = AnnotationProviderRegistry()
    reg.register(PdfAnnotationProvider())
    reg.register(CalibreViewerProvider(annotations_dir=kwargs.get("annotations_dir")))
    reg.register(KindleProvider())
    return reg


__all__ = [
    "Annotation", "AnnotationProvider", "AnnotationProviderRegistry",
    "PdfAnnotationProvider", "CalibreViewerProvider", "KindleProvider",
    "create_default_registry",
]
```

- [ ] **Step 2: Add import-annotations subcommand to rag_demo.py**

Add after the `embed_parser` definition (~line 2768):

```python
# Import-annotations command
import_parser = subparsers.add_parser('import-annotations',
    help='Import annotations from external reading apps (Kindle, Kobo, etc.)')
import_parser.add_argument('--source', required=True,
    choices=['kindle', 'kobo', 'pdf', 'calibre_viewer', 'auto'],
    help='Annotation source')
import_parser.add_argument('--path', required=True,
    help='Path to annotation file/database')
import_parser.add_argument('--dry-run', action='store_true',
    help='Show what would be imported without writing to index')
import_parser.add_argument('--fuzzy-threshold', type=float, default=80.0,
    help='Minimum fuzzy match score for book matching (default: 80)')
import_parser.add_argument('--db-path', default=None,
    help='Database path (default: CALIBRE_LIBRARY/.archilles/rag_db)')
```

Add the handler function and dispatch in `main()`.

- [ ] **Step 3: Test CLI help**

Run: `python scripts/rag_demo.py import-annotations --help`
Expected: Shows help with --source, --path, --dry-run options

- [ ] **Step 4: Commit**

```bash
git add scripts/rag_demo.py src/calibre_mcp/annotation_providers/__init__.py
git commit -m "feat(annotations): add import-annotations CLI subcommand"
```

---

## Task 9: End-to-end integration test

**Files:**
- Create: `tests/test_import_integration.py`

- [ ] **Step 1: Write integration test**

Test the full pipeline: Kindle fixture → parse → match → output

```python
# tests/test_import_integration.py
from pathlib import Path
from src.calibre_mcp.annotation_providers.kindle_provider import KindleProvider
from src.calibre_mcp.book_matcher import BookMatcher

FIXTURES = Path(__file__).parent / "fixtures"

CALIBRE_BOOKS = [
    {"calibre_id": 1, "title": "Die Blechtrommel", "author": "Günter Grass"},
    {"calibre_id": 4, "title": "The Structure of Scientific Revolutions", "author": "Thomas S. Kuhn"},
]


def test_kindle_to_matcher_pipeline():
    """Full pipeline: parse Kindle clippings → match to Calibre books."""
    provider = KindleProvider()
    annotations = provider.extract(str(FIXTURES / "my_clippings_en.txt"))
    assert len(annotations) > 0

    # Prepare items for matcher
    items = [
        {"title": a.book_title, "author": a.book_author, "annotation": a}
        for a in annotations
    ]

    matcher = BookMatcher(CALIBRE_BOOKS)
    matched, unmatched = matcher.match_batch(items)

    assert len(matched) == 3  # All 3 English clippings match "Structure of Scientific Revolutions"
    assert all(m["calibre_id"] == 4 for m in matched)
    assert len(unmatched) == 0


def test_mixed_match_unmatched():
    """Some annotations match, some don't."""
    provider = KindleProvider()
    # Combine German fixture (has "Die Blechtrommel" which matches)
    de_annotations = provider.extract(str(FIXTURES / "my_clippings_de.txt"))
    en_annotations = provider.extract(str(FIXTURES / "my_clippings_en.txt"))

    all_annotations = de_annotations + en_annotations
    items = [
        {"title": a.book_title, "author": a.book_author, "annotation": a}
        for a in all_annotations
    ]

    # Only include Blechtrommel in calibre, not Kuhn
    matcher = BookMatcher([CALIBRE_BOOKS[0]])  # Only Blechtrommel
    matched, unmatched = matcher.match_batch(items)

    assert len(matched) == 2  # Die Blechtrommel entries
    assert len(unmatched) == 3  # Kuhn entries
```

- [ ] **Step 2: Run all tests**

Run: `python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 3: Final commit**

```bash
git add tests/test_import_integration.py
git commit -m "test(annotations): add end-to-end integration test for annotation import"
```
