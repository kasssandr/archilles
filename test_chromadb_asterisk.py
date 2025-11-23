"""
Test if ChromaDB preserves asterisks in metadata values.
"""

import chromadb
from pathlib import Path
import shutil

# Create a temporary test database
test_db = "./test_chroma_db"
if Path(test_db).exists():
    shutil.rmtree(test_db)

client = chromadb.PersistentClient(path=test_db)
collection = client.create_collection("test_collection")

# Add a document with asterisk in metadata
print("Testing ChromaDB metadata handling...\n")

test_values = [
    "11*",
    "12*",
    "13",
    "xiv",
    "A-5*"
]

for i, val in enumerate(test_values):
    collection.add(
        ids=[f"test_{i}"],
        documents=[f"Test document {i}"],
        metadatas=[{"printed_page": val}]
    )
    print(f"Added: {repr(val)}")

print("\nRetrieving values...\n")

for i, val in enumerate(test_values):
    result = collection.get(ids=[f"test_{i}"], include=["metadatas"])
    retrieved = result['metadatas'][0]['printed_page']

    match = "✓" if retrieved == val else "✗"
    print(f"{match} Original: {repr(val):10s} → Retrieved: {repr(retrieved):10s}")

    if retrieved != val:
        print(f"   MISMATCH! Type: {type(retrieved)}")

# Cleanup
shutil.rmtree(test_db)
print("\nTest complete. Database cleaned up.")
