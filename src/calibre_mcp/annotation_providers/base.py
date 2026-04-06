"""
Annotation Provider base types.

Defines the unified Annotation dataclass and AnnotationProvider ABC
used by all annotation source providers (PDF, Calibre Viewer, Kindle, Kobo, etc.).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Annotation:
    """Unified annotation from any reading source."""

    source: str  # "kindle", "kobo", "apple_books", "pdf", "calibre_viewer"
    type: str  # "highlight", "note", "bookmark"
    text: str  # The highlighted text
    note: Optional[str] = None  # User note attached to highlight
    location: str = ""  # Source-specific: Kindle Location, EPUB CFI, PDF page
    page_number: Optional[int] = None
    chapter: Optional[str] = None
    created_at: Optional[datetime] = None
    book_title: Optional[str] = None  # Title as reported by source (for matching)
    book_author: Optional[str] = None  # Author as reported by source (for matching)
    calibre_id: Optional[int] = None  # Calibre book ID (set after matching)
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

    def to_legacy_dict(self) -> dict:
        """Convert to dict matching the old annotations.py format for backward compat."""
        d = {
            "type": self.type,
            "highlighted_text": self.text,
            "notes": self.note or "",
            "source": self.source,
        }
        if self.created_at:
            d["timestamp"] = self.created_at.isoformat()
        if self.page_number is not None:
            d["page"] = self.page_number
            d["spine_index"] = self.page_number - 1 if self.page_number > 0 else 0
        # Propagate raw_metadata fields for pos_frac etc.
        for key in ("pos_frac", "spine_index", "cfi"):
            if key in self.raw_metadata:
                d[key] = self.raw_metadata[key]
        return d


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
