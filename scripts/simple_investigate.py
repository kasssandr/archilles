#!/usr/bin/env python3
"""
Simple investigation of German medieval terms in comments
Uses minimal dependencies
"""

import os
import sys
from pathlib import Path

try:
    import chromadb
    from chromadb.config import Settings
except ImportError:
    print("❌ ChromaDB not installed yet. Please wait for pip install to complete.")
    sys.exit(1)

# Get Calibre library path
library_path = os.getenv('CALIBRE_LIBRARY')
if not library_path:
    print("❌ CALIBRE_LIBRARY environment variable not set")
    sys.exit(1)

db_path = str(Path(library_path) / ".archilles" / "rag_db")

print(f"📚 Loading ChromaDB from: {db_path}\n")

# Initialize ChromaDB client
client = chromadb.PersistentClient(
    path=db_path,
    settings=Settings(anonymized_telemetry=False)
)

# Get the collection
try:
    collection = client.get_collection("archilles")
except Exception as e:
    print(f"❌ Error loading collection: {e}")
    sys.exit(1)

print(f"✅ Collection loaded: {collection.count()} chunks\n")

# Get all Phase 1 metadata chunks
print("=" * 70)
print("SEARCHING FOR GERMAN MEDIEVAL TERMS IN METADATA:")
print("=" * 70)

# Get all Phase 1 metadata
phase1_data = collection.get(where={'chunk_type': 'phase1_metadata'})

print(f"\nTotal Phase 1 metadata chunks: {len(phase1_data['ids'])}\n")

# Search for German medieval terms
search_terms = {
    'mittelalter': [],  # Middle Ages
    'adel': [],         # Nobility
    'vasallen': [],     # Vassals
    'lehen': [],        # Fiefs
    'feudal': []        # Feudal
}

for i, (doc_id, doc, metadata) in enumerate(zip(phase1_data['ids'], phase1_data['documents'], phase1_data['metadatas'])):
    doc_lower = doc.lower()
    for term in search_terms.keys():
        if term in doc_lower:
            search_terms[term].append({
                'id': doc_id,
                'title': metadata.get('book_title', 'Unknown'),
                'author': metadata.get('author', 'N/A'),
                'tags': metadata.get('tags', ''),
                'snippet': doc[:200] if term in doc[:200].lower() else f"...{doc[max(0, doc_lower.find(term)-50):doc_lower.find(term)+150]}..."
            })

# Display results
for term, books in search_terms.items():
    print(f"\n📖 '{term}': Found in {len(books)} books (Phase 1 metadata)")
    if books:
        for book in books[:5]:  # Show first 5
            print(f"   • {book['title']}")
            if book['author'] != 'N/A':
                print(f"     Author: {book['author']}")
            if book['tags']:
                print(f"     Tags: {book['tags'][:100]}")
        if len(books) > 5:
            print(f"   ... and {len(books) - 5} more")

print(f"\n{'='*70}")
print("KEYWORD SEARCH TEST:")
print(f"{'='*70}\n")

# Try direct keyword search for "mittelalter"
print("🔍 Querying for 'mittelalter' (keyword search)...")
try:
    # Simple query without embeddings - just text matching
    results = collection.query(
        query_texts=["mittelalter"],
        n_results=10,
        where={'chunk_type': 'phase1_metadata'}
    )

    print(f"   Found {len(results['ids'][0])} results\n")
    for i, (doc_id, doc, metadata, distance) in enumerate(zip(
        results['ids'][0],
        results['documents'][0],
        results['metadatas'][0],
        results['distances'][0]
    ), 1):
        print(f"[{i}] {metadata.get('book_title', 'Unknown')}")
        print(f"    Author: {metadata.get('author', 'N/A')}")
        print(f"    Distance: {distance:.4f}")

        # Check if mittelalter is actually in the text
        if 'mittelalter' in doc.lower():
            print(f"    ✅ Contains 'mittelalter'")
        else:
            print(f"    ❌ Does NOT contain 'mittelalter' (semantic match only)")
        print()
except Exception as e:
    print(f"❌ Error during query: {e}")

print(f"\n{'='*70}")
print("DONE")
print(f"{'='*70}\n")
