#!/usr/bin/env python3
"""
Inspect what's actually indexed in the database
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

print(f"📚 Loading database...\n")
rag = archillesRAG(db_path=db_path)

# Get all chunks
all_data = rag.collection.get(limit=100)

print(f"✅ Total chunks: {len(all_data['ids'])}\n")

# Search for books with "Marcion" in the searchable text
print("="*70)
print("SEARCHING FOR 'Marcion' IN INDEXED TEXT:")
print("="*70)

marcion_count = 0
for i, (doc_id, document, metadata) in enumerate(zip(all_data['ids'], all_data['documents'], all_data['metadatas'])):
    if 'marcion' in document.lower():
        marcion_count += 1
        print(f"\n[{marcion_count}] {metadata.get('book_title', 'Unknown')}")
        print(f"    Author: {metadata.get('author', 'N/A')}")
        print(f"    Tags: {metadata.get('tags', 'N/A')}")
        print(f"    Chunk Type: {metadata.get('chunk_type', 'N/A')}")
        print(f"\n    Document text (first 500 chars):")
        print(f"    {document[:500]}")
        print("-"*70)

if marcion_count == 0:
    print("\n❌ NO books with 'Marcion' found in indexed text!")
    print("\n🔍 Let's check a few random indexed chunks to see what's actually there:\n")

    for i in range(min(3, len(all_data['ids']))):
        print(f"\n[Sample {i+1}] {all_data['metadatas'][i].get('book_title', 'Unknown')}")
        print(f"    Document text:\n{all_data['documents'][i][:800]}")
        print("-"*70)
else:
    print(f"\n✅ Found {marcion_count} chunks containing 'Marcion'")
