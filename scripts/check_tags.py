#!/usr/bin/env python3
"""
Check where "lehen" appears: in document text vs. tags/metadata
"""

import os
import sys
from pathlib import Path

try:
    import chromadb
    from chromadb.config import Settings
except ImportError:
    print("❌ chromadb package not installed")
    sys.exit(1)

# Get library path
library_path = os.getenv('CALIBRE_LIBRARY')
if not library_path:
    print("❌ CALIBRE_LIBRARY not set")
    sys.exit(1)

db_path = str(Path(library_path) / ".archilles" / "rag_db")

print(f"📊 Checking where 'lehen' appears...\n")

# Initialize ChromaDB client
client = chromadb.PersistentClient(
    path=db_path,
    settings=Settings(anonymized_telemetry=False)
)

collection = client.get_collection("archilles_books")

# Get all documents
all_data = collection.get(include=['documents', 'metadatas'])

print(f"Total chunks: {len(all_data['ids'])}\n")

# Track where "lehen" appears
lehen_in_text = []
lehen_in_tags = []
lehen_in_title = []

for doc_id, document, metadata in zip(all_data['ids'], all_data['documents'], all_data['metadatas']):
    if document is None:
        continue

    doc_lower = document.lower()
    book_title = metadata.get('book_title', 'Unknown')
    tags = metadata.get('tags', '')

    # Check document text
    if 'lehen' in doc_lower:
        lehen_in_text.append({
            'title': book_title,
            'author': metadata.get('author', 'N/A'),
            'chunk_type': metadata.get('chunk_type', 'unknown'),
            'tags': tags
        })

    # Check tags
    if tags and 'lehen' in tags.lower():
        lehen_in_tags.append({
            'title': book_title,
            'author': metadata.get('author', 'N/A'),
            'chunk_type': metadata.get('chunk_type', 'unknown'),
            'tags': tags
        })

    # Check title
    if 'lehen' in book_title.lower():
        lehen_in_title.append({
            'title': book_title,
            'author': metadata.get('author', 'N/A'),
            'chunk_type': metadata.get('chunk_type', 'unknown'),
            'tags': tags
        })

print("="*70)
print("WHERE 'LEHEN' APPEARS:")
print("="*70)

print(f"\n1️⃣  IN DOCUMENT TEXT: {len(set(b['title'] for b in lehen_in_text))} unique books")
if lehen_in_text:
    unique_books = {}
    for book in lehen_in_text:
        if book['title'] not in unique_books:
            unique_books[book['title']] = book

    for title, book in unique_books.items():
        print(f"   • {title}")
        print(f"     Author: {book['author']}")
        print(f"     Chunk type: {book['chunk_type']}")

print(f"\n2️⃣  IN TAGS: {len(set(b['title'] for b in lehen_in_tags))} unique books")
if lehen_in_tags:
    unique_books = {}
    for book in lehen_in_tags:
        if book['title'] not in unique_books:
            unique_books[book['title']] = book

    for title, book in unique_books.items():
        print(f"   • {title}")
        print(f"     Author: {book['author']}")
        print(f"     Tags: {book['tags'][:200]}")

print(f"\n3️⃣  IN BOOK TITLE: {len(set(b['title'] for b in lehen_in_title))} unique books")
if lehen_in_title:
    unique_books = {}
    for book in lehen_in_title:
        if book['title'] not in unique_books:
            unique_books[book['title']] = book

    for title, book in unique_books.items():
        print(f"   • {title}")
        print(f"     Author: {book['author']}")

print(f"\n{'='*70}")
print("CONCLUSION:")
print(f"{'='*70}")

print(f"""
The BM25 keyword index searches in ENRICHED documents that include:
  - Original document text
  - Tags (appended as [TAGS: ...])
  - Book title (appended as [TITLE: ...])
  - Author name (appended as [AUTHOR: ...])

This is WHY your keyword search for "lehen" returned books that don't
contain "lehen" in the actual text - they have "lehen" in their tags!

This is intentional (helps find books by tags), but can be confusing.

CHECK YOUR QUICK_SEARCH RESULTS:
Look at the tags for "Border Lines", "Ethnic Identity", etc.
Do they contain "Lehen" or related terms?
""")
