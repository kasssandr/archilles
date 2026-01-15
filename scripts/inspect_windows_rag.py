#!/usr/bin/env python3
"""
Quick script to inspect your Windows RAG database.

Run this on Windows PowerShell:
    cd C:\Users\tomra\archilles
    $env:RAG_DB_PATH = "D:\Calibre-Bibliothek\.archilles\rag_db"
    python scripts/inspect_windows_rag.py

This will show you what's in your RAG database.
"""

import sys
import os
from pathlib import Path
import json

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

def main():
    # Get RAG DB path
    rag_db_path = os.getenv('RAG_DB_PATH', r'D:\Calibre-Bibliothek\.archilles\rag_db')

    print("=" * 60)
    print("ARCHILLES RAG DATABASE INSPECTOR")
    print("=" * 60)
    print(f"\n📂 Database Location: {rag_db_path}\n")

    # Check if path exists
    db_path = Path(rag_db_path)
    if not db_path.exists():
        print(f"❌ ERROR: Database not found at {rag_db_path}")
        print("\nPossible locations to check:")
        print("  - D:\\Calibre-Bibliothek\\.archilles\\rag_db")
        print("  - C:\\Users\\tomra\\archilles\\archilles_rag_db")
        print("  - ./archilles_rag_db")
        return 1

    print("✅ Database directory exists!\n")

    # List contents
    print("📋 Database Contents:")
    print("-" * 60)

    files = list(db_path.iterdir())
    total_size = 0

    for item in sorted(files):
        if item.is_file():
            size = item.stat().st_size
            total_size += size
            size_mb = size / 1024 / 1024
            print(f"  📄 {item.name:<30} {size_mb:>8.2f} MB")
        elif item.is_dir():
            # Count files in directory
            num_files = len(list(item.rglob('*')))
            print(f"  📁 {item.name:<30} ({num_files} files)")

    print("-" * 60)
    print(f"💾 Total size: {total_size / 1024 / 1024:.2f} MB\n")

    # Check for ChromaDB
    chroma_db = db_path / "chroma.sqlite3"
    if chroma_db.exists():
        print("✅ ChromaDB database found (chroma.sqlite3)")

        try:
            import chromadb
            print("  🔍 Attempting to read ChromaDB...")

            client = chromadb.PersistentClient(path=str(db_path))
            collections = client.list_collections()

            print(f"\n📚 Collections ({len(collections)}):")
            for coll in collections:
                print(f"\n  Collection: {coll.name}")
                count = coll.count()
                print(f"    • Chunks: {count}")

                # Get sample metadata
                if count > 0:
                    results = coll.get(limit=1, include=['metadatas'])
                    if results and results['metadatas']:
                        metadata = results['metadatas'][0]
                        print(f"    • Sample metadata keys: {', '.join(metadata.keys())}")

                        # Show book_id if available
                        if 'book_id' in metadata:
                            print(f"    • Book ID: {metadata['book_id']}")
                        if 'language' in metadata:
                            print(f"    • Language: {metadata['language']}")
                        if 'page' in metadata:
                            print(f"    • Page info available: Yes")

        except ImportError:
            print("  ⚠️  chromadb not installed - can't read contents")
            print("  Run: pip install chromadb")
        except Exception as e:
            print(f"  ⚠️  Error reading ChromaDB: {e}")

    # Check for BM25 index
    bm25_index = db_path / "bm25_index.pkl"
    if bm25_index.exists():
        print(f"\n✅ BM25 keyword search index found ({bm25_index.stat().st_size / 1024:.1f} KB)")

    # Check for metadata
    metadata_file = db_path / "index_metadata.json"
    if metadata_file.exists():
        print(f"\n✅ Index metadata found")
        try:
            with open(metadata_file, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
                print(f"  📋 Metadata preview:")
                for key, value in list(metadata.items())[:5]:
                    print(f"    • {key}: {value}")
        except Exception as e:
            print(f"  ⚠️  Could not read metadata: {e}")

    print("\n" + "=" * 60)
    print("✨ Inspection complete!")
    print("=" * 60)

    return 0

if __name__ == "__main__":
    sys.exit(main())
