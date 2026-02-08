"""
LanceDB Storage Backend for ARCHILLES RAG System.

Replaces ChromaDB with native hybrid search support (vector + full-text).
Designed for scalability to 1M+ chunks with IVF-PQ indexing.
"""

import lancedb
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime
import numpy as np
import logging

logger = logging.getLogger(__name__)


class LanceDBStore:
    """
    LanceDB storage backend for ARCHILLES.

    Features:
    - Native hybrid search (vector + FTS in single query)
    - IVF-PQ index for large corpora (>100k chunks)
    - SQL-like metadata filtering
    - Memory-mapped files for efficient I/O
    """

    # Schema definition for chunks table
    SCHEMA = {
        "id": str,
        "text": str,
        "vector": list,  # Will be converted to Vector type

        # Book metadata (from Calibre)
        "book_id": str,
        "book_title": str,
        "author": str,
        "publisher": str,
        "year": int,
        "calibre_id": int,
        "tags": str,
        "language": str,

        # Position metadata
        "chunk_index": int,
        "chunk_type": str,    # "content", "parent", "child", "calibre_comment"
        "page_number": int,   # Physical PDF page (for navigation)
        "page_label": str,    # Printed page label (for citations, e.g. "xiv", "62")
        "chapter": str,

        # Section metadata (EPUB)
        "section": str,
        "section_title": str,
        "section_type": str,

        # Context expansion (Small-to-Big Retrieval)
        "char_start": int,    # Character offset in extracted full text
        "char_end": int,      # Character offset end in extracted full text
        "window_text": str,   # Chunk + ~500 chars context (for expanded retrieval)

        # Parent-Child hierarchy
        "parent_id": str,     # Empty for parents, references parent chunk ID for children

        # Technical metadata
        "source_file": str,
        "format": str,
        "indexed_at": str,
    }

    def __init__(self, db_path: str, table_name: str = "chunks"):
        """
        Initialize LanceDB connection.

        Args:
            db_path: Path to LanceDB database directory
            table_name: Name of the chunks table
        """
        self.db_path = Path(db_path)
        self.table_name = table_name
        self.db = lancedb.connect(str(self.db_path))
        self.table = None
        self._vector_dim = 1024  # BGE-M3 embedding dimension
        self._ensure_table()

    def _ensure_table(self):
        """Create table if it doesn't exist."""
        if self.table_name in self.db.table_names():
            self.table = self.db.open_table(self.table_name)
        else:
            # Table will be created on first add
            self.table = None

    def _create_table_with_data(self, records: List[Dict[str, Any]]):
        """Create table with initial data (LanceDB requires data to infer schema)."""
        self.table = self.db.create_table(
            self.table_name,
            data=records,
            mode="overwrite"
        )

    def create_indexes(self, num_chunks: int = None):
        """
        Create IVF-PQ and FTS indexes for optimal search performance.

        Should be called after bulk indexing is complete.

        Args:
            num_chunks: Total number of chunks (used to calculate partitions)
        """
        if self.table is None:
            logger.warning("No table exists, skipping index creation")
            return

        chunk_count = num_chunks or self.count()

        # Create IVF-PQ vector index only if we have enough data
        if chunk_count >= 256:
            # Calculate optimal partitions (sqrt(n) is a good heuristic)
            num_partitions = min(256, max(16, int(np.sqrt(chunk_count))))

            try:
                logger.info(f"Creating IVF-PQ index with {num_partitions} partitions...")
                self.table.create_index(
                    metric="cosine",
                    num_partitions=num_partitions,
                    num_sub_vectors=32,
                    index_type="IVF_PQ"
                )
                logger.info("Vector index created successfully")
            except Exception as e:
                logger.warning(f"Could not create vector index: {e}")
        else:
            logger.info(f"Skipping IVF-PQ index (need 256+ chunks, have {chunk_count})")

        # Always create FTS index for hybrid search
        self.create_fts_index()

    def create_fts_index(self):
        """Create full-text search index on text column."""
        if self.table is None:
            logger.warning("No table exists, skipping FTS index creation")
            return

        try:
            logger.info("Creating FTS index on text column...")
            self.table.create_fts_index("text", replace=True)
            logger.info("FTS index created successfully")
        except Exception as e:
            logger.warning(f"Could not create FTS index: {e}")

    def add_chunks(self, chunks: List[Dict[str, Any]], embeddings: np.ndarray) -> int:
        """
        Add chunks with their embeddings to the database.

        Args:
            chunks: List of chunk dictionaries with metadata
            embeddings: Numpy array of embeddings (shape: [n_chunks, embedding_dim])

        Returns:
            Number of chunks added
        """
        if len(chunks) == 0:
            return 0

        # Check existing schema to handle backward compatibility
        existing_columns = set()
        if self.table is not None:
            try:
                existing_columns = set(self.table.schema.names)
            except Exception:
                pass

        records = []
        for i, chunk in enumerate(chunks):
            record = {
                "id": chunk.get("id", f"chunk_{i}"),
                "text": chunk.get("text", ""),
                "vector": embeddings[i].tolist(),

                # Book metadata
                "book_id": chunk.get("book_id", ""),
                "book_title": chunk.get("book_title", chunk.get("title", "")),
                "author": chunk.get("author", ""),
                "publisher": chunk.get("publisher", ""),
                "year": chunk.get("year") or 0,
                "calibre_id": chunk.get("calibre_id") or 0,
                "tags": chunk.get("tags", ""),
                "language": chunk.get("language", ""),

                # Position metadata
                "chunk_index": chunk.get("chunk_index", i),
                "chunk_type": chunk.get("chunk_type", "content"),
                "page_number": chunk.get("page_number") or chunk.get("page") or 0,
                "chapter": chunk.get("chapter", ""),

                # Section metadata (EPUB)
                "section": chunk.get("section", ""),
                "section_title": chunk.get("section_title", ""),
                "section_type": chunk.get("section_type", ""),

                # Context expansion (Small-to-Big Retrieval)
                "char_start": chunk.get("char_start") or 0,
                "char_end": chunk.get("char_end") or 0,
                "window_text": chunk.get("window_text", ""),

                # Parent-Child hierarchy
                "parent_id": chunk.get("parent_id", ""),

                # Technical metadata
                "source_file": chunk.get("source_file", ""),
                "format": chunk.get("format", ""),
                "indexed_at": chunk.get("indexed_at", datetime.now().isoformat()),
            }

            # Add page_label only if table supports it or is new
            if not existing_columns or "page_label" in existing_columns:
                record["page_label"] = chunk.get("page_label", "")

            # Backward compat: only add new fields if table supports them or is new
            if existing_columns and "char_start" not in existing_columns:
                for field in ("char_start", "char_end", "window_text", "parent_id"):
                    record.pop(field, None)

            records.append(record)

        if self.table is None:
            self._create_table_with_data(records)
        else:
            self.table.add(records)

        return len(records)

    def hybrid_search(
        self,
        query_text: str,
        query_vector: np.ndarray,
        top_k: int = 10,
        book_id: Optional[str] = None,
        calibre_id: Optional[int] = None,
        section_type: Optional[str] = None,
        chunk_type: Optional[str] = None,
        language: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Hybrid search combining vector similarity and full-text search.

        Uses LanceDB's native hybrid search with reranking.

        Args:
            query_text: Search query text (for FTS)
            query_vector: Query embedding vector
            top_k: Number of results to return
            book_id: Filter by book_id
            calibre_id: Filter by Calibre ID
            section_type: Filter by section type ("main", "front_matter", "back_matter")
            chunk_type: Filter by chunk type ("content", "phase1_metadata", etc.)
            language: Filter by language code

        Returns:
            List of result dictionaries with metadata and scores
        """
        if self.table is None:
            return []

        # Build filter string
        filters = self._build_filter(
            book_id=book_id,
            calibre_id=calibre_id,
            section_type=section_type,
            chunk_type=chunk_type,
            language=language
        )

        try:
            # Try hybrid search first using explicit vector() and text() methods
            search = self.table.search(query_type="hybrid") \
                .vector(query_vector.tolist()) \
                .text(query_text)

            if filters:
                search = search.where(filters)

            results = search.limit(top_k).to_pandas()
        except Exception as e:
            # Fallback to vector-only search if hybrid fails
            logger.warning(f"Hybrid search failed, falling back to vector: {e}")
            results = self.vector_search(
                query_vector=query_vector,
                top_k=top_k,
                book_id=book_id,
                calibre_id=calibre_id,
                section_type=section_type,
                chunk_type=chunk_type,
                language=language
            )
            return results

        return self._results_to_dicts(results)

    def vector_search(
        self,
        query_vector: np.ndarray,
        top_k: int = 10,
        book_id: Optional[str] = None,
        calibre_id: Optional[int] = None,
        section_type: Optional[str] = None,
        chunk_type: Optional[str] = None,
        language: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Pure vector similarity search.

        Args:
            query_vector: Query embedding vector
            top_k: Number of results to return
            book_id: Filter by book_id
            calibre_id: Filter by Calibre ID
            section_type: Filter by section type
            chunk_type: Filter by chunk type
            language: Filter by language code

        Returns:
            List of result dictionaries with metadata and scores
        """
        if self.table is None:
            return []

        filters = self._build_filter(
            book_id=book_id,
            calibre_id=calibre_id,
            section_type=section_type,
            chunk_type=chunk_type,
            language=language
        )

        search = self.table.search(query_vector.tolist())

        if filters:
            search = search.where(filters)

        results = search.limit(top_k).to_pandas()
        return self._results_to_dicts(results)

    def fts_search(
        self,
        query_text: str,
        top_k: int = 10,
        book_id: Optional[str] = None,
        calibre_id: Optional[int] = None,
        section_type: Optional[str] = None,
        chunk_type: Optional[str] = None,
        language: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Pure full-text search (good for proper nouns, dates, exact phrases).

        Args:
            query_text: Search query text
            top_k: Number of results to return
            book_id: Filter by book_id
            calibre_id: Filter by Calibre ID
            section_type: Filter by section type
            chunk_type: Filter by chunk type
            language: Filter by language code

        Returns:
            List of result dictionaries with metadata and scores
        """
        if self.table is None:
            return []

        filters = self._build_filter(
            book_id=book_id,
            calibre_id=calibre_id,
            section_type=section_type,
            chunk_type=chunk_type,
            language=language
        )

        search = self.table.search(query_text, query_type="fts")

        if filters:
            search = search.where(filters)

        results = search.limit(top_k).to_pandas()
        return self._results_to_dicts(results)

    def _build_filter(
        self,
        book_id: Optional[str] = None,
        calibre_id: Optional[int] = None,
        section_type: Optional[str] = None,
        chunk_type: Optional[str] = None,
        language: Optional[str] = None,
    ) -> Optional[str]:
        """Build SQL-like filter string for LanceDB queries."""
        conditions = []

        if book_id:
            conditions.append(f"book_id = '{book_id}'")

        if calibre_id:
            conditions.append(f"calibre_id = {calibre_id}")

        if section_type:
            if section_type == "main":
                # Exclude front_matter and back_matter
                conditions.append("(section_type = 'main_content' OR section_type = '')")
            else:
                conditions.append(f"section_type = '{section_type}'")

        if chunk_type:
            if chunk_type == "content":
                # Include both flat chunks ("content") and hierarchical children ("child")
                # Parents are excluded — they serve as context, not search targets
                conditions.append("(chunk_type = 'content' OR chunk_type = 'child')")
            else:
                conditions.append(f"chunk_type = '{chunk_type}'")

        if language:
            conditions.append(f"language = '{language}'")

        return " AND ".join(conditions) if conditions else None

    def _results_to_dicts(self, df) -> List[Dict[str, Any]]:
        """Convert pandas DataFrame results to list of dictionaries."""
        if df is None or len(df) == 0:
            return []

        results = []
        for _, row in df.iterrows():
            result = row.to_dict()
            # Convert distance/score columns to unified 'score' field
            # LanceDB returns different columns depending on search type:
            # - _distance: vector search (cosine distance, lower is better)
            # - _score: FTS search (higher is better)
            # - _relevance_score: hybrid search (higher is better)
            if '_distance' in result:
                result['score'] = 1.0 - result['_distance']
                del result['_distance']
            elif '_relevance_score' in result:
                result['score'] = result['_relevance_score']
                del result['_relevance_score']
            elif '_score' in result:
                result['score'] = result['_score']
                del result['_score']
            else:
                result['score'] = 0.0

            # Remove vector from results (too large)
            if 'vector' in result:
                del result['vector']

            results.append(result)

        return results

    def delete_by_book_id(self, book_id: str) -> int:
        """
        Delete all chunks for a specific book.

        Args:
            book_id: The book_id to delete

        Returns:
            Number of chunks deleted (approximate)
        """
        if self.table is None:
            return 0

        count_before = self.count()
        self.table.delete(f"book_id = '{book_id}'")
        count_after = self.count()

        return count_before - count_after

    def delete_by_calibre_id(self, calibre_id: int) -> int:
        """
        Delete all chunks for a specific Calibre ID.

        Args:
            calibre_id: The Calibre ID to delete

        Returns:
            Number of chunks deleted (approximate)
        """
        if self.table is None:
            return 0

        count_before = self.count()
        self.table.delete(f"calibre_id = {calibre_id}")
        count_after = self.count()

        return count_before - count_after

    def get_by_book_id(self, book_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get all chunks for a specific book.

        Args:
            book_id: The book_id to query
            limit: Maximum number of chunks to return

        Returns:
            List of chunk dictionaries
        """
        if self.table is None:
            return []

        df = self.table.search().where(f"book_id = '{book_id}'").limit(limit).to_pandas()
        return self._results_to_dicts(df)

    def get_by_calibre_id(self, calibre_id: int, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get all chunks for a specific Calibre ID.

        Args:
            calibre_id: The Calibre ID to query
            limit: Maximum number of chunks to return

        Returns:
            List of chunk dictionaries
        """
        if self.table is None:
            return []

        df = self.table.search().where(f"calibre_id = {calibre_id}").limit(limit).to_pandas()
        return self._results_to_dicts(df)

    def get_by_id(self, chunk_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a single chunk by its ID (used for parent lookup).

        Args:
            chunk_id: The chunk ID to retrieve

        Returns:
            Chunk dictionary, or None if not found
        """
        if self.table is None:
            return None

        df = self.table.search().where(f"id = '{chunk_id}'").limit(1).to_pandas()
        results = self._results_to_dicts(df)
        return results[0] if results else None

    def get_all(self, limit: int = 1000, offset: int = 0) -> List[Dict[str, Any]]:
        """
        Get all chunks (with pagination).

        Args:
            limit: Maximum number of chunks to return
            offset: Number of chunks to skip

        Returns:
            List of chunk dictionaries
        """
        if self.table is None:
            return []

        # LanceDB doesn't have native offset, so we fetch more and slice
        df = self.table.to_pandas()
        df = df.iloc[offset:offset + limit]
        return df.to_dict(orient="records")

    def get_indexed_books(self) -> List[Dict[str, Any]]:
        """
        Get list of all indexed books with statistics.

        Returns:
            List of dictionaries with book_id, title, author, chunk_count, etc.
        """
        if self.table is None:
            return []

        df = self.table.to_pandas()

        # Group by book_id and aggregate
        books = df.groupby("book_id").agg({
            "book_title": "first",
            "author": "first",
            "calibre_id": "first",
            "year": "first",
            "format": "first",
            "tags": "first",
            "id": "count",  # Count chunks
            "indexed_at": "max"  # Latest indexing time
        }).reset_index()

        books.columns = [
            "book_id", "title", "author", "calibre_id",
            "year", "format", "tags", "chunks", "indexed_at"
        ]

        return books.to_dict(orient="records")

    def count(self) -> int:
        """Get total number of chunks in the database."""
        if self.table is None:
            return 0
        return self.table.count_rows()

    def get_stats(self) -> Dict[str, Any]:
        """
        Get database statistics.

        Returns:
            Dictionary with total_chunks, total_books, file_types, etc.
        """
        if self.table is None:
            return {
                "total_chunks": 0,
                "total_books": 0,
                "avg_chunks_per_book": 0,
                "file_types": {},
                "section_types": {},
            }

        df = self.table.to_pandas()

        return {
            "total_chunks": len(df),
            "total_books": df["book_id"].nunique(),
            "avg_chunks_per_book": len(df) / max(1, df["book_id"].nunique()),
            "file_types": df["format"].value_counts().to_dict() if "format" in df else {},
            "section_types": df["section_type"].value_counts().to_dict() if "section_type" in df else {},
            "languages": df["language"].value_counts().to_dict() if "language" in df else {},
        }

    def close(self):
        """Close the database connection."""
        # LanceDB doesn't require explicit close, but we reset references
        self.table = None
        self.db = None
