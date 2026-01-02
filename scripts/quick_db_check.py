#!/usr/bin/env python3
"""
Quick diagnostic using direct SQLite access to ChromaDB
No heavy dependencies needed!
"""

import sqlite3
import json
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

print(f"📊 Analyzing ChromaDB at: {db_path}\n")

# Connect to SQLite
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# First, let's see what tables exist
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = cursor.fetchall()
print("Available tables:", [t[0] for t in tables])

# Check schema of embeddings table
cursor.execute("PRAGMA table_info(embeddings)")
columns = cursor.fetchall()
print("\nEmbeddings table schema:")
for col in columns:
    print(f"  - {col[1]} ({col[2]})")
print()

# Get all documents with metadata
# ChromaDB stores documents in the 'embeddings' table with 'string_value' column
cursor.execute("""
SELECT e.id, e.string_value, m.string_value as metadata
FROM embeddings e
LEFT JOIN embedding_metadata m ON e.id = m.id AND m.key = 'metadata'
WHERE e.string_value IS NOT NULL
""")

rows = cursor.fetchall()
print(f"Total documents in database: {len(rows)}\n")

# Search for German medieval terms
search_terms = {
    'mittelalter': [],  # Middle Ages
    'adel': [],         # Nobility
    'vasallen': [],     # Vassals
    'lehen': [],        # Fiefs
    'feudal': []        # Feudal
}

chunk_types = {}

for doc_id, document, metadata_json in rows:
    if document is None:
        continue

    doc_lower = document.lower()

    # Parse metadata
    try:
        metadata = json.loads(metadata_json) if metadata_json else {}
    except:
        metadata = {}

    chunk_type = metadata.get('chunk_type', 'unknown')
    chunk_types[chunk_type] = chunk_types.get(chunk_type, 0) + 1

    # Check for terms
    for term in search_terms.keys():
        if term in doc_lower:
            search_terms[term].append({
                'title': metadata.get('book_title', 'Unknown'),
                'author': metadata.get('author', 'N/A'),
                'chunk_type': chunk_type,
                'snippet': document[:200] if term in document[:200].lower() else f"...{document[max(0, doc_lower.find(term)-50):doc_lower.find(term)+100]}..."
            })

print("="*70)
print("CHUNK TYPE DISTRIBUTION:")
print("="*70)
for chunk_type, count in sorted(chunk_types.items()):
    print(f"{chunk_type:20s}: {count:4d} chunks")

print(f"\n{'='*70}")
print("GERMAN MEDIEVAL TERMS IN DOCUMENTS:")
print(f"{'='*70}\n")

for term, matches in search_terms.items():
    print(f"📖 '{term}': Found in {len(matches)} chunks")
    if matches:
        # Show unique books
        unique_books = {}
        for match in matches:
            book_title = match['title']
            if book_title not in unique_books:
                unique_books[book_title] = match

        print(f"   Unique books: {len(unique_books)}")
        for title, match in list(unique_books.items())[:5]:
            print(f"   • {title} [{match['chunk_type']}]")
            if match['author'] != 'N/A':
                print(f"     Author: {match['author']}")

        if len(unique_books) > 5:
            print(f"   ... and {len(unique_books) - 5} more books")
    print()

conn.close()

print("="*70)
print("CONCLUSION:")
print("="*70)
print("""
If terms are found in the data but not appearing in semantic search:
- BGE-M3 embeddings may not capture German domain-specific terminology
- Consider using keyword-only or hybrid search for these terms
- Or filter search to specific chunk_types (e.g., phase1_metadata)
""")
