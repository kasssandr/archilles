#!/usr/bin/env python3
"""
Show information about the current RAG index.

Displays:
- Embedding model used
- Index statistics
- Collection metadata
- Session information

Usage:
    python scripts/show_index_info.py
    python scripts/show_index_info.py --db-path /path/to/rag_db
"""

import sys
import argparse
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import chromadb


def main():
    parser = argparse.ArgumentParser(
        description='Show RAG index information',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('--db-path', help='Database path (default: CALIBRE_LIBRARY/.archilles/rag_db)')
    args = parser.parse_args()

    # Determine database path
    if args.db_path is None:
        calibre_library = os.environ.get('CALIBRE_LIBRARY_PATH')
        if not calibre_library:
            print("ERROR: CALIBRE_LIBRARY_PATH not set and --db-path not provided")
            print("\nSet the environment variable:")
            print('  Windows: $env:CALIBRE_LIBRARY_PATH = "D:\\Calibre-Bibliothek"')
            print('  Linux:   export CALIBRE_LIBRARY_PATH="/path/to/library"')
            sys.exit(1)
        db_path = str(Path(calibre_library) / ".archilles" / "rag_db")
    else:
        db_path = args.db_path

    print("=" * 70)
    print("📚 ARCHILLES RAG INDEX INFORMATION")
    print("=" * 70)
    print(f"\n📂 Database path: {db_path}\n")

    # Check if path exists
    if not Path(db_path).exists():
        print(f"❌ ERROR: Database not found at {db_path}\n")
        sys.exit(1)

    try:
        # Connect to ChromaDB
        client = chromadb.PersistentClient(path=db_path)
        collections = client.list_collections()

        if not collections:
            print("⚠️  No collections found in database\n")
            sys.exit(0)

        # Show each collection
        for coll in collections:
            print(f"📖 Collection: {coll.name}")
            print("-" * 70)

            # Collection metadata
            if coll.metadata:
                print("\n  📋 Collection Metadata:")
                for key, value in coll.metadata.items():
                    print(f"    • {key}: {value}")

            # Count and sample metadata
            count = coll.count()
            print(f"\n  📊 Statistics:")
            print(f"    • Total chunks: {count:,}")

            if count > 0:
                # Get sample to determine metadata structure
                sample = coll.get(limit=min(100, count), include=['metadatas'])

                if sample and sample['metadatas']:
                    # Analyze metadata structure
                    metadata_keys = set()
                    embedding_models = set()
                    chunk_types = set()
                    languages = set()
                    books = set()

                    for meta in sample['metadatas']:
                        if meta:
                            metadata_keys.update(meta.keys())
                            if 'embedding_model' in meta:
                                embedding_models.add(meta['embedding_model'])
                            if 'chunk_type' in meta:
                                chunk_types.add(meta['chunk_type'])
                            if 'language' in meta:
                                languages.add(meta['language'])
                            if 'book_id' in meta:
                                books.add(meta['book_id'])

                    print(f"\n  🔧 Index Configuration:")
                    if embedding_models:
                        print(f"    • Embedding model(s): {', '.join(embedding_models)}")
                    else:
                        print(f"    • Embedding model: Not recorded (likely BAAI/bge-m3)")

                    print(f"\n  📚 Content:")
                    print(f"    • Books indexed: {len(books)}")
                    if chunk_types:
                        print(f"    • Chunk types: {', '.join(chunk_types)}")
                    if languages:
                        lang_list = sorted(languages)
                        print(f"    • Languages: {', '.join(lang_list)}")

                    print(f"\n  🏷️  Available metadata fields:")
                    for key in sorted(metadata_keys):
                        print(f"    • {key}")

            print("\n" + "=" * 70 + "\n")

    except Exception as e:
        print(f"❌ ERROR: {e}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
