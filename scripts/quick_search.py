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
from scripts.snippet_extractor import extract_context_snippet, highlight_terms
import os

def main():
    # Parse command line arguments
    # Usage: python quick_search.py "query" [mode] [top_k]
    if len(sys.argv) < 2:
        query = "Arendt Totalitarismus"
        mode = "hybrid"
        top_k = 5
        print(f"ℹ️  No query provided, using default: '{query}'\n")
    else:
        query = sys.argv[1]
        mode = sys.argv[2] if len(sys.argv) > 2 else "hybrid"
        top_k = int(sys.argv[3]) if len(sys.argv) > 3 else 5

        # Validate mode
        if mode not in ['semantic', 'keyword', 'hybrid']:
            print(f"❌ Invalid mode: {mode}")
            print("   Valid modes: semantic, keyword, hybrid")
            sys.exit(1)

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

    # Test search with specified mode
    print(f"🔍 Searching for: '{query}' (mode: {mode}, top_k: {top_k})\n")

    results = rag.query(query, top_k=top_k, mode=mode)

    if not results:
        print("❌ No results found")
        return

    print(f"Found {len(results)} results:\n")
    print("="*70)

    # Extract query terms for context snippets
    query_terms = query.split()

    for i, result in enumerate(results, 1):
        # Extract metadata from nested dict
        metadata = result.get('metadata', {})

        print(f"\n[{i}] {metadata.get('book_title', 'Unknown')}")
        if metadata.get('author'):
            print(f"    Author: {metadata['author']}")
        if metadata.get('tags'):
            print(f"    Tags: {metadata['tags']}")
        if metadata.get('year'):
            print(f"    Year: {metadata['year']}")
        if metadata.get('chunk_type'):
            print(f"    Type: {metadata['chunk_type']}")
        print(f"    Score: {result.get('score', 0):.4f}")

        # Extract relevant context snippet
        text = result.get('text', '')
        snippet, found_terms = extract_context_snippet(text, query_terms, context_chars=200)

        # Highlight found terms
        if found_terms:
            snippet = highlight_terms(snippet, found_terms)
            print(f"    Matched: {', '.join(found_terms)}")

        print(f"\n    {snippet}")
        print("-"*70)

    print(f"\n✅ Search complete!")

if __name__ == '__main__':
    main()
