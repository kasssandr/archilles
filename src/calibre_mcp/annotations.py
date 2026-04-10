#!/usr/bin/env python3
"""
Calibre Annotations Module

This module handles reading and processing Calibre viewer annotations.

CRITICAL: Calibre uses SHA256 of the FILE PATH, not file content, for annotation lookup!
"""

import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

_TOC_KEYWORDS = frozenset([
    'inhaltsverzeichnis', 'table of contents', 'contents',
    'chapter', 'kapitel', 'part', 'teil', 'section',
    'index', 'register', 'anhang', 'appendix',
    'vorwort', 'preface', 'introduction', 'einleitung',
    'bibliography', 'literaturverzeichnis',
])


def compute_book_hash(book_path: str) -> str:
    """
    Compute the hash used by Calibre for annotation filenames.

    IMPORTANT: Calibre hashes the FILE PATH, not the file content!
    This is how Calibre's viewer stores annotations - by hashing the
    full path to the book file.

    Args:
        book_path: Full path to the book file (e.g., "D:\\Calibre\\Book.epub")

    Returns:
        SHA256 hash of the path (64 character hex string)
    """
    return hashlib.sha256(book_path.encode('utf-8')).hexdigest()


def get_annotations_dir() -> Path:
    """Get the default Calibre annotations directory."""
    if os.name == 'nt':
        appdata = os.environ.get('APPDATA', '')
        return Path(appdata) / 'calibre' / 'viewer' / 'annots'
    return Path.home() / '.local' / 'share' / 'calibre' / 'viewer' / 'annots'


def _resolve_annotations_path(annotations_dir: Optional[str] = None) -> Path:
    """Resolve the annotations directory, falling back to the platform default."""
    return Path(annotations_dir) if annotations_dir else get_annotations_dir()


