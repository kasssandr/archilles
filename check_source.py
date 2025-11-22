import chromadb

client = chromadb.PersistentClient(path="./achilles_rag_db")
collection = client.get_collection("achilles_books")

# Get one chunk from von_Harnack
results = collection.get(
    where={"book_id": "von_Harnack"},
    include=["metadatas"],
    limit=5
)

print("First 5 von_Harnack chunks:")
for meta in results['metadatas']:
    print(f"  page={meta.get('page')}, format={meta.get('format')}, book_title={meta.get('book_title')}")

print("\n" + "="*80 + "\n")

# Get the chunk with our match
match_chunk = collection.get(
    ids=["von_Harnack_chunk_328"],
    include=["documents", "metadatas"]
)

if match_chunk['ids']:
    text = match_chunk['documents'][0]
    meta = match_chunk['metadatas'][0]

    print(f"Match chunk metadata:")
    print(f"  {meta}")

    print(f"\nFull text (first 500 chars):")
    print(text[:500])

    print(f"\n\nFull text (last 500 chars):")
    print(text[-500:])
