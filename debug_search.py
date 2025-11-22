import chromadb
import re

client = chromadb.PersistentClient(path="./achilles_rag_db")
collection = client.get_collection("achilles_books")

query = "evangelista et a presbyteris"
query_normalized = re.sub(r'\s+', ' ', query.lower().strip())

all_data = collection.get()

print(f"Searching {len(all_data['ids'])} chunks for: '{query_normalized}'\n")
print(f"DEBUG: Checking page numbers around the match...\n")

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

# Show pages around the match to understand pagination
if matches:
    match_page = matches[0][0]  # page number of the match
    match_id = matches[0][1]  # chunk ID

    # Extract book_id from chunk_id (e.g., "von_Harnack_chunk_328" → "von_Harnack")
    book_id = '_'.join(match_id.split('_')[:-2]) if '_chunk_' in match_id else None

    print(f"\n" + "="*80)
    print(f"PAGINATION ANALYSIS: Pages around {match_page} in book '{book_id}'")
    print("="*80 + "\n")

    # Get chunks from pages around the match (filtered by book_id!)
    start_page = max(1, match_page - 5)
    end_page = match_page + 5

    for page_num in range(start_page, end_page + 1):
        # Filter by BOTH page AND book_id (ChromaDB requires $and for multiple conditions)
        if book_id:
            where_clause = {"$and": [{"page": page_num}, {"book_id": book_id}]}
        else:
            where_clause = {"page": page_num}

        results = collection.get(
            where=where_clause,
            include=["documents", "metadatas"],
            limit=1
        )

        if results['ids']:
            text = results['documents'][0]
            meta = results['metadatas'][0]

            # Show first 100 chars
            preview = text[:100].replace('\n', ' ')
            mark = " <-- MATCH HERE" if page_num == match_page else ""

            print(f"Page {page_num}: {preview}...{mark}")
        else:
            print(f"Page {page_num}: [no chunk]")
