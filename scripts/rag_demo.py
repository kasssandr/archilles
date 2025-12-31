#!/usr/bin/env python3
"""
ARCHILLES RAG System with Hybrid Search

Features:
1. Extract text from books (30+ formats: PDF, EPUB, DJVU, MOBI, etc.)
2. BGE-M3 embeddings (multilingual, optimized for German/Latin/Greek)
3. BM25 keyword search (exact word matching)
4. Hybrid search (semantic + keyword via Reciprocal Rank Fusion)
5. Language filtering (auto-detected: de, en, la, fr, etc.)
6. ChromaDB local storage (100% offline)

Search Modes:
- hybrid (default): Best of both worlds - finds concepts AND exact words
- semantic: Concept-based search using BGE-M3 embeddings
- keyword: Exact word matching using BM25 (great for Latin phrases, custom terms)

Usage:
    # Index a book
    python scripts/rag_demo.py index "path/to/book.pdf" --book-id "Josephus"

    # Hybrid search (recommended - combines semantic + keyword)
    python scripts/rag_demo.py query "evangelista et a presbyteris"

    # Keyword-only (exact word matching)
    python scripts/rag_demo.py query "Herrschaftslegitimation" --mode keyword

    # With language filter
    python scripts/rag_demo.py query "Rex" --language la --mode hybrid
"""

import sys
import argparse
from pathlib import Path
from typing import List, Dict, Any, Literal
import time
import pickle
import re
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.extractors import UniversalExtractor
from src.calibre_db import CalibreDB
import chromadb
from sentence_transformers import SentenceTransformer
from tqdm import tqdm
import os

try:
    from rank_bm25 import BM25Okapi
    BM25_AVAILABLE = True
except ImportError:
    BM25_AVAILABLE = False


class ChromaDBCorruptionError(Exception):
    """Raised when ChromaDB index is corrupted and needs to be reset."""
    pass


