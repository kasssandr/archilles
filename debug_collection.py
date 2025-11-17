#!/usr/bin/env python3
"""
Debug script to inspect ChromaDB collection metadata structure
"""

import chromadb
from chromadb.config import Settings
import json

# Connect to ChromaDB
client = chromadb.PersistentClient(
    path="./chroma_db",
    settings=Settings(anonymized_telemetry=False)
)

# List all collections
print("=" * 60)
print("Available Collections:")
print("=" * 60)
collections = client.list_collections()
for col in collections:
    print(f"  - {col.name}")

print("\n" + "=" * 60)
print("Inspecting Collection Metadata")
print("=" * 60)

# Get the judenkoenige collection
try:
    collection = client.get_collection(name="judenkoenige")

    # Get sample of 5 chunks
    sample = collection.get(limit=5)

    print(f"\nTotal chunks in collection: {collection.count():,}")
    print(f"\nSample of {len(sample['ids'])} chunks:")
    print("\n" + "-" * 60)

    for i in range(len(sample['ids'])):
        print(f"\nChunk {i+1}:")
        print(f"  ID: {sample['ids'][i]}")
        print(f"  Text preview: {sample['documents'][i][:100]}...")
        print(f"  Metadata: {json.dumps(sample['metadatas'][i], indent=4, ensure_ascii=False)}")
        print("-" * 60)

except Exception as e:
    print(f"Error: {e}")

print("\n" + "=" * 60)
print("Available metadata fields:")
print("=" * 60)

if sample and sample['metadatas']:
    all_keys = set()
    for meta in sample['metadatas']:
        all_keys.update(meta.keys())

    print(f"Fields found: {', '.join(sorted(all_keys))}")
