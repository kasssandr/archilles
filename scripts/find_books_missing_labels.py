#!/usr/bin/env python3
"""
Find books that need re-indexing due to missing page labels.

These are books indexed before the page label extraction feature was added.
They can be identified by:
1. Empty page_label field
2. page_label equals page_number (no real extraction happened)

Usage:
    # List all books with missing page labels
    python scripts/find_books_missing_labels.py

    # Output as JSON (for scripting)
    python scripts/find_books_missing_labels.py --json

    # Output book IDs only (for piping to batch_index.py)
    python scripts/find_books_missing_labels.py --ids-only
"""

import sys
import json
import argparse
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.storage.lancedb_store import LanceDBStore


def find_books_missing_labels(db_path: str = "./data/lancedb") -> dict:
    """
    Find books where page_label is missing or equals page_number.

    Returns:
        Dict with book_id as key, containing:
        - book_title
        - author
        - total_chunks
        - missing_labels: chunks with no real page label
        - indexed_at: when the book was indexed
    """
    store = LanceDBStore(db_path)

    if store.table is None:
        print("❌ No data in database yet", file=sys.stderr)
        return {}

    # Get all chunks with their page info
    df = store.table.to_pandas()

    # Group by book
    books_stats = defaultdict(lambda: {
        'book_title': '',
        'author': '',
        'total_chunks': 0,
        'missing_labels': 0,
        'has_real_labels': 0,
        'indexed_at': '',
        'sample_pages': []
    })

    for _, row in df.iterrows():
        book_id = row.get('book_id', 'unknown')
        page_number = row.get('page_number', 0)
        page_label = row.get('page_label', '')

        stats = books_stats[book_id]
        stats['book_title'] = row.get('book_title', 'Unknown')
        stats['author'] = row.get('author', '')
        stats['total_chunks'] = stats['total_chunks'] + 1

        # Track indexed_at (use earliest)
        indexed_at = row.get('indexed_at', '')
        if indexed_at and (not stats['indexed_at'] or indexed_at < stats['indexed_at']):
            stats['indexed_at'] = indexed_at

        # Check if page_label is missing or just equals page_number
        if not page_label or page_label == '' or page_label == str(page_number):
            stats['missing_labels'] += 1
        else:
            stats['has_real_labels'] += 1
            # Sample some real labels
            if len(stats['sample_pages']) < 3:
                stats['sample_pages'].append(f"{page_label}")

    # Filter to books that need re-indexing
    # Criteria: >90% of chunks have missing labels
    needs_reindex = {}
    for book_id, stats in books_stats.items():
        total = stats['total_chunks']
        missing = stats['missing_labels']
        if total > 0 and (missing / total) > 0.9:
            needs_reindex[book_id] = stats

    return needs_reindex


def main():
    parser = argparse.ArgumentParser(
        description='Find books with missing page labels for re-indexing'
    )
    parser.add_argument('--json', action='store_true',
                       help='Output as JSON')
    parser.add_argument('--ids-only', action='store_true',
                       help='Output only book IDs (one per line)')
    parser.add_argument('--db-path', default='./data/lancedb',
                       help='Path to LanceDB database')

    args = parser.parse_args()

    books = find_books_missing_labels(args.db_path)

    if args.ids_only:
        for book_id in books:
            print(book_id)
        return

    if args.json:
        print(json.dumps(books, indent=2, ensure_ascii=False))
        return

    # Human-readable output
    if not books:
        print("✅ All indexed books have proper page labels!")
        return

    print(f"\n📚 Found {len(books)} books needing page label re-indexing:\n")
    print("-" * 80)

    for book_id, stats in sorted(books.items(), key=lambda x: x[1]['indexed_at']):
        print(f"📖 {stats['book_title']}")
        if stats['author']:
            print(f"   Author: {stats['author']}")
        print(f"   Book ID: {book_id}")
        print(f"   Chunks: {stats['total_chunks']} ({stats['missing_labels']} missing labels)")
        print(f"   Indexed: {stats['indexed_at'][:10] if stats['indexed_at'] else 'Unknown'}")
        print()

    print("-" * 80)
    print(f"\n💡 To re-index these books, you can use:")
    print(f"   python scripts/batch_index.py --reindex-missing-labels")
    print(f"\n   Or re-index by date:")
    if books:
        earliest = min(s['indexed_at'][:10] for s in books.values() if s['indexed_at'])
        print(f"   python scripts/batch_index.py --reindex-before {earliest}")


if __name__ == '__main__':
    main()
