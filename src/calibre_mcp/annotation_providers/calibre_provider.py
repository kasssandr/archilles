"""
Calibre Viewer Annotation Provider.

Reads annotations from Calibre's viewer annotation store (JSON files
hashed by book path).
"""

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
                    created_at = datetime.fromisoformat(
                        timestamp_str.replace("Z", "+00:00")
                    )
                except (ValueError, AttributeError):
                    pass

            raw_metadata = dict(raw)
            # Propagate spine_index and pos_frac for legacy compat
            if "cfi" in raw:
                raw_metadata["cfi"] = raw["cfi"]

            annotations.append(
                Annotation(
                    source="calibre_viewer",
                    type=annot_type,
                    text=text,
                    note=notes or None,
                    location=raw.get("cfi", ""),
                    page_number=raw.get("spine_index"),
                    created_at=created_at,
                    raw_metadata=raw_metadata,
                )
            )

        return annotations
