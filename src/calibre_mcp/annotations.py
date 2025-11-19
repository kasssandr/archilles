#!/usr/bin/env python3
"""
Calibre Annotations Module

This module handles reading and processing Calibre viewer annotations.

CRITICAL: Calibre uses SHA256 of the FILE PATH, not file content, for annotation lookup!
"""

import hashlib
import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime


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
        print(f"Error reading annotations: {e}")
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


# For backward compatibility - these are aliases
get_book_hash = compute_book_hash
calculate_annotation_hash = compute_book_hash
