#!/usr/bin/env python3
"""
Debug script to show why annotation hashes don't match Calibre books.

This helps identify path mismatches between annotation creation and current library.
"""

import sys
from pathlib import Path
import hashlib
import json

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import os
import sqlite3

def compute_book_hash(book_path: str) -> str:
    """Compute SHA256 hash of book path (same as Calibre)."""
    return hashlib.sha256(book_path.encode('utf-8')).hexdigest()


def debug_hashes():
    """Show annotation hashes vs Calibre book hashes."""

    library_path = os.getenv('CALIBRE_LIBRARY_PATH')
    if not library_path:
        print("ERROR: CALIBRE_LIBRARY_PATH not set")
        sys.exit(1)

    library_path = Path(library_path)

    # 1. Get annotation hashes
    annots_dir = Path.home() / ".local" / "share" / "calibre" / "viewer" / "annots"
    if os.name == 'nt':  # Windows
        appdata = os.environ.get('APPDATA', '')
        annots_dir = Path(appdata) / 'calibre' / 'viewer' / 'annots'

    print("=" * 80)
    print("ANNOTATION HASH DEBUG")
    print("=" * 80)
    print(f"\nAnnotations Directory: {annots_dir}")
    print(f"Calibre Library: {library_path}\n")

    if not annots_dir.exists():
        print(f"ERROR: Annotations directory not found!")
        return

    # Get first 5 annotation files
    annotation_files = list(annots_dir.glob("*.json"))[:5]

    if not annotation_files:
        print("No annotation files found!")
        return

    print(f"Found {len(list(annots_dir.glob('*.json')))} annotation files total")
    print(f"Analyzing first 5...\n")

    # 2. Get sample Calibre books
    db_path = library_path / "metadata.db"
    if not db_path.exists():
        print(f"ERROR: metadata.db not found at {db_path}")
        return

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    query = """
    SELECT
        books.id,
        books.title,
        books.path,
        data.name as filename,
        data.format
    FROM books
    JOIN data ON books.id = data.book
    WHERE data.format IN ('EPUB', 'PDF', 'MOBI', 'AZW3')
    ORDER BY books.id
    LIMIT 10
    """

    cursor = conn.execute(query)
    calibre_books = cursor.fetchall()

    print("=" * 80)
    print("SAMPLE ANNOTATION FILES")
    print("=" * 80)

    for i, anno_file in enumerate(annotation_files, 1):
        anno_hash = anno_file.stem

        # Try to read annotation to get any path info
        try:
            with open(anno_file, 'r', encoding='utf-8') as f:
                annots = json.load(f)
            anno_count = len(annots) if isinstance(annots, list) else 0
        except:
            anno_count = "?"

        print(f"\n[{i}] Annotation File:")
        print(f"    Hash: {anno_hash}")
        print(f"    Annotations: {anno_count}")
        print(f"    File: {anno_file.name}")

    print("\n" + "=" * 80)
    print("SAMPLE CALIBRE BOOKS WITH COMPUTED HASHES")
    print("=" * 80)

    for i, book in enumerate(calibre_books, 1):
        # Construct path as done in indexer
        book_path = library_path / book['path'] / f"{book['filename']}.{book['format']}"
        computed_hash = compute_book_hash(str(book_path))

        print(f"\n[{i}] Calibre Book:")
        print(f"    Title: {book['title'][:50]}")
        print(f"    Path: {book['path']}/{book['filename']}.{book['format']}")
        print(f"    Full Path: {book_path}")
        print(f"    Computed Hash: {computed_hash}")

        # Check if this hash matches any annotation
        anno_file = annots_dir / f"{computed_hash}.json"
        if anno_file.exists():
            print(f"    ✓ MATCH! Annotation file exists!")
        else:
            print(f"    ✗ No matching annotation file")

    print("\n" + "=" * 80)
    print("DIAGNOSIS")
    print("=" * 80)

    # Try to find any matches
    calibre_hashes = set()
    for book in calibre_books:
        book_path = library_path / book['path'] / f"{book['filename']}.{book['format']}"
        computed_hash = compute_book_hash(str(book_path))
        calibre_hashes.add(computed_hash)

    annotation_hashes = {f.stem for f in annotation_files}

    matches = calibre_hashes & annotation_hashes

    print(f"\nSample Calibre hashes: {len(calibre_hashes)}")
    print(f"Sample Annotation hashes: {len(annotation_hashes)}")
    print(f"Matches: {len(matches)}")

    if len(matches) == 0:
        print("\n⚠️  NO MATCHES FOUND!")
        print("\nPossible reasons:")
        print("1. Library path changed (books were at different location when annotated)")
        print("2. Books were moved/reorganized in Calibre")
        print("3. Annotations created on different computer/drive letter")
        print("\n💡 Solution:")
        print("   The annotations were likely created when books were at a different path.")
        print("   Unfortunately, Calibre uses the FULL path for hashing, so if the path")
        print("   changed, the hashes won't match.")
        print("\n   Options:")
        print("   a) Re-create annotations (if possible)")
        print("   b) Use a path-independent annotation system")
        print("   c) Modify the hash mapping to be more flexible")
    else:
        print(f"\n✓ Found {len(matches)} matches in sample!")

    conn.close()


if __name__ == '__main__':
    debug_hashes()
