#!/usr/bin/env python3
"""
Diagnostic tool to match annotation files to Calibre books.

Shows which annotation files we have, which books we have, and attempts
to match them using various strategies.
"""

import sys
from pathlib import Path
import hashlib
import sqlite3
import os
import json
from collections import defaultdict

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def compute_book_hash(book_path: str) -> str:
    """Compute SHA256 hash of book path."""
    return hashlib.sha256(book_path.encode('utf-8')).hexdigest()


def extract_book_id_from_path(path: str) -> int:
    """
    Extract Calibre book ID from path.
    Path format: "Author Name\Book Title (ID)\filename"
    """
    import re
    match = re.search(r'\((\d+)\)', path)
    if match:
        return int(match.group(1))
    return None


def main():
    library_path = os.getenv('CALIBRE_LIBRARY_PATH')
    if not library_path:
        print("ERROR: CALIBRE_LIBRARY_PATH not set")
        sys.exit(1)

    library_path = Path(library_path)

    # Get annotations
    annots_dir = Path.home() / ".local" / "share" / "calibre" / "viewer" / "annots"
    if os.name == 'nt':  # Windows
        appdata = os.environ.get('APPDATA', '')
        annots_dir = Path(appdata) / 'calibre' / 'viewer' / 'annots'

    if not annots_dir.exists():
        print(f"ERROR: Annotations directory not found: {annots_dir}")
        sys.exit(1)

    annotation_files = list(annots_dir.glob("*.json"))

    print("=" * 80)
    print("ANNOTATION TO BOOK MATCHING DIAGNOSTIC")
    print("=" * 80)
    print(f"\nAnnotations directory: {annots_dir}")
    print(f"Total annotation files: {len(annotation_files)}")

    # Load annotation info
    annotation_info = {}
    for anno_file in annotation_files:
        try:
            with open(anno_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            if isinstance(data, list):
                # Get text samples
                text_samples = []
                for anno in data[:5]:
                    text = anno.get('highlighted_text', '')
                    if text:
                        text_samples.append(text[:100])

                annotation_info[anno_file.stem] = {
                    'count': len(data),
                    'samples': text_samples,
                    'file': anno_file.name
                }
        except:
            pass

    # Get Calibre books
    db_path = library_path / "metadata.db"
    if not db_path.exists():
        print(f"ERROR: metadata.db not found at {db_path}")
        sys.exit(1)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row

    query = """
    SELECT books.id, books.title, books.path,
           data.name as filename, data.format,
           (SELECT name FROM authors
            JOIN books_authors_link ON authors.id = books_authors_link.author
            WHERE books_authors_link.book = books.id
            LIMIT 1) as author
    FROM books
    JOIN data ON books.id = data.book
    WHERE data.format IN ('EPUB', 'PDF', 'MOBI', 'AZW3')
    ORDER BY books.id
    """

    cursor = conn.execute(query)
    calibre_books = cursor.fetchall()
    conn.close()

    print(f"Calibre library: {library_path}")
    print(f"Total Calibre books: {len(calibre_books)}")

    # Build book ID to metadata mapping
    book_by_id = {}
    for book in calibre_books:
        book_id = extract_book_id_from_path(book['path'])
        if book_id:
            book_by_id[book_id] = {
                'id': book['id'],
                'title': book['title'],
                'author': book['author'],
                'path': book['path'],
                'filename': f"{book['filename']}.{book['format']}",
                'format': book['format']
            }

    print(f"Books with extractable IDs: {len(book_by_id)}")

    # Try comprehensive path matching
    print("\n" + "=" * 80)
    print("ATTEMPTING HASH MATCHING")
    print("=" * 80)

    # Generate path variants
    path_bases = [str(library_path)]

    # Add all drive letters
    current_base = str(library_path)[2:] if len(str(library_path)) > 2 else ""
    if current_base:
        for letter in 'CDEFGHIJKLMNOPQRSTUVWXYZ':
            path_bases.append(f"{letter}:{current_base}")

    print(f"\nTesting {len(path_bases)} path base variants...")

    matches_found = {}
    unmatched_annotations = set(annotation_info.keys())

    for book in calibre_books:
        relative_path = book['path']
        filename = f"{book['filename']}.{book['format']}"
        book_id = extract_book_id_from_path(relative_path)

        for base in path_bases[:20]:  # Limit to prevent too many tests
            # Try different slash variants
            for slash_sep in ['\\', '/']:
                full_path = f"{base}{slash_sep}{relative_path}{slash_sep}{filename}"

                hash_val = compute_book_hash(full_path)

                if hash_val in annotation_info:
                    if hash_val not in matches_found:
                        matches_found[hash_val] = {
                            'book_title': book['title'],
                            'book_author': book['author'],
                            'book_id': book_id,
                            'matched_path': full_path,
                            'annotation_count': annotation_info[hash_val]['count']
                        }
                        unmatched_annotations.discard(hash_val)

    print(f"\n✅ Matched: {len(matches_found)} annotation files")
    print(f"❌ Unmatched: {len(unmatched_annotations)} annotation files")

    if matches_found:
        print("\n" + "=" * 80)
        print("MATCHED ANNOTATIONS (Sample)")
        print("=" * 80)

        for i, (anno_hash, match_info) in enumerate(list(matches_found.items())[:10], 1):
            print(f"\n[{i}] Annotation: {anno_hash[:16]}...")
            print(f"    Book: {match_info['book_title']}")
            print(f"    Author: {match_info['book_author']}")
            print(f"    Book ID: {match_info['book_id']}")
            print(f"    Annotations: {match_info['annotation_count']}")

    if unmatched_annotations:
        print("\n" + "=" * 80)
        print("UNMATCHED ANNOTATIONS (Sample)")
        print("=" * 80)
        print("\nThese annotation files could not be matched to any Calibre book.")
        print("This usually means:")
        print("1. The book was removed from Calibre")
        print("2. The book's title/author was changed (folder structure changed)")
        print("3. The library path structure is very different from tested variants")

        for i, anno_hash in enumerate(list(unmatched_annotations)[:10], 1):
            info = annotation_info[anno_hash]
            print(f"\n[{i}] Hash: {anno_hash[:16]}...")
            print(f"    File: {info['file']}")
            print(f"    Annotations: {info['count']}")

            if info['samples']:
                print(f"    Sample text: {info['samples'][0][:80]}...")

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    match_rate = len(matches_found) / len(annotation_files) * 100 if annotation_files else 0
    print(f"\nMatch rate: {match_rate:.1f}% ({len(matches_found)}/{len(annotation_files)})")

    if match_rate < 50:
        print("\n⚠️  LOW MATCH RATE!")
        print("\nRecommendations:")
        print("1. Run scripts/find_original_path_enhanced.py to test more path variants")
        print("2. Check if books were renamed in Calibre after creating annotations")
        print("3. Consider using fuzzy matching based on annotation content")
        print("4. Verify annotations are from this Calibre library")
    elif match_rate < 100:
        print("\n✓ Partial matches found")
        print("\nFor unmatched annotations, consider:")
        print("- Fuzzy matching based on annotation text content")
        print("- Manual review of unmatched annotations")
    else:
        print("\n✅ All annotations matched!")


if __name__ == '__main__':
    main()