def get_book_annotations(
    book_path: str,
    annotations_dir: Optional[str] = None
) -> Optional[list[dict[str, Any]]]:
    """
    Get all annotations for a specific book.

    Args:
        book_path: Full path to the book file
        annotations_dir: Optional custom annotations directory

    Returns:
        List of annotations or None if not found
    """
    annots_path = _resolve_annotations_path(annotations_dir)

    # Calculate the correct hash from the path
    book_hash = compute_book_hash(book_path)
    annotation_file = annots_path / f"{book_hash}.json"

    if not annotation_file.exists():
        return None

    try:
        with open(annotation_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Calibre stores annotations as a list
        if isinstance(data, list):
            return data
        elif isinstance(data, dict):
            # Some versions might use a different format
            return data.get('annotations', [])
        else:
            return []

    except (json.JSONDecodeError, IOError) as e:
        logger.error(f"Error reading annotations: {e}")
        return None


def _filter_by_type(
    book_path: str,
    annotations_dir: Optional[str],
    predicate,
) -> list[dict[str, Any]]:
    """Return annotations matching the given predicate."""
    annotations = get_book_annotations(book_path, annotations_dir)
    if not annotations:
        return []
    return [a for a in annotations if predicate(a)]


def get_highlights(
    book_path: str,
    annotations_dir: Optional[str] = None
) -> list[dict[str, Any]]:
    """Get only highlight annotations for a book."""
    return _filter_by_type(book_path, annotations_dir,
                           lambda a: a.get('type') == 'highlight')


def get_notes(
    book_path: str,
    annotations_dir: Optional[str] = None
) -> list[dict[str, Any]]:
    """Get only note annotations for a book."""
    return _filter_by_type(book_path, annotations_dir,
                           lambda a: a.get('type') == 'note' or a.get('notes'))


def get_bookmarks(
    book_path: str,
    annotations_dir: Optional[str] = None
) -> list[dict[str, Any]]:
    """Get only bookmark annotations for a book."""
    return _filter_by_type(book_path, annotations_dir,
                           lambda a: a.get('type') == 'bookmark')


def format_annotation(annotation: dict[str, Any]) -> str:
    """
    Format an annotation for display.

    Args:
        annotation: The annotation dictionary

    Returns:
        Formatted string representation
    """
    annot_type = annotation.get('type', 'unknown')
    highlighted_text = annotation.get('highlighted_text', '')
    notes = annotation.get('notes', '')
    timestamp = annotation.get('timestamp', '')

    # Format timestamp if present
    if timestamp:
        try:
            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            timestamp = dt.strftime('%Y-%m-%d %H:%M')
        except (ValueError, AttributeError):
            pass

    result = f"[{annot_type.upper()}]"
    if timestamp:
        result += f" ({timestamp})"
    result += "\n"

    if highlighted_text:
        result += f"Text: {highlighted_text}\n"

    if notes:
        result += f"Note: {notes}\n"

    return result


def list_all_annotated_books(
    annotations_dir: Optional[str] = None
) -> list[dict[str, Any]]:
    """
    List all books that have annotations.

    Args:
        annotations_dir: Optional custom annotations directory

    Returns:
        List of annotation file info (hash, count, size)
    """
    annots_path = _resolve_annotations_path(annotations_dir)

    if not annots_path.exists():
        return []

    results = []
    for json_file in annots_path.glob("*.json"):
        try:
            stat = json_file.stat()
            with open(json_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            count = len(data) if isinstance(data, list) else 0

            results.append({
                'hash': json_file.stem,
                'filename': json_file.name,
                'annotation_count': count,
                'size_bytes': stat.st_size,
                'modified': datetime.fromtimestamp(stat.st_mtime).isoformat()
            })
        except Exception as e:
            results.append({
                'hash': json_file.stem,
                'filename': json_file.name,
                'error': str(e)
            })

    return sorted(results, key=lambda x: x.get('annotation_count', 0), reverse=True)


def search_annotations(
    query: str,
    annotations_dir: Optional[str] = None,
    case_sensitive: bool = False
) -> list[dict[str, Any]]:
    """
    Search through all annotations for matching text.

    Args:
        query: Search query string
        annotations_dir: Optional custom annotations directory
        case_sensitive: Whether to use case-sensitive search

    Returns:
        List of matching annotations with file info
    """
    annots_path = _resolve_annotations_path(annotations_dir)

    if not annots_path.exists():
        return []

    if not case_sensitive:
        query = query.lower()

    results = []

    for json_file in annots_path.glob("*.json"):
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                annotations = json.load(f)

            if not isinstance(annotations, list):
                continue

            for annot in annotations:
                text = annot.get('highlighted_text', '') + ' ' + annot.get('notes', '')

                if not case_sensitive:
                    text = text.lower()

                if query in text:
                    results.append({
                        'file_hash': json_file.stem,
                        'annotation': annot
                    })

        except Exception:
            continue

    return results


def is_toc_marker(
    annotation: dict[str, Any],
    min_length: int = 20,
    exclude_first_percent: float = 5.0
) -> bool:
    """
    Detect if an annotation is likely a TOC marker or other technical highlight.

    This function filters out:
    - Very short highlights (often just chapter titles)
    - Annotations in the first X% of the book (usually TOC/front matter)
    - Annotations containing TOC-like keywords

    Args:
        annotation: The annotation dictionary
        min_length: Minimum character length for valid annotations
        exclude_first_percent: Exclude annotations in first X% of book

    Returns:
        True if annotation appears to be a TOC marker/technical annotation
    """
    text = annotation.get('highlighted_text', '').strip()
    notes = annotation.get('notes', '').strip()

    if len(text) < min_length and not notes:
        return True

    combined = f"{text} {notes}".lower()

    if len(text) < 50:
        if any(keyword in combined for keyword in _TOC_KEYWORDS):
            return True

    pos_frac = annotation.get('pos_frac')
    if pos_frac is not None:
        try:
            position_percent = float(pos_frac) * 100
            if position_percent < exclude_first_percent:
                return True
        except (ValueError, TypeError):
            pass

    spine_index = annotation.get('spine_index')
    if spine_index is not None and spine_index == 0:
        return True

    return False


def filter_annotations(
    annotations: list[dict[str, Any]],
    exclude_toc_markers: bool = True,
    min_length: int = 20,
    exclude_first_percent: float = 5.0,
    annotation_types: Optional[list[str]] = None
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """
    Filter annotations based on various criteria.

    Args:
        annotations: List of annotation dictionaries
        exclude_toc_markers: Whether to exclude TOC markers
        min_length: Minimum text length
        exclude_first_percent: Exclude annotations in first X% of book
        annotation_types: List of annotation types to include (e.g., ['highlight', 'note'])

    Returns:
        Tuple of (filtered_annotations, exclusion_stats)
    """
    if not annotations:
        return [], {}

    filtered = []
    exclusion_stats = {
        'toc_markers': 0,
        'too_short': 0,
        'first_percent': 0,
        'wrong_type': 0
    }

    for annot in annotations:
        # Filter by type
        if annotation_types:
            annot_type = annot.get('type', '')
            if annot_type not in annotation_types:
                exclusion_stats['wrong_type'] += 1
                continue

        # Filter TOC markers
        if exclude_toc_markers:
            if is_toc_marker(annot, min_length, exclude_first_percent):
                exclusion_stats['toc_markers'] += 1
                continue

        filtered.append(annot)

    return filtered, exclusion_stats


def _parse_pdf_date(mod_date: str) -> str:
    """Parse a PDF date string (D:YYYYMMDDHHmmSS) into ISO format."""
    if not mod_date:
        return ""
    try:
        if mod_date.startswith("D:"):
            date_str = mod_date[2:16]
            return datetime.strptime(date_str, "%Y%m%d%H%M%S").isoformat()
    except (ValueError, IndexError):
        pass
    return mod_date


def get_pdf_annotations(pdf_path: str) -> list[dict[str, Any]]:
    """
    Extract annotations from PDF file using PyMuPDF.

    Args:
        pdf_path: Path to PDF file

    Returns:
        List of annotations in standardized format
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return []

    pdf_path = Path(pdf_path)
    if not pdf_path.exists() or pdf_path.suffix.lower() != '.pdf':
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

                pos_frac = (page_num + 1) / total_pages if total_pages > 0 else 0

                annotations.append({
                    'type': anno_type,
                    'highlighted_text': text,
                    'notes': note_content,
                    'timestamp': timestamp,
                    'spine_index': page_num,
                    'pos_frac': pos_frac,
                    'source': 'pdf',
                    'page': page_num + 1
                })

        doc.close()

    except Exception:
        pass

    return annotations


def get_combined_annotations(
    book_path: str,
    annotations_dir: Optional[str] = None,
    include_pdf: bool = True,
    exclude_toc_markers: bool = True,
    min_length: int = 20,
    exclude_first_percent: float = 5.0,
    annotation_types: Optional[list[str]] = None
) -> dict[str, Any]:
    """
    Get annotations from both Calibre Viewer and PDF (if applicable).

    This is the main function that combines all annotation sources
    and applies intelligent filtering. Delegates to annotation providers
    internally.

    Args:
        book_path: Full path to the book file
        annotations_dir: Optional custom annotations directory for Calibre
        include_pdf: Whether to extract PDF annotations
        exclude_toc_markers: Whether to exclude TOC markers
        min_length: Minimum text length for annotations
        exclude_first_percent: Exclude annotations in first X% of book
        annotation_types: Filter by annotation types (e.g., ['highlight', 'note'])

    Returns:
        Dictionary with annotations and metadata
    """
    from .annotation_providers.calibre_provider import CalibreViewerProvider
    from .annotation_providers.pdf_provider import PdfAnnotationProvider

    all_annotations = []

    # Use provider for Calibre Viewer annotations
    calibre_provider = CalibreViewerProvider(annotations_dir=annotations_dir)
    calibre_annots = calibre_provider.extract(book_path)
    all_annotations.extend(a.to_legacy_dict() for a in calibre_annots)

    # Use provider for PDF annotations
    if include_pdf and book_path.lower().endswith('.pdf'):
        pdf_provider = PdfAnnotationProvider()
        pdf_annots = pdf_provider.extract(book_path)
        all_annotations.extend(a.to_legacy_dict() for a in pdf_annots)

    filtered_annotations, exclusion_stats = filter_annotations(
        all_annotations,
        exclude_toc_markers=exclude_toc_markers,
        min_length=min_length,
        exclude_first_percent=exclude_first_percent,
        annotation_types=annotation_types
    )

    book_title = Path(book_path).stem

    return {
        'book_path': book_path,
        'book_title': book_title,
        'total_annotations': len(all_annotations),
        'filtered_annotations': len(filtered_annotations),
        'annotations': filtered_annotations,
        'excluded_count': len(all_annotations) - len(filtered_annotations),
        'exclusion_stats': exclusion_stats
    }


# For backward compatibility - these are aliases
get_book_hash = compute_book_hash
calculate_annotation_hash = compute_book_hash
