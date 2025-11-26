import chromadb
import re

client = chromadb.PersistentClient(path="./archilles_rag_db")
collection = client.get_collection("archilles_books")

# Get chunks around page 329
for page_num in range(327, 332):
    results = collection.get(
        where={"$and": [{"page": page_num}, {"book_id": "von_Harnack"}]},
        include=["documents"],
        limit=1
    )

    if results['ids']:
        text = results['documents'][0]

        print(f"\n{'='*80}")
        print(f"PAGE {page_num}")
        print('='*80)

        # Look for page number patterns in the text
        # Common patterns: "S. 11", "11*", "Seite 11", header/footer numbers

        # Check first 200 chars (header)
        header = text[:200]
        print(f"HEADER: {header[:150]}...")

        # Check last 200 chars (footer)
        footer = text[-200:]
        print(f"FOOTER: ...{footer[-150:]}")

        # Look for "S. XX" pattern
        s_pattern = r'S\.\s*(\d+)'
        matches = re.findall(s_pattern, text)
        if matches:
            print(f"Found 'S. X' patterns: {matches[:5]}")

        # Look for standalone numbers that could be page numbers
        # Typically at start or end of text
        number_pattern = r'^\s*(\d+)\s*[\*\.]?\s*$'
        lines = text.split('\n')
        for i, line in enumerate(lines[:3] + lines[-3:]):
            if re.match(number_pattern, line.strip()):
                print(f"Possible page number in line: '{line.strip()}'")
