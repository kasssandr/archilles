#!/usr/bin/env python3
"""
Diagnostic script to check RAG index status and contents.

Shows:
- Which ChromaDB path is being used
- Which collection name is being used
- How many chunks are indexed
- List of all indexed books with chunk counts
"""

import sys
from pathlib import Path
import chromadb
from collections import Counter

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

def check_rag_index(db_path: str = None):
    """Check RAG index and show statistics."""

    # Use default path if not specified
    if db_path is None:
        db_path = "./archilles_rag_db"

    db_path = Path(db_path).resolve()

    print("=" * 80)
    print("ARCHILLES RAG INDEX DIAGNOSTIC")
    print("=" * 80)
    print(f"\n📁 Database Path: {db_path}")
    print(f"   Exists: {db_path.exists()}")

    if not db_path.exists():
        print("\n❌ ERROR: Database path does not exist!")
        print(f"   Please check if books have been indexed to this location.")
        return

    # Initialize ChromaDB
    try:
        chroma_client = chromadb.PersistentClient(path=str(db_path))
        print(f"   ✓ ChromaDB client connected")
    except Exception as e:
        print(f"\n❌ ERROR: Failed to connect to ChromaDB: {e}")
        return

    # Get collection
    collection_name = "archilles_books"
    try:
        collection = chroma_client.get_collection(name=collection_name)
        print(f"\n📚 Collection: '{collection_name}'")
    except Exception as e:
        print(f"\n❌ ERROR: Collection '{collection_name}' not found!")
        print(f"   Error: {e}")
        print(f"\n   Available collections:")
        for coll in chroma_client.list_collections():
            print(f"   - {coll.name}")
        return

    # Get collection stats
    try:
        count = collection.count()
        print(f"   Total chunks: {count:,}")

        if count == 0:
            print(f"\n⚠️  Collection is empty! No books have been indexed yet.")
            return

        # Get all metadata to analyze books
        print(f"\n🔍 Fetching chunk metadata...")
        results = collection.get(
            limit=count,
            include=['metadatas']
        )

        # Count books
        book_ids = [meta.get('book_id', 'unknown') for meta in results['metadatas']]
        book_counter = Counter(book_ids)

        print(f"\n📖 Indexed Books ({len(book_counter)} total):")
        print(f"{'Book ID':<50} {'Chunks':>10}")
        print("-" * 80)

        for book_id, chunk_count in sorted(book_counter.items(), key=lambda x: x[1], reverse=True):
            print(f"{book_id:<50} {chunk_count:>10,}")

        # Show some sample metadata
        print(f"\n📝 Sample Metadata (first book):")
        sample_meta = results['metadatas'][0]
        for key, value in sorted(sample_meta.items()):
            if isinstance(value, str) and len(value) > 100:
                value = value[:100] + "..."
            print(f"   {key}: {value}")

        # Check BM25 index
        print(f"\n🔎 BM25 Keyword Index:")
        bm25_path = db_path / "bm25_index.pkl"
        if bm25_path.exists():
            import pickle
            try:
                with open(bm25_path, 'rb') as f:
                    bm25_data = pickle.load(f)
                print(f"   ✓ BM25 index exists")
                print(f"   Documents in BM25: {len(bm25_data.get('doc_ids', []))}")
            except Exception as e:
                print(f"   ⚠️  BM25 index exists but failed to load: {e}")
        else:
            print(f"   ⚠️  BM25 index not found (will be rebuilt on first search)")

        print(f"\n" + "=" * 80)
        print("✅ Diagnostic complete!")
        print("=" * 80)

    except Exception as e:
        print(f"\n❌ ERROR: Failed to analyze collection: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='Check ARCHILLES RAG index status')
    parser.add_argument(
        '--db-path',
        type=str,
        default=None,
        help='Path to RAG database (default: ./archilles_rag_db)'
    )

    args = parser.parse_args()

    check_rag_index(args.db_path)
