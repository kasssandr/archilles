#!/usr/bin/env python3
"""
Quick diagnostic using ChromaDB API
Minimal dependencies - just needs chromadb package
"""

import os
from pathlib import Path

try:
    import chromadb
    from chromadb.config import Settings
except ImportError:
    print("❌ chromadb package not installed")
    print("   Install with: pip install chromadb==0.4.22")
    exit(1)

# Get library path
library_path = os.getenv('CALIBRE_LIBRARY')
if not library_path:
    print("❌ CALIBRE_LIBRARY not set")
    exit(1)

db_path = str(Path(library_path) / ".archilles" / "rag_db")

if not Path(db_path).exists():
    print(f"❌ Database not found at: {db_path}")
    exit(1)

print(f"📊 Analyzing ChromaDB at: {db_path}\n")

# Initialize ChromaDB client
try:
    client = chromadb.PersistentClient(
        path=db_path,
        settings=Settings(anonymized_telemetry=False)
    )

    # Get the collection
    collection = client.get_collection("archilles_books")

    print(f"Collection loaded: {collection.count()} documents\n")

except Exception as e:
    print(f"❌ Error loading collection: {e}")
    exit(1)

# Get all documents
print("Fetching all documents...")
all_data = collection.get(include=['documents', 'metadatas'])

print(f"Retrieved {len(all_data['ids'])} documents\n")

# Search for German medieval terms
search_terms = {
    'mittelalter': [],  # Middle Ages
    'adel': [],         # Nobility
    'vasallen': [],     # Vassals
    'lehen': [],        # Fiefs
    'feudal': []        # Feudal
}

chunk_types = {}

for doc_id, document, metadata in zip(all_data['ids'], all_data['documents'], all_data['metadatas']):
    if document is None:
        continue

    doc_lower = document.lower()

    chunk_type = metadata.get('chunk_type', 'unknown')
    chunk_types[chunk_type] = chunk_types.get(chunk_type, 0) + 1

    # Check for terms
    for term in search_terms.keys():
        if term in doc_lower:
            search_terms[term].append({
                'id': doc_id,
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

print("="*70)
print("CONCLUSION:")
print("="*70)

# Calculate findings
total_with_terms = sum(len(set(m['title'] for m in matches)) for matches in search_terms.values())

if total_with_terms > 0:
    print(f"""
✅ Found {total_with_terms} unique books containing German medieval terms

DIAGNOSIS: The data exists in your ChromaDB!

This means your search for "Lehen" should have found these books.
The issue is likely:

1. **Semantic Search Problem**: BGE-M3 embeddings don't capture German
   domain-specific medieval legal terminology well enough

2. **Hybrid Search Weights**: The keyword component might be weighted too low

RECOMMENDED SOLUTIONS:

A. Use keyword-only search for German medieval terms:
   results = rag.query("Lehen", mode='keyword')

B. Filter to metadata chunks only (where comments are):
   # Search only in phase1_metadata chunks

C. Boost hybrid search keyword weight (if implemented)

D. Try compound queries:
   Search for: "Lehen OR mittelalter OR feudal"
""")
else:
    print("""
❌ No German medieval terms found in the database

This could mean:
1. The terms aren't in your Calibre comments
2. The books haven't been indexed yet (only {chunk_types.get('phase1_metadata', 0)} Phase 1 chunks)
3. The terms are spelled differently

Check your Calibre comments to verify they contain these terms.
""")
