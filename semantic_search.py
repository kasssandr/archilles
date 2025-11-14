#!/usr/bin/env python3
"""
Semantic Search Engine using ChromaDB and Sentence Transformers
For intelligent, concept-based quote discovery
"""

import chromadb
from chromadb.config import Settings
from sentence_transformers import SentenceTransformer
from pathlib import Path
from typing import List, Dict, Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class SemanticSearchEngine:
    """
    Semantic search using vector embeddings and ChromaDB
    Finds conceptually related passages, not just keyword matches
    """

    def __init__(
        self,
        chroma_db_path="./chroma_db",
        collection_name="quote_tracker",
        model_name="paraphrase-multilingual-mpnet-base-v2"
    ):
        """
        Initialize semantic search engine

        Args:
            chroma_db_path: Path to ChromaDB storage
            collection_name: Name of the collection to use
            model_name: Sentence transformer model name
        """
        self.chroma_db_path = Path(chroma_db_path)
        self.collection_name = collection_name
        self.model_name = model_name

        # Initialize ChromaDB client
        self.client = chromadb.PersistentClient(
            path=str(self.chroma_db_path),
            settings=Settings(anonymized_telemetry=False)
        )

        # Load sentence transformer model
        logger.info(f"Loading embedding model: {model_name}")
        self.model = SentenceTransformer(model_name)
        logger.info("Model loaded successfully")

        # Get or create collection
        try:
            self.collection = self.client.get_collection(name=collection_name)
            logger.info(f"Using existing collection: {collection_name}")
        except:
            self.collection = self.client.create_collection(
                name=collection_name,
                metadata={"description": "Quote Tracker semantic search"}
            )
            logger.info(f"Created new collection: {collection_name}")

    def index_text_chunks(self, book_id: int, author: str, title: str, chunks: List[str]):
        """
        Index text chunks with semantic embeddings

        Args:
            book_id: Calibre book ID
            author: Book author
            title: Book title
            chunks: List of text chunks to index
        """
        if not chunks:
            logger.warning(f"No chunks to index for book {book_id}")
            return

        # Generate unique IDs for each chunk
        ids = [f"book_{book_id}_chunk_{i}" for i in range(len(chunks))]

        # Create metadata for each chunk
        metadatas = [
            {
                "book_id": str(book_id),
                "author": author,
                "title": title,
                "chunk_index": i,
                "chunk_count": len(chunks)
            }
            for i in range(len(chunks))
        ]

        # Generate embeddings
        logger.info(f"Generating embeddings for {len(chunks)} chunks from '{title}'")
        embeddings = self.model.encode(chunks, show_progress_bar=False).tolist()

        # Add to collection
        self.collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=chunks,
            metadatas=metadatas
        )

        logger.info(f"Indexed {len(chunks)} chunks for book {book_id}")

    def search(self, query: str, limit: int = 20) -> List[Dict]:
        """
        Semantic search for conceptually related passages

        Args:
            query: Search query
            limit: Maximum number of results

        Returns:
            List of results with text, metadata, and similarity scores
        """
        # Generate query embedding
        query_embedding = self.model.encode([query], show_progress_bar=False).tolist()[0]

        # Search in ChromaDB
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=limit
        )

        # Format results
        formatted_results = []

        if not results['ids'] or not results['ids'][0]:
            return formatted_results

        for i in range(len(results['ids'][0])):
            result = {
                'id': results['ids'][0][i],
                'text': results['documents'][0][i],
                'metadata': results['metadatas'][0][i],
                'distance': results['distances'][0][i] if 'distances' in results else None,
                'similarity': 1 - results['distances'][0][i] if 'distances' in results else None,
                'book_id': int(results['metadatas'][0][i].get('book_id', 0)),
                'author': results['metadatas'][0][i].get('author', ''),
                'title': results['metadatas'][0][i].get('title', ''),
                'chunk_index': results['metadatas'][0][i].get('chunk_index', 0)
            }
            formatted_results.append(result)

        return formatted_results

    def is_indexed(self, book_id: int) -> bool:
        """
        Check if a book is already indexed

        Args:
            book_id: Calibre book ID

        Returns:
            True if book has indexed chunks
        """
        try:
            results = self.collection.get(
                where={"book_id": str(book_id)},
                limit=1
            )
            return len(results['ids']) > 0
        except:
            return False

    def get_stats(self) -> Dict:
        """
        Get statistics about the semantic index

        Returns:
            Dictionary with index statistics
        """
        total_chunks = self.collection.count()

        # Get unique books
        all_metadata = self.collection.get()
        unique_books = set()

        if all_metadata and all_metadata['metadatas']:
            for meta in all_metadata['metadatas']:
                if 'book_id' in meta:
                    unique_books.add(meta['book_id'])

        return {
            'total_chunks': total_chunks,
            'unique_books': len(unique_books),
            'collection_name': self.collection_name,
            'model': self.model_name
        }

    def delete_book(self, book_id: int):
        """
        Delete all chunks for a specific book

        Args:
            book_id: Calibre book ID
        """
        try:
            self.collection.delete(
                where={"book_id": str(book_id)}
            )
            logger.info(f"Deleted all chunks for book {book_id}")
        except Exception as e:
            logger.error(f"Error deleting book {book_id}: {e}")

    def clear(self):
        """Clear all indexed data"""
        try:
            self.client.delete_collection(name=self.collection_name)
            self.collection = self.client.create_collection(
                name=self.collection_name,
                metadata={"description": "Quote Tracker semantic search"}
            )
            logger.info("Semantic index cleared")
        except Exception as e:
            logger.error(f"Error clearing index: {e}")


def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 200) -> List[str]:
    """
    Split text into overlapping chunks

    Args:
        text: Full text to chunk
        chunk_size: Size of each chunk in characters
        overlap: Overlap between chunks in characters

    Returns:
        List of text chunks
    """
    if not text or len(text) < chunk_size:
        return [text] if text else []

    chunks = []
    start = 0

    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]

        # Try to break at sentence boundary
        if end < len(text):
            # Look for last period, exclamation, or question mark
            for delimiter in ['. ', '! ', '? ', '.\n', '!\n', '?\n']:
                last_delim = chunk.rfind(delimiter)
                if last_delim > chunk_size * 0.5:  # Only if in latter half
                    chunk = chunk[:last_delim + 1]
                    break

        chunks.append(chunk.strip())

        # Move start forward, accounting for overlap
        start = start + len(chunk) - overlap

    return chunks


if __name__ == '__main__':
    # Simple test
    print("Testing SemanticSearchEngine...")

    engine = SemanticSearchEngine(
        chroma_db_path="./test_chroma_db",
        collection_name="test_collection"
    )

    # Test chunking
    test_text = "This is a test document about ancient Rome. " * 50
    chunks = chunk_text(test_text, chunk_size=100, overlap=20)
    print(f"Created {len(chunks)} chunks from test text")

    # Test indexing
    engine.index_text_chunks(
        book_id=1,
        author="Test Author",
        title="Test Book",
        chunks=chunks
    )

    # Test search
    results = engine.search("ancient Rome", limit=5)
    print(f"\nSemantic search found {len(results)} results")
    for i, result in enumerate(results, 1):
        print(f"{i}. Similarity: {result['similarity']:.2f}")
        print(f"   Text: {result['text'][:100]}...")

    # Test stats
    stats = engine.get_stats()
    print(f"\nIndex stats: {stats}")

    print("\nTest completed!")
