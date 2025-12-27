#!/usr/bin/env python3
"""
Find the original library path by reverse-engineering annotation hashes.

Takes known annotation hashes and tries various path combinations
to find which path generates the matching hash.
"""

import sys
from pathlib import Path
import hashlib
import sqlite3
import os

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def compute_book_hash(book_path: str) -> str:
    """Compute SHA256 hash of book path (same as Calibre)."""
    return hashlib.sha256(book_path.encode('utf-8')).hexdigest()


def find_original_path():
    """
    Reverse-engineer the original library path by testing hash combinations.
    """
    library_path = os.getenv('CALIBRE_LIBRARY_PATH')
    if not library_path:
        print("ERROR: CALIBRE_LIBRARY_PATH not set")
        sys.exit(1)

    library_path = Path(library_path)

    # Get annotation hashes
    annots_dir = Path.home() / ".local" / "share" / "calibre" / "viewer" / "annots"
    if os.name == 'nt':  # Windows
        appdata = os.environ.get('APPDATA', '')
        annots_dir = Path(appdata) / 'calibre' / 'viewer' / 'annots'

    if not annots_dir.exists():
        print(f"ERROR: Annotations directory not found: {annots_dir}")
        sys.exit(1)

    # Get first 10 annotation hashes for testing
    annotation_files = list(annots_dir.glob("*.json"))[:10]
    annotation_hashes = {f.stem for f in annotation_files}

    print("=" * 80)
    print("REVERSE-ENGINEERING ORIGINAL LIBRARY PATH")
    print("=" * 80)
    print(f"\nCurrent library: {library_path}")
    print(f"Annotation hashes to match: {len(annotation_hashes)}")
    print(f"Sample hashes:")
    for h in list(annotation_hashes)[:3]:
        print(f"  {h}")

    # Get Calibre books
    db_path = library_path / "metadata.db"
    if not db_path.exists():
        print(f"\nERROR: metadata.db not found at {db_path}")
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
    LIMIT 50
    """

    cursor = conn.execute(query)
    calibre_books = cursor.fetchall()
    conn.close()

    print(f"\nTesting {len(calibre_books)} books from Calibre DB...")

    # Common path variants to test
    path_variants = []

    # Drive letters
    drives = ['C:', 'D:', 'E:', 'F:', 'G:', 'H:']

    # Common library names
    library_names = [
        'Calibre-Bibliothek',
        'Calibre Library',
        'Calibre',
        'calibre',
        'Books',
        'My Books',
        'eBooks'
    ]

    # Combination of drives and library names
    for drive in drives:
        for lib_name in library_names:
            path_variants.append(f"{drive}\\{lib_name}")
            path_variants.append(f"{drive}\\Users\\tomra\\{lib_name}")  # User-specific
            path_variants.append(f"{drive}\\Users\\tomra\\Documents\\{lib_name}")

    # Add current path base with different drives
    current_base = str(library_path)[2:]  # Remove drive letter
    for drive in drives:
        path_variants.append(drive + current_base)

    print(f"\nTesting {len(path_variants)} path variants...")
    print("\n" + "=" * 80)

    matches_found = {}

    # Test each book against each path variant
    for book in calibre_books:
        relative_path = book['path']
        filename = f"{book['filename']}.{book['format']}"

        for variant_base in path_variants:
            # Construct full path
            full_path = Path(variant_base) / relative_path / filename
            computed_hash = compute_book_hash(str(full_path))

            # Check if this hash matches any annotation hash
            if computed_hash in annotation_hashes:
                if variant_base not in matches_found:
                    matches_found[variant_base] = []

                matches_found[variant_base].append({
                    'hash': computed_hash,
                    'title': book['title'],
                    'author': book['author'],
                    'path': str(full_path)
                })

    # Show results
    if matches_found:
        print("✅ FOUND MATCHING PATH(S)!\n")

        # Sort by number of matches
        sorted_matches = sorted(matches_found.items(), key=lambda x: len(x[1]), reverse=True)

        for variant_base, matches in sorted_matches:
            print(f"\n{'='*80}")
            print(f"PATH: {variant_base}")
            print(f"MATCHES: {len(matches)}")
            print(f"{'='*80}")

            for i, match in enumerate(matches[:5], 1):  # Show first 5
                print(f"\n[{i}] Title: {match['title']}")
                print(f"    Author: {match['author']}")
                print(f"    Hash: {match['hash'][:16]}...")
                print(f"    Full Path: {match['path']}")

            if len(matches) > 5:
                print(f"\n... and {len(matches) - 5} more matches")

        # Recommendation
        best_path = sorted_matches[0][0]
        best_count = len(sorted_matches[0][1])

        print("\n" + "=" * 80)
        print("RECOMMENDATION")
        print("=" * 80)
        print(f"\n🎯 Original library path was likely:")
        print(f"   {best_path}")
        print(f"\n   ({best_count} of {len(annotation_hashes)} test hashes matched)")

        if best_count == len(annotation_hashes):
            print("\n   ✅ All test hashes matched! This is very likely correct.")
        elif best_count > len(annotation_hashes) * 0.5:
            print(f"\n   ⚠️  {best_count}/{len(annotation_hashes)} matched. This is probably correct.")
        else:
            print(f"\n   ⚠️  Only {best_count}/{len(annotation_hashes)} matched. May need more variants.")

    else:
        print("❌ NO MATCHES FOUND")
        print("\nThe original library path is not among the tested variants.")
        print("\nPossible reasons:")
        print("1. Library was on a network drive or unusual location")
        print("2. Library had a non-standard name")
        print("3. Path included special characters or spaces")
        print("\n💡 Try manually testing specific paths:")
        print("   python scripts/find_original_path.py")


if __name__ == '__main__':
    find_original_path()
