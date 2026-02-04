#!/usr/bin/env python3
"""
ARCHILLES RAG System with Hybrid Search

Features:
1. Extract text from books (30+ formats: PDF, EPUB, DJVU, MOBI, etc.)
2. BGE-M3 embeddings (multilingual, optimized for German/Latin/Greek)
3. LanceDB with native hybrid search (vector + full-text)
4. Language filtering (auto-detected: de, en, la, fr, etc.)
5. Local storage (100% offline)

Search Modes:
- hybrid (default): Best of both worlds - finds concepts AND exact words
- semantic: Concept-based search using BGE-M3 embeddings
- keyword: Exact word matching using full-text search (great for Latin phrases, custom terms)

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
import re
from datetime import datetime
import numpy as np

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.extractors import UniversalExtractor
from src.calibre_db import CalibreDB
from src.storage import LanceDBStore
from sentence_transformers import SentenceTransformer
from tqdm import tqdm
import os


class LanceDBError(Exception):
    """Raised when LanceDB operations fail."""
    pass


# Keep for backward compatibility with other scripts
ChromaDBCorruptionError = LanceDBError


class archillesRAG:
    """
    Simple RAG system for academic books.

    Features:
    - BGE-M3 embeddings (1024 dimensions, multilingual)
    - LanceDB with native hybrid search
    - Exact page citations
    - Semantic + keyword search
    """

    def __init__(
        self,
        db_path: str = "./archilles_rag_db",
        model_name: str = None,  # Will be set by profile or default to BGE-M3
        reset_db: bool = False,
        enable_ocr: bool = False,
        force_ocr: bool = False,
        ocr_backend: str = "auto",
        ocr_language: str = "deu+eng",
        profile: str = None,  # 'minimal', 'balanced', 'maximal', or None (auto-detect)
        use_modular_pipeline: bool = False  # Future: use modular architecture
    ):
        """
        Initialize RAG system.

        Args:
            db_path: Path to LanceDB storage
            model_name: Sentence transformer model (overrides profile if set)
            reset_db: If True, delete and recreate the database
            enable_ocr: Enable OCR for scanned PDFs (auto-detect)
            force_ocr: Force OCR even for digital PDFs
            ocr_backend: OCR backend (auto, tesseract, lighton, olmocr)
            ocr_language: Language codes for Tesseract
            profile: Hardware profile (minimal/balanced/maximal) - auto-detects if None
            use_modular_pipeline: Use ModularPipeline architecture (future)
        """
        # Determine model and settings from profile
        if profile:
            from src.archilles.profiles import get_profile
            profile_config = get_profile(profile)
            if model_name is None:
                model_name = profile_config.embedding_model
            self.batch_size = profile_config.batch_size
            self.device = profile_config.embedding_device
            print(f"Initializing ARCHILLES RAG (profile: {profile})...")
        else:
            # Default to BGE-M3 and auto-detect device
            if model_name is None:
                model_name = "BAAI/bge-m3"
            self.batch_size = 8  # Conservative default for 4GB GPUs
            import torch
            self.device = 'cuda' if torch.cuda.is_available() else 'cpu'
            print(f"Initializing ARCHILLES RAG...")

        print(f"  Database: {db_path}")
        print(f"  Model: {model_name}")

        # Map string backend to enum
        from src.extractors import OCRBackend
        backend_map = {
            "auto": OCRBackend.AUTO,
            "tesseract": OCRBackend.TESSERACT,
            "lighton": OCRBackend.LIGHTON,
            "olmocr": OCRBackend.OLMOCR,
        }
        ocr_backend_enum = backend_map.get(ocr_backend.lower(), OCRBackend.AUTO)

        # Initialize extractor with OCR options
        self.extractor = UniversalExtractor(
            chunk_size=512,
            overlap=128,
            enable_ocr=enable_ocr,
            force_ocr=force_ocr,
            ocr_backend=ocr_backend_enum,
            ocr_language=ocr_language
        )

        if enable_ocr or force_ocr:
            print(f"  OCR: {'force' if force_ocr else 'auto-detect'} ({ocr_backend})")

        # Initialize embedding model
        print(f"  Loading embedding model... (first time: ~500 MB download)")

        # Use device from profile or auto-detected
        self.embedding_model = SentenceTransformer(model_name, device=self.device)
        print(f"  Model loaded: {model_name} (device: {self.device})")

        # Handle database reset if requested
        self.db_path = Path(db_path)
        if reset_db:
            print(f"  Resetting database (deleting existing data)...")
            import shutil
            if self.db_path.exists():
                shutil.rmtree(self.db_path)
                print(f"    Deleted {db_path}")

        # Initialize LanceDB
        try:
            self.store = LanceDBStore(db_path=str(self.db_path))
            print(f"  LanceDB ready")

            # Count chunks
            chunk_count = self.store.count()
            print(f"  Current index: {chunk_count} chunks")

        except Exception as e:
            raise LanceDBError(
                f"LanceDB initialization failed.\n"
                f"Error: {e}\n\n"
                f"To recover, run with --reset-db flag:\n"
                f"  python scripts/batch_index.py --tag \"YourTag\" --reset-db\n\n"
                f"WARNING: This will delete the entire index. You'll need to re-index all books."
            )

        print(f"  Native hybrid search ready (vector + full-text)\n")

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

        # Merge: Calibre metadata takes priority (user-curated), file fills gaps
        merged = {}

        # File metadata first (fallback)
        merged.update(file_metadata)
        # Calibre metadata second (preferred - overwrites file metadata)
        merged.update(calibre_metadata)

        # Track ISBN source
        if merged.get('isbn'):
            if calibre_metadata.get('isbn'):
                merged['isbn_source'] = 'calibre'
            elif file_metadata.get('isbn'):
                merged['isbn_source'] = 'file'

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

    def _index_book_phase1(self, book_path: Path, book_id: str, book_metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Phase 1 indexing: Metadata + comments only (fast).

        Creates a single searchable chunk with all metadata fields.

        Args:
            book_path: Path to book file
            book_id: Book identifier
            book_metadata: Extracted metadata dictionary

        Returns:
            Dictionary with indexing statistics
        """
        print("  [Phase 1: Metadata + Comments only]")
        start_time = time.time()

        # Build searchable metadata text
        metadata_parts = []

        # Title
        title = book_metadata.get('title', book_path.stem)
        metadata_parts.append(f"Title: {title}")

        # Author
        if book_metadata.get('author'):
            metadata_parts.append(f"Author: {book_metadata['author']}")

        # Publisher
        if book_metadata.get('publisher'):
            metadata_parts.append(f"Publisher: {book_metadata['publisher']}")

        # ISBN
        if book_metadata.get('isbn'):
            metadata_parts.append(f"ISBN: {book_metadata['isbn']}")

        # Year
        if book_metadata.get('year'):
            metadata_parts.append(f"Year: {book_metadata['year']}")

        # Tags
        if book_metadata.get('tags'):
            tags_str = ', '.join(book_metadata['tags']) if isinstance(book_metadata['tags'], list) else book_metadata['tags']
            metadata_parts.append(f"Tags: {tags_str}")

        # Subject/Keywords
        if book_metadata.get('subject'):
            metadata_parts.append(f"Subject: {book_metadata['subject']}")
        if book_metadata.get('keywords'):
            metadata_parts.append(f"Keywords: {book_metadata['keywords']}")

        # Description
        if book_metadata.get('description'):
            metadata_parts.append(f"Description: {book_metadata['description']}")

        # Calibre comments (most important for search!)
        if book_metadata.get('comments'):
            metadata_parts.append(f"\n[CALIBRE COMMENT]\n{book_metadata['comments']}")

        # Combine into single searchable text
        searchable_text = "\n".join(metadata_parts)

        # Generate embedding
        print("  [1/2] Generating metadata embedding...")
        embedding = self.embedding_model.encode(
            searchable_text,
            show_progress_bar=False,
            convert_to_numpy=True
        ).tolist()

        # Prepare metadata for LanceDB
        chunk_metadata = {
            'book_id': book_id,
            'book_title': title,
            'chunk_index': 0,  # Single chunk for metadata
            'chunk_type': 'phase1_metadata',
            'format': book_path.suffix.lower().replace('.', ''),
            'indexed_at': datetime.now().isoformat(),
            'phase': 'phase1'
        }

        # Add all book metadata fields
        if book_metadata.get('author'):
            chunk_metadata['author'] = book_metadata['author']
        if book_metadata.get('publisher'):
            chunk_metadata['publisher'] = book_metadata['publisher']
        if book_metadata.get('isbn'):
            chunk_metadata['isbn'] = book_metadata['isbn']
            if book_metadata.get('isbn_source'):
                chunk_metadata['isbn_source'] = book_metadata['isbn_source']
        if book_metadata.get('year'):
            chunk_metadata['year'] = book_metadata['year']
        if book_metadata.get('calibre_id'):
            chunk_metadata['calibre_id'] = book_metadata['calibre_id']
        if book_metadata.get('tags'):
            chunk_metadata['tags'] = ', '.join(book_metadata['tags']) if isinstance(book_metadata['tags'], list) else book_metadata['tags']
        if book_metadata.get('custom_fields'):
            import json
            chunk_metadata['custom_fields'] = json.dumps(book_metadata['custom_fields'])

        chunk_metadata['source_file'] = str(book_path)

        # Index in LanceDB
        print("  [2/2] Indexing metadata chunk...")
        chunk_data = {
            'id': f"{book_id}_metadata",
            'text': searchable_text,
            **chunk_metadata
        }
        embeddings_array = np.array([embedding])
        self.store.add_chunks([chunk_data], embeddings_array)

        index_time = time.time() - start_time

        print(f"  Phase 1 complete ({index_time:.1f}s)")
        print(f"     Collection size: {self.store.count()} chunks\n")

        return {
            'book_id': book_id,
            'chunks_indexed': 1,
            'total_words': len(searchable_text.split()),
            'total_pages': None,
            'extraction_time': 0,
            'embedding_time': index_time,
            'indexing_time': index_time,
            'total_time': index_time,
            'phase': 'phase1'
        }

    def index_book(self, book_path: str, book_id: str = None, force: bool = False, phase: str = 'phase2') -> Dict[str, Any]:
        """
        Extract and index a book.

        Args:
            book_path: Path to book file
            book_id: Optional book ID (default: filename)
            force: If True, delete existing chunks before re-indexing
            phase: 'phase1' (metadata + comments only, fast) or 'phase2' (full content, slow)

        Returns:
            Dictionary with indexing statistics
        """
        book_path = Path(book_path)

        if not book_path.exists():
            raise FileNotFoundError(f"Book not found: {book_path}")

        book_id = book_id or book_path.stem

        print(f"INDEXING BOOK: {book_path.name}")
        print(f"  Book ID: {book_id}\n")

        # Check for existing chunks and handle force reindex
        existing = self.store.get_by_book_id(book_id, limit=1)
        if existing:
            if force:
                print(f"  Deleting existing chunks for {book_id}...", flush=True)
                deleted = self.store.delete_by_book_id(book_id)
                print(f"    Deleted {deleted} chunks")
            else:
                # Count existing chunks
                all_existing = self.store.get_by_book_id(book_id, limit=10000)
                print(f"  Book already indexed ({len(all_existing)} chunks). Use --force to reindex.")
                return {
                    'book_id': book_id,
                    'status': 'already_indexed',
                    'chunks_indexed': len(all_existing),
                    'existing_chunks': len(all_existing)
                }

        # Extract metadata (author, title, year, ISBN, publisher, etc.)
        # Works for PDF, EPUB, and other formats
        book_metadata = self._extract_metadata(book_path)

        # PHASE 1: Metadata + Comments only (fast indexing)
        if phase == 'phase1':
            return self._index_book_phase1(book_path, book_id, book_metadata)

        # PHASE 2: Full content indexing (default)
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

        # Batch process for speed (batch_size determined by profile)
        for i in tqdm(range(0, len(texts), self.batch_size), desc="    Embedding"):
            batch = texts[i:i+self.batch_size]
            batch_embeddings = self.embedding_model.encode(
                batch,
                show_progress_bar=False,
                convert_to_numpy=True
            )
            embeddings.extend(batch_embeddings.tolist())

        embed_time = time.time() - start_time
        print(f"    ? Generated {len(embeddings)} embeddings in {embed_time:.1f}s\n")

        # Step 3: Index in LanceDB
        print("  [3/3] Indexing in LanceDB...")
        start_time = time.time()

        # Prepare chunks with metadata
        chunks = []
        for i, chunk in enumerate(extracted.chunks):
            chunk_data = {
                'id': f"{book_id}_chunk_{i}",
                'text': chunk['text'],
                'book_id': book_id,
                'book_title': extracted.metadata.file_path.stem,
                'chunk_index': i,
                'chunk_type': 'content',
                'format': extracted.metadata.detected_format,
                'indexed_at': datetime.now().isoformat(),
            }

            # Add book metadata
            if book_metadata:
                if book_metadata.get('author'):
                    chunk_data['author'] = book_metadata['author']
                if book_metadata.get('title'):
                    chunk_data['book_title'] = book_metadata['title']
                if book_metadata.get('year'):
                    chunk_data['year'] = book_metadata['year']
                if book_metadata.get('publisher'):
                    chunk_data['publisher'] = book_metadata['publisher']
                if book_metadata.get('calibre_id'):
                    chunk_data['calibre_id'] = book_metadata['calibre_id']
                if book_metadata.get('tags'):
                    chunk_data['tags'] = ', '.join(book_metadata['tags']) if isinstance(book_metadata['tags'], list) else book_metadata['tags']

            # Add source file path
            chunk_data['source_file'] = str(extracted.metadata.file_path)

            # Add page info if available
            if 'metadata' in chunk and chunk['metadata'].get('page'):
                chunk_data['page_number'] = chunk['metadata']['page']

            # Add chapter info if available
            if 'metadata' in chunk and chunk['metadata'].get('chapter'):
                chunk_data['chapter'] = chunk['metadata']['chapter']

            # Add section info if available (EPUB section metadata)
            if 'metadata' in chunk and chunk['metadata'].get('section'):
                chunk_data['section'] = chunk['metadata']['section']
            if 'metadata' in chunk and chunk['metadata'].get('section_title'):
                chunk_data['section_title'] = chunk['metadata']['section_title']
            if 'metadata' in chunk and chunk['metadata'].get('section_type'):
                chunk_data['section_type'] = chunk['metadata']['section_type']

            # Add language info if available
            if 'metadata' in chunk and chunk['metadata'].get('language'):
                chunk_data['language'] = chunk['metadata']['language']

            chunks.append(chunk_data)

        # Add Calibre comments as separate chunk (if available)
        if book_metadata and book_metadata.get('comments'):
            print(f"    Adding Calibre comment as searchable chunk...")

            comment_text = f"[CALIBRE_COMMENT] {book_metadata['comments']}"

            # Generate embedding for comment
            comment_embedding = self.embedding_model.encode(
                comment_text,
                show_progress_bar=False,
                convert_to_numpy=True
            )

            comment_chunk = {
                'id': f"{book_id}_comment",
                'text': comment_text,
                'book_id': book_id,
                'book_title': book_metadata.get('title', extracted.metadata.file_path.stem),
                'chunk_index': -1,
                'chunk_type': 'calibre_comment',
                'format': extracted.metadata.detected_format,
                'indexed_at': datetime.now().isoformat(),
            }

            if book_metadata.get('author'):
                comment_chunk['author'] = book_metadata['author']
            if book_metadata.get('publisher'):
                comment_chunk['publisher'] = book_metadata['publisher']
            if book_metadata.get('calibre_id'):
                comment_chunk['calibre_id'] = book_metadata['calibre_id']
            if book_metadata.get('tags'):
                comment_chunk['tags'] = ', '.join(book_metadata['tags']) if isinstance(book_metadata['tags'], list) else book_metadata['tags']

            chunks.append(comment_chunk)
            embeddings.append(comment_embedding.tolist())

        # Convert embeddings to numpy array
        embeddings_array = np.array(embeddings)

        # Add to LanceDB
        num_indexed = self.store.add_chunks(chunks, embeddings_array)

        index_time = time.time() - start_time
        print(f"    Indexed {num_indexed} chunks in {index_time:.1f}s\n")

        # Summary
        total_time = extract_time + embed_time + index_time
        print(f"INDEXING COMPLETE")
        print(f"  Total time: {total_time:.1f}s")
        print(f"  Collection size: {self.store.count()} chunks\n")

        return {
            'book_id': book_id,
            'chunks_indexed': num_indexed,
            'total_words': extracted.metadata.total_words,
            'total_pages': extracted.metadata.total_pages,
            'extraction_time': extract_time,
            'embedding_time': embed_time,
            'indexing_time': index_time,
            'total_time': total_time,
        }

    def query(
        self,
        query_text: str,
        top_k: int = 10,
        mode: Literal['semantic', 'keyword', 'hybrid'] = 'hybrid',
        language: str = None,
        book_id: str = None,
        exact_phrase: bool = False,
        tag_filter: List[str] = None,
        section_filter: str = None,
        chunk_type_filter: str = 'content',
        max_per_book: int = 2
    ) -> List[Dict[str, Any]]:
        """
        Search for relevant passages.

        Args:
            query_text: Search query
            top_k: Number of results to return (default: 10)
            mode: Search mode - 'semantic' (BGE-M3), 'keyword' (FTS), or 'hybrid' (both, default)
            language: Filter by language (e.g., 'de', 'en', 'la') or comma-separated list
            book_id: Filter by specific book ID
            exact_phrase: Use exact phrase matching (for Latin quotes, etc.)
            tag_filter: Filter by Calibre tags (e.g., ['Geschichte', 'Philosophie'])
            section_filter: Filter by section type ('main_content', 'front_matter', 'back_matter')
                           Use 'main' to exclude front/back matter from results
            chunk_type_filter: Filter by chunk type (default: 'content' - book text only)
                              'content' = book text only (DEFAULT - excludes Calibre comments)
                              'calibre_comment' = Calibre comments only
                              None = all chunk types (book text + comments mixed)
            max_per_book: Maximum results per book (default: 2, use 999 for unlimited)

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
        if chunk_type_filter:
            filters.append(f"chunk_type={chunk_type_filter}")
        if max_per_book < 999:
            filters.append(f"max {max_per_book}/book")

        filter_msg = f" ({', '.join(filters)})" if filters else ""
        print(f"QUERY [{mode.upper()}]: \"{query_text}\"{filter_msg}")
        print(f"  Searching {self.store.count()} chunks...\n")

        # Oversample to allow for diversity filtering
        # If max_per_book is set, we need to fetch more results than top_k
        # to ensure we have enough diverse results after filtering
        # Higher factor (5) enables finding more diverse books in large libraries
        oversample_factor = 5 if max_per_book < 999 else 1
        search_top_k = top_k * oversample_factor

        # Route to appropriate search method
        if mode == 'semantic':
            results = self._semantic_search(query_text, search_top_k, language, book_id, chunk_type_filter)
        elif mode == 'keyword':
            results = self._keyword_search(query_text, search_top_k, language, book_id, chunk_type_filter, exact_phrase=exact_phrase)
        elif mode == 'hybrid':
            results = self._hybrid_search(query_text, search_top_k, language, book_id, chunk_type_filter, exact_phrase=exact_phrase)
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
        book_id: str = None,
        chunk_type_filter: str = None
    ) -> List[Dict[str, Any]]:
        """Semantic search using BGE-M3 embeddings via LanceDB."""
        # Generate query embedding
        query_embedding = self.embedding_model.encode(
            query_text,
            convert_to_numpy=True
        )

        # Resolve book_id to calibre_id if numeric
        calibre_id = None
        resolved_book_id = book_id
        if book_id and str(book_id).isdigit():
            calibre_id = int(book_id)
            resolved_book_id = None

        # Search in LanceDB
        results = self.store.vector_search(
            query_vector=query_embedding,
            top_k=top_k,
            book_id=resolved_book_id,
            calibre_id=calibre_id,
            chunk_type=chunk_type_filter,
            language=language
        )

        # Format results
        return self._format_lancedb_results(results, score_type='semantic')

    def _keyword_search(
        self,
        query_text: str,
        top_k: int,
        language: str = None,
        book_id: str = None,
        chunk_type_filter: str = None,
        exact_phrase: bool = False
    ) -> List[Dict[str, Any]]:
        """Keyword search using LanceDB full-text search."""
        # For exact phrase matching, use different approach
        if exact_phrase:
            return self._exact_phrase_search(query_text, top_k, language, book_id, chunk_type_filter)

        # Resolve book_id to calibre_id if numeric
        calibre_id = None
        resolved_book_id = book_id
        if book_id and str(book_id).isdigit():
            calibre_id = int(book_id)
            resolved_book_id = None

        # Search in LanceDB using full-text search
        results = self.store.fts_search(
            query_text=query_text,
            top_k=top_k,
            book_id=resolved_book_id,
            calibre_id=calibre_id,
            chunk_type=chunk_type_filter,
            language=language
        )

        # Format results
        return self._format_lancedb_results(results, score_type='keyword')

    def _exact_phrase_search(
        self,
        query_text: str,
        top_k: int,
        language: str = None,
        book_id: str = None,
        chunk_type_filter: str = None
    ) -> List[Dict[str, Any]]:
        """
        Exact phrase matching (case-insensitive).

        Finds documents that contain the EXACT phrase, not just the words.
        Critical for Latin phrases like "evangelista et a presbyteris".

        IMPORTANT: Normalizes whitespace to handle line breaks!
        """
        # Get all chunks (filtered by book/language if specified)
        calibre_id = None
        resolved_book_id = book_id
        if book_id and str(book_id).isdigit():
            calibre_id = int(book_id)
            resolved_book_id = None

        # Fetch chunks to search through
        all_chunks = self.store.get_all(limit=10000)

        # Normalize query
        query_normalized = re.sub(r'\s+', ' ', query_text.lower().strip())

        # Find exact matches
        matches = []
        for chunk in all_chunks:
            # Apply filters
            if language:
                langs = [l.strip() for l in language.split(',')] if ',' in language else [language]
                if chunk.get('language') not in langs:
                    continue

            if resolved_book_id and chunk.get('book_id') != resolved_book_id:
                continue

            if calibre_id and chunk.get('calibre_id') != calibre_id:
                continue

            if chunk_type_filter and chunk.get('chunk_type') != chunk_type_filter:
                continue

            # Normalize document text
            doc_text = chunk.get('text', '')
            doc_normalized = re.sub(r'\s+', ' ', doc_text.lower())

            # Check for exact phrase
            if query_normalized in doc_normalized:
                count = doc_normalized.count(query_normalized)
                matches.append({
                    'rank': 0,
                    'text': doc_text,
                    'metadata': chunk,
                    'score': count,
                    'similarity': min(count / 10.0, 1.0),
                })

        # Sort by score
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
        chunk_type_filter: str = None,
        exact_phrase: bool = False
    ) -> List[Dict[str, Any]]:
        """
        Hybrid search using LanceDB native hybrid search (vector + FTS).

        IMPORTANT: If exact_phrase=True, ONLY returns exact phrase matches!
        """
        # For exact phrase matching, skip hybrid search entirely
        if exact_phrase:
            return self._keyword_search(query_text, top_k, language, book_id, chunk_type_filter, exact_phrase=True)

        # Generate query embedding
        query_embedding = self.embedding_model.encode(
            query_text,
            convert_to_numpy=True
        )

        # Resolve book_id to calibre_id if numeric
        calibre_id = None
        resolved_book_id = book_id
        if book_id and str(book_id).isdigit():
            calibre_id = int(book_id)
            resolved_book_id = None

        # Use LanceDB native hybrid search
        results = self.store.hybrid_search(
            query_text=query_text,
            query_vector=query_embedding,
            top_k=top_k,
            book_id=resolved_book_id,
            calibre_id=calibre_id,
            chunk_type=chunk_type_filter,
            language=language
        )

        # Format and apply boost factors
        formatted_results = self._format_lancedb_results(results, score_type='hybrid')

        # Apply boost factors for Calibre comments and tag matches
        query_terms = set(query_text.lower().split())

        for result in formatted_results:
            metadata = result['metadata']

            # Boost for Calibre comments
            if metadata.get('chunk_type') == 'calibre_comment':
                result['score'] *= 1.2
                result['similarity'] *= 1.2

            # Boost for tag matches
            if metadata.get('tags'):
                result_tags = set(metadata['tags'].lower().split(', '))
                if query_terms & result_tags:
                    result['score'] *= 1.15
                    result['similarity'] *= 1.15

        # Re-sort by boosted scores
        formatted_results.sort(key=lambda x: x['score'], reverse=True)

        # Re-assign ranks
        for i, result in enumerate(formatted_results):
            result['rank'] = i + 1

        return formatted_results

    def _format_lancedb_results(self, results: List[Dict], score_type: str = 'semantic') -> List[Dict[str, Any]]:
        """Format LanceDB results into standard format."""
        formatted_results = []

        for i, result in enumerate(results):
            # Extract text and score
            text = result.get('text', '')
            score = result.get('score', 0.0)

            # Build metadata dict (all fields except text, vector, score)
            metadata = {k: v for k, v in result.items()
                       if k not in ('text', 'vector', 'score', '_distance', '_score')}

            formatted_result = {
                'rank': i + 1,
                'text': text,
                'metadata': metadata,
                'similarity': score,
                'score': score,
                'score_type': score_type
            }
            formatted_results.append(formatted_result)

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
                # Simple tokenization: lowercase and split on word boundaries
                query_tokens = re.findall(r"[\w'-]+", query_text.lower())

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

            # Build citation with section/chapter info
            citation_parts = []
            if metadata.get('book_title'):
                citation_parts.append(metadata['book_title'])

            # Priority: Section number and/or section title
            section = metadata.get('section')
            section_title = metadata.get('section_title')

            if section and section_title:
                # Best case: "Section 19.20 - LAND WARFARE"
                citation_parts.append(f"Section {section} - {section_title}")
            elif section:
                # Just section number: "Section 19.20"
                citation_parts.append(f"Section {section}")
            elif section_title:
                # Just section title: "LAND WARFARE"
                citation_parts.append(section_title)
            elif metadata.get('chapter'):
                # Fallback: chapter name
                citation_parts.append(metadata['chapter'])

            # Also show page number if available (in addition to section)
            printed_page = metadata.get('printed_page')
            printed_conf = metadata.get('printed_page_confidence', 0.0)
            page_warning = None

            # Debug mode: show raw metadata values
            if os.environ.get('DEBUG_METADATA'):
                print(f"    [DEBUG] section: {repr(section)}, section_title: {repr(section_title)}")
                print(f"    [DEBUG] printed_page: {repr(printed_page)} (type: {type(printed_page).__name__})")

            if printed_page and printed_conf >= 0.8:
                # Use printed page number (high confidence)
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

            citation = ', '.join(citation_parts) if citation_parts else metadata.get('book_id', 'Unknown')

            # Add chunk type indicator
            chunk_type = metadata.get('chunk_type', '')
            type_indicator = ''
            if chunk_type == 'calibre_comment':
                type_indicator = ' [CALIBRE_COMMENT]'
            elif chunk_type == 'phase1_metadata':
                type_indicator = ' [METADATA]'

            print(f"\n[{rank}] {citation}{type_indicator}")
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

            # Build citation with section-aware priority
            section = metadata.get('section')
            section_title = metadata.get('section_title')
            chapter = metadata.get('chapter')

            citation_parts = []

            # Priority 1: Section info (if available)
            if section and section_title:
                citation_parts.append(f"Section {section} - {section_title}")
            elif section:
                citation_parts.append(f"Section {section}")
            elif section_title:
                citation_parts.append(section_title)
            elif chapter:
                citation_parts.append(chapter)

            # Add page info
            printed_page = metadata.get('printed_page')
            printed_conf = metadata.get('printed_page_confidence', 0.0)

            if printed_page and printed_conf >= 0.8:
                page_str = f"S. {str(printed_page)}"
                if printed_conf < 1.0:
                    page_str += f" (Konfidenz: {printed_conf:.2f})"
                citation_parts.append(page_str)
            elif metadata.get('page'):
                citation_parts.append(f"PDF S. {metadata['page']}")

            # Result header with author and year
            author = metadata.get('author', '')
            year = metadata.get('year', '')

            # Add chunk type indicator
            chunk_type = metadata.get('chunk_type', '')
            type_indicator = ''
            if chunk_type == 'calibre_comment':
                type_indicator = ' 📝'  # Emoji for markdown
            elif chunk_type == 'phase1_metadata':
                type_indicator = ' ℹ️'

            if author and year:
                header = f"## [{rank}] {author}: {book_title} ({year}){type_indicator}"
            elif author:
                header = f"## [{rank}] {author}: {book_title}{type_indicator}"
            elif year:
                header = f"## [{rank}] {book_title} ({year}){type_indicator}"
            else:
                header = f"## [{rank}] {book_title}{type_indicator}"

            lines.append(header)

            # Location (section + page)
            if citation_parts:
                lines.append(f"**Ort:** {' | '.join(citation_parts)}  ")

            # Relevanz
            lines.append(f"**Relevanz:** {similarity:.3f}  ")

            # Direct link to PDF/EPUB (file:/// protocol)
            source_file = metadata.get('source_file')
            calibre_id = metadata.get('calibre_id')

            link_parts = []

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

                link_parts.append(f"[{filename}]({file_url})")

            # Add Calibre URI if available (opens in Calibre library viewer)
            if calibre_id:
                # Format: calibre://view/<calibre_id>
                # Optional: add #page=N if we have a page number
                calibre_url = f"calibre://view/{calibre_id}"

                # Add page anchor if we have page info
                if metadata.get('page'):
                    calibre_url += f"#page={metadata['page']}"

                link_parts.append(f"[📚 Open in Calibre]({calibre_url})")

            if link_parts:
                lines.append(f"**Quelle:** {' | '.join(link_parts)}  ")

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
  python scripts/rag_demo.py query "Herrschaftslegitimation" --mode keyword    # Exact word matching (FTS)
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
    # OCR options
    index_parser.add_argument('--enable-ocr', action='store_true', help='Enable OCR for scanned PDFs (auto-detect)')
    index_parser.add_argument('--force-ocr', action='store_true', help='Force OCR even for digital PDFs (skip text extraction)')
    index_parser.add_argument('--ocr-backend', choices=['auto', 'tesseract', 'lighton', 'olmocr'], default='auto',
                              help='OCR backend: auto (best available), tesseract, lighton, olmocr')
    index_parser.add_argument('--ocr-language', default='deu+eng', help='Tesseract language codes (default: deu+eng)')
    # Hardware profile options
    index_parser.add_argument('--profile', choices=['minimal', 'balanced', 'maximal'],
                              help='Hardware profile: minimal (CPU), balanced (GPU 6-12GB), maximal (GPU 12GB+)')
    index_parser.add_argument('--use-modular-pipeline', action='store_true',
                              help='Use new ModularPipeline architecture (parser→chunker→embedder)')

    # Query command
    query_parser = subparsers.add_parser('query', help='Search indexed books')
    query_parser.add_argument('query', help='Search query')
    query_parser.add_argument('--top-k', type=int, default=10, help='Number of results (default: 10)')
    query_parser.add_argument('--mode', choices=['semantic', 'keyword', 'hybrid'], default='hybrid',
                              help='Search mode: semantic (BGE-M3), keyword (FTS), or hybrid (both, default)')
    query_parser.add_argument('--exact', action='store_true',
                              help='Exact phrase matching (case-insensitive) - critical for Latin quotes')
    query_parser.add_argument('--language', help='Filter by language (e.g., de, en, la) or comma-separated')
    query_parser.add_argument('--book-id', help='Filter by specific book ID')
    query_parser.add_argument('--tag-filter', nargs='+', help='Filter by Calibre tags (e.g., --tag-filter Geschichte Philosophie)')
    query_parser.add_argument('--section', choices=['main', 'main_content', 'front_matter', 'back_matter'],
                              help='Filter by section type: main (exclude index/TOC), front_matter, back_matter')
    query_parser.add_argument('--chunk-type', choices=['phase1_metadata', 'content', 'calibre_comment', 'all'],
                              default='content',
                              help='Filter by chunk type: content (book text only, DEFAULT), calibre_comment (Calibre comments), all (both)')
    query_parser.add_argument('--max-per-book', type=int, default=2, help='Maximum results per book (default: 2, use 999 for unlimited)')
    query_parser.add_argument('--db-path', default=None, help='Database path (default: CALIBRE_LIBRARY/.archilles/rag_db)')
    query_parser.add_argument('--export', metavar='FILE', help='Export results to Markdown file (for Joplin/Obsidian)')

    # Stats command
    stats_parser = subparsers.add_parser('stats', help='Show index statistics')
    stats_parser.add_argument('--db-path', default=None, help='Database path (default: CALIBRE_LIBRARY/.archilles/rag_db)')

    # Create-index command
    create_index_parser = subparsers.add_parser('create-index', help='Create search indexes (FTS and/or IVF-PQ)')
    create_index_parser.add_argument('--db-path', default=None, help='Database path (default: CALIBRE_LIBRARY/.archilles/rag_db)')
    create_index_parser.add_argument('--fts-only', action='store_true', help='Only create FTS index (skip IVF-PQ vector index)')

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
        # Initialize RAG with OCR and profile options (only for index command)
        reset_db = getattr(args, 'reset_db', False)
        enable_ocr = getattr(args, 'enable_ocr', False)
        force_ocr = getattr(args, 'force_ocr', False)
        ocr_backend = getattr(args, 'ocr_backend', 'auto')
        ocr_language = getattr(args, 'ocr_language', 'deu+eng')
        profile = getattr(args, 'profile', None)
        use_modular_pipeline = getattr(args, 'use_modular_pipeline', False)

        rag = archillesRAG(
            db_path=args.db_path,
            reset_db=reset_db,
            enable_ocr=enable_ocr,
            force_ocr=force_ocr,
            ocr_backend=ocr_backend,
            ocr_language=ocr_language,
            use_modular_pipeline=use_modular_pipeline,
            profile=profile
        )

        if args.command == 'index':
            # Index a book
            stats = rag.index_book(args.book_path, args.book_id, force=args.force)

        elif args.command == 'query':
            # Search
            # Handle chunk_type: 'all' means no filter (None), otherwise use the specified type
            chunk_type = args.chunk_type if hasattr(args, 'chunk_type') else 'content'
            chunk_type_filter = None if chunk_type == 'all' else chunk_type

            results = rag.query(
                args.query,
                top_k=args.top_k,
                mode=args.mode,
                language=args.language,
                book_id=args.book_id,
                exact_phrase=args.exact,
                tag_filter=args.tag_filter if hasattr(args, 'tag_filter') else None,
                section_filter=args.section if hasattr(args, 'section') else None,
                chunk_type_filter=chunk_type_filter,
                max_per_book=args.max_per_book if hasattr(args, 'max_per_book') else 2
            )
            rag.print_results(results, query_text=args.query)

            # Export to Markdown if requested
            if args.export:
                output_file = rag.export_to_markdown(results, args.query, args.export)
                print(f"? Exported to: {output_file}")

        elif args.command == 'stats':
            # Show stats
            print(f"INDEX STATISTICS\n")
            print(f"  Total chunks: {rag.store.count()}")
            print(f"  Database path: {args.db_path}\n")

        elif args.command == 'create-index':
            # Create search indexes
            chunk_count = rag.store.count()
            print(f"Creating indexes for {chunk_count} chunks...\n")

            if args.fts_only:
                rag.store.create_fts_index()
            else:
                rag.store.create_indexes(chunk_count)

            print("\nIndex creation complete.")

    except LanceDBError as e:
        # LanceDB error - show helpful error message
        print(f"\n{'='*60}")
        print(f"DATABASE ERROR")
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
