import chromadb

client = chromadb.PersistentClient(path="./archilles_rag_db")
collection = client.get_collection("archilles_books")

# Check the specific chunk that matches our query
chunk = collection.get(
    ids=["von_Harnack_chunk_328"],
    include=["metadatas"]
)

if chunk['metadatas']:
    meta = chunk['metadatas'][0]
    print("Chunk: von_Harnack_chunk_328")
    print(f"  page: {meta.get('page')}")
    print(f"  printed_page: {meta.get('printed_page')}")
    print(f"  printed_page_confidence: {meta.get('printed_page_confidence')}")
    print()

# Also check pages 328 and 329
for page_num in [328, 329, 330, 331]:
    results = collection.get(
        where={"$and": [{"book_id": "von_Harnack"}, {"page": page_num}]},
        include=["metadatas"],
        limit=1
    )

    if results['metadatas']:
        meta = results['metadatas'][0]
        print(f"PDF page {page_num}:")
        print(f"  printed_page: {meta.get('printed_page')}")
        print(f"  confidence: {meta.get('printed_page_confidence')}")
    else:
        print(f"PDF page {page_num}: No chunk found")
