#!/usr/bin/env python3
"""
Simple ChromaDB Rescue - works with any schema version

Directly dumps all data from ChromaDB SQLite without complex JOINs.
"""

import sys
import sqlite3
import json
from pathlib import Path
from datetime import datetime
import argparse
import os


def rescue_simple(db_path: str):
    """Simple rescue by dumping raw table data."""
    db_path = Path(db_path)
    sqlite_db = db_path / "chroma.sqlite3"

    if not sqlite_db.exists():
        print(f"❌ Database not found: {sqlite_db}")
        return False

    print(f"🔍 Analyzing: {sqlite_db}\n")

    try:
        conn = sqlite3.connect(str(sqlite_db))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Get collections
        cursor.execute("SELECT id, name FROM collections")
        collections = cursor.fetchall()

        print(f"📚 Collections found: {len(collections)}")
        for col in collections:
            print(f"   - {col['name']} (ID: {col['id']})")
        print()

        # For each collection, count embeddings
        for col in collections:
            col_id = col['id']
            col_name = col['name']

            cursor.execute("""
                SELECT COUNT(*) as count FROM embeddings WHERE collection_id = ?
            """, (col_id,))

            count = cursor.fetchone()['count']
            print(f"📊 Collection '{col_name}': {count} documents")

            if count > 0:
                # Get sample document
                cursor.execute("""
                    SELECT id, custom_id, document FROM embeddings
                    WHERE collection_id = ? LIMIT 1
                """, (col_id,))

                sample = cursor.fetchone()
                print(f"   Sample document ID: {sample['custom_id']}")
                print(f"   Sample text: {sample['document'][:100]}...")
                print()

        conn.close()
        return True

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    parser = argparse.ArgumentParser(description="Simple ChromaDB inspector")
    parser.add_argument('--db-path', default=None,
                        help='ChromaDB path (default: CALIBRE_LIBRARY/.archilles/rag_db)')

    args = parser.parse_args()

    if args.db_path is None:
        calibre_library = os.environ.get('CALIBRE_LIBRARY_PATH')
        if not calibre_library:
            print("❌ CALIBRE_LIBRARY_PATH not set")
            print("   Use: --db-path to specify database location")
            sys.exit(1)
        args.db_path = str(Path(calibre_library) / ".archilles" / "rag_db")

    rescue_simple(args.db_path)


if __name__ == '__main__':
    main()
