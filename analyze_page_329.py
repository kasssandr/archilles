import chromadb

client = chromadb.PersistentClient(path="./achilles_rag_db")
collection = client.get_collection("achilles_books")

# Get the chunk for PDF page 329
results = collection.get(
    where={"$and": [{"book_id": "von_Harnack"}, {"page": 329}]},
    include=["documents"],
    limit=1
)

if results['documents']:
    text = results['documents'][0]
    lines = text.split('\n')

    print("PDF PAGE 329 TEXT ANALYSIS")
    print("="*80)
    print(f"Total lines: {len(lines)}")
    print(f"Total characters: {len(text)}\n")

    print("FIRST 5 LINES (header area):")
    print("-"*80)
    for i, line in enumerate(lines[:5]):
        print(f"Line {i}: {repr(line)}")

    print("\n" + "="*80)
    print("LAST 5 LINES (footer area):")
    print("-"*80)
    for i, line in enumerate(lines[-5:]):
        print(f"Line {len(lines)-5+i}: {repr(line)}")

    print("\n" + "="*80)
    print("LOOKING FOR PAGE NUMBERS:")
    print("-"*80)

    import re
    # Check for asterisk patterns
    asterisk_pattern = r'(\d+)\*'
    matches = re.findall(asterisk_pattern, text)
    if matches:
        print(f"Found asterisk numbers: {matches}")
    else:
        print("No asterisk numbers found")

    # Check first line specifically
    first_line = lines[0] if lines else ""
    print(f"\nFirst line: '{first_line}'")
    if re.search(asterisk_pattern, first_line):
        print("  → Contains asterisk number!")
    else:
        print("  → No asterisk number in first line")
else:
    print("No chunk found for PDF page 329")
