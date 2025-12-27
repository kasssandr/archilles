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

        Uses comprehensive path variant testing to handle library migrations.

        Strategy:
        1. Get all books from Calibre metadata.db (including stable book IDs)
        2. For each book, test MANY path variants (different drives, locations)
        3. Use the book ID in the path as a stable identifier
        4. Test 100+ path combinations per book to maximize match probability

        This handles cases where:
        - Library was moved between drives (E: → D:)
        - Library was moved between folders
        - Drive letters changed

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

        # Generate comprehensive path variants
        path_bases = []

        # 1. Current library path
        path_bases.append(str(self.library_path))

        # 2. All drive letters (A: through Z:) - comprehensive search
        current_path_without_drive = str(self.library_path)[2:] if len(str(self.library_path)) > 2 else ""

        if current_path_without_drive:
            for letter in 'CDEFGHIJKLMNOPQRSTUVWXYZ':
                path_bases.append(f"{letter}:{current_path_without_drive}")

        # 3. Common library locations with all drives
        library_name = Path(self.library_path).name  # e.g., "Calibre-Bibliothek"
        common_parent_paths = [
            "",  # Root
            "\\Users\\tomra",
            "\\Users\\tomra\\Documents",
            "\\Users\\tomra\\OneDrive",
            "\\Users\\tomra\\Desktop",
            "\\",
            "\\Books",
            "\\eBooks",
            "\\Documents"
        ]

        library_name_variants = [
            library_name,  # Current name
            'Calibre-Bibliothek',
            'Calibre Library',
            'Calibre',
            'calibre',
            'Books',
            'eBooks'
        ]

        # Combine drives + parents + library names
        for letter in 'CDEFGH':  # Most common drives for testing
            for parent in common_parent_paths[:4]:  # Limit combinations
                for lib_name in library_name_variants[:3]:
                    path_bases.append(f"{letter}:{parent}\\{lib_name}")

        # Remove duplicates while preserving order
        seen = set()
        path_bases = [x for x in path_bases if not (x in seen or seen.add(x))]

        logger.info(f"Testing {len(path_bases)} path base variants for hash matching...")

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
            rows = cursor.fetchall()

            books_matched = 0

            for row in rows:
                relative_path = row['path']  # e.g., "Author\Title (123)"
                filename = f"{row['filename']}.{row['format']}"

                book_metadata = {
                    'book_id': row['id'],
                    'title': row['title'],
                    'author': row['author'] or 'Unknown',
                    'format': row['format']
                }

                current_path = Path(self.library_path) / relative_path / filename
                book_matched = False

                # Test all path variants for this book
                for base_path in path_bases:
                    try:
                        # Construct full path with this base
                        test_path_str = f"{base_path}\\{relative_path}\\{filename}"

                        # Test multiple slash variants (Windows path normalization)
                        path_variants = [
                            test_path_str,  # Original with backslashes
                            test_path_str.replace('\\', '/'),  # Forward slashes
                            str(Path(test_path_str)),  # Platform normalized
                        ]

                        for path_variant in set(path_variants):  # Remove duplicates
                            test_hash = compute_book_hash(path_variant)

                            if test_hash not in hash_mapping:
                                hash_mapping[test_hash] = {
                                    **book_metadata,
                                    'path': str(current_path),  # Store current path
                                    'original_path_base': base_path  # Track which base worked
                                }
                                book_matched = True
                    except Exception as e:
                        # Skip invalid path combinations
                        continue

                if book_matched:
                    books_matched += 1

            conn.close()
            logger.info(f"Created hash mapping: {len(hash_mapping)} hash variants from {len(rows)} books")
            logger.info(f"Books with at least one hash variant: {books_matched}/{len(rows)}")

        except Exception as e:
            logger.error(f"Failed to create hash mapping: {e}")

        return hash_mapping

    def _fuzzy_match_book(
        self,
        annotation_hash: str,
        annotation_file: Path,
        calibre_books: List[Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """
        Fallback: Try to match annotation to book using fuzzy matching.

        When hash-matching fails (library path changed), try to match based on:
        1. Title/author similarity to annotation text
        2. Filename keyword matching
        3. Content-based matching

        Args:
            annotation_hash: Hash of annotation file
            annotation_file: Path to annotation JSON file
            calibre_books: List of all Calibre books with metadata

        Returns:
            Best matching book metadata or None
        """
        try:
            # Read annotation file to get clues
            with open(annotation_file, 'r', encoding='utf-8') as f:
                annotations = json.load(f)

            if not isinstance(annotations, list) or not annotations:
                return None

            # Strategy: Use difflib for fuzzy string matching
            from difflib import SequenceMatcher

            best_match = None
            best_score = 0.0
            min_score = 0.6  # Minimum similarity threshold

            # Collect text snippets from annotations for matching
            annotation_texts = []
            for anno in annotations[:5]:  # Use first 5 annotations
                text = anno.get('highlighted_text', '')
                if text:
                    annotation_texts.append(text.lower())

            combined_text = ' '.join(annotation_texts)[:500]

            # Try matching against each Calibre book
            for book in calibre_books:
                score = 0.0

                # 1. Match based on title similarity
                if book.get('title'):
                    title = book['title'].lower()
                    # Check if title appears in annotation text
                    if title in combined_text:
                        score += 0.8
                    else:
                        # Fuzzy match title
                        title_sim = SequenceMatcher(None, title, combined_text[:len(title)*3]).ratio()
                        score += title_sim * 0.3

                # 2. Match based on author similarity
                if book.get('author'):
                    author = book['author'].lower()
                    if author in combined_text:
                        score += 0.5
                    else:
                        author_sim = SequenceMatcher(None, author, combined_text[:len(author)*3]).ratio()
                        score += author_sim * 0.2

                # 3. Match based on filename similarity
                if book.get('filename'):
                    filename = book['filename'].lower()
                    filename_parts = filename.split()
                    for part in filename_parts:
                        if len(part) > 3 and part in combined_text:
                            score += 0.1

                # Update best match if this score is higher
                if score > best_score and score >= min_score:
                    best_score = score
                    best_match = {
                        'book_id': book['id'],
                        'title': book['title'],
                        'author': book.get('author', 'Unknown'),
                        'path': str(Path(self.library_path) / book['path'] / f"{book['filename']}.{book['format']}"),
                        'format': book['format'],
                        'match_score': score
                    }

            if best_match:
                logger.info(f"Fuzzy matched {annotation_hash[:12]} to '{best_match['title']}' (score: {best_score:.2f})")
                return best_match

            return None

        except Exception as e:
            logger.debug(f"Could not fuzzy match {annotation_hash[:12]}: {e}")
            return None

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
            logger.info(f"Mapped {len(hash_mapping)} hash variants from library")
        else:
            logger.warning("No hash mapping available - will use placeholder paths")

        # Get all Calibre books for fuzzy matching fallback
        calibre_books = []
        if self.library_path:
            try:
                import sqlite3
                db_path = Path(self.library_path) / "metadata.db"
                if db_path.exists():
                    conn = sqlite3.connect(str(db_path))
                    conn.row_factory = sqlite3.Row
                    query = """
                    SELECT books.id, books.title, books.path,
                           data.name as filename, data.format,
                           (SELECT name FROM authors
                            JOIN books_authors_link ON authors.id = books_authors_link.author
                            WHERE books_authors_link.book = books.id
                            LIMIT 1) as author
                    FROM books
                    JOIN data ON books.id = data.book
                    WHERE data.format IN ('EPUB', 'PDF', 'MOBI', 'AZW3')
                    """
                    cursor = conn.execute(query)
                    calibre_books = [dict(row) for row in cursor.fetchall()]
                    conn.close()
            except Exception as e:
                logger.debug(f"Could not load Calibre books for fuzzy matching: {e}")

        # Report hash matching effectiveness
        if hash_mapping:
            # Count how many actual annotation files we have
            annots_dir_path = Path(self.annotations_dir)
            actual_anno_hashes = {f.stem for f in annots_dir_path.glob("*.json")}
            matched_hashes = actual_anno_hashes & set(hash_mapping.keys())

            logger.info(f"Annotation files: {len(actual_anno_hashes)}")
            logger.info(f"Hash mapping size: {len(hash_mapping)}")
            logger.info(f"Direct hash matches: {len(matched_hashes)}/{len(actual_anno_hashes)}")

            if len(matched_hashes) > 0:
                # Show sample matches with their path bases
                sample_matches = list(matched_hashes)[:3]
                logger.info("Sample matched annotation hashes:")
                for anno_hash in sample_matches:
                    book_info = hash_mapping[anno_hash]
                    original_base = book_info.get('original_path_base', 'unknown')
                    logger.info(f"  {anno_hash[:16]}... → '{book_info['title']}' (base: {original_base})")
            else:
                logger.warning("No direct hash matches found - will use fuzzy matching for all books")

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

                # If hash didn't match, try fuzzy matching
                if not book_meta and calibre_books:
                    anno_file = Path(self.annotations_dir) / f"{book_hash}.json"
                    book_meta = self._fuzzy_match_book(book_hash, anno_file, calibre_books)
                    if book_meta:
                        logger.info(f"Fuzzy matched annotation {book_hash[:12]} to '{book_meta.get('title', 'Unknown')}'")

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
