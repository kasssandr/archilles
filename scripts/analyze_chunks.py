#!/usr/bin/env python3
"""
Test search in different chunk types
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.rag_demo import archillesRAG
import os

# Get library path
library_path = os.getenv('CALIBRE_LIBRARY')
if not library_path:
    print("❌ CALIBRE_LIBRARY not set")
    sys.exit(1)

db_path = str(Path(library_path) / ".archilles" / "rag_db")

print("📊 Analyzing chunk distribution...\n")
rag = archillesRAG(db_path=db_path)

# Get all chunks and analyze
all_data = rag.collection.get()

# Count by chunk type
from collections import Counter
chunk_types = Counter()
books_by_type = {}

for metadata in all_data['metadatas']:
    chunk_type = metadata.get('chunk_type', 'unknown')
    book_id = metadata.get('book_id', 'unknown')

    chunk_types[chunk_type] += 1

    if chunk_type not in books_by_type:
        books_by_type[chunk_type] = set()
    books_by_type[chunk_type].add(book_id)

print("="*70)
print("CHUNK TYPE DISTRIBUTION:")
print("="*70)
for chunk_type, count in chunk_types.most_common():
    num_books = len(books_by_type.get(chunk_type, set()))
    print(f"{chunk_type:20s}: {count:4d} chunks in {num_books} books")

print(f"\nTotal chunks: {len(all_data['ids'])}")
print(f"Total unique books: {len(set(m.get('book_id') for m in all_data['metadatas']))}")

# Query example
if len(sys.argv) > 1:
    query = " ".join(sys.argv[1:])
    print(f"\n{'='*70}")
    print(f"TESTING QUERY: '{query}'")
    print(f"{'='*70}\n")

    # Search in all
    print("🔍 Searching in ALL chunks...")
    results_all = rag.query(query, top_k=3, mode='hybrid')
    print(f"   Found {len(results_all)} results")
    for r in results_all[:3]:
        meta = r.get('metadata', {})
        print(f"   - {meta.get('book_title', 'Unknown')} [{meta.get('chunk_type', 'unknown')}]")

    print("\n🔍 Searching in CONTENT only...")
    # Note: Would need to filter - showing concept
    content_results = [r for r in results_all if r.get('metadata', {}).get('chunk_type') == 'content']
    print(f"   Found {len(content_results)} content results")
    for r in content_results[:3]:
        meta = r.get('metadata', {})
        print(f"   - {meta.get('book_title', 'Unknown')}")

    print("\n🔍 Searching in METADATA only...")
    metadata_results = [r for r in results_all if r.get('metadata', {}).get('chunk_type') == 'phase1_metadata']
    print(f"   Found {len(metadata_results)} metadata results")
    for r in metadata_results[:3]:
        meta = r.get('metadata', {})
        print(f"   - {meta.get('book_title', 'Unknown')}")
