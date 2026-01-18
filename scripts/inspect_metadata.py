#!/usr/bin/env python3
"""Quick script to inspect metadata for specific chunks."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.rag_demo import archillesRAG

def inspect_book_metadata(book_id: str, limit: int = 5):
    """Show metadata for a few chunks from a specific book."""
    rag = archillesRAG()
    print(f"📂 Database: {rag.db_path}")
    print(f"📊 Total chunks in index: {rag.collection.count()}")

    # Query chunks for this book
    where_clause = None
    if book_id.isdigit():
        # Numeric ID - try both calibre_id formats
        where_clause = {
            '$or': [
                {'calibre_id': int(book_id)},
                {'calibre_id': book_id}
            ]
        }
    else:
        where_clause = {'book_id': book_id}

    results = rag.collection.get(
        where=where_clause,
        limit=limit
    )

    print(f"\n📚 Showing {len(results['ids'])} chunks from book {book_id}\n")

    for i, (chunk_id, metadata) in enumerate(zip(results['ids'], results['metadatas']), 1):
        print(f"{'='*80}")
        print(f"Chunk {i}: {chunk_id[:50]}...")
        print(f"{'='*80}")

        # Key fields to check
        print(f"Book ID: {metadata.get('book_id', 'N/A')}")
        print(f"Calibre ID: {metadata.get('calibre_id', 'N/A')}")
        print(f"Title: {metadata.get('book_title', 'N/A')}")
        print(f"Chapter: {metadata.get('chapter', 'N/A')}")
        print(f"Section: {metadata.get('section', 'N/A')}")
        print(f"Section Title: {metadata.get('section_title', 'N/A')}")
        print(f"Section Type: {metadata.get('section_type', 'N/A')}")
        print(f"Chunk Type: {metadata.get('chunk_type', 'N/A')}")
        print(f"Page: {metadata.get('page', 'N/A')}")
        print(f"Indexed At: {metadata.get('indexed_at', 'N/A')}")
        print()

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Inspect metadata for a book')
    parser.add_argument('book_id', help='Book ID or Calibre ID to inspect')
    parser.add_argument('--limit', type=int, default=5, help='Number of chunks to show')

    args = parser.parse_args()
    inspect_book_metadata(args.book_id, args.limit)
