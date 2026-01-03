#!/usr/bin/env python3
"""
Test different search modes to see which works best
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

print(f"📚 Loading RAG database...\n")
rag = archillesRAG(db_path=db_path)

query = "Marcion Kanonisierung"

# Test all three modes
for mode in ['keyword', 'semantic', 'hybrid']:
    print(f"\n{'='*70}")
    print(f"MODE: {mode.upper()}")
    print(f"{'='*70}\n")

    results = rag.query(query, top_k=5, mode=mode)

    if not results:
        print("❌ No results found")
        continue

    print(f"Found {len(results)} results:\n")

    for i, result in enumerate(results, 1):
        # Debug: Show what keys are in the result
        if i == 1:
            print(f"DEBUG - Result keys: {list(result.keys())}\n")

        print(f"[{i}] {result.get('book_title', 'Unknown')}")
        print(f"    Author: {result.get('author', 'N/A')}")
        print(f"    Score: {result.get('score', 0):.4f}")

        # Try alternative key names
        if 'metadata' in result:
            print(f"    Metadata: {result['metadata']}")

        # Show if Marcion or Kanonisierung is in the text
        text = result.get('text', result.get('document', ''))
        has_marcion = 'marcion' in text.lower()
        has_kanon = 'kanonisierung' in text.lower()
        print(f"    Contains: {'Marcion' if has_marcion else ''} {'Kanonisierung' if has_kanon else ''}")

        # Show snippet
        snippet = text[:150] if text else '(no text)'
        print(f"    Snippet: {snippet}...")
        print()

print(f"\n{'='*70}")
print("DONE")
print(f"{'='*70}\n")
