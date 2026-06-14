"""Kanonische Hash-Funktionen fuer Change-Detection (Befund 7.15).

Eine Stelle fuer die Calibre-Metadata-Hash- und die Annotation-Content-Hash-
Logik. Wird von Watchdog, Engine, Calibre-Adapter und patch_comments genutzt.
Die erzeugten Hashes sind byte-identisch zu den bisherigen verteilten Kopien
(Invarianten I1-I3 in PLAN_2026-06-14_HASH_MODUL.md) -- Aenderungen hier loesen
einen Reindex aller Buecher aus.
"""
import hashlib
import json
from typing import Any, Dict, List


def compute_metadata_hash(book_metadata: Dict[str, Any]) -> str:
    """MD5 ueber comments/tags/title/author/publisher (Calibre-Change-Detection).

    Tags werden unabhaengig vom Eingabetyp sortiert, damit Calibres interne
    Tag-Reihenfolge den Hash nicht aendert. Ein leeres/None-Dict ergibt ''.
    """
    if not book_metadata:
        return ''
    tags = book_metadata.get('tags', [])
    if isinstance(tags, str):
        tags = sorted(t.strip() for t in tags.split(',') if t.strip())
    elif isinstance(tags, list):
        tags = sorted(tags)
    relevant = {
        'comments': book_metadata.get('comments', ''),
        'tags': tags,
        'title': book_metadata.get('title', ''),
        'author': book_metadata.get('author', ''),
        'publisher': book_metadata.get('publisher', ''),
    }
    return hashlib.md5(
        json.dumps(relevant, sort_keys=True, ensure_ascii=False).encode('utf-8')
    ).hexdigest()


def compute_annotation_hash(annotations: List[Dict[str, Any]]) -> str:
    """MD5 ueber alle Annotationen eines Buchs (Change-Detection).

    Sortiert nach 'highlighted_text|notes|type', join mit '\\n'. Leere Liste -> ''.
    """
    if not annotations:
        return ''
    texts = sorted(
        f"{a.get('highlighted_text', '')}|{a.get('notes', '')}|{a.get('type', '')}"
        for a in annotations
    )
    return hashlib.md5('\n'.join(texts).encode('utf-8')).hexdigest()
