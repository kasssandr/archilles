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
from html import escape as _html_escape
from pathlib import Path
from typing import List, Dict, Any, Literal, Optional
import time
import re
import hashlib
import json
from datetime import datetime
import numpy as np

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.archilles.config import get_library_path, get_rag_db_path
from src.archilles.constants import ChunkType, SectionType
from src.service.archilles_service import diversify_results
from src.extractors import UniversalExtractor
from src.calibre_db import CalibreDB
from src.storage import LanceDBStore
from src.calibre_mcp.annotations import get_combined_annotations
from sentence_transformers import SentenceTransformer
from tqdm import tqdm
import os


class LanceDBError(Exception):
    """Raised when LanceDB operations fail."""
    pass



class archillesRAG:
    """
    Simple RAG system for academic books.

    Features:
    - BGE-M3 embeddings (1024 dimensions, multilingual)
    - LanceDB with native hybrid search
    - Exact page citations
    - Semantic + keyword search
    """

    # Fields to copy from Calibre book_data into chunk metadata
    _CALIBRE_FIELDS = ('author', 'title', 'publisher', 'language', 'isbn',
                       'calibre_id', 'tags', 'comments', 'custom_fields')

    # Common stop words for multilingual queries
    STOP_WORDS = {
        # English
        'a', 'an', 'and', 'are', 'as', 'at', 'be', 'by', 'for', 'from',
        'has', 'he', 'in', 'is', 'it', 'its', 'of', 'on', 'that', 'the',
        'to', 'was', 'will', 'with', 'or', 'but', 'not', 'this', 'these',
        # German
        'der', 'die', 'das', 'den', 'dem', 'des', 'ein', 'eine', 'einer',
        'eines', 'einem', 'einen', 'und', 'oder', 'aber', 'von', 'zu',
        'im', 'am', 'um', 'bei', 'mit', 'für', 'aus', 'auf', 'durch',
        # French
        'le', 'la', 'les', 'un', 'une', 'des', 'du', 'de', 'd', 'et', 'ou',
        'mais', 'dans', 'pour', 'par', 'sur', 'avec', 'au', 'aux', 'ce',
        'cette', 'ces', 'est', 'sont', 'être', 'avoir', 'à', 'son', 'sa',
        # Spanish
        'el', 'la', 'los', 'las', 'un', 'una', 'unos', 'unas', 'y', 'o',
        'pero', 'en', 'por', 'para', 'con', 'sin', 'sobre', 'del', 'al',
        'es', 'son', 'ser', 'estar', 'haber', 'ha', 'han', 'su', 'sus',
        # Italian
        'il', 'lo', 'la', 'i', 'gli', 'le', 'un', 'uno', 'una', 'e', 'o',
        'ma', 'in', 'di', 'd', 'da', 'per', 'con', 'su', 'del', 'della', 'dei',
        'degli', 'delle', 'al', 'alla', 'ai', 'agli', 'alle', 'è', 'sono',
        # Portuguese
        'o', 'a', 'os', 'as', 'um', 'uma', 'uns', 'umas', 'e', 'ou',
        'mas', 'em', 'de', 'por', 'para', 'com', 'sem', 'sobre', 'do',
        'da', 'dos', 'das', 'ao', 'à', 'aos', 'às', 'é', 'são', 'seu', 'sua',
        # Dutch
        'de', 'het', 'een', 'en', 'of', 'maar', 'in', 'op', 'voor', 'van',
        'met', 'door', 'bij', 'aan', 'naar', 'om', 'over', 'is', 'zijn',
        'was', 'waren', 'heeft', 'hebben', 'had', 'hadden', 'zijn', 'der',
        # Latin
        'et', 'in', 'ad', 'cum', 'ex', 'ab', 'a', 'e', 'de', 'per', 'pro', 'sub',
        'atque', 'sed', 'aut', 'vel', 'ac', 'neque', 'nec', 'est', 'sunt',
        # Russian (Cyrillic)
        'и', 'в', 'на', 'с', 'по', 'для', 'к', 'от', 'за', 'о',
        'из', 'у', 'это', 'как', 'но', 'или', 'а', 'не', 'что', 'он',
        # Greek (ancient & modern)
        'ο', 'η', 'το', 'οι', 'τα', 'και', 'ή', 'αλλά', 'σε', 'από',
        'για', 'με', 'στο', 'στη', 'στον', 'στην', 'του', 'της', 'των', 'εν',
        # Hebrew (with common particles)
        'ה', 'ו', 'ב', 'ל', 'מ', 'ש', 'של', 'את', 'על', 'אל', 'עם',
        'כי', 'אם', 'או', 'זה', 'זאת', 'אלה', 'הוא', 'היא',
        # Arabic
        'في', 'من', 'إلى', 'على', 'هذا', 'هذه', 'و', 'أو', 'لا',
        'ما', 'هو', 'هي', 'التي', 'الذي', 'مع', 'عن', 'إن', 'ال',
    }

    @staticmethod
    def _format_tags(tags) -> str:
        """Format tags as a comma-separated string, whether input is a list or string."""
        return ', '.join(tags) if isinstance(tags, list) else tags

    @staticmethod
    def _resolve_book_id(book_id: str):
        """
        Resolve book_id to (resolved_book_id, calibre_id, source_id) tuple.

        If book_id is numeric, treat it as a calibre_id *and* source_id
        (backward compat).  Otherwise it's a plain book_id string.
        """
        if book_id and str(book_id).isdigit():
            return None, int(book_id), str(book_id)
        return book_id, None, None

    @staticmethod
    def _format_section_citation(metadata: Dict[str, Any]) -> str:
        """
        Build a section/chapter citation string from metadata.
        Returns empty string if no section info is available.
        """
        section = metadata.get('section')
        section_title = metadata.get('section_title')

        if section and section_title:
            return f"Section {section} - {section_title}"
        if section:
            return f"Section {section}"
        if section_title:
            return section_title
        if metadata.get('chapter'):
            return metadata['chapter']
        return ''

    @staticmethod
    def _format_section_meta(metadata: Dict[str, Any], label: str = "Kapitel") -> str:
        """
        Build a section/chapter metadata string for XML/inline output.
        Returns empty string if no section info is available.
        """
        section = metadata.get('section')
        section_title = metadata.get('section_title')

        if section and section_title:
            return f"{label}: {section} - {section_title}"
        if section_title:
            return f"{label}: {section_title}"
        if section:
            return f"Abschnitt: {section}"
        if metadata.get('chapter'):
            return f"{label}: {metadata['chapter']}"
        return ''

    @staticmethod
    def _resolve_page_info(metadata: Dict[str, Any]):
        """
        Resolve the best page value and optional warning from metadata.
        Returns (page_value_or_None, is_pdf_page: bool, warning_or_None).

        page_value is the raw page number/label (e.g. "213", "xiv").
        is_pdf_page indicates whether this is a PDF page (vs. printed/label).
        """
        page_label = metadata.get('page_label')
        printed_page = metadata.get('printed_page')
        printed_conf = metadata.get('printed_page_confidence', 0.0)

        if page_label:
            return page_label, False, None

        if printed_page and printed_conf >= 0.8:
            warning = None
            if printed_conf < 0.9:
                warning = f"Seitenzahl-Konfidenz: {printed_conf:.2f} - bitte verifizieren"
            return printed_page, False, warning

        page = metadata.get('page') or metadata.get('page_number')
        if page:
            warning = None
            if printed_page:
                warning = f"Gedruckte Seitenzahl unsicher (Konfidenz: {printed_conf:.2f})"
            return page, True, warning

        return None, False, None

    def _apply_book_metadata_to_chunk(self, chunk_data: Dict[str, Any],
                                       book_metadata: Dict[str, Any]) -> None:
        """Copy standard book metadata fields into a chunk dict (in-place)."""
        if not book_metadata:
            return
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
        if book_metadata.get('source_id'):
            chunk_data['source_id'] = book_metadata['source_id']
        if book_metadata.get('tags'):
            chunk_data['tags'] = self._format_tags(book_metadata['tags'])

    @staticmethod
    def _build_annotation_text(annot: Dict[str, Any]) -> str:
        """
        Build searchable annotation text from a highlight/note annotation.
        Returns empty string if annotation has no meaningful content.
        """
        highlighted = annot.get('highlighted_text', '').strip()
        notes = annot.get('notes', '').strip()

        if highlighted and notes:
            return f"[ANNOTATION] {highlighted} | Note: {notes}"
        if highlighted:
            return f"[ANNOTATION] {highlighted}"
        if notes:
            return f"[ANNOTATION_NOTE] {notes}"
        return ''

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
        use_modular_pipeline: bool = False,  # Future: use modular architecture
        hierarchical: bool = False,  # Enable parent-child chunking
        adapter=None,  # Optional SourceAdapter for metadata lookup
        skip_model: bool = False,  # Skip loading embedding model (for prepare-only mode)
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
            hierarchical: Enable parent-child chunking (parents ~2048, children ~512 tokens)
        """
        self.hierarchical = hierarchical
        self.use_modular_pipeline = use_modular_pipeline
        self.profile_name = profile
        self._adapter = adapter  # SourceAdapter (or None for legacy CalibreDB path)
        # Determine model and settings from profile
        import torch
        cuda_available = torch.cuda.is_available()

        if profile:
            from src.archilles.profiles import get_profile
            profile_config = get_profile(profile)
            if model_name is None:
                model_name = profile_config.embedding_model
            self.batch_size = profile_config.batch_size
            # Auto-detect: use CUDA if profile wants it AND it's available
            if profile_config.embedding_device == "cuda" and cuda_available:
                self.device = "cuda"
            else:
                self.device = "cpu"
                if profile_config.embedding_device == "cuda" and not cuda_available:
                    print(f"  ⚠️  CUDA not available, falling back to CPU")
            print(f"Initializing ARCHILLES RAG (profile: {profile})...")
        else:
            # Default to BGE-M3 and auto-detect device
            if model_name is None:
                model_name = "BAAI/bge-m3"
            self.batch_size = 8  # Conservative default for 4GB GPUs
            self.device = 'cuda' if cuda_available else 'cpu'
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

        # Initialize embedding model (skip for prepare-only mode)
        if skip_model:
            self.embedding_model = None
            print(f"  Embedding model: skipped (prepare-only mode)")
        else:
            print(f"  Loading embedding model... (first time: ~500 MB download)")
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

            # Count chunks (cached — refreshed via _refresh_chunk_count())
            self._chunk_count = self.store.count()
            print(f"  Current index: {self._chunk_count} chunks")

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

    @staticmethod
    def _compute_metadata_hash(book_metadata: Dict[str, Any]) -> str:
        """
        Compute a hash of Calibre metadata fields that matter for indexing.
        Used to detect metadata changes without re-indexing the full book text.

        Fields included: comments, tags, title, author, publisher.
        """
        if not book_metadata:
            return ''
        tags = book_metadata.get('tags', [])
        if isinstance(tags, list):
            tags = sorted(tags)
        relevant = {
            'comments': book_metadata.get('comments', ''),
            'tags': tags,
            'title': book_metadata.get('title', ''),
            'author': book_metadata.get('author', ''),
            'publisher': book_metadata.get('publisher', ''),
        }
        return hashlib.md5(json.dumps(relevant, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()

    @staticmethod
    def _compute_annotation_hash(annotations: List[Dict[str, Any]]) -> str:
        """
        Compute a hash over all annotations for a book.
        Used to detect annotation changes without re-indexing the full book text.
        """
        if not annotations:
            return ''
        # Sort by text content for deterministic hash
        texts = sorted(
            f"{a.get('highlighted_text', '')}|{a.get('notes', '')}|{a.get('type', '')}"
            for a in annotations
        )
        return hashlib.md5('\n'.join(texts).encode('utf-8')).hexdigest()

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
        Extract metadata from source adapter or Calibre database (read-only).

        Uses the SourceAdapter if available; falls back to direct CalibreDB
        access for backward compatibility.

        Args:
            file_path: Path to book file

        Returns:
            Dictionary with metadata (empty if not in any known library)
        """
        # ── New path: use SourceAdapter ─────────────────────────
        if self._adapter is not None:
            try:
                doc_meta = self._adapter.get_metadata_by_path(file_path)
                if doc_meta is None:
                    return {}
                metadata = {}
                # Map DocumentMetadata fields to the dict format the rest
                # of rag_demo.py expects (matching _CALIBRE_FIELDS keys).
                if doc_meta.authors:
                    metadata['author'] = ' & '.join(doc_meta.authors)
                if doc_meta.title:
                    metadata['title'] = doc_meta.title
                if doc_meta.publisher:
                    metadata['publisher'] = doc_meta.publisher
                if doc_meta.language:
                    metadata['language'] = doc_meta.language
                if doc_meta.identifiers.get('isbn'):
                    metadata['isbn'] = doc_meta.identifiers['isbn']
                if doc_meta.tags:
                    metadata['tags'] = doc_meta.tags
                if doc_meta.comments:
                    metadata['comments'] = doc_meta.comments
                if doc_meta.comments_html:
                    metadata['comments_html'] = doc_meta.comments_html
                if doc_meta.custom_fields:
                    metadata['custom_fields'] = doc_meta.custom_fields
                # Adapter-agnostic ID  →  both source_id and calibre_id
                metadata['source_id'] = doc_meta.doc_id
                if doc_meta.doc_id.isdigit():
                    metadata['calibre_id'] = int(doc_meta.doc_id)
                return metadata
            except Exception:
                pass
            return {}

        # ── Legacy path: direct CalibreDB access ───────────────
        metadata = {}
        try:
            library_path = CalibreDB.find_library_path(file_path)
            if not library_path:
                return metadata

            with CalibreDB(library_path) as calibre:
                book_data = calibre.get_book_by_path(file_path)

                if book_data:
                    for field in self._CALIBRE_FIELDS:
                        if book_data.get(field):
                            metadata[field] = book_data[field]
                    # Backfill source_id from calibre_id for consistency
                    if book_data.get('calibre_id'):
                        metadata['source_id'] = str(book_data['calibre_id'])
                    if book_data.get('comments_html'):
                        metadata['comments_html'] = book_data['comments_html']
        except Exception:
            pass

        return metadata

    def _index_book_modular_pipeline(self, book_path: Path, book_id: str, book_metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Index a book using the ModularPipeline architecture.

        Uses the new parser → chunker → embedder pipeline instead of
        UniversalExtractor + manual embedding. Activated by --use-modular-pipeline flag.

        Args:
            book_path: Path to book file
            book_id: Book identifier
            book_metadata: Metadata from _extract_metadata()

        Returns:
            Dictionary with indexing statistics
        """
        from src.archilles.pipeline import ModularPipeline

        profile_name = self.profile_name or 'minimal'
        print(f"  Using ModularPipeline (profile: {profile_name})")

        try:
            pipeline = ModularPipeline.from_profile(profile_name)
            processed = pipeline.process(book_path)

            print(f"  Parsed: {processed.page_count or 'N/A'} pages in {processed.parse_time:.1f}s")
            print(f"  Chunked: {processed.chunk_count} chunks in {processed.chunk_time:.1f}s")
            print(f"  Embedded: {processed.chunk_count} vectors in {processed.embed_time:.1f}s")

            # Store via the LanceDB adapter
            calibre_id = book_metadata.get('calibre_id', 0)
            source_id = book_metadata.get('source_id') or (str(calibre_id) if calibre_id else None)
            chunks_added = self.store.add_processed_documents(
                processed,
                book_metadata={
                    "book_id": book_id,
                    "author": book_metadata.get('author', ''),
                    "publisher": book_metadata.get('publisher', ''),
                    "year": book_metadata.get('year', 0),
                    "tags": book_metadata.get('tags', ''),
                    "language": book_metadata.get('language', ''),
                },
                calibre_id=calibre_id if calibre_id else None,
                source_id=source_id,
            )

            # Unload model to free GPU memory
            pipeline.unload()

            print(f"\n  Indexed {chunks_added} chunks in {processed.total_time:.1f}s total")

            return {
                'book_id': book_id,
                'status': 'indexed',
                'chunks_indexed': chunks_added,
                'pipeline': 'modular',
                'profile': profile_name,
                'parse_time': processed.parse_time,
                'chunk_time': processed.chunk_time,
                'embed_time': processed.embed_time,
                'total_time': processed.total_time,
            }

        except Exception as e:
            print(f"\n  ModularPipeline failed: {e}")
            print(f"  Falling back to legacy extractor...")
            self.use_modular_pipeline = False  # Disable for this session
            return self.index_book(str(book_path), book_id, force=True)

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
            metadata_parts.append(f"Tags: {self._format_tags(book_metadata['tags'])}")

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
            'chunk_type': ChunkType.PHASE1_METADATA,
            'format': book_path.suffix.lower().replace('.', ''),
            'indexed_at': datetime.now().isoformat(),
            'phase': 'phase1'
        }

        # Add all book metadata fields
        self._apply_book_metadata_to_chunk(chunk_metadata, book_metadata)
        if book_metadata.get('isbn'):
            chunk_metadata['isbn'] = book_metadata['isbn']
            if book_metadata.get('isbn_source'):
                chunk_metadata['isbn_source'] = book_metadata['isbn_source']
        if book_metadata.get('custom_fields'):
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

        print(f"  File: {book_path.name}")

        # Check for existing CONTENT chunks (not just metadata)
        # Books with only phase1_metadata chunks still need full content indexing
        existing = self.store.get_by_book_id(book_id, limit=100)
        content_chunks = [c for c in existing
                          if c.get('chunk_type', ChunkType.CONTENT) in ChunkType.HIERARCHICAL_TYPES]
        if content_chunks:
            if force:
                print(f"  Deleting existing chunks for {book_id}...", flush=True)
                deleted = self.store.delete_by_book_id(book_id)
                print(f"    Deleted {deleted} chunks")
            else:
                # Check if metadata or annotations have changed (smart update without full re-index)
                book_metadata = self._extract_metadata(book_path)
                current_meta_hash = self._compute_metadata_hash(book_metadata)
                stored_meta_hash = content_chunks[0].get('metadata_hash', '')

                # Check annotation changes
                try:
                    annot_result = get_combined_annotations(
                        book_path=str(book_path), include_pdf=True,
                        exclude_toc_markers=True, min_length=20
                    )
                    current_annotations = annot_result.get('annotations', [])
                    current_annot_hash = self._compute_annotation_hash(current_annotations)
                except Exception:
                    current_annotations = []
                    current_annot_hash = ''
                existing_annot_chunks = [c for c in existing if c.get('chunk_type') == ChunkType.ANNOTATION]
                stored_annot_hash = existing_annot_chunks[0].get('annotation_hash', '') if existing_annot_chunks else ''

                meta_changed = current_meta_hash != stored_meta_hash
                annot_changed = current_annot_hash != stored_annot_hash

                if meta_changed or annot_changed:
                    return self._update_metadata_only(
                        book_id, book_metadata, current_meta_hash, existing,
                        annotations=current_annotations if annot_changed else None,
                        annotation_hash=current_annot_hash if annot_changed else None,
                        book_path=book_path,
                    )

                print(f"  Book already indexed ({len(content_chunks)} content chunks). Use --force to reindex.")
                return {
                    'book_id': book_id,
                    'status': 'already_indexed',
                    'chunks_indexed': len(content_chunks),
                    'existing_chunks': len(existing)
                }
        elif existing and not force:
            # Has metadata-only chunks — delete them before full indexing
            print(f"  Replacing {len(existing)} metadata-only chunks with full content...")
            self.store.delete_by_book_id(book_id)

        # Extract metadata (author, title, year, ISBN, publisher, etc.)
        # Works for PDF, EPUB, and other formats
        book_metadata = self._extract_metadata(book_path)

        # MODULAR PIPELINE PATH: Use new architecture if flag is set
        if self.use_modular_pipeline:
            return self._index_book_modular_pipeline(book_path, book_id, book_metadata)

        # PHASE 1: Metadata + Comments only (fast indexing)
        if phase == 'phase1':
            return self._index_book_phase1(book_path, book_id, book_metadata)

        # PHASE 2: Full content indexing (default)
        # Step 1: Extract text
        start_time = time.time()
        extracted = self.extractor.extract(book_path)
        extract_time = time.time() - start_time

        # Detect scanned/mostly-scanned PDFs
        needs_ocr = False
        if extracted.metadata.detected_format == 'pdf':
            total_pages = extracted.metadata.total_pages or 0
            total_words = extracted.metadata.total_words or 0
            if not extracted.chunks:
                needs_ocr = True
                print(f"  ⚠️  No text extracted — likely fully scanned. Re-index with --enable-ocr.")
            elif total_pages >= 3 and total_words > 0 and (total_words / total_pages) < 150:
                # Also check page coverage: if most pages have chunks, it's front-matter, not scanned
                pages_with_text = len(set(
                    c['metadata'].get('page', 0)
                    for c in extracted.chunks
                    if isinstance(c.get('metadata'), dict)
                )) if extracted.chunks else 0
                page_coverage = pages_with_text / total_pages if total_pages > 0 else 1.0
                if page_coverage < 0.4:
                    needs_ocr = True
                    wpp = total_words // total_pages
                    print(f"  ⚠️  Only {total_words}w across {total_pages}p ({wpp}w/p), text on {pages_with_text}/{total_pages} pages — likely mostly scanned. Re-index with --enable-ocr.")

        if self.hierarchical and extracted.full_text:
            from src.extractors.base import BaseExtractor
            from src.extractors.models import ChunkMetadata

            chunker = type('HierarchicalChunker', (BaseExtractor,), {
                'extract': lambda self, fp: None,
                'supports': lambda self, fp: True
            })(chunk_size=512, overlap=100)

            base_meta = ChunkMetadata(
                book_id=book_metadata.get('calibre_id'),
                title=book_metadata.get('title'),
                author=book_metadata.get('author'),
                year=book_metadata.get('year'),
                source_file=str(book_path),
            )

            extracted.chunks = chunker._create_hierarchical_chunks(
                text=extracted.full_text,
                book_id=book_id,
                base_metadata=base_meta,
                parent_size=2048,
                parent_overlap=400,
                child_size=512,
                child_overlap=100,
                window_chars=500
            )
            parent_count = sum(1 for c in extracted.chunks if c.get('metadata', {}).get('chunk_type') == ChunkType.PARENT)
            child_count = sum(1 for c in extracted.chunks if c.get('metadata', {}).get('chunk_type') == ChunkType.CHILD)
            print(f"  Extract: {parent_count}p+{child_count}c chunks, {extracted.metadata.total_words:,}w, {extracted.metadata.total_pages or '?'}p ({extract_time:.1f}s)")
        else:
            print(f"  Extract: {len(extracted.chunks)} chunks, {extracted.metadata.total_words:,}w, {extracted.metadata.total_pages or '?'}p ({extract_time:.1f}s)")

        # Step 2: Generate embeddings
        start_time = time.time()

        texts = [chunk['text'] for chunk in extracted.chunks]
        embedding_batches = []

        # Batch process for speed (batch_size determined by profile)
        for i in tqdm(range(0, len(texts), self.batch_size), desc="    Embedding"):
            batch = texts[i:i+self.batch_size]
            batch_embeddings = self.embedding_model.encode(
                batch,
                show_progress_bar=False,
                convert_to_numpy=True
            )
            embedding_batches.append(batch_embeddings)

        embeddings_array = np.concatenate(embedding_batches) if embedding_batches else np.array([])

        embed_time = time.time() - start_time
        print(f"  Embed:   {len(embeddings_array)} vectors ({embed_time:.1f}s)")

        # Step 3: Index in LanceDB
        start_time = time.time()

        # Prepare chunks with metadata
        # Pre-compute values that are identical for every chunk in this book
        indexed_at = datetime.now().isoformat()
        meta_hash = self._compute_metadata_hash(book_metadata) if book_metadata else ''

        chunks = []
        for i, chunk in enumerate(extracted.chunks):
            # Use hierarchical chunk_id if available, otherwise generate
            chunk_id = chunk.get('chunk_id', f"{book_id}_chunk_{i}")
            chunk_type = chunk.get('metadata', {}).get('chunk_type', ChunkType.CONTENT)

            chunk_data = {
                'id': chunk_id,
                'text': chunk['text'],
                'book_id': book_id,
                'book_title': extracted.metadata.file_path.stem,
                'chunk_index': i,
                'chunk_type': chunk_type,
                'format': extracted.metadata.detected_format,
                'indexed_at': indexed_at,
            }

            # Copy optional fields from chunk metadata
            chunk_meta = chunk.get('metadata', {})
            for field in ('char_start', 'char_end'):
                if chunk_meta.get(field) is not None:
                    chunk_data[field] = chunk_meta[field]
            if chunk.get('window_text'):
                chunk_data['window_text'] = chunk['window_text']

            # Parent-Child hierarchy
            if chunk.get('parent_id') is not None:
                chunk_data['parent_id'] = chunk['parent_id']

            # Add book metadata
            self._apply_book_metadata_to_chunk(chunk_data, book_metadata)

            # Add metadata hash for change detection
            if meta_hash:
                chunk_data['metadata_hash'] = meta_hash

            # Add source file path
            chunk_data['source_file'] = str(extracted.metadata.file_path)

            # Copy page, section, and language info from chunk metadata
            for src_key, dst_key in [
                ('page', 'page_number'), ('page_label', 'page_label'),
                ('chapter', 'chapter'), ('section', 'section'),
                ('section_title', 'section_title'), ('section_type', 'section_type'),
                ('language', 'language'),
            ]:
                if chunk_meta.get(src_key):
                    chunk_data[dst_key] = chunk_meta[src_key]

            chunks.append(chunk_data)

        # Collect extra embedding arrays for comments/annotations
        extra_embedding_arrays = []

        # Add Calibre comments as structured chunk(s) (if available)
        has_comment = bool(book_metadata and (book_metadata.get('comments') or book_metadata.get('comments_html')))
        if has_comment:
            comment_chunks, comment_embeddings = self._build_comment_chunks(
                book_metadata=book_metadata,
                book_id=book_id,
                book_format=extracted.metadata.detected_format,
                metadata_hash=meta_hash,
            )
            chunks.extend(comment_chunks)
            if comment_embeddings:
                extra_embedding_arrays.append(np.array(comment_embeddings))

        # Add user annotations (highlights, notes from Calibre Viewer + PDF)
        annot_count = 0
        try:
            annot_result = get_combined_annotations(
                book_path=str(book_path),
                include_pdf=True,
                exclude_toc_markers=True,
                min_length=20
            )
            annotations = annot_result.get('annotations', [])
            if annotations:
                annot_hash = self._compute_annotation_hash(annotations)

                # Build annotation chunks and collect texts for batched embedding
                annot_texts = []
                annot_chunks_pending = []
                for idx, annot in enumerate(annotations):
                    annot_text = self._build_annotation_text(annot)
                    if not annot_text:
                        continue

                    annot_chunk = {
                        'id': f"{book_id}_annot_{idx}",
                        'text': annot_text,
                        'book_id': book_id,
                        'book_title': book_metadata.get('title', book_path.stem) if book_metadata else book_path.stem,
                        'chunk_index': -(idx + 10),  # Negative to distinguish from content
                        'chunk_type': ChunkType.ANNOTATION,
                        'annotation_type': annot.get('type', ''),
                        'annotation_source': annot.get('source', ''),
                        'annotation_hash': annot_hash,
                        'page_number': annot.get('page', 0) or 0,
                        'format': extracted.metadata.detected_format,
                        'indexed_at': indexed_at,
                        'metadata_hash': meta_hash,
                    }
                    self._apply_book_metadata_to_chunk(annot_chunk, book_metadata)
                    annot_texts.append(annot_text)
                    annot_chunks_pending.append(annot_chunk)

                # Batch-encode all annotation texts at once
                if annot_texts:
                    annot_emb = self.embedding_model.encode(
                        annot_texts, show_progress_bar=False, convert_to_numpy=True
                    )
                    chunks.extend(annot_chunks_pending)
                    extra_embedding_arrays.append(annot_emb)

                annot_count = len(annot_texts)

        except Exception as e:
            print(f"  ⚠ Annotation extraction failed (non-fatal): {e}")
            annot_count = 0

        # Concatenate all embedding arrays (content + comments + annotations)
        all_arrays = [embeddings_array] + extra_embedding_arrays if len(embeddings_array) else extra_embedding_arrays
        embeddings_array = np.concatenate(all_arrays) if all_arrays else np.array([])

        # Add to LanceDB
        num_indexed = self.store.add_chunks(chunks, embeddings_array)

        index_time = time.time() - start_time
        extras = []
        if has_comment:
            extras.append("comment")
        if annot_count:
            extras.append(f"{annot_count} annot")
        extras_str = f" + {', '.join(extras)}" if extras else ""
        total_time = extract_time + embed_time + index_time
        print(f"  Index:   {num_indexed} chunks{extras_str} ({index_time:.1f}s) | total {total_time:.1f}s")

        return {
            'book_id': book_id,
            'chunks_indexed': num_indexed,
            'total_words': extracted.metadata.total_words,
            'total_pages': extracted.metadata.total_pages,
            'extraction_time': extract_time,
            'embedding_time': embed_time,
            'indexing_time': index_time,
            'total_time': total_time,
            'needs_ocr': needs_ocr,
        }

    def prepare_book(self, book_path: str, book_id: str = None,
                     output_dir: str = "./prepared_chunks") -> Dict[str, Any]:
        """
        Extract and chunk a book WITHOUT embedding (Phase 1 of two-phase indexing).
        Writes one JSONL file per book to output_dir.

        Args:
            book_path: Path to book file
            book_id: Optional book ID (default: filename)
            output_dir: Directory for JSONL output files

        Returns:
            Dictionary with preparation statistics
        """
        book_path = Path(book_path)
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        if not book_path.exists():
            raise FileNotFoundError(f"Book not found: {book_path}")

        book_id = book_id or book_path.stem

        print(f"  File: {book_path.name}")

        # Extract metadata
        book_metadata = self._extract_metadata(book_path)
        calibre_id = book_metadata.get('calibre_id', 0) or 0

        # Check skip-if-exists
        out_file = output_dir / f"{calibre_id}.jsonl"
        if out_file.exists():
            # Quick check: count lines to compare chunk_count
            with open(out_file, 'r', encoding='utf-8') as f:
                header = json.loads(f.readline())
                if header.get('_header'):
                    print(f"  Already prepared ({header.get('chunk_count', '?')} chunks). Skipping.")
                    return {
                        'book_id': book_id,
                        'status': 'already_prepared',
                        'chunk_count': header.get('chunk_count', 0),
                    }

        # Step 1: Extract text
        start_time = time.time()
        extracted = self.extractor.extract(book_path)
        extract_time = time.time() - start_time

        # Handle hierarchical chunking if requested
        if self.hierarchical and extracted.full_text:
            from src.extractors.base import BaseExtractor
            from src.extractors.models import ChunkMetadata

            chunker = type('HierarchicalChunker', (BaseExtractor,), {
                'extract': lambda self, fp: None,
                'supports': lambda self, fp: True
            })(chunk_size=512, overlap=100)

            base_meta = ChunkMetadata(
                book_id=book_metadata.get('calibre_id'),
                title=book_metadata.get('title'),
                author=book_metadata.get('author'),
                year=book_metadata.get('year'),
                source_file=str(book_path),
            )

            extracted.chunks = chunker._create_hierarchical_chunks(
                text=extracted.full_text,
                book_id=book_id,
                base_metadata=base_meta,
                parent_size=2048,
                parent_overlap=400,
                child_size=512,
                child_overlap=100,
                window_chars=500
            )

        print(f"  Extract: {len(extracted.chunks)} chunks, {extracted.metadata.total_words:,}w, {extracted.metadata.total_pages or '?'}p ({extract_time:.1f}s)")

        # Detect scanned/mostly-scanned PDFs
        needs_ocr = False
        if extracted.metadata.detected_format == 'pdf':
            total_pages = extracted.metadata.total_pages or 0
            total_words = extracted.metadata.total_words or 0
            if not extracted.chunks:
                needs_ocr = True
                print(f"  \u26a0\ufe0f  No text extracted \u2014 likely fully scanned. Re-index with --enable-ocr.")
            elif total_pages >= 3 and total_words > 0 and (total_words / total_pages) < 150:
                pages_with_text = len(set(
                    c['metadata'].get('page', 0)
                    for c in extracted.chunks
                    if isinstance(c.get('metadata'), dict)
                )) if extracted.chunks else 0
                page_coverage = pages_with_text / total_pages if total_pages > 0 else 1.0
                if page_coverage < 0.4:
                    needs_ocr = True
                    wpp = total_words // total_pages
                    print(f"  \u26a0\ufe0f  Only {total_words}w across {total_pages}p ({wpp}w/p), text on {pages_with_text}/{total_pages} pages \u2014 likely mostly scanned. Re-index with --enable-ocr.")

        # Step 2: Build chunk dicts (same as index_book, without embeddings)
        # Pre-compute values that are identical for every chunk in this book
        indexed_at = datetime.now().isoformat()
        meta_hash = self._compute_metadata_hash(book_metadata) if book_metadata else ''

        chunks = []
        for i, chunk in enumerate(extracted.chunks):
            chunk_id = chunk.get('chunk_id', f"{book_id}_chunk_{i}")
            chunk_type = chunk.get('metadata', {}).get('chunk_type', ChunkType.CONTENT)

            chunk_data = {
                'id': chunk_id,
                'text': chunk['text'],
                'book_id': book_id,
                'book_title': extracted.metadata.file_path.stem,
                'chunk_index': i,
                'chunk_type': chunk_type,
                'format': extracted.metadata.detected_format,
                'indexed_at': indexed_at,
            }

            chunk_meta = chunk.get('metadata', {})
            for field in ('char_start', 'char_end'):
                if chunk_meta.get(field) is not None:
                    chunk_data[field] = chunk_meta[field]
            if chunk.get('window_text'):
                chunk_data['window_text'] = chunk['window_text']

            if chunk.get('parent_id') is not None:
                chunk_data['parent_id'] = chunk['parent_id']

            self._apply_book_metadata_to_chunk(chunk_data, book_metadata)

            if meta_hash:
                chunk_data['metadata_hash'] = meta_hash

            chunk_data['source_file'] = str(extracted.metadata.file_path)

            for src_key, dst_key in [
                ('page', 'page_number'), ('page_label', 'page_label'),
                ('chapter', 'chapter'), ('section', 'section'),
                ('section_title', 'section_title'), ('section_type', 'section_type'),
                ('language', 'language'),
            ]:
                if chunk_meta.get(src_key):
                    chunk_data[dst_key] = chunk_meta[src_key]

            chunks.append(chunk_data)

        # Step 2b: Add Calibre comments as structured chunk(s) (if available)
        has_comment = bool(book_metadata and (book_metadata.get('comments') or book_metadata.get('comments_html')))
        if has_comment:
            comment_chunks, _ = self._build_comment_chunks(
                book_metadata=book_metadata,
                book_id=book_id,
                book_format=extracted.metadata.detected_format,
                metadata_hash=meta_hash,
                embed=False,
            )
            chunks.extend(comment_chunks)

        # Step 3: Write JSONL
        header = {
            '_header': True,
            'calibre_id': calibre_id,
            'book_id': book_id,
            'book_metadata': {k: v for k, v in book_metadata.items()
                             if k not in ('custom_fields',)},
            'chunk_count': len(chunks),
            'prepared_at': datetime.now().isoformat(),
        }

        with open(out_file, 'w', encoding='utf-8') as f:
            f.write(json.dumps(header, ensure_ascii=False) + '\n')
            for chunk in chunks:
                f.write(json.dumps(chunk, ensure_ascii=False) + '\n')

        print(f"  Prepared: {len(chunks)} chunks -> {out_file.name} ({out_file.stat().st_size / 1024:.0f} KB)")

        return {
            'book_id': book_id,
            'status': 'prepared',
            'chunk_count': len(chunks),
            'extraction_time': extract_time,
            'output_file': str(out_file),
            'needs_ocr': needs_ocr,
        }

    def embed_prepared(self, input_dir: str, mode: str = 'local',
                       host: str = None, port: int = 8000, token: str = None,
                       batch_size: int = 100, use_gzip: bool = True,
                       profile: str = None, force: bool = False) -> Dict[str, Any]:
        """
        Embed pre-prepared chunks and store in LanceDB (Phase 2 of two-phase indexing).

        Args:
            input_dir: Directory with JSONL files from prepare_book()
            mode: 'local' (use local GPU/CPU) or 'remote' (use remote server)
            host: Remote server host (required if mode='remote')
            port: Remote server port
            token: Bearer token for remote server
            batch_size: Texts per HTTP request (remote) or encode batch (local)
            use_gzip: Use gzip compression for remote requests
            profile: Hardware profile for local mode
            force: Delete existing chunks and re-embed (for re-indexing with improved chunks)

        Returns:
            Summary statistics
        """
        input_dir = Path(input_dir)
        if not input_dir.exists():
            raise FileNotFoundError(f"Input directory not found: {input_dir}")

        # Set up embedder
        if mode == 'remote':
            if not host:
                raise ValueError("--host required for remote mode")
            from src.archilles.embedders.remote import RemoteBGEEmbedder
            embedder = RemoteBGEEmbedder(
                host=host, port=port, token=token,
                batch_size=batch_size, use_gzip=use_gzip,
            )
            embedder.load_model()  # checks health
            print(f"  Remote embedder: {host}:{port}")
        else:
            # Use local SentenceTransformer (already loaded in self.embedding_model)
            if self.embedding_model is None:
                raise RuntimeError("No embedding model loaded. Don't use --skip-model with local embed mode.")
            print(f"  Local embedder: {self.device}, batch_size={self.batch_size}")

        # Load progress tracker
        progress_file = input_dir / '.progress.json'
        if progress_file.exists():
            with open(progress_file, 'r') as f:
                progress = json.load(f)
        else:
            progress = {'embedded': []}
        embedded_set = set(progress['embedded'])

        # Find all JSONL files
        jsonl_files = sorted(input_dir.glob('*.jsonl'))
        if not jsonl_files:
            print("  No JSONL files found.")
            return {'total_books': 0, 'total_chunks': 0}

        total_books = 0
        total_chunks = 0
        skipped = 0

        for jsonl_file in jsonl_files:
            # Parse header
            with open(jsonl_file, 'r', encoding='utf-8') as f:
                first_line = f.readline()
                header = json.loads(first_line)
                if not header.get('_header'):
                    print(f"  Skipping {jsonl_file.name}: no header")
                    continue

                file_key = str(header.get('calibre_id', jsonl_file.stem))

                # Skip if already embedded
                if file_key in embedded_set:
                    skipped += 1
                    continue

                # Check LanceDB for existing chunks
                book_id = header['book_id']
                existing = self.store.get_by_book_id(book_id, limit=1)
                content = [c for c in existing if c.get('chunk_type', ChunkType.CONTENT) in ChunkType.HIERARCHICAL_TYPES]
                if content and not force:
                    print(f"  {book_id}: already in LanceDB ({len(content)}+ chunks). Skipping.")
                    embedded_set.add(file_key)
                    skipped += 1
                    continue
                elif content and force:
                    deleted = self.store.delete_by_book_id(book_id)
                    print(f"  {book_id}: {deleted} alte Chunks gelöscht.", end=' ', flush=True)

                # Read chunks
                chunk_lines = f.readlines()

            chunks = [json.loads(line) for line in chunk_lines]
            if not chunks:
                continue

            print(f"  {book_id}: {len(chunks)} chunks...", end=' ', flush=True)

            # Embed
            texts = [c['text'] for c in chunks]
            start = time.time()

            if mode == 'remote':
                result = embedder.embed_batch(texts)
                embeddings_array = result.embeddings
            else:
                # Local: batch through SentenceTransformer
                all_emb = []
                for i in range(0, len(texts), self.batch_size):
                    batch = texts[i:i + self.batch_size]
                    batch_emb = self.embedding_model.encode(
                        batch, show_progress_bar=False, convert_to_numpy=True
                    )
                    all_emb.append(batch_emb)
                embeddings_array = np.concatenate(all_emb, axis=0)

            embed_time = time.time() - start

            # Store in LanceDB
            num_added = self.store.add_chunks(chunks, embeddings_array)
            print(f"{num_added} indexed ({embed_time:.1f}s)")

            total_books += 1
            total_chunks += num_added

            # Update progress
            embedded_set.add(file_key)
            progress['embedded'] = list(embedded_set)
            with open(progress_file, 'w') as f:
                json.dump(progress, f)

        print(f"\n  Done: {total_books} books, {total_chunks} chunks embedded. {skipped} skipped.")
        return {
            'total_books': total_books,
            'total_chunks': total_chunks,
            'skipped': skipped,
        }

    def _build_comment_chunks(
        self,
        book_metadata: Dict[str, Any],
        book_id: str,
        book_format: str,
        metadata_hash: str,
        embed: bool = True,
    ) -> tuple:
        """
        Build calibre_comment chunk(s) with structure-aware text.

        If comments_html is available, parses H2–H4 headlines into separate
        chunks and prepends bold/<strong>/!!!...!!! passages as "Kernaussagen:"
        so they carry extra weight in the embedding.

        Returns:
            (chunks, embeddings) — parallel lists ready for store.add_chunks()
        """
        from src.calibre_db import CalibreDB

        comments_html = book_metadata.get('comments_html', '')
        if comments_html:
            sections = CalibreDB.parse_html_comment(comments_html)
        else:
            plain = book_metadata.get('comments', '')
            sections = [{'headline': None, 'headline_level': None,
                         'text': plain, 'key_passages': []}] if plain else []

        if not sections:
            return [], []

        # Split sections that are too long for a useful single embedding.
        # BGE-M3 retrieval quality degrades significantly beyond ~500 words.
        # Long headline-less sections (e.g. a 3500-word comment block) are
        # split at word boundaries into sub-chunks of MAX_COMMENT_WORDS each.
        MAX_COMMENT_WORDS = 400

        def split_section(section: dict) -> list:
            words = section['text'].split()
            if len(words) <= MAX_COMMENT_WORDS:
                return [section]
            # Split at sentence boundaries (. ! ?) — never mid-sentence
            sentences = re.split(r'(?<=[.!?])\s+', section['text'])
            sub_sections = []
            current_words = 0
            current_sents: list[str] = []
            first = True
            for sent in sentences:
                sent_words = len(sent.split())
                if current_sents and current_words + sent_words > MAX_COMMENT_WORDS:
                    sub_sections.append({
                        'headline': section['headline'],
                        'headline_level': section['headline_level'],
                        'text': ' '.join(current_sents),
                        'key_passages': section['key_passages'] if first else [],
                    })
                    first = False
                    current_sents = [sent]
                    current_words = sent_words
                else:
                    current_sents.append(sent)
                    current_words += sent_words
            if current_sents:
                sub_sections.append({
                    'headline': section['headline'],
                    'headline_level': section['headline_level'],
                    'text': ' '.join(current_sents),
                    'key_passages': section['key_passages'] if first else [],
                })
            return sub_sections

        flat_sections = []
        for section in sections:
            flat_sections.extend(split_section(section))

        chunks, embeddings = [], []
        title = book_metadata.get('title', book_id)

        for i, section in enumerate(flat_sections):
            parts = []
            if section['headline']:
                parts.append(f"## {section['headline']} ##")
            if section['key_passages']:
                kp = ' | '.join(section['key_passages'])
                parts.append(f"Kernaussagen: {kp}")
            if section['text']:
                parts.append(section['text'])

            chunk_text = f"[CALIBRE_COMMENT] {' '.join(parts)}"

            if embed:
                embedding = self.embedding_model.encode(
                    chunk_text, show_progress_bar=False, convert_to_numpy=True
                )
            else:
                embedding = []

            chunk = {
                'id': f"{book_id}_comment_{i}",
                'text': chunk_text,
                'book_id': book_id,
                'book_title': title,
                'chunk_index': -(i + 1),
                'chunk_type': ChunkType.CALIBRE_COMMENT,
                'format': book_format,
                'indexed_at': datetime.now().isoformat(),
                'metadata_hash': metadata_hash,
            }
            if section['headline']:
                chunk['section_title'] = section['headline']
            self._apply_book_metadata_to_chunk(chunk, book_metadata)

            chunks.append(chunk)
            embeddings.append(embedding.tolist() if hasattr(embedding, 'tolist') else embedding)

        return chunks, embeddings

    def _update_metadata_only(self, book_id: str, book_metadata: Dict[str, Any],
                               new_hash: str, existing_chunks: list,
                               annotations: Optional[List[Dict[str, Any]]] = None,
                               annotation_hash: Optional[str] = None,
                               book_path: Optional[Path] = None) -> Dict[str, Any]:
        """
        Smart metadata/annotation update: refresh only changed parts
        WITHOUT re-extracting or re-embedding the book text.

        This is ~50-100x faster than a full re-index (~1-2s vs ~90s).
        """
        start_time = time.time()
        meta_changed = new_hash != (existing_chunks[0].get('metadata_hash', '') if existing_chunks else '')
        annot_changed = annotations is not None

        if meta_changed and annot_changed:
            print(f"  📝 Metadata + annotations changed — updating without full re-index...")
        elif meta_changed:
            print(f"  📝 Metadata changed — updating without full re-index...")
        elif annot_changed:
            print(f"  📝 Annotations changed — updating without full re-index...")

        # 1. Update metadata fields in all content chunks (no embedding change)
        updated_fields = {}
        if book_metadata.get('author'):
            updated_fields['author'] = book_metadata['author']
        if book_metadata.get('title'):
            updated_fields['book_title'] = book_metadata['title']
        if book_metadata.get('tags'):
            updated_fields['tags'] = self._format_tags(book_metadata['tags'])
        if book_metadata.get('publisher'):
            updated_fields['publisher'] = book_metadata['publisher']
        updated_fields['metadata_hash'] = new_hash

        if updated_fields:
            num_updated = self.store.update_metadata_fields(book_id, updated_fields)
            print(f"    Updated metadata in {num_updated} chunks")

        # 2. Replace calibre_comment chunk if metadata changed
        comment_added = False
        if meta_changed:
            old_comment_chunks = [c for c in existing_chunks if c.get('chunk_type') == ChunkType.CALIBRE_COMMENT]
            if old_comment_chunks:
                deleted = self.store.delete_by_book_id_and_type(book_id, ChunkType.CALIBRE_COMMENT)
                print(f"    Deleted {deleted} old comment chunk(s)")

            if book_metadata.get('comments') or book_metadata.get('comments_html'):
                book_format = existing_chunks[0].get('format', '') if existing_chunks else ''
                comment_chunks, comment_embeddings = self._build_comment_chunks(
                    book_metadata=book_metadata,
                    book_id=book_id,
                    book_format=book_format,
                    metadata_hash=new_hash,
                )
                if comment_chunks:
                    embeddings_array = np.array(comment_embeddings)
                    self.store.add_chunks(comment_chunks, embeddings_array)
                    comment_added = True
                    print(f"    Added {len(comment_chunks)} comment chunk(s)")

        # 3. Replace annotation chunks if annotations changed
        annot_updated = False
        if annot_changed and annotations is not None:
            # Delete old annotation chunks
            old_annot_count = len([c for c in existing_chunks if c.get('chunk_type') == ChunkType.ANNOTATION])
            if old_annot_count:
                deleted = self.store.delete_by_book_id_and_type(book_id, ChunkType.ANNOTATION)
                print(f"    Deleted {deleted} old annotation chunk(s)")

            # Add new annotation chunks
            if annotations:
                annot_chunks = []
                annot_embeddings = []
                for idx, annot in enumerate(annotations):
                    annot_text = self._build_annotation_text(annot)
                    if not annot_text:
                        continue

                    annot_embedding = self.embedding_model.encode(
                        annot_text, show_progress_bar=False, convert_to_numpy=True
                    )

                    annot_chunk = {
                        'id': f"{book_id}_annot_{idx}",
                        'text': annot_text,
                        'book_id': book_id,
                        'book_title': book_metadata.get('title', book_id),
                        'chunk_index': -(idx + 10),
                        'chunk_type': ChunkType.ANNOTATION,
                        'annotation_type': annot.get('type', ''),
                        'annotation_source': annot.get('source', ''),
                        'annotation_hash': annotation_hash or '',
                        'page_number': annot.get('page', 0) or 0,
                        'format': existing_chunks[0].get('format', ''),
                        'indexed_at': datetime.now().isoformat(),
                        'metadata_hash': new_hash,
                    }
                    self._apply_book_metadata_to_chunk(annot_chunk, book_metadata)

                    annot_chunks.append(annot_chunk)
                    annot_embeddings.append(annot_embedding.tolist())

                if annot_chunks:
                    embeddings_array = np.array(annot_embeddings)
                    self.store.add_chunks(annot_chunks, embeddings_array)
                    print(f"    Added {len(annot_chunks)} new annotation chunks")
                    annot_updated = True
            else:
                print(f"    No annotations found (removed all)")

        elapsed = time.time() - start_time
        content_count = len([c for c in existing_chunks
                           if c.get('chunk_type', ChunkType.CONTENT) in ChunkType.HIERARCHICAL_TYPES])
        print(f"  ✅ Updated in {elapsed:.1f}s (content chunks untouched: {content_count})\n")

        return {
            'book_id': book_id,
            'status': 'metadata_updated',
            'chunks_indexed': content_count,
            'metadata_updated': meta_changed,
            'comment_updated': comment_added,
            'annotations_updated': annot_updated,
            'total_time': elapsed,
        }

    def _remove_stop_words(self, query_text: str) -> tuple:
        """
        Remove common stop words from query for better search results.

        Returns:
            Tuple of (cleaned_query, removed_words)
        """
        original_words = query_text.split()
        result_words = []
        removed = []

        for word in original_words:
            clean_word = word.lower().strip('.,;:!?"\'()[]{}')
            if clean_word in self.STOP_WORDS:
                removed.append(word)
            else:
                result_words.append(word)

        return ' '.join(result_words), removed

    def query(
        self,
        query_text: str,
        top_k: int = 10,
        mode: Literal['semantic', 'keyword', 'hybrid'] = 'hybrid',
        language: str = None,
        book_id: str = None,
        exact_phrase: bool = False,
        tag_filter: List[str] = None,
        section_filter: str = SectionType.MAIN,
        chunk_type_filter: str = ChunkType.CONTENT,
        max_per_book: int = 2,
        min_similarity: float = 0.0
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
            section_filter: Filter by section type (default: 'main' = exclude front/back matter)
                           'main' = main content only (excludes bibliography, index, etc.)
                           'main_content' / 'front_matter' / 'back_matter' = exact match
                           None = all sections (no filtering)
            chunk_type_filter: Filter by chunk type (default: 'content' - book text only)
                              'content' = book text only (DEFAULT - excludes Calibre comments)
                              'calibre_comment' = Calibre comments only
                              None = all chunk types (book text + comments mixed)
            max_per_book: Maximum results per book (default: 2, use 999 for unlimited)
            min_similarity: Minimum similarity score for semantic results (0.0-1.0, default: 0.0)
                           Higher = stricter, fewer but more relevant results

        Returns:
            List of relevant chunks with metadata and scores
        """
        # Remove stop words for better search quality (unless exact phrase matching)
        original_query = query_text
        if not exact_phrase:
            query_text, removed_words = self._remove_stop_words(query_text)
            if removed_words:
                print(f"  ℹ️  Removed common words: {', '.join(removed_words)}")
            if not query_text.strip():
                # All words were stop words!
                print("  ⚠️  Query contains only common words. Using original query.")
                query_text = original_query

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
        print(f"  Searching {self._chunk_count} chunks...\n")

        # Oversample to allow for diversity filtering
        # If max_per_book is set, we need to fetch more results than top_k
        # to ensure we have enough diverse results after filtering
        # Higher factor (5) enables finding more diverse books in large libraries
        oversample_factor = 5 if max_per_book < 999 else 1
        search_top_k = top_k * oversample_factor

        # Route to appropriate search method
        if mode == 'semantic':
            results = self._semantic_search(query_text, search_top_k, language, book_id, chunk_type_filter, section_type=section_filter)
        elif mode == 'keyword':
            results = self._keyword_search(query_text, search_top_k, language, book_id, chunk_type_filter, exact_phrase=exact_phrase, section_type=section_filter)
        elif mode == 'hybrid':
            results = self._hybrid_search(query_text, search_top_k, language, book_id, chunk_type_filter, exact_phrase=exact_phrase, section_type=section_filter)
        else:
            raise ValueError(f"Invalid mode: {mode}. Must be 'semantic', 'keyword', or 'hybrid'")

        # Filter out trivially short chunks (titles, headings, bibliography entries)
        # A meaningful academic passage should be at least ~100 characters
        min_chunk_length = 100
        short_count = sum(1 for r in results if len(r.get('text', '')) < min_chunk_length)
        results = [r for r in results if len(r.get('text', '')) >= min_chunk_length]
        if short_count > 0:
            print(f"  Filtered {short_count} trivially short chunks (<{min_chunk_length} chars)")

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

        # Diversify results by book (max N results per book)
        if max_per_book < 999 and len(results) > 0:
            results = diversify_results(results, max_per_book, top_k)
        else:
            results = results[:top_k]

        # Apply minimum similarity threshold (for semantic/hybrid modes)
        if min_similarity > 0.0 and mode in ['semantic', 'hybrid']:
            original_count = len(results)
            results = [r for r in results if r.get('score', 0) >= min_similarity]
            filtered_count = original_count - len(results)
            if filtered_count > 0:
                print(f"  🎯 Filtered {filtered_count} results below {min_similarity:.0%} similarity")

        return results

    def _semantic_search(
        self,
        query_text: str,
        top_k: int,
        language: str = None,
        book_id: str = None,
        chunk_type_filter: str = None,
        section_type: str = None
    ) -> List[Dict[str, Any]]:
        """Semantic search using BGE-M3 embeddings via LanceDB."""
        query_embedding = self.embedding_model.encode(
            query_text,
            convert_to_numpy=True
        )

        resolved_book_id, calibre_id, source_id = self._resolve_book_id(book_id)

        results = self.store.vector_search(
            query_vector=query_embedding,
            top_k=top_k,
            book_id=resolved_book_id,
            calibre_id=calibre_id,
            source_id=source_id,
            chunk_type=chunk_type_filter,
            language=language,
            section_type=section_type
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
        exact_phrase: bool = False,
        section_type: str = None
    ) -> List[Dict[str, Any]]:
        """Keyword search using LanceDB full-text search."""
        if exact_phrase:
            return self._exact_phrase_search(query_text, top_k, language, book_id, chunk_type_filter)

        resolved_book_id, calibre_id, source_id = self._resolve_book_id(book_id)

        results = self.store.fts_search(
            query_text=query_text,
            top_k=top_k,
            book_id=resolved_book_id,
            calibre_id=calibre_id,
            source_id=source_id,
            chunk_type=chunk_type_filter,
            language=language,
            section_type=section_type
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
        resolved_book_id, calibre_id, source_id = self._resolve_book_id(book_id)

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

            if source_id and str(chunk.get('source_id', '')) != source_id and chunk.get('calibre_id') != calibre_id:
                continue
            elif calibre_id and not source_id and chunk.get('calibre_id') != calibre_id:
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
        exact_phrase: bool = False,
        section_type: str = None
    ) -> List[Dict[str, Any]]:
        """
        Hybrid search using LanceDB native hybrid search (vector + FTS).

        IMPORTANT: If exact_phrase=True, ONLY returns exact phrase matches!
        """
        # For exact phrase matching, skip hybrid search entirely
        if exact_phrase:
            return self._keyword_search(query_text, top_k, language, book_id, chunk_type_filter, exact_phrase=True, section_type=section_type)

        query_embedding = self.embedding_model.encode(
            query_text,
            convert_to_numpy=True
        )

        resolved_book_id, calibre_id, source_id = self._resolve_book_id(book_id)

        results = self.store.hybrid_search(
            query_text=query_text,
            query_vector=query_embedding,
            top_k=top_k,
            book_id=resolved_book_id,
            calibre_id=calibre_id,
            source_id=source_id,
            chunk_type=chunk_type_filter,
            language=language,
            section_type=section_type
        )

        # Format and apply boost factors
        formatted_results = self._format_lancedb_results(results, score_type='hybrid')

        # Apply boost factors for Calibre comments and tag matches
        query_terms = set(query_text.lower().split())

        for result in formatted_results:
            metadata = result['metadata']

            # Boost for Calibre comments
            if metadata.get('chunk_type') == ChunkType.CALIBRE_COMMENT:
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

            section_citation = self._format_section_citation(metadata)
            if section_citation:
                citation_parts.append(section_citation)

            # Debug mode: show raw metadata values
            if os.environ.get('DEBUG_METADATA'):
                print(f"    [DEBUG] section: {repr(metadata.get('section'))}, section_title: {repr(metadata.get('section_title'))}")
                print(f"    [DEBUG] page_label: {repr(metadata.get('page_label'))}, printed_page: {repr(metadata.get('printed_page'))}")

            page_val, is_pdf, page_warning = self._resolve_page_info(metadata)
            if page_val:
                citation_parts.append(f"PDF S. {page_val}" if is_pdf else f"S. {page_val}")

            citation = ', '.join(citation_parts) if citation_parts else metadata.get('book_id', 'Unknown')

            # Add chunk type indicator
            chunk_type = metadata.get('chunk_type', '')
            type_indicator = ''
            if chunk_type == ChunkType.CALIBRE_COMMENT:
                type_indicator = ' [CALIBRE_COMMENT]'
            elif chunk_type == ChunkType.PHASE1_METADATA:
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

            citation_parts = []

            section_citation = self._format_section_citation(metadata)
            if section_citation:
                citation_parts.append(section_citation)

            # Add page info
            page_val, is_pdf, _ = self._resolve_page_info(metadata)
            if page_val:
                citation_parts.append(f"PDF S. {page_val}" if is_pdf else f"S. {page_val}")

            # Result header with author and year
            author = metadata.get('author', '')
            year = metadata.get('year', '')

            # Add chunk type indicator
            chunk_type = metadata.get('chunk_type', '')
            type_indicator = ''
            if chunk_type == ChunkType.CALIBRE_COMMENT:
                type_indicator = ' 📝'  # Emoji for markdown
            elif chunk_type == ChunkType.PHASE1_METADATA:
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
    def get_system_prompt(citation_config=None) -> str:
        """
        Get the system prompt for Claude with citation instructions.

        Args:
            citation_config: Optional CitationConfig instance. When provided,
                rule 5 includes the user's preferred bibliography style.

        Returns XML-formatted instructions that tell Claude to cite sources.
        """
        # Build bibliography instruction (rule 5)
        if citation_config is not None:
            from src.citation.config import format_bibliography_instruction
            bib_instruction = (
                "Fasse am Ende alle zitierten Quellen als Literaturliste zusammen. "
                + format_bibliography_instruction(citation_config)
            )
        else:
            bib_instruction = "Fasse am Ende alle zitierten Quellen als Literaturliste zusammen."

        return f"""<system_instructions>
Du bist ein akademischer Forschungsassistent. Deine Aufgabe ist es, die Frage des Nutzers NUR auf Basis der bereitgestellten Dokumentenauszüge zu beantworten.

<rules>
1. Zitiere jede Tatsachenbehauptung sofort mit der ID des Dokuments in eckigen Klammern, z.B. [doc_1].
2. Nutze keine externen Informationen. Wenn die Antwort nicht in den Dokumenten steht, sage das klar.
3. Antworte in der Sprache des Nutzers, behalte aber den wissenschaftlichen Fachjargon bei.
4. Bei mehreren Quellen für dieselbe Aussage: gib alle relevanten IDs an, z.B. [doc_1, doc_3].
5. {bib_instruction}
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

            # Build metadata line (matches inline metadata format)
            meta_parts = []

            if metadata.get('author'):
                meta_parts.append(f"Autor: {metadata['author']}")
            if metadata.get('book_title'):
                meta_parts.append(f"Titel: {metadata['book_title']}")
            if metadata.get('year'):
                meta_parts.append(f"Jahr: {metadata['year']}")

            section_meta = self._format_section_meta(metadata)
            if section_meta:
                meta_parts.append(section_meta)

            page_val, _, _ = self._resolve_page_info(metadata)
            if page_val:
                meta_parts.append(f"Seite: {page_val}")

            meta_str = " | ".join(meta_parts) if meta_parts else "Metadaten nicht verfügbar"

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
        Expand chunk context using stored window_text or parent chunk (Small-to-Big Retrieval).

        Priority:
        1. Use window_text if stored in the index (pre-computed context window)
        2. Use parent chunk text if parent_id is available (hierarchical retrieval)
        3. Fall back to original chunk text

        Args:
            chunk_text: Original chunk text from search result
            metadata: Chunk metadata (may contain window_text, parent_id)
            expansion_chars: Characters to add before and after (not used for window_text)

        Returns:
            Expanded text with context, or original chunk if expansion not possible
        """
        # Option 1: Use pre-computed window_text from the index
        window_text = metadata.get('window_text', '')
        if window_text and len(window_text) > len(chunk_text):
            return window_text

        # Option 2: Load parent chunk for context (hierarchical retrieval)
        parent_id = metadata.get('parent_id', '')
        if parent_id and hasattr(self, 'store'):
            parent = self.store.get_by_id(parent_id)
            if parent and parent.get('text'):
                return parent['text']

        # Graceful degradation: return original chunk
        return chunk_text

    def _build_inline_metadata(self, metadata: Dict[str, Any], doc_id: str) -> str:
        """
        Build inline metadata string to inject before chunk text.

        Format: <<<QUELLE ID=doc_1>>>
                [Autor: Arendt | Titel: Vita activa | Jahr: 1958 | Kapitel: Das Handeln | Seite: 213]

        This provides context for interpretation -- a sentence from Arendt
        means something different than the same sentence from Heidegger.
        """
        meta_parts = []

        if metadata.get('author'):
            meta_parts.append(f"Autor: {metadata['author']}")
        if metadata.get('book_title'):
            meta_parts.append(f"Titel: {metadata['book_title']}")
        if metadata.get('year'):
            meta_parts.append(f"Jahr: {metadata['year']}")

        section_meta = self._format_section_meta(metadata)
        if section_meta:
            meta_parts.append(section_meta)

        page_val, _, _ = self._resolve_page_info(metadata)
        if page_val:
            meta_parts.append(f"Seite: {page_val}")

        if metadata.get('language'):
            meta_parts.append(f"Sprache: {metadata['language']}")

        meta_str = " | ".join(meta_parts) if meta_parts else "keine Metadaten"

        return f"<<<QUELLE ID={doc_id}>>>\n[{meta_str}]"

    @staticmethod
    def _escape_xml(text: str) -> str:
        """Escape XML special characters."""
        return _html_escape(text, quote=True)

    def create_claude_prompt(
        self,
        results: List[Dict[str, Any]],
        query_text: str,
        expand_context: bool = False,
        expansion_chars: int = 400,
        citation_config=None,
    ) -> Dict[str, str]:
        """
        Create a complete prompt package for Claude with system instructions and XML documents.

        This combines:
        - System prompt with citation rules (style-aware when citation_config is provided)
        - XML-formatted documents with metadata
        - User query

        Args:
            results: Search results from query()
            query_text: Original user query
            expand_context: Enable context expansion (Small-to-Big) if available
            expansion_chars: Characters to add before/after chunk (default: 400)
            citation_config: Optional CitationConfig for bibliography style

        Returns:
            Dictionary with 'system' and 'user' prompts
        """
        system_prompt = self.get_system_prompt(citation_config=citation_config)
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


def _handle_import_annotations(args):
    """Handle the import-annotations subcommand (no RAG model needed)."""
    from src.calibre_mcp.annotation_providers import create_default_registry
    from src.calibre_mcp.book_matcher import BookMatcher

    source = args.source
    file_path = args.path

    # Resolve library path for Calibre DB matching
    library_path = get_library_path(required=False)
    library_path = str(library_path) if library_path else None

    # 1. Parse annotations
    print(f"\n{'='*60}")
    print(f"ANNOTATION IMPORT — Source: {source}")
    print(f"{'='*60}\n")

    registry = create_default_registry()

    if source == 'auto':
        provider = registry.detect(file_path)
        if not provider:
            print(f"ERROR: Could not auto-detect provider for: {file_path}")
            print(f"Available sources: {registry.available}")
            sys.exit(1)
        print(f"  Auto-detected provider: {provider.name}")
    else:
        provider = registry.get(source)
        if not provider:
            print(f"ERROR: Unknown source '{source}'. Available: {registry.available}")
            sys.exit(1)

    annotations = provider.extract(file_path)
    print(f"  Parsed: {len(annotations)} annotations from {file_path}")

    if not annotations:
        print("\n  No annotations found. Nothing to import.")
        return

    # Group by book for display
    by_book = {}
    for a in annotations:
        key = a.book_title or "(unknown)"
        by_book.setdefault(key, []).append(a)

    print(f"  Books:  {len(by_book)}")
    for title, annots in sorted(by_book.items()):
        types = {}
        for a in annots:
            types[a.type] = types.get(a.type, 0) + 1
        type_str = ", ".join(f"{v} {k}s" for k, v in types.items())
        print(f"    - {title}: {type_str}")

    # 2. Match to Calibre library
    if library_path:
        print(f"\n  Matching against Calibre library: {library_path}")
        try:
            from src.calibre_db import CalibreDB
            with CalibreDB(Path(library_path)) as db:
                books = db.get_all_books_brief()
            print(f"  Calibre books loaded: {len(books)}")
        except Exception as e:
            print(f"  WARNING: Could not load Calibre DB: {e}")
            books = []

        if books:
            matcher = BookMatcher(books, fuzzy_threshold=args.fuzzy_threshold)
            items = [
                {"title": a.book_title or "", "author": a.book_author, "annotation": a}
                for a in annotations
            ]
            matched, unmatched = matcher.match_batch(items)

            print(f"\n  Match results:")
            print(f"    Matched:   {len(matched)} annotations")
            print(f"    Unmatched: {len(unmatched)} annotations")

            if matched:
                # Group matched by calibre book
                by_calibre = {}
                for m in matched:
                    cid = m["calibre_id"]
                    by_calibre.setdefault(cid, {"title": m["calibre_title"], "items": []})
                    by_calibre[cid]["items"].append(m)
                print(f"\n  Matched books:")
                for cid, info in sorted(by_calibre.items()):
                    score = info["items"][0].get("match_score", 0)
                    mtype = info["items"][0].get("match_type", "?")
                    print(f"    [{cid}] {info['title']} — {len(info['items'])} annotations ({mtype}, score: {score:.0f})")

            if unmatched:
                print(f"\n  Unmatched (not in Calibre library):")
                unmatched_titles = set()
                for u in unmatched:
                    t = u.get("title", "(unknown)")
                    if t not in unmatched_titles:
                        unmatched_titles.add(t)
                        print(f"    - {t}")

                if not args.dry_run and library_path:
                    review_path = Path(library_path) / ".archilles" / "unmatched_annotations.json"
                    review_path.parent.mkdir(parents=True, exist_ok=True)
                    review_data = [{"title": u.get("title"), "author": u.get("author")} for u in unmatched]
                    with open(review_path, "w", encoding="utf-8") as f:
                        json.dump(review_data, f, indent=2, ensure_ascii=False)
                    print(f"\n  Review queue written to: {review_path}")
    else:
        print(f"\n  WARNING: No ARCHILLES_LIBRARY_PATH set — skipping Calibre matching.")
        print(f"  Set the environment variable to enable book matching.")
        matched = []

    # 3. Summary
    if args.dry_run:
        print(f"\n  DRY RUN — no changes written to index.")
        print(f"  Remove --dry-run to import into the ARCHILLES index.\n")
    else:
        print(f"\n  NOTE: Embedding into LanceDB index not yet implemented.")
        print(f"  Annotations were parsed and matched but not stored.\n")


def main():
    """Main CLI interface."""
    parser = argparse.ArgumentParser(
        description="archilles Mini-RAG: Semantic search in academic books",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Index a book
  python scripts/rag_demo.py index "C:/Calibre Library/Author Name/Book Title (1)/book.pdf"

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
  python scripts/rag_demo.py query "political theory" --book-id "Arendt_VitaActiva"

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
    index_parser.add_argument('--hierarchical', action='store_true',
                              help='Enable parent-child chunking (parents ~2048, children ~512 tokens)')

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
                              default='main',
                              help='Filter by section type (default: main = exclude bibliography/index/TOC)')
    query_parser.add_argument('--all-sections', action='store_true',
                              help='Search all sections including bibliography and index (overrides --section)')
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

    # Prepare command (extract + chunk, no embedding)
    prepare_parser = subparsers.add_parser('prepare', help='Extract and chunk a book without embedding (Phase 1)')
    prepare_parser.add_argument('book_path', help='Path to book file')
    prepare_parser.add_argument('--book-id', help='Optional book ID (default: filename)')
    prepare_parser.add_argument('--output-dir', default='./prepared_chunks', help='Output directory for JSONL files')
    prepare_parser.add_argument('--db-path', default=None, help='Database path (for metadata extraction)')
    prepare_parser.add_argument('--enable-ocr', action='store_true', help='Enable OCR for scanned PDFs')
    prepare_parser.add_argument('--force-ocr', action='store_true', help='Force OCR even for digital PDFs')
    prepare_parser.add_argument('--ocr-backend', choices=['auto', 'tesseract', 'lighton', 'olmocr'], default='auto')
    prepare_parser.add_argument('--ocr-language', default='deu+eng', help='Tesseract language codes')
    prepare_parser.add_argument('--hierarchical', action='store_true', help='Enable parent-child chunking')

    # Embed command (embed prepared chunks, store in LanceDB)
    embed_parser = subparsers.add_parser('embed', help='Embed prepared chunks and store in LanceDB (Phase 2)')
    embed_parser.add_argument('--input-dir', default='./prepared_chunks', help='Directory with JSONL files from prepare')
    embed_parser.add_argument('--mode', choices=['local', 'remote'], default='local', help='Embedding mode')
    embed_parser.add_argument('--host', help='Remote embedding server host (e.g. http://1.2.3.4:8000)')
    embed_parser.add_argument('--port', type=int, default=8000, help='Remote server port')
    embed_parser.add_argument('--token', help='Bearer token for remote server')
    embed_parser.add_argument('--batch-size', type=int, default=100, help='Texts per batch')
    embed_parser.add_argument('--use-gzip', action='store_true', default=True, help='Use gzip for remote requests')
    embed_parser.add_argument('--no-gzip', action='store_true', help='Disable gzip for remote requests')
    embed_parser.add_argument('--force', action='store_true', help='Re-embed: delete existing chunks and replace with prepared chunks')
    embed_parser.add_argument('--db-path', default=None, help='Database path')
    embed_parser.add_argument('--profile', choices=['minimal', 'balanced', 'maximal'], help='Hardware profile for local mode')

    # Import-annotations command
    import_parser = subparsers.add_parser('import-annotations',
        help='Import annotations from external reading apps (Kindle, Kobo, etc.)')
    import_parser.add_argument('--source', required=True,
        choices=['kindle', 'kobo', 'pdf', 'calibre_viewer', 'auto'],
        help='Annotation source')
    import_parser.add_argument('--path', required=True,
        help='Path to annotation file or database')
    import_parser.add_argument('--dry-run', action='store_true',
        help='Show what would be imported without writing to index')
    import_parser.add_argument('--fuzzy-threshold', type=float, default=80.0,
        help='Minimum fuzzy match score for book matching (0-100, default: 80)')
    import_parser.add_argument('--db-path', default=None,
        help='Database path (default: CALIBRE_LIBRARY/.archilles/rag_db)')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    # Handle import-annotations separately (no RAG model needed)
    if args.command == 'import-annotations':
        _handle_import_annotations(args)
        return

    # Determine default database path if not specified
    if args.db_path is None:
        args.db_path = get_rag_db_path()
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
        hierarchical = getattr(args, 'hierarchical', False)

        # Skip embedding model for prepare command (no GPU needed)
        skip_model = (args.command == 'prepare')

        rag = archillesRAG(
            db_path=args.db_path,
            reset_db=reset_db,
            enable_ocr=enable_ocr,
            force_ocr=force_ocr,
            ocr_backend=ocr_backend,
            ocr_language=ocr_language,
            use_modular_pipeline=use_modular_pipeline,
            profile=profile,
            hierarchical=hierarchical,
            skip_model=skip_model,
        )

        if args.command == 'index':
            # Index a book
            stats = rag.index_book(args.book_path, args.book_id, force=args.force)

        elif args.command == 'query':
            # Search
            # Handle chunk_type: 'all' means no filter (None), otherwise use the specified type
            chunk_type = args.chunk_type if hasattr(args, 'chunk_type') else ChunkType.CONTENT
            chunk_type_filter = None if chunk_type == 'all' else chunk_type

            results = rag.query(
                args.query,
                top_k=args.top_k,
                mode=args.mode,
                language=args.language,
                book_id=args.book_id,
                exact_phrase=args.exact,
                tag_filter=args.tag_filter if hasattr(args, 'tag_filter') else None,
                section_filter=None if getattr(args, 'all_sections', False) else getattr(args, 'section', 'main'),
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
            stats = rag.store.get_stats()
            print(f"INDEX STATISTICS\n")
            print(f"  Total chunks:  {stats['total_chunks']}")
            print(f"  Total books:   {stats['total_books']}")
            print(f"  Avg chunks/book: {stats['avg_chunks_per_book']:.1f}")
            print(f"  Database path: {args.db_path}\n")
            if stats.get('chunk_types'):
                print(f"  Chunk types:")
                for ct, n in sorted(stats['chunk_types'].items(), key=lambda x: -x[1]):
                    print(f"    {ct:<25} {n:>8}")
                print()
            if stats.get('languages'):
                print(f"  Languages:")
                for lang, n in sorted(stats['languages'].items(), key=lambda x: -x[1])[:10]:
                    print(f"    {lang:<25} {n:>8}")
                print()
            if stats.get('file_types'):
                print(f"  File types:")
                for ft, n in sorted(stats['file_types'].items(), key=lambda x: -x[1]):
                    print(f"    {ft:<25} {n:>8}")
                print()

        elif args.command == 'prepare':
            # Prepare book (extract + chunk, no embedding)
            stats = rag.prepare_book(
                args.book_path,
                book_id=args.book_id,
                output_dir=args.output_dir,
            )

        elif args.command == 'embed':
            # Embed prepared chunks
            use_gzip = not getattr(args, 'no_gzip', False)
            stats = rag.embed_prepared(
                input_dir=args.input_dir,
                mode=args.mode,
                host=args.host,
                port=args.port,
                token=args.token,
                batch_size=args.batch_size,
                use_gzip=use_gzip,
                profile=profile,
                force=getattr(args, 'force', False),
            )

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
