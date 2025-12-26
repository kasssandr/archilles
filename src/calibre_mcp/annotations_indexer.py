#!/usr/bin/env python3
"""
Calibre Annotations Indexer

This module handles indexing annotations for semantic search using ChromaDB.
Creates embeddings for annotations (highlights + notes) for fast semantic retrieval.
"""

import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

try:
    import chromadb
    from chromadb.config import Settings
    from chromadb.utils import embedding_functions
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False

from .annotations import (
    list_all_annotated_books,
    get_combined_annotations,
    get_annotations_dir
)

logger = logging.getLogger(__name__)


def load_config() -> Dict[str, Any]:
    """
    Load configuration from .archilles/config.json if available.

    Searches in common locations:
    1. CALIBRE_LIBRARY env var + .archilles/config.json
    2. Home directory Calibre Library variants
    3. Current working directory

    Returns:
        Configuration dictionary, or empty dict if not found
    """
    import os

    possible_paths = []

    # Try CALIBRE_LIBRARY env var
    calibre_lib = os.getenv("CALIBRE_LIBRARY")
    if calibre_lib:
        possible_paths.append(Path(calibre_lib) / ".archilles" / "config.json")

    # Try common Calibre Library locations
    home = Path.home()
    possible_paths.extend([
        home / "Calibre Library" / ".archilles" / "config.json",
        home / "Calibre-Bibliothek" / ".archilles" / "config.json",  # German
        Path("D:/Calibre-Bibliothek") / ".archilles" / "config.json",  # User's specific path
    ])

    # Try current directory
    possible_paths.append(Path.cwd() / ".archilles" / "config.json")

    for config_path in possible_paths:
        if config_path.exists():
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    logger.info(f"Loaded configuration from: {config_path}")
                    return config
            except Exception as e:
                logger.warning(f"Failed to load config from {config_path}: {e}")

    logger.info("No configuration file found, using defaults")
    return {}


