#!/usr/bin/env python3
"""
Explore ChromaDB schema to find where documents are stored
"""

import sqlite3
import os
from pathlib import Path

# Get library path
library_path = os.getenv('CALIBRE_LIBRARY')
if not library_path:
    print("❌ CALIBRE_LIBRARY not set")
    exit(1)

db_path = Path(library_path) / ".archilles" / "rag_db" / "chroma.sqlite3"

if not db_path.exists():
    print(f"❌ Database not found at: {db_path}")
    exit(1)

print(f"📊 Exploring ChromaDB schema at: {db_path}\n")

# Connect to SQLite
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Get all tables
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = [t[0] for t in cursor.fetchall()]

for table_name in tables:
    if table_name.startswith('sqlite_'):
        continue

    print(f"\n{'='*70}")
    print(f"TABLE: {table_name}")
    print(f"{'='*70}")

    # Get schema
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = cursor.fetchall()
    print("Columns:")
    for col in columns:
        print(f"  - {col[1]:20s} {col[2]:15s} {('NOT NULL' if col[3] else '')}")

    # Get row count
    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
    count = cursor.fetchone()[0]
    print(f"\nRow count: {count}")

    # Show sample data if not too many rows
    if count > 0 and count < 10:
        cursor.execute(f"SELECT * FROM {table_name} LIMIT 5")
        rows = cursor.fetchall()
        print(f"\nSample data:")
        for row in rows:
            print(f"  {row}")
    elif count > 0:
        cursor.execute(f"SELECT * FROM {table_name} LIMIT 2")
        rows = cursor.fetchall()
        print(f"\nFirst 2 rows:")
        for row in rows:
            # Truncate long values
            truncated = []
            for val in row:
                if isinstance(val, str) and len(val) > 50:
                    truncated.append(val[:50] + "...")
                elif isinstance(val, bytes):
                    truncated.append(f"<bytes: {len(val)} bytes>")
                else:
                    truncated.append(val)
            print(f"  {truncated}")

conn.close()

print(f"\n{'='*70}")
print("RECOMMENDATIONS:")
print(f"{'='*70}")
print("""
Look for tables that might contain document text:
- Tables with 'string_value' or 'document' or 'text' columns
- Tables with metadata about books
- Full-text search tables (embedding_fulltext_search*)

The actual document text is likely in one of:
- embedding_metadata (if stored as metadata)
- embedding_fulltext_search tables (for full-text indexing)
- Or accessed through ChromaDB's collection.get() API
""")
