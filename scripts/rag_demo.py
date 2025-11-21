#!/usr/bin/env python3
"""
Mini-RAG Proof-of-Concept for Achilles

Demonstrates:
1. Extract text from a book (any format)
2. Generate BGE-M3 embeddings (multilingual, optimized for German/Latin)
3. Index in ChromaDB (local vector database)
4. Semantic search with exact citations (page numbers)

Usage:
    # Index a book
    python scripts/rag_demo.py index "path/to/book.pdf"

    # Query the indexed book
    python scripts/rag_demo.py query "What does Josephus say about the Jewish kings?"

    # Query with top-K results
    python scripts/rag_demo.py query "Judenkönige" --top-k 10
"""

import sys
import argparse
from pathlib import Path
from typing import List, Dict, Any
import time

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.extractors import UniversalExtractor
import chromadb
from sentence_transformers import SentenceTransformer
from tqdm import tqdm


class AchillesRAG:
    """
    Simple RAG system for academic books.

    Features:
    - BGE-M3 embeddings (1024 dimensions, multilingual)
    - ChromaDB local storage
    - Exact page citations
    - Semantic search
    """

    def __init__(
        self,
        db_path: str = "./achilles_rag_db",
        model_name: str = "BAAI/bge-m3"
    ):
        """
        Initialize RAG system.

        Args:
            db_path: Path to ChromaDB storage
            model_name: Sentence transformer model (default: BGE-M3)
        """
        print(f"🚀 Initializing Achilles RAG...")
        print(f"  Database: {db_path}")
        print(f"  Model: {model_name}")

        # Initialize extractor
        self.extractor = UniversalExtractor(
            chunk_size=512,
            overlap=128
        )

        # Initialize embedding model
        print(f"  Loading embedding model... (first time: ~500 MB download)")
        self.embedding_model = SentenceTransformer(model_name)
        print(f"  ✓ Model loaded: {model_name}")

        # Initialize ChromaDB
        self.chroma_client = chromadb.PersistentClient(path=db_path)

        # Get or create collection
        self.collection = self.chroma_client.get_or_create_collection(
            name="achilles_books",
            metadata={"hnsw:space": "cosine"}
        )

        print(f"  ✓ ChromaDB ready")
        print(f"  Current index: {self.collection.count()} chunks\n")

    def index_book(self, book_path: str, book_id: str = None) -> Dict[str, Any]:
        """
        Extract and index a book.

        Args:
            book_path: Path to book file
            book_id: Optional book ID (default: filename)

        Returns:
            Dictionary with indexing statistics
        """
        book_path = Path(book_path)

        if not book_path.exists():
            raise FileNotFoundError(f"Book not found: {book_path}")

        book_id = book_id or book_path.stem

        print(f"📚 INDEXING BOOK: {book_path.name}")
        print(f"  Book ID: {book_id}\n")

        # Step 1: Extract text
        print("  [1/3] Extracting text...")
        start_time = time.time()
        extracted = self.extractor.extract(book_path)
        extract_time = time.time() - start_time

        print(f"    ✓ Extracted {len(extracted.chunks)} chunks in {extract_time:.1f}s")
        print(f"    ✓ {extracted.metadata.total_words:,} words, {extracted.metadata.total_pages or 'N/A'} pages\n")

        # Step 2: Generate embeddings
        print("  [2/3] Generating embeddings...")
        start_time = time.time()

        texts = [chunk['text'] for chunk in extracted.chunks]
        embeddings = []

        # Batch process for speed
        batch_size = 32
        for i in tqdm(range(0, len(texts), batch_size), desc="    Embedding"):
            batch = texts[i:i+batch_size]
            batch_embeddings = self.embedding_model.encode(
                batch,
                show_progress_bar=False,
                convert_to_numpy=True
            )
            embeddings.extend(batch_embeddings.tolist())

        embed_time = time.time() - start_time
        print(f"    ✓ Generated {len(embeddings)} embeddings in {embed_time:.1f}s\n")

        # Step 3: Index in ChromaDB
        print("  [3/3] Indexing in ChromaDB...")
        start_time = time.time()

        # Prepare data
        ids = []
        documents = []
        metadatas = []

        for i, (chunk, embedding) in enumerate(zip(extracted.chunks, embeddings)):
            chunk_id = f"{book_id}_chunk_{i}"
            ids.append(chunk_id)
            documents.append(chunk['text'])

            # Metadata for citation
            metadata = {
                'book_id': book_id,
                'book_title': extracted.metadata.file_path.stem,
                'chunk_index': i,
                'format': extracted.metadata.detected_format,
            }

            # Add page info if available
            if 'metadata' in chunk and chunk['metadata'].get('page'):
                metadata['page'] = chunk['metadata']['page']

            # Add chapter info if available
            if 'metadata' in chunk and chunk['metadata'].get('chapter'):
                metadata['chapter'] = chunk['metadata']['chapter']

            metadatas.append(metadata)

        # Add to collection
        self.collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas
        )

        index_time = time.time() - start_time
        print(f"    ✓ Indexed {len(ids)} chunks in {index_time:.1f}s\n")

        # Summary
        total_time = extract_time + embed_time + index_time
        print(f"✅ INDEXING COMPLETE")
        print(f"  Total time: {total_time:.1f}s")
        print(f"  Collection size: {self.collection.count()} chunks\n")

        return {
            'book_id': book_id,
            'chunks_indexed': len(ids),
            'total_words': extracted.metadata.total_words,
            'total_pages': extracted.metadata.total_pages,
            'extraction_time': extract_time,
            'embedding_time': embed_time,
            'indexing_time': index_time,
            'total_time': total_time,
        }

    def query(self, query_text: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """
        Search for relevant passages.

        Args:
            query_text: Search query
            top_k: Number of results to return

        Returns:
            List of relevant chunks with metadata and scores
        """
        print(f"🔍 QUERY: \"{query_text}\"")
        print(f"  Searching {self.collection.count()} chunks...\n")

        # Generate query embedding
        query_embedding = self.embedding_model.encode(
            query_text,
            convert_to_numpy=True
        ).tolist()

        # Search in ChromaDB
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k
        )

        # Format results
        formatted_results = []

        if results['ids'] and len(results['ids'][0]) > 0:
            for i in range(len(results['ids'][0])):
                result = {
                    'rank': i + 1,
                    'text': results['documents'][0][i],
                    'metadata': results['metadatas'][0][i],
                    'distance': results['distances'][0][i],
                    'similarity': 1 - results['distances'][0][i],  # Convert distance to similarity
                }
                formatted_results.append(result)

        return formatted_results

    def print_results(self, results: List[Dict[str, Any]]):
        """Pretty print search results."""
        if not results:
            print("❌ No results found.\n")
            return

        print(f"📊 TOP {len(results)} RESULTS:\n")
        print("=" * 80)

        for result in results:
            rank = result['rank']
            similarity = result['similarity']
            metadata = result['metadata']
            text = result['text']

            # Build citation
            citation_parts = []
            if metadata.get('book_title'):
                citation_parts.append(metadata['book_title'])
            if metadata.get('page'):
                citation_parts.append(f"S. {metadata['page']}")
            elif metadata.get('chapter'):
                citation_parts.append(metadata['chapter'])

            citation = ', '.join(citation_parts) if citation_parts else metadata.get('book_id', 'Unknown')

            print(f"\n[{rank}] {citation}")
            print(f"    Relevanz: {similarity:.3f} ({'sehr hoch' if similarity > 0.8 else 'hoch' if similarity > 0.6 else 'mittel'})")
            print(f"    Text: {text[:300]}{'...' if len(text) > 300 else ''}")

        print("\n" + "=" * 80 + "\n")


