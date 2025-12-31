#!/usr/bin/env python3
"""
ChromaDB Data Rescue Script

Attempts to extract all documents and metadata from a corrupted ChromaDB
by directly accessing the SQLite database, bypassing the corrupted HNSW index.

Usage:
    python scripts/rescue_chromadb.py --db-path "D:\Calibre-Bibliothek\.archilles\rag_db"
"""

import sys
import sqlite3
import json
import pickle
from pathlib import Path
from datetime import datetime
import argparse
import os


def rescue_chromadb(db_path: str, output_dir: str = None):
    """
    Rescue data from corrupted ChromaDB by direct SQLite access.

    Args:
        db_path: Path to ChromaDB directory
        output_dir: Directory to save rescued data (default: db_path/rescue_TIMESTAMP)
    """
    db_path = Path(db_path)

    # Check if database exists
    sqlite_db = db_path / "chroma.sqlite3"
    if not sqlite_db.exists():
        print(f"❌ ChromaDB SQLite file not found: {sqlite_db}")
        print(f"   Expected location: {db_path}/chroma.sqlite3")
        return False

    print(f"🔍 Attempting to rescue data from: {db_path}")
    print(f"   SQLite DB: {sqlite_db}")
    print()

    # Create output directory
    if output_dir is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = db_path / f"rescue_{timestamp}"
    else:
        output_dir = Path(output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"💾 Rescue data will be saved to: {output_dir}\n")

    try:
        # Connect directly to SQLite database
        conn = sqlite3.connect(str(sqlite_db))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Get collection info
        print("📊 Analyzing database...")
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        print(f"   Found tables: {', '.join(tables)}\n")

        # Get collections
        cursor.execute("SELECT * FROM collections")
        collections = cursor.fetchall()

        if not collections:
            print("❌ No collections found in database")
            conn.close()
            return False

        print(f"📚 Found {len(collections)} collection(s):")
        for col in collections:
            print(f"   - {col['name']} (ID: {col['id']})")
        print()

        # For each collection, extract embeddings
        total_rescued = 0

        for collection in collections:
            collection_id = collection['id']
            collection_name = collection['name']

            print(f"🔄 Rescuing collection: {collection_name}")

            # Get embeddings (documents + metadata)
            cursor.execute("""
                SELECT
                    e.id,
                    e.embedding,
                    e.document,
                    e.custom_id,
                    GROUP_CONCAT(mk.key || '=' || COALESCE(ms.string_value,
                                                           CAST(mi.int_value AS TEXT),
                                                           CAST(mf.float_value AS TEXT),
                                                           CAST(mb.bool_value AS TEXT)), '|||') as metadata
                FROM embeddings e
                LEFT JOIN embedding_metadata em ON e.id = em.id
                LEFT JOIN metadata_keys mk ON em.key_id = mk.id
                LEFT JOIN metadata_str ms ON em.id = ms.id AND em.key_id = ms.key_id
                LEFT JOIN metadata_int mi ON em.id = mi.id AND em.key_id = mi.key_id
                LEFT JOIN metadata_float mf ON em.id = mf.id AND em.key_id = mf.key_id
                LEFT JOIN metadata_bool mb ON em.id = mb.id AND em.key_id = mb.key_id
                WHERE e.collection_id = ?
                GROUP BY e.id
            """, (collection_id,))

            embeddings = cursor.fetchall()

            print(f"   Found {len(embeddings)} documents")

            if not embeddings:
                print(f"   ⚠️  No documents in this collection")
                continue

            # Convert to list of dicts
            rescued_data = []
            book_ids = set()

            for emb in embeddings:
                # Parse metadata
                metadata = {}
                if emb['metadata']:
                    for pair in emb['metadata'].split('|||'):
                        if '=' in pair:
                            key, value = pair.split('=', 1)
                            metadata[key] = value

                # Track unique books
                if 'book_id' in metadata:
                    book_ids.add(metadata['book_id'])

                rescued_data.append({
                    'id': emb['custom_id'],
                    'document': emb['document'],
                    'metadata': metadata,
                    'embedding': None  # Don't save embeddings (will be regenerated)
                })

            # Save to JSON
            output_file = output_dir / f"{collection_name}_rescued.json"
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump({
                    'collection_name': collection_name,
                    'total_documents': len(rescued_data),
                    'unique_books': len(book_ids),
                    'rescued_at': datetime.now().isoformat(),
                    'documents': rescued_data
                }, f, indent=2, ensure_ascii=False)

            print(f"   ✅ Saved {len(rescued_data)} documents to: {output_file}")
            print(f"   📚 Unique books rescued: {len(book_ids)}")

            # Also save a summary of books
            if book_ids:
                book_summary = {}
                for doc in rescued_data:
                    book_id = doc['metadata'].get('book_id')
                    if book_id:
                        if book_id not in book_summary:
                            book_summary[book_id] = {
                                'book_id': book_id,
                                'title': doc['metadata'].get('book_title', 'Unknown'),
                                'author': doc['metadata'].get('author', 'Unknown'),
                                'chunks': 0,
                                'indexed_at': doc['metadata'].get('indexed_at', 'Unknown'),
                                'format': doc['metadata'].get('format', 'Unknown')
                            }
                        book_summary[book_id]['chunks'] += 1

                summary_file = output_dir / f"{collection_name}_books.json"
                with open(summary_file, 'w', encoding='utf-8') as f:
                    json.dump(list(book_summary.values()), f, indent=2, ensure_ascii=False)

                print(f"   📋 Book summary saved to: {summary_file}\n")

            total_rescued += len(rescued_data)

        conn.close()

        # Final summary
        print(f"\n{'='*60}")
        print(f"✅ RESCUE COMPLETE!")
        print(f"{'='*60}")
        print(f"  Total documents rescued: {total_rescued:,}")
        print(f"  Saved to: {output_dir}")
        print(f"{'='*60}\n")

        print("📝 Next steps:")
        print("1. Verify the rescued data in the JSON files")
        print("2. If data looks good, you can safely reset the database:")
        print(f"   python scripts/batch_index.py --tag YourTag --reset-db")
        print("3. Note: You'll need to re-index books (embeddings can't be rescued)")
        print("   But at least you have a backup of what was indexed!\n")

        return True

    except Exception as e:
        print(f"❌ Error during rescue: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Rescue data from corrupted ChromaDB",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Rescue data from default location
  python scripts/rescue_chromadb.py

  # Rescue from specific database
  python scripts/rescue_chromadb.py --db-path "D:\\Calibre-Bibliothek\\.archilles\\rag_db"

  # Save to custom location
  python scripts/rescue_chromadb.py --output "D:\\chromadb_backup"
        """
    )

    parser.add_argument('--db-path', default=None,
                        help='ChromaDB path (default: CALIBRE_LIBRARY/.archilles/rag_db)')
    parser.add_argument('--output', default=None,
                        help='Output directory for rescued data (default: db-path/rescue_TIMESTAMP)')

    args = parser.parse_args()

    # Determine database path
    if args.db_path is None:
        calibre_library = os.environ.get('CALIBRE_LIBRARY_PATH')
        if not calibre_library:
            print("\n" + "="*60)
            print("ERROR: CALIBRE_LIBRARY_PATH not set")
            print("="*60 + "\n")
            print("Please set the environment variable OR use --db-path:\n")
            print("  Windows (PowerShell):")
            print('    $env:CALIBRE_LIBRARY_PATH = "C:\\path\\to\\Calibre-Library"')
            print('    python scripts/rescue_chromadb.py\n')
            print("  OR specify path directly:")
            print('    python scripts/rescue_chromadb.py --db-path "D:\\Calibre-Bibliothek\\.archilles\\rag_db"\n')
            sys.exit(1)
        args.db_path = str(Path(calibre_library) / ".archilles" / "rag_db")

    # Attempt rescue
    success = rescue_chromadb(args.db_path, args.output)

    if not success:
        print("\n⚠️  Rescue failed. Your data may be unrecoverable.")
        print("   You may need to use --reset-db and re-index everything.\n")
        sys.exit(1)


if __name__ == '__main__':
    main()