class AnnotationsIndexer:
    """
    Indexes annotations for semantic search using ChromaDB.

    Each annotation is stored with:
    - Text: Combined highlighted_text + notes
    - Metadata: book_hash, book_path, annotation_type, timestamp, page, source
    """

    def __init__(
        self,
        chroma_persist_dir: Optional[str] = None,
        annotations_dir: Optional[str] = None,
        collection_name: str = "calibre_annotations",
        embedding_model: Optional[str] = None,
        library_path: Optional[str] = None
    ):
        """
        Initialize the annotations indexer.

        Args:
            chroma_persist_dir: Directory to persist ChromaDB data
            annotations_dir: Calibre annotations directory
            collection_name: Name of ChromaDB collection
            embedding_model: Embedding model name (default: from config or all-mpnet-base-v2)
            library_path: Path to Calibre library (needed for hash mapping)
        """
        if not CHROMADB_AVAILABLE:
            raise ImportError(
                "ChromaDB is required for semantic search. "
                "Install with: pip install chromadb"
            )

        # Load configuration
        config = load_config()

        self.annotations_dir = annotations_dir or str(get_annotations_dir())
        self.collection_name = collection_name
        self.library_path = library_path

        # Determine embedding model
        if embedding_model is None:
            embedding_model = config.get('embedding_model', 'all-mpnet-base-v2')

        self.embedding_model = embedding_model
        logger.info(f"Using embedding model: {self.embedding_model}")

        # Initialize ChromaDB
        if chroma_persist_dir:
            self.chroma_client = chromadb.PersistentClient(
                path=chroma_persist_dir,
                settings=Settings(anonymized_telemetry=False)
            )
        else:
            # Use in-memory database
            self.chroma_client = chromadb.Client(
                settings=Settings(anonymized_telemetry=False)
            )

        # Create embedding function with explicit model
        self.embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=self.embedding_model
        )

        # Get or create collection with explicit embedding function
        self.collection = self.chroma_client.get_or_create_collection(
            name=collection_name,
            embedding_function=self.embedding_function,
            metadata={
                "description": "Calibre book annotations with semantic search",
                "embedding_model": self.embedding_model
            }
        )

    def _create_hash_to_book_mapping(self) -> Dict[str, Dict[str, Any]]:
        """
        Create mapping from annotation hash to book metadata.

        This function:
        1. Reads all books from Calibre's metadata.db
        2. Constructs full paths for each book file
        3. Computes annotation hashes
        4. Returns mapping: hash → {title, author, path, format}

        Returns:
            Dictionary mapping annotation hash to book metadata
        """
        if not self.library_path:
            logger.warning("No library_path provided, cannot create hash mapping")
            return {}

        import sqlite3
        from .annotations import compute_book_hash

        db_path = Path(self.library_path) / "metadata.db"
        if not db_path.exists():
            logger.warning(f"metadata.db not found at {db_path}")
            return {}

        hash_mapping = {}

        try:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row

            # Query to get all books with their paths and metadata
            query = """
            SELECT
                books.id,
                books.title,
                books.path,
                data.name as filename,
                data.format,
                (SELECT name FROM authors
                 JOIN books_authors_link ON authors.id = books_authors_link.author
                 WHERE books_authors_link.book = books.id
                 LIMIT 1) as author
            FROM books
            JOIN data ON books.id = data.book
            WHERE data.format IN ('EPUB', 'PDF', 'MOBI', 'AZW3')
            ORDER BY books.id
            """

            cursor = conn.execute(query)

            for row in cursor:
                # Construct full path: library_path / book_path / filename.format
                book_path = Path(self.library_path) / row['path'] / f"{row['filename']}.{row['format']}"

                # Compute annotation hash
                book_hash = compute_book_hash(str(book_path))

                # Store metadata
                hash_mapping[book_hash] = {
                    'book_id': row['id'],
                    'title': row['title'],
                    'author': row['author'] or 'Unknown',
                    'path': str(book_path),
                    'format': row['format']
                }

            conn.close()
            logger.info(f"Created hash mapping for {len(hash_mapping)} books")

        except Exception as e:
            logger.error(f"Failed to create hash mapping: {e}")

        return hash_mapping

    def _create_annotation_id(self, book_hash: str, index: int) -> str:
        """Create unique ID for annotation."""
        return f"{book_hash}_anno_{index}"

    def _prepare_annotation_text(self, annotation: Dict[str, Any]) -> str:
        """
        Prepare annotation text for embedding.

        Combines highlighted_text and notes into searchable text.
        Filters out spaced/locked text (e.g., "w o r d" -> skip).
        """
        import re

        text_parts = []

        highlighted = annotation.get('highlighted_text', '').strip()
        if highlighted:
            # Check if text is spaced (more than 30% single chars separated by spaces/newlines)
            words = re.split(r'\s+', highlighted)
            single_chars = sum(1 for w in words if len(w) <= 2)
            if len(words) > 10 and single_chars / len(words) > 0.3:
                # Likely spaced/locked text - skip
                return ""
            text_parts.append(highlighted)

        notes = annotation.get('notes', '').strip()
        if notes:
            text_parts.append(f"Note: {notes}")

        return " | ".join(text_parts)

    def _prepare_annotation_metadata(
        self,
        annotation: Dict[str, Any],
        book_hash: str,
        book_path: str,
        book_title: Optional[str] = None,
        book_author: Optional[str] = None,
        book_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Prepare metadata for annotation.

        ChromaDB requires metadata values to be str, int, float, or bool.
        """
        metadata = {
            'book_hash': book_hash,
            'book_path': book_path,
            'type': annotation.get('type', 'unknown'),
            'source': annotation.get('source', 'unknown'),
        }

        # Add book metadata if available
        if book_title:
            metadata['book_title'] = str(book_title)

        if book_author:
            metadata['book_author'] = str(book_author)

        if book_id is not None:
            metadata['book_id'] = int(book_id)

        # Add timestamp if available
        timestamp = annotation.get('timestamp', '')
        if timestamp:
            metadata['timestamp'] = str(timestamp)

        # Add page/position if available
        page = annotation.get('page')
        if page is not None:
            metadata['page'] = int(page)

        spine_index = annotation.get('spine_index')
        if spine_index is not None:
            metadata['spine_index'] = int(spine_index)

        pos_frac = annotation.get('pos_frac')
        if pos_frac is not None:
            metadata['position_percent'] = float(pos_frac * 100)

        return metadata

    def index_book_annotations(
        self,
        book_path: str,
        book_hash: Optional[str] = None,
        exclude_toc_markers: bool = True,
        min_length: int = 20
    ) -> int:
        """
        Index annotations for a single book.

        Args:
            book_path: Path to the book file
            book_hash: Optional pre-computed book hash
            exclude_toc_markers: Whether to exclude TOC markers
            min_length: Minimum annotation length

        Returns:
            Number of annotations indexed
        """
        # Get annotations with filtering
        result = get_combined_annotations(
            book_path=book_path,
            annotations_dir=self.annotations_dir,
            exclude_toc_markers=exclude_toc_markers,
            min_length=min_length
        )

        annotations = result.get('annotations', [])
        if not annotations:
            return 0

        # Use book_hash from result or provided
        if book_hash is None:
            from .annotations import compute_book_hash
            book_hash = compute_book_hash(book_path)

        # Prepare data for ChromaDB
        ids = []
        documents = []
        metadatas = []

        for idx, annotation in enumerate(annotations):
            # Create text for embedding
            text = self._prepare_annotation_text(annotation)
            if not text:
                continue  # Skip empty annotations

            # Create ID
            anno_id = self._create_annotation_id(book_hash, idx)

            # Prepare metadata
            metadata = self._prepare_annotation_metadata(
                annotation,
                book_hash,
                book_path
            )

            ids.append(anno_id)
            documents.append(text)
            metadatas.append(metadata)

        # Add to collection (upsert to handle updates)
        if ids:
            self.collection.upsert(
                ids=ids,
                documents=documents,
                metadatas=metadatas
            )

        logger.info(
            f"Indexed {len(ids)} annotations for book: {Path(book_path).name}"
        )

        return len(ids)

    def index_all_annotations(
        self,
        exclude_toc_markers: bool = True,
        min_length: int = 20,
        force_reindex: bool = False
    ) -> Dict[str, int]:
        """
        Index all annotations from all books in the library.

        Args:
            exclude_toc_markers: Whether to exclude TOC markers
            min_length: Minimum annotation length
            force_reindex: Whether to reindex even if already indexed

        Returns:
            Dictionary with indexing statistics
        """
        stats = {
            'total_books': 0,
            'total_annotations': 0,
            'skipped_books': 0,
            'errors': 0,
            'books_without_metadata': 0
        }

        # Get all annotated books
        annotated_books = list_all_annotated_books(self.annotations_dir)

        if not annotated_books:
            logger.warning("No annotated books found")
            return stats

        stats['total_books'] = len(annotated_books)

        # Create hash-to-book mapping from Calibre library
        logger.info("Creating hash-to-book mapping from Calibre library...")
        hash_mapping = self._create_hash_to_book_mapping()

        if hash_mapping:
            logger.info(f"Mapped {len(hash_mapping)} books from library")
        else:
            logger.warning("No hash mapping available - will use placeholder paths")

        # Index annotations for each book
        for book_info in annotated_books:
            book_hash = book_info['hash']

            try:
                # Check if already indexed (unless force reindex)
                if not force_reindex:
                    existing = self.collection.get(
                        where={"book_hash": book_hash},
                        limit=1
                    )
                    if existing and existing['ids']:
                        stats['skipped_books'] += 1
                        continue

                # Get book metadata from hash mapping
                book_meta = hash_mapping.get(book_hash, {})

                if not book_meta:
                    # No metadata found - use placeholder
                    book_meta = {
                        'title': f'Unknown (hash: {book_hash[:12]}...)',
                        'author': 'Unknown',
                        'path': f'hash:{book_hash}',
                        'book_id': None
                    }
                    stats['books_without_metadata'] += 1

                # Read annotations file
                anno_file = Path(self.annotations_dir) / f"{book_hash}.json"
                if not anno_file.exists():
                    continue

                with open(anno_file, 'r', encoding='utf-8') as f:
                    annotations = json.load(f)

                if not isinstance(annotations, list):
                    continue

                # Prepare for indexing
                ids = []
                documents = []
                metadatas = []

                for idx, annotation in enumerate(annotations):
                    # Apply filters
                    if exclude_toc_markers:
                        from .annotations import is_toc_marker
                        if is_toc_marker(annotation, min_length):
                            continue

                    text = self._prepare_annotation_text(annotation)
                    if not text or len(text) < min_length:
                        continue

                    anno_id = self._create_annotation_id(book_hash, idx)
                    metadata = self._prepare_annotation_metadata(
                        annotation,
                        book_hash,
                        book_meta.get('path', f'hash:{book_hash}'),
                        book_title=book_meta.get('title'),
                        book_author=book_meta.get('author'),
                        book_id=book_meta.get('book_id')
                    )

                    ids.append(anno_id)
                    documents.append(text)
                    metadatas.append(metadata)

                # Index batch
                if ids:
                    self.collection.upsert(
                        ids=ids,
                        documents=documents,
                        metadatas=metadatas
                    )
                    stats['total_annotations'] += len(ids)

                    # Log with book title if available
                    book_title = book_meta.get('title', book_hash[:12])
                    logger.info(f"Indexed {len(ids)} annotations from '{book_title}'")

            except Exception as e:
                logger.error(f"Error indexing book {book_hash}: {e}")
                stats['errors'] += 1

        return stats

    def search_annotations(
        self,
        query: str,
        n_results: int = 10,
        filter_metadata: Optional[Dict[str, Any]] = None,
        max_per_book: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Semantic search through annotations.

        Args:
            query: Search query
            n_results: Maximum number of results
            filter_metadata: Optional metadata filter (e.g., {'type': 'highlight'})
            max_per_book: Maximum results per book (None = unlimited)

        Returns:
            List of matching annotations with metadata and scores
        """
        # Fetch more results if we're limiting per book
        fetch_count = n_results * 3 if max_per_book else n_results

        results = self.collection.query(
            query_texts=[query],
            n_results=fetch_count,
            where=filter_metadata
        )

        # Format results
        formatted_results = []

        if results['ids'] and results['ids'][0]:
            book_counts = {}

            for i in range(len(results['ids'][0])):
                metadata = results['metadatas'][0][i]
                book_hash = metadata.get('book_hash', 'unknown')

                # Check per-book limit
                if max_per_book:
                    book_counts[book_hash] = book_counts.get(book_hash, 0) + 1
                    if book_counts[book_hash] > max_per_book:
                        continue

                formatted_results.append({
                    'id': results['ids'][0][i],
                    'text': results['documents'][0][i],
                    'metadata': metadata,
                    'distance': results['distances'][0][i] if 'distances' in results else None
                })

                # Stop when we have enough results
                if len(formatted_results) >= n_results:
                    break

        return formatted_results

    def get_collection_stats(self) -> Dict[str, Any]:
        """Get statistics about the indexed annotations."""
        count = self.collection.count()

        # Get sample to analyze
        if count > 0:
            sample = self.collection.get(limit=min(1000, count))

            # Count by type
            type_counts = {}
            source_counts = {}

            for metadata in sample['metadatas']:
                anno_type = metadata.get('type', 'unknown')
                type_counts[anno_type] = type_counts.get(anno_type, 0) + 1

                source = metadata.get('source', 'unknown')
                source_counts[source] = source_counts.get(source, 0) + 1

            # Count unique books
            unique_books = len(set(m.get('book_hash') for m in sample['metadatas']))

            return {
                'total_annotations': count,
                'unique_books_sampled': unique_books,
                'type_distribution': type_counts,
                'source_distribution': source_counts
            }

        return {'total_annotations': 0}

    def clear_index(self):
        """Clear all annotations from the index."""
        self.chroma_client.delete_collection(self.collection_name)
        self.collection = self.chroma_client.get_or_create_collection(
            name=self.collection_name,
            embedding_function=self.embedding_function,
            metadata={
                "description": "Calibre book annotations with semantic search",
                "embedding_model": self.embedding_model
            }
        )
        logger.info("Annotation index cleared")


def main():
    """CLI for indexing annotations."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Index Calibre annotations for semantic search"
    )
    parser.add_argument(
        '--chroma-dir',
        help='ChromaDB persistence directory',
        default='./chroma_annotations'
    )
    parser.add_argument(
        '--annotations-dir',
        help='Calibre annotations directory (default: auto-detect)'
    )
    parser.add_argument(
        '--reindex',
        action='store_true',
        help='Force reindexing of all annotations'
    )
    parser.add_argument(
        '--stats',
        action='store_true',
        help='Show index statistics'
    )
    parser.add_argument(
        '--search',
        help='Search annotations'
    )
    parser.add_argument(
        '--max-per-book',
        type=int,
        default=2,
        help='Maximum results per book (default: 2, use 0 for unlimited)'
    )

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Create indexer
    indexer = AnnotationsIndexer(
        chroma_persist_dir=args.chroma_dir,
        annotations_dir=args.annotations_dir
    )

    # Show stats
    if args.stats:
        stats = indexer.get_collection_stats()
        print("\n=== Annotation Index Statistics ===")
        print(f"Total annotations: {stats['total_annotations']}")
        if stats['total_annotations'] > 0:
            print(f"Unique books (sampled): {stats.get('unique_books_sampled', 'N/A')}")
            print("\nType distribution:")
            for anno_type, count in stats.get('type_distribution', {}).items():
                print(f"  {anno_type}: {count}")
            print("\nSource distribution:")
            for source, count in stats.get('source_distribution', {}).items():
                print(f"  {source}: {count}")
        return

    # Search
    if args.search:
        max_per_book = args.max_per_book if args.max_per_book > 0 else None
        results = indexer.search_annotations(
            args.search,
            n_results=10,
            max_per_book=max_per_book
        )
        print(f"\n=== Search Results for: '{args.search}' ===")
        if max_per_book:
            print(f"(Max {max_per_book} result{'s' if max_per_book > 1 else ''} per book)\n")
        else:
            print("(Unlimited results per book)\n")

        for i, result in enumerate(results, 1):
            metadata = result['metadata']
            print(f"{i}. {result['text'][:200]}...")

            # Show book title and author if available
            book_title = metadata.get('book_title', 'Unknown Title')
            book_author = metadata.get('book_author', 'Unknown Author')
            print(f"   Book: {book_title} by {book_author}")

            # Show annotation type and page if available
            anno_type = metadata.get('type', 'unknown')
            page_info = f" (page {metadata['page']})" if 'page' in metadata else ""
            print(f"   Type: {anno_type}{page_info}")

            if result['distance'] is not None:
                print(f"   Distance: {result['distance']:.4f}")
            print()
        return

    # Index
    print("Indexing annotations...")
    stats = indexer.index_all_annotations(force_reindex=args.reindex)

    print("\n=== Indexing Complete ===")
    print(f"Books processed: {stats['total_books']}")
    print(f"Annotations indexed: {stats['total_annotations']}")
    print(f"Books skipped: {stats['skipped_books']}")
    print(f"Errors: {stats['errors']}")


if __name__ == '__main__':
    main()
