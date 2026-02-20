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
import re
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime

logger = logging.getLogger(__name__)


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
    # Hash the path string, not the file content
    return hashlib.sha256(book_path.encode('utf-8')).hexdigest()


def get_annotations_dir() -> Path:
    """
    Get the default Calibre annotations directory.

    Returns:
        Path to the annotations directory
    """
    if os.name == 'nt':  # Windows
        appdata = os.environ.get('APPDATA', '')
        return Path(appdata) / 'calibre' / 'viewer' / 'annots'
    else:  # Linux/Mac
        home = Path.home()
        return home / '.local' / 'share' / 'calibre' / 'viewer' / 'annots'


def get_book_annotations(
    book_path: str,
    annotations_dir: Optional[str] = None
) -> Optional[List[Dict[str, Any]]]:
    """
    Get all annotations for a specific book.

    Args:
        book_path: Full path to the book file
        annotations_dir: Optional custom annotations directory

    Returns:
        List of annotations or None if not found
    """
    if annotations_dir:
        annots_path = Path(annotations_dir)
    else:
        annots_path = get_annotations_dir()

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


def get_highlights(
    book_path: str,
    annotations_dir: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Get only highlight annotations for a book.

    Args:
        book_path: Full path to the book file
        annotations_dir: Optional custom annotations directory

    Returns:
        List of highlight annotations
    """
    annotations = get_book_annotations(book_path, annotations_dir)
    if not annotations:
        return []

    return [
        annot for annot in annotations
        if annot.get('type') == 'highlight'
    ]


def get_notes(
    book_path: str,
    annotations_dir: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Get only note annotations for a book.

    Args:
        book_path: Full path to the book file
        annotations_dir: Optional custom annotations directory

    Returns:
        List of note annotations
    """
    annotations = get_book_annotations(book_path, annotations_dir)
    if not annotations:
        return []

    return [
        annot for annot in annotations
        if annot.get('type') == 'note' or annot.get('notes')
    ]


def get_bookmarks(
    book_path: str,
    annotations_dir: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Get only bookmark annotations for a book.

    Args:
        book_path: Full path to the book file
        annotations_dir: Optional custom annotations directory

    Returns:
        List of bookmark annotations
    """
    annotations = get_book_annotations(book_path, annotations_dir)
    if not annotations:
        return []

    return [
        annot for annot in annotations
        if annot.get('type') == 'bookmark'
    ]


def format_annotation(annotation: Dict[str, Any]) -> str:
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
) -> List[Dict[str, Any]]:
    """
    List all books that have annotations.

    Args:
        annotations_dir: Optional custom annotations directory

    Returns:
        List of annotation file info (hash, count, size)
    """
    if annotations_dir:
        annots_path = Path(annotations_dir)
    else:
        annots_path = get_annotations_dir()

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
) -> List[Dict[str, Any]]:
    """
    Search through all annotations for matching text.

    Args:
        query: Search query string
        annotations_dir: Optional custom annotations directory
        case_sensitive: Whether to use case-sensitive search

    Returns:
        List of matching annotations with file info
    """
    if annotations_dir:
        annots_path = Path(annotations_dir)
    else:
        annots_path = get_annotations_dir()

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
    annotation: Dict[str, Any],
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

    # Check text length
    if len(text) < min_length and not notes:
        return True

    # TOC and technical keywords
    toc_keywords = [
        'inhaltsverzeichnis', 'table of contents', 'contents',
        'chapter', 'kapitel', 'part', 'teil', 'section',
        'index', 'register', 'anhang', 'appendix',
        'vorwort', 'preface', 'introduction', 'einleitung',
        'bibliography', 'literaturverzeichnis'
    ]

    # Combine text and notes for keyword check
    combined = f"{text} {notes}".lower()

    # Check for TOC keywords (but only if text is short)
    if len(text) < 50:  # Only apply keyword filter to short snippets
        if any(keyword in combined for keyword in toc_keywords):
            return True

    # Check position in book (if available)
    # Calibre stores position as 'pos' or calculate from 'spine_index'
    pos_frac = annotation.get('pos_frac')
    if pos_frac is not None:
        try:
            position_percent = float(pos_frac) * 100
            if position_percent < exclude_first_percent:
                return True
        except (ValueError, TypeError):
            pass

    # Alternative: check spine_index (chapter index)
    spine_index = annotation.get('spine_index')
    if spine_index is not None and spine_index == 0:
        # First chapter might be TOC
        return True

    return False


def filter_annotations(
    annotations: List[Dict[str, Any]],
    exclude_toc_markers: bool = True,
    min_length: int = 20,
    exclude_first_percent: float = 5.0,
    annotation_types: Optional[List[str]] = None
) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
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


def get_pdf_annotations(pdf_path: str) -> List[Dict[str, Any]]:
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
        # PyMuPDF not installed, return empty list
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

                # Extract highlighted text
                text = ""
                if annot_type_raw in ["Highlight", "Underline", "StrikeOut", "Squiggly"]:
                    # Get text from annotation rectangle
                    rect = annot.rect
                    text = page.get_textbox(rect).strip()

                # Extract note/comment
                note_content = annot.info.get("content", "").strip()

                # Extract timestamp
                mod_date = annot.info.get("modDate", "")
                timestamp = ""
                if mod_date:
                    # Parse PDF date format: D:YYYYMMDDHHmmSS
                    try:
                        if mod_date.startswith("D:"):
                            date_str = mod_date[2:16]  # YYYYMMDDHHmmSS
                            timestamp = datetime.strptime(date_str, "%Y%m%d%H%M%S").isoformat()
                    except (ValueError, IndexError):
                        timestamp = mod_date

                # Determine annotation type
                if annot_type_raw in ["Highlight", "Underline"]:
                    anno_type = "highlight"
                elif annot_type_raw in ["Text", "FreeText"]:
                    anno_type = "note"
                else:
                    anno_type = "bookmark"

                # Calculate position in document
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

    except Exception as e:
        # Silently fail if PDF cannot be read
        pass

    return annotations


def get_combined_annotations(
    book_path: str,
    annotations_dir: Optional[str] = None,
    include_pdf: bool = True,
    exclude_toc_markers: bool = True,
    min_length: int = 20,
    exclude_first_percent: float = 5.0,
    annotation_types: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Get annotations from both Calibre Viewer and PDF (if applicable).

    This is the main function that combines all annotation sources
    and applies intelligent filtering.

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
    all_annotations = []

    # Get Calibre Viewer annotations
    calibre_annots = get_book_annotations(book_path, annotations_dir)
    if calibre_annots:
        for annot in calibre_annots:
            annot['source'] = 'calibre_viewer'
        all_annotations.extend(calibre_annots)

    # Get PDF annotations if requested and file is PDF
    if include_pdf and book_path.lower().endswith('.pdf'):
        pdf_annots = get_pdf_annotations(book_path)
        all_annotations.extend(pdf_annots)

    # Apply filters
    filtered_annotations, exclusion_stats = filter_annotations(
        all_annotations,
        exclude_toc_markers=exclude_toc_markers,
        min_length=min_length,
        exclude_first_percent=exclude_first_percent,
        annotation_types=annotation_types
    )

    # Get book title from path
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
