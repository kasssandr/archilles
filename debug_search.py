import chromadb
import re

client = chromadb.PersistentClient(path="./achilles_rag_db")
collection = client.get_collection("books")

query = "evangelista et a presbyteris"
query_normalized = re.sub(r'\s+', ' ', query.lower().strip())

all_data = collection.get()

print(f"Searching {len(all_data['ids'])} chunks for: '{query_normalized}'\n")

matches = []
for i, (doc_id, text, meta) in enumerate(zip(all_data['ids'], all_data['documents'], all_data['metadatas'])):
    text_normalized = re.sub(r'\s+', ' ', text.lower())

    if query_normalized in text_normalized:
        page = meta.get('page', 'unknown')
        matches.append((page, doc_id, text))

        print(f"✓ Found in: {page}")
        print(f"  Chunk ID: {doc_id}")
        print(f"  Text length: {len(text)} chars")

        # Find position with regex (flexible whitespace)
        query_escaped = re.escape(query.lower())
        query_pattern = re.sub(r'\\ ', r'\\s+', query_escaped)
        match = re.search(query_pattern, text, re.IGNORECASE)

        if match:
            pos = match.start()
            print(f"  Position in text: {pos}")
            # Show actual text around phrase
            start = max(0, pos - 150)
            end = min(len(text), pos + 250)
            print(f"  Text snippet:")
            print(f"  {text[start:end]}")
        else:
            print(f"  ERROR: Regex didn't find it!")

        print("\n" + "="*80 + "\n")

print(f"\nTotal matches: {len(matches)}")
