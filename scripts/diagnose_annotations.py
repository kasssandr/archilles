#!/usr/bin/env python3
"""
Diagnose script to check if annotation metadata is correctly stored in ChromaDB.
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import os
import chromadb

def diagnose_annotations():
    """Check what's actually in the ChromaDB annotations collection."""

    # Get library path from environment
    library_path = os.getenv('CALIBRE_LIBRARY_PATH')
    if not library_path:
        print("ERROR: CALIBRE_LIBRARY_PATH not set")
        sys.exit(1)

    # ChromaDB path (same as in MCP server)
    chroma_path = Path(library_path) / ".archilles" / "chroma_db"

    if not chroma_path.exists():
        print(f"ERROR: ChromaDB not found at {chroma_path}")
        sys.exit(1)

    print(f"📁 ChromaDB Path: {chroma_path}")
    print(f"   Exists: ✓\n")

    # Connect to ChromaDB
    client = chromadb.PersistentClient(path=str(chroma_path))

    # Get collection
    try:
        collection = client.get_collection(name="calibre_annotations")
        print(f"✓ Collection 'calibre_annotations' found")
    except Exception as e:
        print(f"✗ Collection not found: {e}")
        print("\nAvailable collections:")
        for coll in client.list_collections():
            print(f"  - {coll.name}")
        sys.exit(1)

    # Get count
    count = collection.count()
    print(f"✓ Total annotations: {count}\n")

    if count == 0:
        print("⚠️  Collection is empty!")
        return

    # Get first 3 annotations to inspect metadata
    print("=" * 80)
    print("SAMPLE ANNOTATIONS (first 3)")
    print("=" * 80)

    results = collection.get(
        limit=3,
        include=['metadatas', 'documents']
    )

    for i, (doc_id, metadata, document) in enumerate(zip(
        results['ids'],
        results['metadatas'],
        results['documents']
    ), 1):
        print(f"\n[{i}] ID: {doc_id}")
        print(f"    Text: {document[:100]}...")
        print(f"    Metadata fields present:")

        # Check which fields are present
        fields_to_check = [
            'book_hash',
            'book_title',      # ← Should be here!
            'book_author',     # ← Should be here!
            'book_id',         # ← Should be here!
            'book_path',
            'type',
            'source',
            'timestamp',
            'page',
            'spine_index',
            'position_percent'
        ]

        for field in fields_to_check:
            if field in metadata:
                value = metadata[field]
                # Truncate long values
                if isinstance(value, str) and len(value) > 50:
                    value = value[:50] + "..."

                # Highlight important fields
                marker = "✓" if field in ['book_title', 'book_author', 'book_id'] else " "
                print(f"      {marker} {field}: {value}")
            else:
                # Mark missing important fields
                marker = "✗" if field in ['book_title', 'book_author', 'book_id'] else " "
                print(f"      {marker} {field}: (missing)")

    # Statistics on metadata fields
    print("\n" + "=" * 80)
    print("METADATA FIELD COVERAGE")
    print("=" * 80)

    # Sample more annotations for statistics
    sample_size = min(100, count)
    sample = collection.get(
        limit=sample_size,
        include=['metadatas']
    )

    field_counts = {}
    for metadata in sample['metadatas']:
        for field in metadata.keys():
            field_counts[field] = field_counts.get(field, 0) + 1

    print(f"\nFields present in sample of {sample_size} annotations:")
    for field, count in sorted(field_counts.items(), key=lambda x: x[1], reverse=True):
        percentage = (count / sample_size) * 100
        print(f"  {field}: {count}/{sample_size} ({percentage:.1f}%)")

    # Check if critical fields are missing
    critical_fields = ['book_title', 'book_author', 'book_id']
    missing_critical = [f for f in critical_fields if f not in field_counts or field_counts[f] < sample_size * 0.5]

    if missing_critical:
        print(f"\n⚠️  WARNING: Critical fields missing or incomplete:")
        for field in missing_critical:
            coverage = field_counts.get(field, 0) / sample_size * 100
            print(f"     - {field}: {coverage:.1f}% coverage")
        print(f"\n💡 This means annotations were indexed BEFORE the metadata fix.")
        print(f"   Solution: Re-index with force_reindex=True in Claude Desktop")
    else:
        print(f"\n✓ All critical metadata fields present!")


if __name__ == '__main__':
    diagnose_annotations()
