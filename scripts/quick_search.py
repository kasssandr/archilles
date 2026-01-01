#!/usr/bin/env python3
"""
Quick search test for ARCHILLES indexed data
Usage: python scripts/quick_search.py "your query here"
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.rag_demo import archillesRAG
import os

def main():
    # Get query from command line or use default
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
    else:
        query = "Arendt Totalitarismus"
        print(f"ℹ️  No query provided, using default: '{query}'\n")

    # Get Calibre library path
    library_path = os.getenv('CALIBRE_LIBRARY')
    if not library_path:
        print("❌ CALIBRE_LIBRARY environment variable not set")
        sys.exit(1)

    db_path = str(Path(library_path) / ".archilles" / "rag_db")

    print(f"📚 Loading RAG database from: {db_path}\n")

    # Initialize RAG
    try:
        rag = archillesRAG(db_path=db_path)
    except Exception as e:
        print(f"❌ Error loading database: {e}")
        sys.exit(1)

    # Show collection stats
    total_chunks = rag.collection.count()
    print(f"✅ Database loaded: {total_chunks} chunks indexed\n")

    # Test search
    print(f"🔍 Searching for: '{query}'\n")

    results = rag.search(query, top_k=5)

    if not results:
        print("❌ No results found")
        return

    print(f"Found {len(results)} results:\n")
    print("="*70)

    for i, result in enumerate(results, 1):
        print(f"\n[{i}] {result.get('book_title', 'Unknown')}")
        if result.get('author'):
            print(f"    Author: {result['author']}")
        if result.get('tags'):
            print(f"    Tags: {result['tags']}")
        if result.get('chunk_type'):
            print(f"    Type: {result['chunk_type']}")
        print(f"    Score: {result.get('score', 0):.4f}")

        # Show snippet
        text = result.get('text', '')
        snippet = text[:300] + "..." if len(text) > 300 else text
        print(f"\n    {snippet}")
        print("-"*70)

    print(f"\n✅ Search complete!")

if __name__ == '__main__':
    main()
