"""
PDF Annotation Provider.

Extracts annotations (highlights, notes, bookmarks) embedded in PDF files
using PyMuPDF (fitz).
"""

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
            import fitz  # PyMuPDF
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
                    if annot_type_raw in (
                        "Highlight", "Underline", "StrikeOut", "Squiggly"
                    ):
                        text = page.get_textbox(annot.rect).strip()

                    note_content = annot.info.get("content", "").strip()
                    timestamp = _parse_pdf_date(annot.info.get("modDate", ""))

                    if annot_type_raw in ("Highlight", "Underline"):
                        anno_type = "highlight"
                    elif annot_type_raw in ("Text", "FreeText"):
                        anno_type = "note"
                    else:
                        anno_type = "bookmark"

                    pos_frac = (
                        (page_num + 1) / total_pages if total_pages > 0 else 0
                    )

                    annotations.append(
                        Annotation(
                            source="pdf",
                            type=anno_type,
                            text=text,
                            note=note_content or None,
                            location=f"page:{page_num + 1}",
                            page_number=page_num + 1,
                            created_at=timestamp,
                            raw_metadata={
                                "annot_type_raw": annot_type_raw,
                                "pos_frac": pos_frac,
                                "spine_index": page_num,
                            },
                        )
                    )

            doc.close()
        except Exception as e:
            logger.error(f"Error extracting PDF annotations from {path}: {e}")

        return annotations
