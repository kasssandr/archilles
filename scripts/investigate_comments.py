#!/usr/bin/env python3
"""
Investigate why German medieval terms aren't being found in comments
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.rag_demo import archillesRAG
import os

# Get Calibre library path
library_path = os.getenv('CALIBRE_LIBRARY')
if not library_path:
    print("❌ CALIBRE_LIBRARY environment variable not set")
    sys.exit(1)

db_path = str(Path(library_path) / ".archilles" / "rag_db")

print("📚 Loading RAG database...\n")
rag = archillesRAG(db_path=db_path)

# Get all Phase 1 metadata chunks (includes comments)
all_data = rag.collection.get(where={'chunk_type': 'phase1_metadata'})

print("="*70)
print("SEARCHING FOR GERMAN MEDIEVAL TERMS IN COMMENTS:")
print("="*70)

# Search for terms the user mentioned
search_terms = {
    'mittelalter': [],  # Middle Ages
    'adel': [],         # Nobility
    'vasallen': [],     # Vassals
    'lehen': [],        # Fiefs
    'feudal': []        # Feudal
}

for doc, metadata in zip(all_data['documents'], all_data['metadatas']):
    doc_lower = doc.lower()
    for term in search_terms.keys():
        if term in doc_lower:
            search_terms[term].append({
                'title': metadata.get('book_title', 'Unknown'),
                'author': metadata.get('author', 'N/A'),
                'tags': metadata.get('tags', ''),
                'snippet': doc[:200] if term in doc[:200].lower() else f"...{doc[doc_lower.find(term)-50:doc_lower.find(term)+100]}..."
            })

# Display results
for term, books in search_terms.items():
    print(f"\n📖 '{term}': Found in {len(books)} books")
    if books:
        for book in books[:5]:  # Show first 5
            print(f"   • {book['title']}")
            print(f"     Author: {book['author']}")
            if book['tags']:
                print(f"     Tags: {book['tags'][:100]}")
        if len(books) > 5:
            print(f"   ... and {len(books) - 5} more")

print(f"\n{'='*70}")
print("TESTING DIFFERENT SEARCH MODES:")
print(f"{'='*70}\n")

query = "Lehen Mittelalter"

# Test each mode
for mode in ['keyword', 'semantic', 'hybrid']:
    print(f"\n🔍 MODE: {mode.upper()}")
    print("-"*70)

    results = rag.query(query, top_k=5, mode=mode)

    if not results:
        print("   ❌ No results")
        continue

    for i, result in enumerate(results, 1):
        metadata = result.get('metadata', {})
        chunk_type = metadata.get('chunk_type', 'unknown')

        print(f"\n[{i}] {metadata.get('book_title', 'Unknown')} [{chunk_type}]")
        print(f"    Author: {metadata.get('author', 'N/A')}")
        print(f"    Score: {result.get('score', 0):.4f}")

        # Check if terms are in the text
        text_lower = result.get('text', '').lower()
        found_terms = [term for term in ['lehen', 'mittelalter', 'adel', 'vasallen'] if term in text_lower]
        if found_terms:
            print(f"    Contains: {', '.join(found_terms)}")

print(f"\n{'='*70}")
print("TESTING COMMENT-ONLY SEARCH:")
print(f"{'='*70}\n")

# Try searching only in phase1_metadata
print("🔍 Searching 'mittelalter' in KEYWORD mode (exact matching)...")
results = rag.query("mittelalter", top_k=10, mode='keyword')
metadata_results = [r for r in results if r.get('metadata', {}).get('chunk_type') == 'phase1_metadata']

print(f"   Found {len(metadata_results)} results in Phase 1 metadata\n")
for i, result in enumerate(metadata_results[:5], 1):
    metadata = result.get('metadata', {})
    print(f"[{i}] {metadata.get('book_title', 'Unknown')}")
    print(f"    Author: {metadata.get('author', 'N/A')}")
    print(f"    Score: {result.get('score', 0):.4f}")
    print()
