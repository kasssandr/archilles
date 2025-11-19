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
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False

from .annotations import (
    list_all_annotated_books,
    get_combined_annotations,
    get_annotations_dir
)

logger = logging.getLogger(__name__)


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
        collection_name: str = "calibre_annotations"
    ):
        """
        Initialize the annotations indexer.

        Args:
            chroma_persist_dir: Directory to persist ChromaDB data
            annotations_dir: Calibre annotations directory
            collection_name: Name of ChromaDB collection
        """
        if not CHROMADB_AVAILABLE:
            raise ImportError(
                "ChromaDB is required for semantic search. "
                "Install with: pip install chromadb"
            )

        self.annotations_dir = annotations_dir or str(get_annotations_dir())
        self.collection_name = collection_name

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

        # Get or create collection
        self.collection = self.chroma_client.get_or_create_collection(
            name=collection_name,
            metadata={"description": "Calibre book annotations with semantic search"}
        )

    def _create_annotation_id(self, book_hash: str, index: int) -> str:
        """Create unique ID for annotation."""
        return f"{book_hash}_anno_{index}"

    def _prepare_annotation_text(self, annotation: Dict[str, Any]) -> str:
        """
        Prepare annotation text for embedding.

        Combines highlighted_text and notes into searchable text.
        """
        text_parts = []

        highlighted = annotation.get('highlighted_text', '').strip()
        if highlighted:
            text_parts.append(highlighted)

        notes = annotation.get('notes', '').strip()
        if notes:
            text_parts.append(f"Note: {notes}")

        return " | ".join(text_parts)

    def _prepare_annotation_metadata(
        self,
        annotation: Dict[str, Any],
        book_hash: str,
        book_path: str
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
            'errors': 0
        }

        # Get all annotated books
        annotated_books = list_all_annotated_books(self.annotations_dir)

        if not annotated_books:
            logger.warning("No annotated books found")
            return stats

        stats['total_books'] = len(annotated_books)

        # For each book, we need to find the actual book path
        # Since we only have the hash, we need to scan the library
        # This is a limitation - ideally we'd have a mapping

        # For now, we'll use a workaround:
        # Read annotations directly and use hash as identifier
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

                # Read annotations file directly
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
                        f"hash:{book_hash}"  # Placeholder path
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
                    logger.info(f"Indexed {len(ids)} annotations from {book_hash}")

            except Exception as e:
                logger.error(f"Error indexing book {book_hash}: {e}")
                stats['errors'] += 1

        return stats

    def search_annotations(
        self,
        query: str,
        n_results: int = 10,
        filter_metadata: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Semantic search through annotations.

        Args:
            query: Search query
            n_results: Maximum number of results
            filter_metadata: Optional metadata filter (e.g., {'type': 'highlight'})

        Returns:
            List of matching annotations with metadata and scores
        """
        results = self.collection.query(
            query_texts=[query],
            n_results=n_results,
            where=filter_metadata
        )

        # Format results
        formatted_results = []

        if results['ids'] and results['ids'][0]:
            for i in range(len(results['ids'][0])):
                formatted_results.append({
                    'id': results['ids'][0][i],
                    'text': results['documents'][0][i],
                    'metadata': results['metadatas'][0][i],
                    'distance': results['distances'][0][i] if 'distances' in results else None
                })

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
            metadata={"description": "Calibre book annotations with semantic search"}
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
        results = indexer.search_annotations(args.search, n_results=5)
        print(f"\n=== Search Results for: '{args.search}' ===\n")
        for i, result in enumerate(results, 1):
            print(f"{i}. {result['text'][:200]}...")
            print(f"   Book: {result['metadata'].get('book_path', 'N/A')}")
            print(f"   Type: {result['metadata'].get('type')}")
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