def main():
    """Main CLI interface."""
    parser = argparse.ArgumentParser(
        description="Achilles Mini-RAG: Semantic search in academic books",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Index Josephus Antiquitates
  python scripts/rag_demo.py index "D:/Calibre-Bibliothek/Flavius Josephus/Judische Altertumer_...pdf"

  # Query
  python scripts/rag_demo.py query "Was sagt Josephus über die Judenkönige?"

  # Query with more results
  python scripts/rag_demo.py query "Jewish kings" --top-k 10
        """
    )

    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # Index command
    index_parser = subparsers.add_parser('index', help='Index a book')
    index_parser.add_argument('book_path', help='Path to book file')
    index_parser.add_argument('--book-id', help='Optional book ID (default: filename)')
    index_parser.add_argument('--db-path', default='./achilles_rag_db', help='Database path')

    # Query command
    query_parser = subparsers.add_parser('query', help='Search indexed books')
    query_parser.add_argument('query', help='Search query')
    query_parser.add_argument('--top-k', type=int, default=5, help='Number of results (default: 5)')
    query_parser.add_argument('--db-path', default='./achilles_rag_db', help='Database path')

    # Stats command
    stats_parser = subparsers.add_parser('stats', help='Show index statistics')
    stats_parser.add_argument('--db-path', default='./achilles_rag_db', help='Database path')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    try:
        # Initialize RAG
        rag = AchillesRAG(db_path=args.db_path)

        if args.command == 'index':
            # Index a book
            stats = rag.index_book(args.book_path, args.book_id)

        elif args.command == 'query':
            # Search
            results = rag.query(args.query, args.top_k)
            rag.print_results(results)

        elif args.command == 'stats':
            # Show stats
            print(f"📊 INDEX STATISTICS\n")
            print(f"  Total chunks: {rag.collection.count()}")
            print(f"  Database path: {args.db_path}\n")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
