#!/usr/bin/env python3
"""Quick script to inspect metadata for specific chunks."""

import sys
import os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.rag_demo import archillesRAG

def inspect_book_metadata(book_id: str, limit: int = 5):
    """Show metadata for a few chunks from a specific book."""
    # Use same database path logic as main script
    calibre_library = os.environ.get('CALIBRE_LIBRARY_PATH')
    if calibre_library:
        db_path = str(Path(calibre_library) / ".archilles" / "rag_db")
        print(f"Using default RAG database: {db_path}")
    else:
        db_path = "./archilles_rag_db"
        print(f"WARNING: CALIBRE_LIBRARY_PATH not set, using local: {db_path}")

    rag = archillesRAG(db_path=db_path)
    print(f"Total chunks in index: {rag.store.count()}")

    # Query chunks for this book
    if book_id.isdigit():
        # Numeric ID - use calibre_id
        results = rag.store.get_by_calibre_id(int(book_id), limit=limit)
    else:
        # String ID - use book_id
        results = rag.store.get_by_book_id(book_id, limit=limit)

    print(f"\nShowing {len(results)} chunks from book {book_id}\n")

    for i, chunk in enumerate(results, 1):
        print(f"{'='*80}")
        print(f"Chunk {i}: {chunk.get('id', 'N/A')[:50]}...")
        print(f"{'='*80}")

        # Key fields to check
        print(f"Book ID: {chunk.get('book_id', 'N/A')}")
        print(f"Calibre ID: {chunk.get('calibre_id', 'N/A')}")
        print(f"Title: {chunk.get('book_title', 'N/A')}")
        print(f"Chapter: {chunk.get('chapter', 'N/A')}")
        print(f"Section: {chunk.get('section', 'N/A')}")
        print(f"Section Title: {chunk.get('section_title', 'N/A')}")
        print(f"Section Type: {chunk.get('section_type', 'N/A')}")
        print(f"Chunk Type: {chunk.get('chunk_type', 'N/A')}")
        print(f"Page: {chunk.get('page_number', 'N/A')}")
        print(f"Source File: {chunk.get('source_file', 'N/A')}")
        print(f"Indexed At: {chunk.get('indexed_at', 'N/A')}")
        print()

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Inspect metadata for a book')
    parser.add_argument('book_id', help='Book ID or Calibre ID to inspect')
    parser.add_argument('--limit', type=int, default=5, help='Number of chunks to show')

    args = parser.parse_args()
    inspect_book_metadata(args.book_id, args.limit)
