"""Check if the converted PDF has a Table of Contents."""

import fitz  # PyMuPDF
from pathlib import Path

# Find the temp PDF that was created from the DJVU
# It should be in Calibre's temp directory or similar

print("Looking for von Harnack PDF...")
print("Checking common locations...\n")

# Check if there's a source file path in the chunks
import chromadb

client = chromadb.PersistentClient(path="./achilles_rag_db")
collection = client.get_collection("achilles_books")

result = collection.get(
    where={"book_id": "von_Harnack"},
    include=["metadatas"],
    limit=1
)

if result['metadatas']:
    meta = result['metadatas'][0]
    print(f"Metadata: {meta}")
    source_file = meta.get('source_file')

    if source_file:
        print(f"\nSource file: {source_file}")

        # Try to open it
        if Path(source_file).exists():
            print("Opening PDF...\n")

            doc = fitz.open(source_file)

            toc = doc.get_toc()

            if toc:
                print(f"✓ Found TOC with {len(toc)} entries!\n")
                print("="*80)
                print("TABLE OF CONTENTS")
                print("="*80 + "\n")

                for level, title, page in toc[:30]:  # Show first 30 entries
                    indent = "  " * (level - 1)
                    print(f"{indent}{title:60s} → Page {page}")

                if len(toc) > 30:
                    print(f"\n... ({len(toc) - 30} more entries)")

            else:
                print("✗ No TOC found in PDF")
                print("This might be a scanned PDF without embedded TOC")

            doc.close()
        else:
            print(f"✗ File not found: {source_file}")
    else:
        print("✗ No source_file in metadata")
        print("\nThe file might be in Calibre's temp directory.")
        print("Do you know where the original DJVU or converted PDF is?")
