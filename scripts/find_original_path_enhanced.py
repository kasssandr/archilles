#!/usr/bin/env python3
"""
Enhanced path reconstruction with slash variant testing.

Tests both forward and backward slashes since Calibre may normalize paths differently.
"""

import sys
from pathlib import Path
import hashlib
import sqlite3
import os
import json

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def compute_book_hash(book_path: str) -> str:
    """Compute SHA256 hash of book path (same as Calibre)."""
    return hashlib.sha256(book_path.encode('utf-8')).hexdigest()


def normalize_path_variants(path: str):
    """Generate different path normalization variants."""
    variants = []

    # Original
    variants.append(path)

    # Replace backslashes with forward slashes
    variants.append(path.replace('\\', '/'))

    # Replace forward slashes with backslashes
    variants.append(path.replace('/', '\\'))

    # Normalize with Path (platform-specific)
    try:
        variants.append(str(Path(path)))
    except:
        pass

    # Remove duplicates
    return list(set(variants))


def find_original_path():
    """
    Reverse-engineer the original library path with enhanced variant testing.
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

    # Get first 20 annotation files for testing
    annotation_files = list(annots_dir.glob("*.json"))[:20]
    annotation_hashes = {f.stem for f in annotation_files}

    # Also load actual annotation content to help with debugging
    sample_annotations = {}
    for anno_file in annotation_files[:5]:
        try:
            with open(anno_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list) and data:
                    # Get first annotation with text
                    for anno in data:
                        if anno.get('highlighted_text'):
                            sample_annotations[anno_file.stem] = {
                                'text_preview': anno['highlighted_text'][:100],
                                'annotation_count': len(data)
                            }
                            break
        except:
            pass

    print("=" * 80)
    print("ENHANCED PATH RECONSTRUCTION (with slash variants)")
    print("=" * 80)
    print(f"\nCurrent library: {library_path}")
    print(f"Annotation hashes to match: {len(annotation_hashes)}")
    print(f"\nSample annotation hashes with content:")
    for hash_key, info in list(sample_annotations.items())[:3]:
        print(f"  {hash_key[:16]}... ({info['annotation_count']} annotations)")
        print(f"    Preview: {info['text_preview']}...")

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
    LIMIT 100
    """

    cursor = conn.execute(query)
    calibre_books = cursor.fetchall()
    conn.close()

    print(f"\nTesting {len(calibre_books)} books from Calibre DB...")

    # Path base variants to test
    path_bases = []

    # 1. Current path
    path_bases.append(str(library_path))

    # 2. All drive letters with current path structure
    current_base = str(library_path)[2:] if len(str(library_path)) > 2 else ""
    for drive in 'CDEFGHIJKLMNOPQRSTUVWXYZ':
        path_bases.append(f"{drive}:{current_base}")

    # 3. Common library locations
    library_name = library_path.name
    for drive in 'CDEFGH':
        for parent in ['', '\\Users\\tomra', '\\Users\\tomra\\Documents']:
            path_bases.append(f"{drive}:{parent}\\{library_name}")

    # Remove duplicates
    path_bases = list(set(path_bases))

    print(f"\nTesting {len(path_bases)} base paths...")
    print("=" * 80)

    matches_found = {}
    total_hashes_tested = 0

    # Test each book against each path variant
    for book in calibre_books:
        relative_path = book['path']
        filename = f"{book['filename']}.{book['format']}"

        for base_path in path_bases:
            # Construct full path
            full_path = f"{base_path}\\{relative_path}\\{filename}"

            # Test multiple path normalization variants
            for path_variant in normalize_path_variants(full_path):
                total_hashes_tested += 1
                computed_hash = compute_book_hash(path_variant)

                # Check if this hash matches any annotation hash
                if computed_hash in annotation_hashes:
                    if base_path not in matches_found:
                        matches_found[base_path] = []

                    matches_found[base_path].append({
                        'hash': computed_hash,
                        'title': book['title'],
                        'author': book['author'],
                        'book_id': book['id'],
                        'path': path_variant,
                        'relative_path': f"{relative_path}\\{filename}"
                    })

    print(f"\nTotal hash combinations tested: {total_hashes_tested:,}")

    # Show results
    if matches_found:
        print("\n✅ FOUND MATCHING PATH(S)!\n")

        # Sort by number of matches
        sorted_matches = sorted(matches_found.items(), key=lambda x: len(x[1]), reverse=True)

        for base_path, matches in sorted_matches:
            print(f"\n{'='*80}")
            print(f"BASE PATH: {base_path}")
            print(f"MATCHES: {len(matches)}")
            print(f"{'='*80}")

            for i, match in enumerate(matches[:10], 1):  # Show first 10
                print(f"\n[{i}] Title: {match['title']}")
                print(f"    Author: {match['author']}")
                print(f"    Book ID: {match['book_id']}")
                print(f"    Hash: {match['hash'][:16]}...")
                print(f"    Relative: {match['relative_path']}")
                print(f"    Full Path: {match['path'][:100]}...")

            if len(matches) > 10:
                print(f"\n... and {len(matches) - 10} more matches")

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
        print("\n❌ NO MATCHES FOUND")
        print(f"\nTested {total_hashes_tested:,} hash combinations with no matches.")
        print("\nThis suggests:")
        print("1. The relative path structure in Calibre may have changed")
        print("   (books reorganized, metadata changed, etc.)")
        print("2. Annotations may be from a completely different library")
        print("3. There may be encoding or unicode normalization issues")
        print("\n💡 Debug suggestions:")
        print("   - Check if book titles/authors were changed in Calibre")
        print("   - Verify annotations are from this Calibre library")
        print("   - Try manually looking at a few relative paths in metadata.db")


if __name__ == '__main__':
    find_original_path()
