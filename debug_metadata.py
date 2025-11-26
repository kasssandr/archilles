import chromadb

client = chromadb.PersistentClient(path="./archilles_rag_db")
collection = client.get_collection("archilles_books")

# Get the chunk from S. 329
results = collection.get(
    where={"page": "S. 329"},
    include=["metadatas"],
    limit=1
)

if results['ids']:
    print("Metadata for S. 329:")
    print(results['metadatas'][0])
    print("\n" + "="*80 + "\n")

# Get another chunk to compare
results2 = collection.get(
    where={"page": "S. 337"},
    include=["metadatas"],
    limit=1
)

if results2['ids']:
    print("Metadata for S. 337:")
    print(results2['metadatas'][0])
    print("\n" + "="*80 + "\n")

# Get first few chunks to see pattern
all_chunks = collection.get(limit=10, include=["metadatas"])
print("First 10 chunk pages:")
for meta in all_chunks['metadatas']:
    print(f"  page={meta.get('page')}, page_label={meta.get('page_label')}, source_file={meta.get('source_file')}")
