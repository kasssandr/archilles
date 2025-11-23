"""
Debug script to check if asterisks are preserved in metadata.
"""

import chromadb

client = chromadb.PersistentClient(path="./achilles_rag_db")
collection = client.get_collection("achilles_books")

# Check PDF page 329 (should have printed_page "11*")
results = collection.get(
    where={"$and": [{"book_id": "von_Harnack"}, {"page": 329}]},
    include=["metadatas"],
    limit=1
)

if results['metadatas']:
    meta = results['metadatas'][0]
    printed_page = meta.get('printed_page')

    print(f"PDF page 329 metadata:")
    print(f"  printed_page value: {repr(printed_page)}")
    print(f"  printed_page type: {type(printed_page)}")
    print(f"  confidence: {meta.get('printed_page_confidence')}")

    # Check if asterisk is present
    if printed_page:
        if '*' in str(printed_page):
            print(f"  ✓ Asterisk IS present in database")
        else:
            print(f"  ✗ Asterisk is MISSING from database")
            print(f"     This means the issue occurred during database update")

    # Test the display formatting
    print(f"\nDisplay test:")
    citation = f"S. {printed_page}"
    print(f"  f\"S. {{printed_page}}\" → \"{citation}\"")
else:
    print("No chunk found for PDF page 329")
