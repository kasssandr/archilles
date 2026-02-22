#!/usr/bin/env python3
"""
Analyze chunk type distribution and optionally test queries against different chunk types.

Usage:
    # Show chunk distribution only
    python scripts/analyze_chunks.py

    # Test a query across chunk types
    python scripts/analyze_chunks.py "Totalitarismus"
"""

import os
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.rag_demo import archillesRAG


def get_db_path() -> str:
    """Resolve the RAG database path from environment."""
    library_path = os.getenv('CALIBRE_LIBRARY')
    if not library_path:
        print("CALIBRE_LIBRARY not set")
        sys.exit(1)
    return str(Path(library_path) / ".archilles" / "rag_db")


def analyze_distribution(rag: archillesRAG) -> None:
    """Print chunk type distribution across all indexed books."""
    all_data = rag.collection.get()

    chunk_types = Counter()
    books_by_type: dict[str, set[str]] = {}

    for metadata in all_data['metadatas']:
        chunk_type = metadata.get('chunk_type', 'unknown')
        book_id = metadata.get('book_id', 'unknown')

        chunk_types[chunk_type] += 1
        books_by_type.setdefault(chunk_type, set()).add(book_id)

    print("=" * 70)
    print("CHUNK TYPE DISTRIBUTION:")
    print("=" * 70)
    for chunk_type, count in chunk_types.most_common():
        num_books = len(books_by_type.get(chunk_type, set()))
        print(f"{chunk_type:20s}: {count:4d} chunks in {num_books} books")

    total_books = len(set(m.get('book_id') for m in all_data['metadatas']))
    print(f"\nTotal chunks: {len(all_data['ids'])}")
    print(f"Total unique books: {total_books}")


def test_query(rag: archillesRAG, query: str) -> None:
    """Run a test query and show results broken down by chunk type."""
    print(f"\n{'=' * 70}")
    print(f"TESTING QUERY: '{query}'")
    print(f"{'=' * 70}\n")

    print("Searching in ALL chunks...")
    results = rag.query(query, top_k=3, mode='hybrid')
    print(f"   Found {len(results)} results")
    for r in results[:3]:
        meta = r.get('metadata', {})
        print(f"   - {meta.get('book_title', 'Unknown')} [{meta.get('chunk_type', 'unknown')}]")

    print("\nSearching in CONTENT only...")
    content_results = [r for r in results if r.get('metadata', {}).get('chunk_type') == 'content']
    print(f"   Found {len(content_results)} content results")
    for r in content_results[:3]:
        meta = r.get('metadata', {})
        print(f"   - {meta.get('book_title', 'Unknown')}")

    print("\nSearching in METADATA only...")
    metadata_results = [r for r in results if r.get('metadata', {}).get('chunk_type') == 'phase1_metadata']
    print(f"   Found {len(metadata_results)} metadata results")
    for r in metadata_results[:3]:
        meta = r.get('metadata', {})
        print(f"   - {meta.get('book_title', 'Unknown')}")


def main() -> None:
    db_path = get_db_path()
    print("Analyzing chunk distribution...\n")
    rag = archillesRAG(db_path=db_path)

    analyze_distribution(rag)

    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
        test_query(rag, query)


if __name__ == '__main__':
    main()