class archillesRAG:
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
        db_path: str = "./archilles_rag_db",
        model_name: str = "BAAI/bge-m3",
        reset_db: bool = False
    ):
        """
        Initialize RAG system.

        Args:
            db_path: Path to ChromaDB storage
            model_name: Sentence transformer model (default: BGE-M3)
            reset_db: If True, delete and recreate the database (use for recovery from corruption)
        """
        print(f"?? Initializing ARCHILLES RAG...")
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
        print(f"  ? Model loaded: {model_name}")

        # Handle database reset if requested
        if reset_db:
            print(f"  ? Resetting database (deleting corrupted data)...")
            import shutil
            db_path_obj = Path(db_path)
            if db_path_obj.exists():
                shutil.rmtree(db_path_obj)
                print(f"    ? Deleted {db_path}")

        # Initialize ChromaDB with error handling for corruption
        try:
            self.chroma_client = chromadb.PersistentClient(path=db_path)

            # Get or create collection
            self.collection = self.chroma_client.get_or_create_collection(
                name="archilles_books",
                metadata={"hnsw:space": "cosine"}
            )

            print(f"  ? ChromaDB ready")

            # Try to count chunks - this will fail if database is corrupted
            try:
                chunk_count = self.collection.count()
                print(f"  Current index: {chunk_count} chunks")
            except Exception as count_error:
                # ChromaDB corruption detected
                raise ChromaDBCorruptionError(
                    f"ChromaDB index is corrupted (likely from interrupted indexing).\n"
                    f"Error: {count_error}\n\n"
                    f"To recover, run with --reset-db flag:\n"
                    f"  python scripts/batch_index.py --tag \"YourTag\" --reset-db\n\n"
                    f"WARNING: This will delete the entire index. You'll need to re-index all books."
                )

        except Exception as e:
            # Check if this is a known corruption error
            if "hnsw" in str(e).lower() or "compactor" in str(e).lower():
                raise ChromaDBCorruptionError(
                    f"ChromaDB index is corrupted (likely from interrupted indexing).\n"
                    f"Error: {e}\n\n"
                    f"To recover, run with --reset-db flag:\n"
                    f"  python scripts/batch_index.py --tag \"YourTag\" --reset-db\n\n"
                    f"WARNING: This will delete the entire index. You'll need to re-index all books."
                )
            else:
                # Re-raise other errors
                raise

        # Initialize BM25 index for hybrid search
        self.db_path = Path(db_path)
        self.bm25_index = None
        self.bm25_docs = None
        self.bm25_ids = None
        self.bm25_metadatas = None  # Cache metadata to avoid SQLite variable limit

        # Load BM25 index (skip if database was just reset)
        if not reset_db:
            self._load_bm25_index()
        else:
            print(f"  ? BM25 index will be built on first indexing")

        if BM25_AVAILABLE and self.bm25_index:
            print(f"  ? BM25 keyword search ready\n")
        elif not BM25_AVAILABLE:
            print(f"  ? BM25 not available (install: pip install rank-bm25)\n")
        else:
            print(f"  ? BM25 index empty (will be built on first indexing)\n")

    def _extract_metadata(self, file_path: Path) -> Dict[str, Any]:
        """
        Universal metadata extraction with Calibre integration.

        Priority:
        1. File metadata (EPUB/PDF embedded metadata)
        2. Calibre database (fallback for ISBN, etc.)

        Args:
            file_path: Path to book file

        Returns:
            Dictionary with metadata + isbn_source tracking
        """
        file_ext = file_path.suffix.lower()

        # Extract from file first
        if file_ext == '.pdf':
            file_metadata = self._extract_pdf_metadata(file_path)
        elif file_ext == '.epub':
            file_metadata = self._extract_epub_metadata(file_path)
        else:
            file_metadata = {}

        # Try Calibre database for missing fields (especially ISBN)
        calibre_metadata = self._extract_calibre_metadata(file_path)

        # Merge: File metadata takes priority, Calibre fills gaps
        merged = {}

        # Always prefer file metadata
        merged.update(calibre_metadata)  # Calibre first (lower priority)
        merged.update(file_metadata)     # File second (higher priority)

        # Track ISBN source
        if merged.get('isbn'):
            if file_metadata.get('isbn'):
                merged['isbn_source'] = 'file'
            elif calibre_metadata.get('isbn'):
                merged['isbn_source'] = 'calibre'

        return merged

    def _extract_pdf_metadata(self, file_path: Path) -> Dict[str, Any]:
        """Extract metadata from PDF files."""
        metadata = {}

        try:
            import fitz  # PyMuPDF

            doc = fitz.open(str(file_path))
            pdf_info = doc.metadata

            # Extract standard PDF metadata
            if pdf_info:
                # Author
                if pdf_info.get('author'):
                    metadata['author'] = pdf_info['author'].strip()

                # Title
                if pdf_info.get('title'):
                    metadata['title'] = pdf_info['title'].strip()

                # Subject (often used for subtitle/description)
                if pdf_info.get('subject'):
                    metadata['subject'] = pdf_info['subject'].strip()

                # Keywords
                if pdf_info.get('keywords'):
                    metadata['keywords'] = pdf_info['keywords'].strip()

                # Creation/Modification date (extract year)
                if pdf_info.get('creationDate'):
                    try:
                        # Format: D:20191203... (YYYYMMDD)
                        date_str = pdf_info['creationDate']
                        if date_str.startswith('D:') and len(date_str) >= 6:
                            year_str = date_str[2:6]
                            metadata['year'] = int(year_str)
                    except (ValueError, IndexError):
                        pass

                # Producer/Creator (often contains software used)
                if pdf_info.get('creator'):
                    metadata['creator'] = pdf_info['creator'].strip()

            doc.close()

        except Exception as e:
            # Silently fail if metadata extraction doesn't work
            pass

        return metadata

    def _extract_epub_metadata(self, file_path: Path) -> Dict[str, Any]:
        """Extract metadata from EPUB files using Dublin Core standards."""
        metadata = {}

        try:
            from ebooklib import epub

            book = epub.read_epub(str(file_path))

            # Dublin Core metadata (standard for EPUBs)
            # Author
            author = book.get_metadata('DC', 'creator')
            if author and author[0]:
                metadata['author'] = str(author[0][0]).strip()

            # Title
            title = book.get_metadata('DC', 'title')
            if title and title[0]:
                metadata['title'] = str(title[0][0]).strip()

            # Publisher
            publisher = book.get_metadata('DC', 'publisher')
            if publisher and publisher[0]:
                metadata['publisher'] = str(publisher[0][0]).strip()

            # Language
            language = book.get_metadata('DC', 'language')
            if language and language[0]:
                metadata['language'] = str(language[0][0]).strip()

            # Date/Year
            date = book.get_metadata('DC', 'date')
            if date and date[0]:
                try:
                    date_str = str(date[0][0])
                    # Try to extract year (formats: YYYY, YYYY-MM-DD, etc.)
                    import re
                    year_match = re.search(r'(\d{4})', date_str)
                    if year_match:
                        metadata['year'] = int(year_match.group(1))
                except (ValueError, AttributeError):
                    pass

            # ISBN
            identifier = book.get_metadata('DC', 'identifier')
            if identifier:
                for id_tuple in identifier:
                    id_str = str(id_tuple[0]).strip()
                    # Check if it's an ISBN (formats: "isbn:123", "ISBN 123", "123" with 10/13 digits)
                    if 'isbn' in id_str.lower():
                        # Extract just the ISBN number (remove "isbn:" prefix)
                        isbn_clean = id_str.lower().replace('isbn:', '').replace('isbn', '').strip()
                        metadata['isbn'] = isbn_clean
                        break
                    elif id_str.replace('-', '').replace(' ', '').isdigit() and len(id_str.replace('-', '').replace(' ', '')) in [10, 13]:
                        # Pure numeric ISBN without prefix
                        metadata['isbn'] = id_str
                        break

            # Subject/Keywords
            subject = book.get_metadata('DC', 'subject')
            if subject and subject[0]:
                # Can have multiple subjects
                subjects = [str(s[0]).strip() for s in subject if s]
                metadata['subject'] = ', '.join(subjects)

            # Description (often contains book summary)
            description = book.get_metadata('DC', 'description')
            if description and description[0]:
                metadata['description'] = str(description[0][0]).strip()

        except Exception as e:
            # Silently fail if metadata extraction doesn't work
            pass

        return metadata

    def _extract_calibre_metadata(self, file_path: Path) -> Dict[str, Any]:
        """
        Extract metadata from Calibre database (read-only).

        Args:
            file_path: Path to book file

        Returns:
            Dictionary with Calibre metadata (empty if not in Calibre library)
        """
        metadata = {}

        try:
            # Find Calibre library
            library_path = CalibreDB.find_library_path(file_path)
            if not library_path:
                return metadata

            # Query Calibre DB
            with CalibreDB(library_path) as calibre:
                book_data = calibre.get_book_by_path(file_path)

                if book_data:
                    # Map Calibre fields to our metadata
                    if book_data.get('author'):
                        metadata['author'] = book_data['author']
                    if book_data.get('title'):
                        metadata['title'] = book_data['title']
                    if book_data.get('publisher'):
                        metadata['publisher'] = book_data['publisher']
                    if book_data.get('language'):
                        metadata['language'] = book_data['language']
                    if book_data.get('isbn'):
                        metadata['isbn'] = book_data['isbn']
                    if book_data.get('calibre_id'):
                        metadata['calibre_id'] = book_data['calibre_id']
                    if book_data.get('tags'):
                        metadata['tags'] = book_data['tags']
                    if book_data.get('comments'):
                        metadata['comments'] = book_data['comments']
                    if book_data.get('custom_fields'):
                        metadata['custom_fields'] = book_data['custom_fields']

        except Exception as e:
            # Silently fail if Calibre DB not available
            pass

        return metadata

    def index_book(self, book_path: str, book_id: str = None, force: bool = False) -> Dict[str, Any]:
        """
        Extract and index a book.

        Args:
            book_path: Path to book file
            book_id: Optional book ID (default: filename)
            force: If True, delete existing chunks before re-indexing

        Returns:
            Dictionary with indexing statistics
        """
        book_path = Path(book_path)

        if not book_path.exists():
            raise FileNotFoundError(f"Book not found: {book_path}")

        book_id = book_id or book_path.stem

        print(f"📚 INDEXING BOOK: {book_path.name}")
        print(f"  Book ID: {book_id}\n")

        # Check for existing chunks and handle force reindex
        existing = self.collection.get(where={"book_id": book_id})
        if existing and existing['ids']:
            if force:
                print(f"  🗑️  Deleting {len(existing['ids'])} existing chunks...", flush=True)
                self.collection.delete(ids=existing['ids'])
            else:
                print(f"  ⚠️  Book already indexed ({len(existing['ids'])} chunks). Use --force to reindex.")
                return {
                    'book_id': book_id,
                    'status': 'already_indexed',
                    'existing_chunks': len(existing['ids'])
                }

        # Extract metadata (author, title, year, ISBN, publisher, etc.)
        # Works for PDF, EPUB, and other formats
        book_metadata = self._extract_metadata(book_path)

        # Step 1: Extract text
        print("  [1/3] Extracting text...")
        start_time = time.time()
        extracted = self.extractor.extract(book_path)
        extract_time = time.time() - start_time

        print(f"    ? Extracted {len(extracted.chunks)} chunks in {extract_time:.1f}s")
        print(f"    ? {extracted.metadata.total_words:,} words, {extracted.metadata.total_pages or 'N/A'} pages\n")

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
        print(f"    ? Generated {len(embeddings)} embeddings in {embed_time:.1f}s\n")

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
                'indexed_at': datetime.now().isoformat(),  # Track when this was indexed
            }

            # Add book metadata (author, title, year, ISBN, publisher, etc.)
            # Works for PDF, EPUB, and other formats
            if book_metadata:
                if book_metadata.get('author'):
                    metadata['author'] = book_metadata['author']
                if book_metadata.get('title'):
                    # Prefer embedded title over filename
                    metadata['book_title'] = book_metadata['title']
                if book_metadata.get('year'):
                    metadata['year'] = book_metadata['year']
                if book_metadata.get('subject'):
                    metadata['subject'] = book_metadata['subject']
                if book_metadata.get('keywords'):
                    metadata['keywords'] = book_metadata['keywords']

                # EPUB-specific fields
                if book_metadata.get('publisher'):
                    metadata['publisher'] = book_metadata['publisher']
                if book_metadata.get('isbn'):
                    metadata['isbn'] = book_metadata['isbn']
                    # Track ISBN source (file vs calibre)
                    if book_metadata.get('isbn_source'):
                        metadata['isbn_source'] = book_metadata['isbn_source']
                if book_metadata.get('description'):
                    metadata['description'] = book_metadata['description']
                if book_metadata.get('calibre_id'):
                    metadata['calibre_id'] = book_metadata['calibre_id']
                if book_metadata.get('tags'):
                    # Store tags as comma-separated string for ChromaDB compatibility
                    metadata['tags'] = ', '.join(book_metadata['tags']) if isinstance(book_metadata['tags'], list) else book_metadata['tags']
                if book_metadata.get('custom_fields'):
                    # Store custom fields as JSON string for ChromaDB compatibility
                    import json
                    metadata['custom_fields'] = json.dumps(book_metadata['custom_fields'])

            # Add source file path for direct links
            metadata['source_file'] = str(extracted.metadata.file_path)

            # Add page info if available
            if 'metadata' in chunk and chunk['metadata'].get('page'):
                metadata['page'] = chunk['metadata']['page']

            # Add chapter info if available
            if 'metadata' in chunk and chunk['metadata'].get('chapter'):
                metadata['chapter'] = chunk['metadata']['chapter']

            # Add language info if available
            if 'metadata' in chunk and chunk['metadata'].get('language'):
                metadata['language'] = chunk['metadata']['language']

            metadatas.append(metadata)

        # Add Calibre comments as separate chunk (if available)
        if book_metadata and book_metadata.get('comments'):
            print(f"    ? Adding Calibre comment as searchable chunk...")

            comment_text = f"[CALIBRE_COMMENT] {book_metadata['comments']}"

            # Generate embedding for comment
            comment_embedding = self.embedding_model.encode(
                comment_text,
                show_progress_bar=False,
                convert_to_numpy=True
            ).tolist()

            # Create comment chunk metadata
            comment_metadata = {
                'book_id': book_id,
                'book_title': book_metadata.get('title', extracted.metadata.file_path.stem),
                'chunk_index': -1,  # Special index for comments
                'chunk_type': 'calibre_comment',
                'format': extracted.metadata.detected_format,
                'indexed_at': datetime.now().isoformat(),  # Track when this was indexed
            }

            # Copy book metadata to comment chunk
            if book_metadata.get('author'):
                comment_metadata['author'] = book_metadata['author']
            if book_metadata.get('publisher'):
                comment_metadata['publisher'] = book_metadata['publisher']
            if book_metadata.get('isbn'):
                comment_metadata['isbn'] = book_metadata['isbn']
            if book_metadata.get('calibre_id'):
                comment_metadata['calibre_id'] = book_metadata['calibre_id']
            if book_metadata.get('tags'):
                comment_metadata['tags'] = ', '.join(book_metadata['tags']) if isinstance(book_metadata['tags'], list) else book_metadata['tags']
            if book_metadata.get('custom_fields'):
                import json
                comment_metadata['custom_fields'] = json.dumps(book_metadata['custom_fields'])

            # Add to lists
            ids.append(f"{book_id}_comment")
            documents.append(comment_text)
            embeddings.append(comment_embedding)
            metadatas.append(comment_metadata)

        # Add to collection in batches (ChromaDB limit for large books)
        batch_size = 500  # Safe batch size for ChromaDB
        total_chunks = len(ids)

        if total_chunks <= batch_size:
            # Small book: single batch
            self.collection.add(
                ids=ids,
                embeddings=embeddings,
                documents=documents,
                metadatas=metadatas
            )
        else:
            # Large book: batch processing
            print(f"    📦 Processing {total_chunks} chunks in batches of {batch_size}...", flush=True)
            for i in range(0, total_chunks, batch_size):
                batch_end = min(i + batch_size, total_chunks)
                batch_num = i // batch_size + 1
                total_batches = (total_chunks + batch_size - 1) // batch_size

                self.collection.add(
                    ids=ids[i:batch_end],
                    embeddings=embeddings[i:batch_end],
                    documents=documents[i:batch_end],
                    metadatas=metadatas[i:batch_end]
                )
                print(f"      Batch {batch_num}/{total_batches}: {batch_end}/{total_chunks} chunks", flush=True)

        index_time = time.time() - start_time
        print(f"    ? Indexed {len(ids)} chunks in {index_time:.1f}s\n")

        # Summary
        total_time = extract_time + embed_time + index_time
        print(f"? INDEXING COMPLETE")
        print(f"  Total time: {total_time:.1f}s")
        print(f"  Collection size: {self.collection.count()} chunks\n")

        # Update BM25 index after indexing
        if BM25_AVAILABLE:
            self._rebuild_bm25_index()

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

    def _tokenize(self, text: str) -> List[str]:
        """
        Simple tokenizer for BM25.

        Lowercases and splits on word boundaries.
        Academic-friendly: keeps hyphens, apostrophes.
        """
        # Lowercase
        text = text.lower()
        # Split on whitespace and punctuation (but keep hyphens, apostrophes)
        tokens = re.findall(r"[\w'-]+", text)
        return tokens

    def _load_bm25_index(self):
        """Load BM25 index from disk if available."""
        bm25_path = self.db_path / "bm25_index.pkl"

        if not bm25_path.exists():
            return

        try:
            with open(bm25_path, 'rb') as f:
                data = pickle.load(f)
                self.bm25_index = data['index']
                self.bm25_docs = data['docs']
                self.bm25_ids = data['ids']
                self.bm25_metadatas = data.get('metadatas', None)  # Load cached metadata
        except Exception as e:
            print(f"  ? Could not load BM25 index: {e}")

    def _save_bm25_index(self):
        """Save BM25 index to disk."""
        if not self.bm25_index:
            return

        bm25_path = self.db_path / "bm25_index.pkl"
        bm25_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with open(bm25_path, 'wb') as f:
                pickle.dump({
                    'index': self.bm25_index,
                    'docs': self.bm25_docs,
                    'ids': self.bm25_ids,
                    'metadatas': self.bm25_metadatas  # Cache metadata to avoid SQLite limit
                }, f)
        except Exception as e:
            print(f"  ? Could not save BM25 index: {e}")

    def _rebuild_bm25_index(self):
        """Rebuild BM25 index from ChromaDB documents + metadata (tags, title, author)."""
        if not BM25_AVAILABLE:
            return

        # Get all documents from ChromaDB in batches to avoid SQLite variable limit
        # ChromaDB's get() without parameters can hit SQLite's ~999 variable limit
        print("  Fetching documents from ChromaDB...")
        all_ids = []
        all_docs = []
        all_metadatas = []
        batch_size = 500
        offset = 0

        while True:
            batch = self.collection.get(limit=batch_size, offset=offset)
            if not batch['ids']:
                break
            all_ids.extend(batch['ids'])
            all_docs.extend(batch['documents'])
            all_metadatas.extend(batch['metadatas'])
            offset += batch_size
            if len(batch['ids']) < batch_size:
                break  # Last batch

        if not all_ids:
            return

        print(f"  Loaded {len(all_ids)} chunks for BM25 indexing...")

        # Store original documents, IDs, and metadata
        self.bm25_ids = all_ids
        self.bm25_docs = all_docs
        self.bm25_metadatas = all_metadatas  # Cache for filtering without SQLite limit

        # Create enriched documents with metadata for BM25 indexing
        # This makes tags, titles, authors searchable via keyword search
        enriched_docs = []
        for doc, metadata in zip(self.bm25_docs, self.bm25_metadatas):
            enriched_text = doc

            # Add tags to searchable text (if available)
            if metadata.get('tags'):
                enriched_text += f" [TAGS: {metadata['tags']}]"

            # Add book title (helps finding books by title)
            if metadata.get('book_title'):
                enriched_text += f" [TITLE: {metadata['book_title']}]"

            # Add author (helps finding books by author)
            if metadata.get('author'):
                enriched_text += f" [AUTHOR: {metadata['author']}]"

            # Add custom fields (if available) - makes user-defined Calibre fields searchable
            if metadata.get('custom_fields'):
                # Custom fields are stored as JSON string in metadata
                # Parse and add to searchable text
                try:
                    import json
                    custom_fields = metadata['custom_fields']
                    if isinstance(custom_fields, str):
                        custom_fields = json.loads(custom_fields)

                    for field_label, field_data in custom_fields.items():
                        if isinstance(field_data, dict) and 'value' in field_data:
                            value = field_data['value']
                            name = field_data.get('name', field_label)
                            enriched_text += f" [CUSTOM_{field_label.upper()}: {value}]"
                except Exception:
                    pass  # Silently skip if parsing fails

            enriched_docs.append(enriched_text)

        # Tokenize enriched documents
        tokenized_docs = [self._tokenize(doc) for doc in enriched_docs]

        # Build BM25 index
        self.bm25_index = BM25Okapi(tokenized_docs)

        # Save to disk
        self._save_bm25_index()

    def query(
        self,
        query_text: str,
        top_k: int = 5,
        mode: Literal['semantic', 'keyword', 'hybrid'] = 'hybrid',
        language: str = None,
        book_id: str = None,
        exact_phrase: bool = False,
        tag_filter: List[str] = None,
        section_filter: str = None,
        max_per_book: int = 3
    ) -> List[Dict[str, Any]]:
        """
        Search for relevant passages.

        Args:
            query_text: Search query
            top_k: Number of results to return
            mode: Search mode - 'semantic' (BGE-M3), 'keyword' (BM25), or 'hybrid' (both)
            language: Filter by language (e.g., 'de', 'en', 'la') or comma-separated list
            book_id: Filter by specific book ID
            exact_phrase: Use exact phrase matching (for Latin quotes, etc.)
            tag_filter: Filter by Calibre tags (e.g., ['Geschichte', 'Philosophie'])
            section_filter: Filter by section type ('main_content', 'front_matter', 'back_matter')
                           Use 'main' to exclude front/back matter from results
            max_per_book: Maximum results per book (default: 3, use 999 for unlimited)

        Returns:
            List of relevant chunks with metadata and scores
        """
        # Build filter message
        filters = []
        if language:
            filters.append(f"language={language}")
        if book_id:
            filters.append(f"book={book_id}")
        if exact_phrase:
            filters.append("exact phrase")
        if tag_filter:
            filters.append(f"tags={', '.join(tag_filter)}")
        if section_filter:
            filters.append(f"section={section_filter}")
        if max_per_book < 999:
            filters.append(f"max {max_per_book}/book")

        filter_msg = f" ({', '.join(filters)})" if filters else ""
        mode_emoji = {"semantic": "??", "keyword": "??", "hybrid": "??"}
        print(f"{mode_emoji.get(mode, '??')} QUERY [{mode.upper()}]: \"{query_text}\"{filter_msg}")
        print(f"  Searching {self.collection.count()} chunks...\n")

        # Oversample to allow for diversity filtering
        # If max_per_book is set, we need to fetch more results than top_k
        # to ensure we have enough diverse results after filtering
        # Higher factor (5) enables finding more diverse books in large libraries
        oversample_factor = 5 if max_per_book < 999 else 1
        search_top_k = top_k * oversample_factor

        # Route to appropriate search method
        if mode == 'semantic':
            results = self._semantic_search(query_text, search_top_k, language, book_id)
        elif mode == 'keyword':
            results = self._keyword_search(query_text, search_top_k, language, book_id, exact_phrase=exact_phrase)
        elif mode == 'hybrid':
            results = self._hybrid_search(query_text, search_top_k, language, book_id, exact_phrase=exact_phrase)
        else:
            raise ValueError(f"Invalid mode: {mode}. Must be 'semantic', 'keyword', or 'hybrid'")

        # Post-filter by tags (if specified)
        if tag_filter:
            filtered_results = []
            for result in results:
                result_tags = result['metadata'].get('tags', '')
                if result_tags:
                    # Check if any of the filter tags match
                    result_tag_list = [t.strip().lower() for t in result_tags.split(',')]
                    filter_tag_list = [t.strip().lower() for t in tag_filter]
                    if any(ft in result_tag_list for ft in filter_tag_list):
                        filtered_results.append(result)

            # Re-rank after filtering
            for i, result in enumerate(filtered_results):
                result['rank'] = i + 1

            results = filtered_results  # Don't truncate yet - need data for diversification

        # Post-filter by section type (if specified)
        if section_filter:
            filtered_results = []
            for result in results:
                section_type = result['metadata'].get('section_type', 'main_content')

                # 'main' is shorthand for main_content only (exclude front/back matter)
                if section_filter == 'main':
                    if section_type == 'main_content' or section_type is None:
                        filtered_results.append(result)
                elif section_type == section_filter:
                    filtered_results.append(result)

            # Re-rank after filtering
            for i, result in enumerate(filtered_results):
                result['rank'] = i + 1

            results = filtered_results  # Don't truncate yet - need data for diversification

        # Diversify results by book (max N results per book)
        if max_per_book < 999 and len(results) > 0:
            diversified_results = []
            book_counts = {}  # Track how many results per book

            for result in results:
                book_id_val = result['metadata'].get('book_id', 'unknown')

                # Count current results from this book
                current_count = book_counts.get(book_id_val, 0)

                # Add result if under limit
                if current_count < max_per_book:
                    diversified_results.append(result)
                    book_counts[book_id_val] = current_count + 1

                # Stop when we have enough results
                if len(diversified_results) >= top_k:
                    break

            # Re-rank after diversification
            for i, result in enumerate(diversified_results):
                result['rank'] = i + 1

            results = diversified_results
        else:
            # No diversification - just truncate to top_k
            results = results[:top_k]

        return results

    def _semantic_search(
        self,
        query_text: str,
        top_k: int,
        language: str = None,
        book_id: str = None
    ) -> List[Dict[str, Any]]:
        """Semantic search using BGE-M3 embeddings."""
        # Generate query embedding
        query_embedding = self.embedding_model.encode(
            query_text,
            convert_to_numpy=True
        ).tolist()

        # Build where clause for filtering
        where_clause = self._build_where_clause(language, book_id)

        # Search in ChromaDB
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where_clause
        )

        # Format results
        return self._format_results(results, score_type='semantic')

    def _keyword_search(
        self,
        query_text: str,
        top_k: int,
        language: str = None,
        book_id: str = None,
        exact_phrase: bool = False
    ) -> List[Dict[str, Any]]:
        """Keyword search using BM25 or exact phrase matching."""
        if not BM25_AVAILABLE:
            print("  ? BM25 not available. Install with: pip install rank-bm25")
            return []

        # Build BM25 index on-the-fly if not available
        if not self.bm25_index:
            print("  Building BM25 index on-the-fly...")
            self._rebuild_bm25_index()
            if not self.bm25_index:
                print("  ? Could not build BM25 index (no documents?)")
                return []

        # For exact phrase matching, use different approach
        if exact_phrase:
            return self._exact_phrase_search(query_text, top_k, language, book_id)

        # Tokenize query
        query_tokens = self._tokenize(query_text)

        # Get BM25 scores
        scores = self.bm25_index.get_scores(query_tokens)

        # Get top-k indices
        top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k * 10]  # Get more for filtering

        # Use cached metadata (avoids SQLite variable limit with large indexes)
        all_metadata = self.bm25_metadatas

        # Filter by language/book_id
        filtered_results = []
        for idx in top_indices:
            metadata = all_metadata[idx]

            # Apply filters
            if language:
                langs = [l.strip() for l in language.split(',')] if ',' in language else [language]
                if metadata.get('language') not in langs:
                    continue

            if book_id and metadata.get('book_id') != book_id:
                continue

            filtered_results.append({
                'rank': len(filtered_results) + 1,
                'text': self.bm25_docs[idx],
                'metadata': metadata,
                'score': scores[idx],
                'similarity': min(scores[idx] / 10.0, 1.0),  # Normalize BM25 score to 0-1
            })

            if len(filtered_results) >= top_k:
                break

        return filtered_results

    def _exact_phrase_search(
        self,
        query_text: str,
        top_k: int,
        language: str = None,
        book_id: str = None
    ) -> List[Dict[str, Any]]:
        """
        Exact phrase matching (case-insensitive).

        Finds documents that contain the EXACT phrase, not just the words.
        Critical for Latin phrases like "evangelista et a presbyteris".

        IMPORTANT: Normalizes whitespace to handle line breaks!
        "evangelista\net a presbyteris" matches "evangelista et a presbyteris"
        """
        import re

        # Normalize query: lowercase + collapse whitespace (newlines, tabs, multiple spaces ? single space)
        query_normalized = re.sub(r'\s+', ' ', query_text.lower().strip())

        # Use cached data (avoids SQLite variable limit with large indexes)
        # Find exact matches
        matches = []
        for idx, (doc_id, doc_text, metadata) in enumerate(zip(
            self.bm25_ids,
            self.bm25_docs,
            self.bm25_metadatas
        )):
            # Apply filters first
            if language:
                langs = [l.strip() for l in language.split(',')] if ',' in language else [language]
                if metadata.get('language') not in langs:
                    continue

            if book_id and metadata.get('book_id') != book_id:
                continue

            # Normalize document text: lowercase + collapse whitespace
            # This handles line breaks! "evangelista\net a presbyteris" ? "evangelista et a presbyteris"
            doc_normalized = re.sub(r'\s+', ' ', doc_text.lower())

            # Check for exact phrase in normalized text
            if query_normalized in doc_normalized:
                # Count occurrences for scoring
                count = doc_normalized.count(query_normalized)

                matches.append({
                    'rank': 0,  # Will be set later
                    'text': doc_text,  # Keep ORIGINAL text (with line breaks)
                    'metadata': metadata,
                    'score': count,  # More occurrences = higher score
                    'similarity': min(count / 10.0, 1.0),  # Normalize
                })

        # Sort by score (number of occurrences)
        matches.sort(key=lambda x: x['score'], reverse=True)

        # Assign ranks
        for i, match in enumerate(matches[:top_k]):
            match['rank'] = i + 1

        return matches[:top_k]

    def _hybrid_search(
        self,
        query_text: str,
        top_k: int,
        language: str = None,
        book_id: str = None,
        exact_phrase: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Hybrid search combining semantic (BGE-M3) and keyword (BM25).

        Uses Reciprocal Rank Fusion (RRF) to combine scores.

        IMPORTANT: If exact_phrase=True, ONLY returns exact phrase matches (no semantic mixing!)
        """
        # For exact phrase matching, skip semantic search entirely
        # We want ONLY exact matches, not semantically similar results!
        if exact_phrase:
            return self._keyword_search(query_text, top_k, language, book_id, exact_phrase=True)

        # Get results from both methods (request more to have enough after fusion)
        semantic_results = self._semantic_search(query_text, top_k * 2, language, book_id)
        keyword_results = self._keyword_search(query_text, top_k * 2, language, book_id, exact_phrase=False)

        if not BM25_AVAILABLE or not keyword_results:
            # Fallback to semantic-only
            return semantic_results[:top_k]

        # Reciprocal Rank Fusion (RRF)
        # RRF score = sum(1 / (k + rank)) for each result
        k = 60  # RRF constant (standard value)
        rrf_scores = {}

        # Add semantic scores
        for result in semantic_results:
            doc_id = result['metadata'].get('chunk_index', id(result['text']))
            rrf_scores[doc_id] = {
                'score': 1 / (k + result['rank']),
                'result': result
            }

        # Add keyword scores (accumulate if already present)
        for result in keyword_results:
            doc_id = result['metadata'].get('chunk_index', id(result['text']))
            if doc_id in rrf_scores:
                rrf_scores[doc_id]['score'] += 1 / (k + result['rank'])
            else:
                rrf_scores[doc_id] = {
                    'score': 1 / (k + result['rank']),
                    'result': result
                }

        # Apply boost factors BEFORE sorting
        # Extract query terms for tag matching
        query_terms = set(query_text.lower().split())

        for doc_id, data in rrf_scores.items():
            result_metadata = data['result']['metadata']

            # Boost for Calibre comments (curated content)
            if result_metadata.get('chunk_type') == 'calibre_comment':
                data['score'] *= 1.2

            # Boost for tag matches
            if result_metadata.get('tags'):
                result_tags = set(result_metadata['tags'].lower().split(', '))
                if query_terms & result_tags:  # If any query term matches any tag
                    data['score'] *= 1.15

        # Sort by RRF score (now with boosts applied)
        sorted_results = sorted(rrf_scores.items(), key=lambda x: x[1]['score'], reverse=True)

        # Format final results
        final_results = []
        for i, (doc_id, data) in enumerate(sorted_results[:top_k]):
            result = data['result'].copy()
            result['rank'] = i + 1
            result['similarity'] = min(data['score'], 1.0)  # Normalize
            final_results.append(result)

        return final_results

    def _build_where_clause(self, language: str = None, book_id: str = None):
        """Build ChromaDB where clause for filtering."""
        if not (language or book_id):
            return None

        where_conditions = {}

        if language:
            # Support comma-separated languages
            if ',' in language:
                langs = [l.strip() for l in language.split(',')]
                where_conditions['language'] = {'$in': langs}
            else:
                where_conditions['language'] = language

        if book_id:
            where_conditions['book_id'] = book_id

        # Combine conditions with AND
        if len(where_conditions) > 1:
            return {'$and': [{k: v} for k, v in where_conditions.items()]}
        elif where_conditions:
            return where_conditions
        return None

    def _format_results(self, results: Dict, score_type: str = 'semantic') -> List[Dict[str, Any]]:
        """Format ChromaDB results into standard format."""
        formatted_results = []

        if not results['ids'] or len(results['ids'][0]) == 0:
            return formatted_results

        for i in range(len(results['ids'][0])):
            result = {
                'rank': i + 1,
                'text': results['documents'][0][i],
                'metadata': results['metadatas'][0][i],
                'distance': results['distances'][0][i],
                'similarity': 1 - results['distances'][0][i],  # Convert distance to similarity
                'score_type': score_type
            }
            formatted_results.append(result)

        return formatted_results

    def _get_context_snippet(self, text: str, query_text: str, context_chars: int = 200) -> str:
        """
        Extract a relevant snippet from text that contains query terms.

        For keyword/hybrid searches, this shows WHERE the match was found.
        Much better UX than showing first 300 chars which might not contain the match!

        IMPORTANT: Handles line breaks in phrases!
        If query is "evangelista et a presbyteris" and text has line break:
        "...evangelista\net a presbyteris..." ? still finds it!

        Args:
            text: Full chunk text
            query_text: Original query
            context_chars: Characters of context around match (default: 200)

        Returns:
            Snippet with "..." prefix/suffix if truncated
        """
        import re

        text_lower = text.lower()
        query_lower = query_text.lower()
        best_match_pos = len(text)  # Default: end of text

        # Strategy 1: Try to find the ENTIRE query phrase first (exact phrase matching)
        # This is critical for Latin quotes like "evangelista et a presbyteris"
        phrase_pos = text_lower.find(query_lower)
        if phrase_pos != -1:
            best_match_pos = phrase_pos
        else:
            # Strategy 1b: Try regex matching with flexible whitespace
            # This handles line breaks! "evangelista\s+et\s+a\s+presbyteris" matches "evangelista\net a presbyteris"
            # Escape special regex chars in query, then replace spaces with \s+
            query_escaped = re.escape(query_lower)
            query_pattern = re.sub(r'\\ ', r'\\s+', query_escaped)  # Replace escaped spaces with \s+

            match = re.search(query_pattern, text_lower, re.IGNORECASE)
            if match:
                best_match_pos = match.start()
            else:
                # Strategy 2: Fallback to individual token matching
                # This works for partial matches or when query is multiple concepts
                query_tokens = self._tokenize(query_text)

                if not query_tokens:
                    # No tokens found, show beginning
                    return text[:300] + ('...' if len(text) > 300 else '')

                # Find first occurrence of any query token
                for token in query_tokens:
                    pos = text_lower.find(token.lower())
                    if pos != -1 and pos < best_match_pos:
                        best_match_pos = pos

        # If no match found (shouldn't happen), show beginning
        if best_match_pos == len(text):
            return text[:300] + ('...' if len(text) > 300 else '')

        # Calculate snippet boundaries
        start = max(0, best_match_pos - context_chars)
        end = min(len(text), best_match_pos + context_chars)

        # Extract snippet
        snippet = text[start:end]

        # Add ellipsis if truncated
        if start > 0:
            snippet = '...' + snippet
        if end < len(text):
            snippet = snippet + '...'

        return snippet

    def print_results(self, results: List[Dict[str, Any]], query_text: str = ""):
        """Pretty print search results with context snippets."""
        if not results:
            print("? No results found.\n")
            return

        print(f"?? TOP {len(results)} RESULTS:\n")
        print("=" * 80)

        for result in results:
            rank = result['rank']
            similarity = result['similarity']
            metadata = result['metadata']
            text = result['text']

            # Build citation with printed page numbers
            citation_parts = []
            if metadata.get('book_title'):
                citation_parts.append(metadata['book_title'])

            # Check for printed page number with confidence
            printed_page = metadata.get('printed_page')
            printed_conf = metadata.get('printed_page_confidence', 0.0)
            page_warning = None

            # Debug mode: show raw metadata values
            if os.environ.get('DEBUG_METADATA'):
                print(f"    [DEBUG] printed_page: {repr(printed_page)} (type: {type(printed_page).__name__})")

            if printed_page and printed_conf >= 0.8:
                # Use printed page number (high confidence)
                # Explicitly convert to string to preserve special characters like asterisks
                printed_page_str = str(printed_page) if printed_page else ""
                citation_parts.append(f"S. {printed_page_str}")

                # Add warning if confidence < 0.9
                if printed_conf < 0.9:
                    page_warning = f"Seitenzahl-Konfidenz: {printed_conf:.2f} - bitte verifizieren"
            elif metadata.get('page'):
                # Fallback to PDF page number
                citation_parts.append(f"PDF S. {metadata['page']}")

                # Add warning if printed page exists but low confidence
                if printed_page:
                    page_warning = f"? Gedruckte Seitenzahl unsicher (Konfidenz: {printed_conf:.2f})"
            elif metadata.get('chapter'):
                citation_parts.append(metadata['chapter'])

            citation = ', '.join(citation_parts) if citation_parts else metadata.get('book_id', 'Unknown')

            print(f"\n[{rank}] {citation}")
            print(f"    Relevanz: {similarity:.3f} ({'sehr hoch' if similarity > 0.8 else 'hoch' if similarity > 0.6 else 'mittel'})")

            # Show page number warning if applicable
            if page_warning:
                print(f"    ?? {page_warning}")

            # Show context snippet with query terms (if available)
            if query_text:
                snippet = self._get_context_snippet(text, query_text)
            else:
                snippet = text[:300] + ('...' if len(text) > 300 else '')

            print(f"    Text: {snippet}")

        print("\n" + "=" * 80 + "\n")

    def export_to_markdown(
        self,
        results: List[Dict[str, Any]],
        query_text: str,
        output_file: str = None
    ) -> str:
        """
        Export search results to Markdown format (optimized for Joplin).

        Args:
            results: Search results from query()
            query_text: Original search query
            output_file: Optional file path (default: auto-generated)

        Returns:
            Path to the created markdown file
        """
        from datetime import datetime

        if not output_file:
            timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            safe_query = "".join(c if c.isalnum() else "_" for c in query_text[:30])
            output_file = f"archilles_search_{safe_query}_{timestamp}.md"

        # Build markdown content
        lines = []

        # Header
        lines.append(f"# ARCHILLES RAG - Suchergebnisse")
        lines.append(f"")
        lines.append(f"**Query:** `{query_text}`  ")
        lines.append(f"**Datum:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  ")
        lines.append(f"**Ergebnisse:** {len(results)}")
        lines.append(f"")
        lines.append(f"---")
        lines.append(f"")

        # Results
        for result in results:
            rank = result['rank']
            similarity = result['similarity']
            metadata = result['metadata']
            text = result['text']

            # Build citation
            book_title = metadata.get('book_title', metadata.get('book_id', 'Unknown'))

            # Page number with confidence
            printed_page = metadata.get('printed_page')
            printed_conf = metadata.get('printed_page_confidence', 0.0)

            if printed_page and printed_conf >= 0.8:
                page_str = f"S. {str(printed_page)}"
                if printed_conf < 1.0:
                    page_str += f" (Konfidenz: {printed_conf:.2f})"
            elif metadata.get('page'):
                page_str = f"PDF S. {metadata['page']}"
            else:
                page_str = metadata.get('chapter', '')

            # Result header with author and year
            author = metadata.get('author', '')
            year = metadata.get('year', '')

            if author and year:
                header = f"## [{rank}] {author}: {book_title} ({year})"
            elif author:
                header = f"## [{rank}] {author}: {book_title}"
            elif year:
                header = f"## [{rank}] {book_title} ({year})"
            else:
                header = f"## [{rank}] {book_title}"

            lines.append(header)

            # Page number
            if page_str:
                lines.append(f"**Seite:** {page_str}  ")

            # Relevanz
            lines.append(f"**Relevanz:** {similarity:.3f}  ")

            # Direct link to PDF/EPUB (file:/// protocol)
            source_file = metadata.get('source_file')
            if source_file:
                # Create file:/// URL for clickable links in Joplin/Obsidian
                # Windows: file:///D:/path/to/file.pdf
                # Linux/Mac: file:///home/user/file.pdf

                # Normalize path separators to forward slashes for URLs
                url_path = source_file.replace('\\', '/')

                # Add file:/// prefix
                if url_path.startswith('/'):
                    # Unix path
                    file_url = f"file://{url_path}"
                else:
                    # Windows path (e.g., D:/...)
                    file_url = f"file:///{url_path}"

                # Extract filename (handle both Windows and Unix paths)
                if '/' in url_path:
                    filename = url_path.split('/')[-1]
                else:
                    filename = url_path

                lines.append(f"**Quelle:** [{filename}]({file_url})  ")

            lines.append(f"")

            # Quote
            snippet = self._get_context_snippet(text, query_text) if query_text else text[:300]
            lines.append(f"> {snippet}")
            lines.append(f"")

            # Additional metadata
            meta_lines = []
            if metadata.get('language'):
                meta_lines.append(f"Sprache: {metadata['language']}")
            if metadata.get('subject'):
                meta_lines.append(f"Thema: {metadata['subject']}")
            if metadata.get('publisher'):
                meta_lines.append(f"Verlag: {metadata['publisher']}")
            if metadata.get('isbn'):
                isbn_text = f"ISBN: {metadata['isbn']}"
                # Add warning if ISBN from Calibre (not from file)
                if metadata.get('isbn_source') == 'calibre':
                    isbn_text += " ?"
                meta_lines.append(isbn_text)

            if meta_lines:
                lines.append(f"*{'   '.join(meta_lines)}*  ")

            lines.append(f"")
            lines.append(f"---")
            lines.append(f"")

        # Footer with tags
        tags = ["#archilles", "#rag", "#suche"]
        if any(r['metadata'].get('language') == 'la' for r in results):
            tags.append("#latein")
        if any(r['metadata'].get('language') == 'de' for r in results):
            tags.append("#deutsch")

        lines.append(f"")
        lines.append(" ".join(tags))

        # Write file
        content = "\n".join(lines)
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(content)

        return output_file

    @staticmethod
    def get_system_prompt() -> str:
        """
        Get the system prompt for Claude with citation instructions.

        Returns XML-formatted instructions that tell Claude to cite sources.
        """
        return """<system_instructions>
Du bist ein akademischer Forschungsassistent. Deine Aufgabe ist es, die Frage des Nutzers NUR auf Basis der bereitgestellten Dokumentenauszüge zu beantworten.

<rules>
1. Zitiere jede Tatsachenbehauptung sofort mit der ID des Dokuments in eckigen Klammern, z.B. [doc_1].
2. Nutze keine externen Informationen. Wenn die Antwort nicht in den Dokumenten steht, sage das klar.
3. Antworte in der Sprache des Nutzers, behalte aber den wissenschaftlichen Fachjargon bei.
4. Bei mehreren Quellen für dieselbe Aussage: gib alle relevanten IDs an, z.B. [doc_1, doc_3].
5. Fasse am Ende alle zitierten Quellen als Literaturliste zusammen.
</rules>
</system_instructions>"""

    def format_results_as_xml(
        self,
        results: List[Dict[str, Any]],
        query_text: str,
        expand_context: bool = False,
        expansion_chars: int = 400
    ) -> str:
        """
        Format search results as XML-structured documents for Claude.

        Creates a <documents> block with individual <document> entries,
        each containing <meta> and <content> sections.

        Args:
            results: Search results from query()
            query_text: Original user query
            expand_context: Enable context expansion (Small-to-Big) if char_offsets available
            expansion_chars: Characters to add before/after chunk (default: 400)

        Returns:
            XML-formatted string ready for Claude
        """
        lines = []

        lines.append("<documents>")

        for i, result in enumerate(results, start=1):
            doc_id = f"doc_{i}"
            metadata = result['metadata']
            text = result['text']

            # Apply context expansion if enabled and available
            if expand_context:
                text = self.expand_chunk_context(text, metadata, expansion_chars)

            # Build metadata line
            meta_parts = []

            if metadata.get('author'):
                meta_parts.append(f"Autor: {metadata['author']}")

            if metadata.get('book_title'):
                meta_parts.append(f"Titel: {metadata['book_title']}")

            if metadata.get('year'):
                meta_parts.append(f"Jahr: {metadata['year']}")

            # Page number (prefer printed page if available)
            if metadata.get('printed_page') and metadata.get('printed_page_confidence', 0) >= 0.8:
                meta_parts.append(f"Seite: {metadata['printed_page']}")
            elif metadata.get('page'):
                meta_parts.append(f"Seite: {metadata['page']}")
            elif metadata.get('chapter'):
                meta_parts.append(f"Kapitel: {metadata['chapter']}")

            meta_str = ", ".join(meta_parts) if meta_parts else "Metadaten nicht verfügbar"

            # Build inline metadata for content injection
            inline_meta = self._build_inline_metadata(metadata, doc_id)

            # Inject metadata into text content
            # This helps Claude understand context (e.g., a quote from Arendt vs. Heidegger)
            text_with_metadata = f"{inline_meta}\n{text}\n<<<ENDE QUELLE>>>"

            # Build XML document entry
            lines.append(f"   <document id=\"{doc_id}\">")
            lines.append(f"      <meta>{meta_str}</meta>")
            lines.append(f"      <content>{self._escape_xml(text_with_metadata)}</content>")
            lines.append(f"   </document>")

        lines.append("</documents>")
        lines.append("")
        lines.append("<user_query>")
        lines.append(self._escape_xml(query_text))
        lines.append("</user_query>")

        return "\n".join(lines)

    def expand_chunk_context(
        self,
        chunk_text: str,
        metadata: Dict[str, Any],
        expansion_chars: int = 400
    ) -> str:
        """
        Expand chunk context by adding surrounding text (Small-to-Big Retrieval).

        IMPORTANT: Requires char_start, char_end, and original_text in metadata!
        Currently NOT IMPLEMENTED because these fields are not stored in the index.

        To activate this feature:
        1. Modify index_book() to store char_start, char_end in metadata
        2. Store full book text somewhere accessible (e.g., metadata['original_text_ref'])
        3. This function will then retrieve and expand the context

        Args:
            chunk_text: Original chunk text from search result
            metadata: Chunk metadata (must contain char_start, char_end, original_text)
            expansion_chars: Characters to add before and after (default: 400)

        Returns:
            Expanded text with context, or original chunk if expansion not possible
        """
        # Check if we have the required fields
        if not all(k in metadata for k in ['char_start', 'char_end', 'original_text']):
            # Graceful degradation: return original chunk
            # No error - just log a debug message
            import logging
            logger = logging.getLogger(__name__)
            logger.debug("Context expansion not available (char_offsets not in index)")
            return chunk_text

        # Extract required data
        char_start = metadata['char_start']
        char_end = metadata['char_end']
        original_text = metadata['original_text']

        # Calculate expanded boundaries
        expanded_start = max(0, char_start - expansion_chars)
        expanded_end = min(len(original_text), char_end + expansion_chars)

        # Extract expanded context
        expanded_text = original_text[expanded_start:expanded_end]

        # Optional: Mark the original chunk within the expanded context
        # This helps Claude identify the most relevant part
        # prefix = expanded_text[:char_start - expanded_start]
        # core = expanded_text[char_start - expanded_start:char_end - expanded_start]
        # suffix = expanded_text[char_end - expanded_start:]
        # return f"{prefix}>>>{core}<<<{suffix}"

        return expanded_text

    def _build_inline_metadata(self, metadata: Dict[str, Any], doc_id: str) -> str:
        """
        Build inline metadata string to inject before chunk text.

        Format: <<<QUELLE ID=doc_1>>>
                [Metadaten: Autor="X", Titel="Y", Jahr=Z, Seite=123]

        This provides context for interpretation (Arendt vs. Heidegger matters!)
        """
        meta_parts = []

        if metadata.get('author'):
            # Quote the author name to handle special characters
            meta_parts.append(f'Autor="{metadata["author"]}"')

        if metadata.get('book_title'):
            meta_parts.append(f'Titel="{metadata["book_title"]}"')

        if metadata.get('year'):
            meta_parts.append(f'Jahr={metadata["year"]}')

        # Page number
        if metadata.get('printed_page') and metadata.get('printed_page_confidence', 0) >= 0.8:
            meta_parts.append(f'Seite={metadata["printed_page"]}')
        elif metadata.get('page'):
            meta_parts.append(f'Seite={metadata["page"]}')
        elif metadata.get('chapter'):
            meta_parts.append(f'Kapitel="{metadata["chapter"]}"')

        meta_str = ", ".join(meta_parts) if meta_parts else "keine Metadaten"

        return f"<<<QUELLE ID={doc_id}>>>\n[Metadaten: {meta_str}]"

    def _escape_xml(self, text: str) -> str:
        """Escape XML special characters."""
        return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;"))

    def create_claude_prompt(
        self,
        results: List[Dict[str, Any]],
        query_text: str,
        expand_context: bool = False,
        expansion_chars: int = 400
    ) -> Dict[str, str]:
        """
        Create a complete prompt package for Claude with system instructions and XML documents.

        This combines:
        - System prompt with citation rules
        - XML-formatted documents with metadata
        - User query

        Args:
            results: Search results from query()
            query_text: Original user query
            expand_context: Enable context expansion (Small-to-Big) if available
            expansion_chars: Characters to add before/after chunk (default: 400)

        Returns:
            Dictionary with 'system' and 'user' prompts
        """
        system_prompt = self.get_system_prompt()
        xml_content = self.format_results_as_xml(
            results,
            query_text,
            expand_context=expand_context,
            expansion_chars=expansion_chars
        )

        return {
            'system': system_prompt,
            'user': xml_content,
            'num_sources': len(results),
            'total_tokens_approx': len(system_prompt.split()) + len(xml_content.split())
        }


def main():
    """Main CLI interface."""
    parser = argparse.ArgumentParser(
        description="archilles Mini-RAG: Semantic search in academic books",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Index Josephus Antiquitates
  python scripts/rag_demo.py index "D:/Calibre-Bibliothek/Flavius Josephus/Judische Altertumer_...pdf"

  # Recover from corrupted database (after CTRL+C during indexing)
  python scripts/rag_demo.py index "book.pdf" --reset-db

  # Query (hybrid mode by default - combines semantic + keyword)
  python scripts/rag_demo.py query "evangelista et a presbyteris"

  # Search modes (demonstration with different query types)
  python scripts/rag_demo.py query "network analysis" --mode hybrid     # Best: semantic + keyword (default)
  python scripts/rag_demo.py query "Herrschaftslegitimation" --mode keyword    # Exact word matching (BM25)
  python scripts/rag_demo.py query "migration narratives" --mode semantic   # Concept search (BGE-M3)

  # Filter by language
  python scripts/rag_demo.py query "kings" --language de
  python scripts/rag_demo.py query "Rex" --language la
  python scripts/rag_demo.py query "kings" --language de,en

  # Filter by book
  python scripts/rag_demo.py query "Marcion" --book-id "von_Harnack"

  # More results
  python scripts/rag_demo.py query "Jewish kings" --top-k 10

  # Result diversity (max results per book)
  python scripts/rag_demo.py query "Herrschaftslegitimation" --max-per-book 2  # Max 2 results per book
  python scripts/rag_demo.py query "Macht" --max-per-book 1                    # Max 1 result per book (max diversity)
  python scripts/rag_demo.py query "Marcion" --max-per-book 999                # Unlimited (all from one book OK)

  # Export to Markdown (for Joplin/Obsidian)
  python scripts/rag_demo.py query "evangelista et a presbyteris" --exact --export zitate.md
        """
    )

    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # Index command
    index_parser = subparsers.add_parser('index', help='Index a book')
    index_parser.add_argument('book_path', help='Path to book file')
    index_parser.add_argument('--book-id', help='Optional book ID (default: filename)')
    index_parser.add_argument('--db-path', default=None, help='Database path (default: CALIBRE_LIBRARY/.archilles/rag_db)')
    index_parser.add_argument('--force', action='store_true', help='Force reindex (delete existing chunks first)')
    index_parser.add_argument('--reset-db', action='store_true', help='Reset corrupted database (WARNING: deletes all indexed data)')

    # Query command
    query_parser = subparsers.add_parser('query', help='Search indexed books')
    query_parser.add_argument('query', help='Search query')
    query_parser.add_argument('--top-k', type=int, default=5, help='Number of results (default: 5)')
    query_parser.add_argument('--mode', choices=['semantic', 'keyword', 'hybrid'], default='hybrid',
                              help='Search mode: semantic (BGE-M3), keyword (BM25), or hybrid (both, default)')
    query_parser.add_argument('--exact', action='store_true',
                              help='Exact phrase matching (case-insensitive) - critical for Latin quotes')
    query_parser.add_argument('--language', help='Filter by language (e.g., de, en, la) or comma-separated')
    query_parser.add_argument('--book-id', help='Filter by specific book ID')
    query_parser.add_argument('--tag-filter', nargs='+', help='Filter by Calibre tags (e.g., --tag-filter Geschichte Philosophie)')
    query_parser.add_argument('--section', choices=['main', 'main_content', 'front_matter', 'back_matter'],
                              help='Filter by section type: main (exclude index/TOC), front_matter, back_matter')
    query_parser.add_argument('--max-per-book', type=int, default=3, help='Maximum results per book (default: 3, use 999 for unlimited)')
    query_parser.add_argument('--db-path', default=None, help='Database path (default: CALIBRE_LIBRARY/.archilles/rag_db)')
    query_parser.add_argument('--export', metavar='FILE', help='Export results to Markdown file (for Joplin/Obsidian)')

    # Stats command
    stats_parser = subparsers.add_parser('stats', help='Show index statistics')
    stats_parser.add_argument('--db-path', default=None, help='Database path (default: CALIBRE_LIBRARY/.archilles/rag_db)')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    # Determine default database path if not specified
    # Requires CALIBRE_LIBRARY_PATH env var for portable installation
    if args.db_path is None:
        calibre_library = os.environ.get('CALIBRE_LIBRARY_PATH')
        if not calibre_library:
            print("\n" + "="*60)
            print("ERROR: CALIBRE_LIBRARY_PATH not set")
            print("="*60 + "\n")
            print("Please set the environment variable to your Calibre library:\n")
            print("  Windows (PowerShell):")
            print('    $env:CALIBRE_LIBRARY_PATH = "C:\\path\\to\\Calibre-Library"\n')
            print("  Linux/macOS:")
            print('    export CALIBRE_LIBRARY_PATH="/path/to/Calibre-Library"\n')
            print("Or specify the database path directly with --db-path\n")
            sys.exit(1)
        args.db_path = str(Path(calibre_library) / ".archilles" / "rag_db")
        print(f"📚 Using default RAG database: {args.db_path}")

    try:
        # Initialize RAG
        reset_db = getattr(args, 'reset_db', False)
        rag = archillesRAG(db_path=args.db_path, reset_db=reset_db)

        if args.command == 'index':
            # Index a book
            stats = rag.index_book(args.book_path, args.book_id, force=args.force)

        elif args.command == 'query':
            # Search
            results = rag.query(
                args.query,
                top_k=args.top_k,
                mode=args.mode,
                language=args.language,
                book_id=args.book_id,
                exact_phrase=args.exact,
                tag_filter=args.tag_filter if hasattr(args, 'tag_filter') else None,
                section_filter=args.section if hasattr(args, 'section') else None,
                max_per_book=args.max_per_book if hasattr(args, 'max_per_book') else 3
            )
            rag.print_results(results, query_text=args.query)

            # Export to Markdown if requested
            if args.export:
                output_file = rag.export_to_markdown(results, args.query, args.export)
                print(f"? Exported to: {output_file}")

        elif args.command == 'stats':
            # Show stats
            print(f"?? INDEX STATISTICS\n")
            print(f"  Total chunks: {rag.collection.count()}")
            print(f"  Database path: {args.db_path}\n")

    except ChromaDBCorruptionError as e:
        # ChromaDB is corrupted - show helpful error message
        print(f"\n{'='*60}")
        print(f"❌ DATABASE CORRUPTION DETECTED")
        print(f"{'='*60}\n")
        print(str(e))
        print(f"\n{'='*60}\n")
        sys.exit(1)
    except Exception as e:
        print(f"? Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
