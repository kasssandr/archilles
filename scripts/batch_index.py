#!/usr/bin/env python3
"""
ARCHILLES Batch Indexer

Index multiple books from Calibre library by tag, author, or other criteria.

Hardware-Adaptive Profiles:
    - minimal:  CPU-only, resource-efficient (for laptops, <6GB VRAM)
    - balanced: GPU-accelerated, good quality (6-12GB VRAM)
    - maximal:  Full GPU, maximum quality (>12GB VRAM)

Usage:
    # Index ALL books in the library (no filter required)
    python scripts/batch_index.py --all

    # Index with a specific profile (auto-detects hardware if not specified)
    python scripts/batch_index.py --all --profile minimal
    python scripts/batch_index.py --all --profile balanced

    # Index all books with tag "Leit-Literatur"
    python scripts/batch_index.py --tag "Leit-Literatur"

    # Index specific author's books
    python scripts/batch_index.py --author "Hannah Arendt"

    # Dry run (show what would be indexed)
    python scripts/batch_index.py --tag "Leit-Literatur" --dry-run

    # Limit number of books (for testing)
    python scripts/batch_index.py --tag "Leit-Literatur" --limit 5

    # Continue from where you left off (skip already indexed)
    python scripts/batch_index.py --tag "Leit-Literatur" --skip-existing

    # Recover from corrupted database (e.g., after CTRL+C during indexing)
    python scripts/batch_index.py --tag "Leit-Literatur" --reset-db

    # Re-index books that were indexed before a certain date (with improved code)
    python scripts/batch_index.py --tag "Leit-Literatur" --reindex-before 2024-12-01

    # Re-index books with missing page labels (indexed before page label feature)
    python scripts/batch_index.py --tag "Leit-Literatur" --reindex-missing-labels

    # Run in non-interactive mode (auto-resume sessions, no prompts)
    python scripts/batch_index.py --tag "Leit-Literatur" --non-interactive

    # Filter by author(s) — works alongside --tag, --all, or --author (OR logic)
    python scripts/batch_index.py --tag "Leit-Literatur" --filter-author "Arendt"
    python scripts/batch_index.py --tag "Leit-Literatur" --rating 0 --filter-author "Arendt" --filter-author "Benjamin"
    python scripts/batch_index.py --all --filter-author "Tucholsky"

    # Include books tagged "exclude" or "Übersetzung" (excluded by default)
    python scripts/batch_index.py --tag "Leit-Literatur" --include-excluded
"""

import argparse
import json
import os
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.rag_demo import archillesRAG, LanceDBError
from scripts.safe_indexer import SafeIndexer
from scripts.find_books_missing_labels import find_books_missing_labels

# Hardware-adaptive profile system
from src.archilles.hardware import detect_hardware, print_hardware_detection, select_profile_interactive
from src.archilles.profiles import get_profile, list_profiles, IndexingProfile, create_index_metadata

# Preferred book formats in order of priority
PREFERRED_FORMATS = ['.pdf', '.epub', '.mobi', '.azw3', '.txt', '.md', '.txtz']

# Tags excluded by default — books carrying these tags are skipped unless
# --include-excluded is passed explicitly.
DEFAULT_EXCLUDED_TAGS = ['exclude', 'Übersetzung']


def get_library_path() -> Path:
    """Get library path from environment variable.

    Accepts ARCHILLES_LIBRARY_PATH or CALIBRE_LIBRARY_PATH (legacy).

    Raises:
        SystemExit: If neither variable is set
    """
    library_path = os.environ.get('ARCHILLES_LIBRARY_PATH') or os.environ.get('CALIBRE_LIBRARY_PATH')
    if not library_path:
        print("\n" + "="*60)
        print("ERROR: Library path not set")
        print("="*60 + "\n")
        print("Please set one of these environment variables:\n")
        print("  Windows (PowerShell):")
        print('    $env:ARCHILLES_LIBRARY_PATH = "C:\\path\\to\\Library"\n')
        print("  Linux/macOS:")
        print('    export ARCHILLES_LIBRARY_PATH="/path/to/Library"\n')
        print("  Legacy: CALIBRE_LIBRARY_PATH is also accepted.\n")
        sys.exit(1)
    return Path(library_path)


# Backward-compatible alias
get_calibre_library_path = get_library_path


def _discover_formats(book_path: Path) -> List[Dict[str, str]]:
    """Find available book formats in a Calibre book directory."""
    formats = []
    for ext in PREFERRED_FORMATS:
        for file in book_path.glob(f'*{ext}'):
            formats.append({
                'format': ext[1:].upper(),
                'path': str(file)
            })
    return formats


def _select_best_format(formats: List[Dict[str, str]], prefer_format: str = 'PDF') -> Dict[str, str]:
    """Select the best format from available formats.

    Tries prefer_format first, then falls back through the remaining
    PREFERRED_FORMATS order, then returns whatever is available.
    """
    order = [prefer_format.upper()] + [
        f[1:].upper() for f in PREFERRED_FORMATS
        if f[1:].upper() != prefer_format.upper()
    ]
    for fmt in order:
        for f in formats:
            if f['format'] == fmt:
                return f
    return formats[0]


def _build_book_entry(row: sqlite3.Row, library_path: Path, include_rating: bool = False) -> Optional[Dict[str, Any]]:
    """Build a standardized book dictionary from a database row.

    Returns None if the book has no supported formats on disk.
    """
    book_path = library_path / row['path']
    formats = _discover_formats(book_path)

    if not formats:
        return None

    entry = {
        'id': row['id'],
        'title': row['title'],
        'author': row['author'] or 'Unknown',
        'path': str(book_path),
        'formats': formats,
        'best_format': _select_best_format(formats),
    }

    if include_rating:
        entry['rating'] = row['rating'] // 2 if row['rating'] else 0

    return entry


def get_books_by_tag(library_path: Path, tag_name: str, min_rating: int = 0, exclude_tags: List[str] = None, rating: Optional[int] = None, author_filter: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """
    Get all books with a specific tag from Calibre database.

    Args:
        library_path: Path to Calibre library
        tag_name: Tag to filter by (case-insensitive)
        min_rating: Minimum star rating (1-5, 0 = no filter). Mutually exclusive with rating.
        exclude_tags: List of tags to exclude (e.g., ['DeepL', 'Machine-translated'])
        rating: Exact star rating to filter by (0 = no rating / NULL, 1-5 = exact star count).
                Mutually exclusive with min_rating.
        author_filter: Optional list of author name fragments; only books where at least one
                       author matches ANY of the fragments (partial, case-insensitive) are
                       returned.  Can be combined with --tag, --all, or --author.

    Returns:
        List of book dictionaries with metadata and file paths
    """
    db_path = library_path / "metadata.db"

    if not db_path.exists():
        raise FileNotFoundError(f"Calibre database not found: {db_path}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Build query with optional rating filter
    # Calibre stores rating in separate table (0-10 scale), we use 1-5 stars
    calibre_rating = min_rating * 2 if min_rating > 0 else 0

    query = """
    SELECT
        books.id,
        books.title,
        books.path,
        ratings.rating as rating,
        GROUP_CONCAT(authors.name, ' & ') as author
    FROM books
    INNER JOIN books_tags_link ON books.id = books_tags_link.book
    INNER JOIN tags ON books_tags_link.tag = tags.id
    LEFT JOIN books_authors_link ON books.id = books_authors_link.book
    LEFT JOIN authors ON books_authors_link.author = authors.id
    LEFT JOIN books_ratings_link ON books.id = books_ratings_link.book
    LEFT JOIN ratings ON books_ratings_link.rating = ratings.id
    WHERE LOWER(tags.name) = LOWER(?)
    """

    params = [tag_name]

    if calibre_rating > 0:
        query += " AND ratings.rating >= ?"
        params.append(calibre_rating)

    # Exact rating filter (--rating):
    # rating=0  → only books with no rating (Calibre stores NULL)
    # rating=N  → only books with exactly N stars (Calibre stores N*2 on a 0-10 scale)
    if rating is not None:
        if rating == 0:
            query += " AND ratings.rating IS NULL"
        else:
            query += " AND ratings.rating = ?"
            params.append(rating * 2)

    # Exclude books that have any of the excluded tags
    if exclude_tags:
        placeholders = ', '.join(['LOWER(?)' for _ in exclude_tags])
        query += f"""
        AND NOT EXISTS (
            SELECT 1 FROM books_tags_link btl_excl
            INNER JOIN tags t_excl ON btl_excl.tag = t_excl.id
            WHERE btl_excl.book = books.id
            AND LOWER(t_excl.name) IN ({placeholders})
        )
        """
        params.extend(exclude_tags)

    # Optional author filter: keep only books where at least one author matches
    # any of the given fragments (partial, case-insensitive).
    # Uses an EXISTS subquery so GROUP_CONCAT still shows all co-authors.
    if author_filter:
        or_clauses = ' OR '.join(['LOWER(af.name) LIKE LOWER(?)' for _ in author_filter])
        query += f"""
        AND EXISTS (
            SELECT 1 FROM books_authors_link bal_f
            INNER JOIN authors af ON bal_f.author = af.id
            WHERE bal_f.book = books.id
            AND ({or_clauses})
        )
        """
        params.extend([f'%{a}%' for a in author_filter])

    # Group by book to avoid duplicates when books have multiple authors
    query += " GROUP BY books.id"
    query += " ORDER BY ratings.rating DESC, author, books.title"

    cursor = conn.execute(query, params)
    rows = cursor.fetchall()

    books = []
    for row in rows:
        entry = _build_book_entry(row, library_path, include_rating=True)
        if entry:
            books.append(entry)

    conn.close()
    return books


def get_all_books(library_path: Path, author_filter: Optional[List[str]] = None, exclude_tags: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """
    Get ALL books from Calibre database (no filtering).

    Uses GROUP_CONCAT to handle multi-author books correctly.

    Args:
        library_path: Path to Calibre library
        author_filter: Optional list of author name fragments; only books where at least one
                       author matches ANY of the fragments (partial, case-insensitive) are
                       returned.
        exclude_tags: List of tags to exclude (e.g., ['exclude', 'Übersetzung'])

    Returns:
        List of book dictionaries with metadata and file paths
    """
    db_path = library_path / "metadata.db"

    if not db_path.exists():
        raise FileNotFoundError(f"Calibre database not found: {db_path}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    query = """
    SELECT
        books.id,
        books.title,
        books.path,
        GROUP_CONCAT(authors.name, ' & ') as author
    FROM books
    LEFT JOIN books_authors_link ON books.id = books_authors_link.book
    LEFT JOIN authors ON books_authors_link.author = authors.id
    """

    params: List[Any] = []
    conditions = []

    if author_filter:
        or_clauses = ' OR '.join(['LOWER(af.name) LIKE LOWER(?)' for _ in author_filter])
        conditions.append(f"""EXISTS (
        SELECT 1 FROM books_authors_link bal_f
        INNER JOIN authors af ON bal_f.author = af.id
        WHERE bal_f.book = books.id AND ({or_clauses})
    )""")
        params.extend([f'%{a}%' for a in author_filter])

    if exclude_tags:
        placeholders = ', '.join(['LOWER(?)' for _ in exclude_tags])
        conditions.append(f"""NOT EXISTS (
        SELECT 1 FROM books_tags_link btl_excl
        INNER JOIN tags t_excl ON btl_excl.tag = t_excl.id
        WHERE btl_excl.book = books.id AND LOWER(t_excl.name) IN ({placeholders})
    )""")
        params.extend(exclude_tags)

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += " GROUP BY books.id ORDER BY books.id"

    cursor = conn.execute(query, params)
    rows = cursor.fetchall()

    books = []
    for row in rows:
        entry = _build_book_entry(row, library_path)
        if entry:
            books.append(entry)

    conn.close()
    return books


def get_books_by_author(library_path: Path, author_name: str, min_rating: int = 0, rating: Optional[int] = None, exclude_tags: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """
    Get all books by a specific author from Calibre database.

    Args:
        library_path: Path to Calibre library
        author_name: Author name to filter by (partial match, case-insensitive)
        min_rating: Minimum star rating (1-5, 0 = no filter). Mutually exclusive with rating.
        rating: Exact star rating to filter by (0 = no rating / NULL, 1-5 = exact star count).
                Mutually exclusive with min_rating.
        exclude_tags: List of tags to exclude (e.g., ['exclude', 'Übersetzung'])

    Returns:
        List of book dictionaries with metadata and file paths
    """
    db_path = library_path / "metadata.db"

    if not db_path.exists():
        raise FileNotFoundError(f"Calibre database not found: {db_path}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # First find all books that have the author we're looking for
    # Then get all authors for those books (to show co-authors)
    query = """
    SELECT
        books.id,
        books.title,
        books.path,
        ratings.rating as rating,
        GROUP_CONCAT(all_authors.name, ' & ') as author
    FROM books
    INNER JOIN books_authors_link bal ON books.id = bal.book
    INNER JOIN authors ON bal.author = authors.id
    LEFT JOIN books_authors_link all_bal ON books.id = all_bal.book
    LEFT JOIN authors all_authors ON all_bal.author = all_authors.id
    LEFT JOIN books_ratings_link ON books.id = books_ratings_link.book
    LEFT JOIN ratings ON books_ratings_link.rating = ratings.id
    WHERE LOWER(authors.name) LIKE LOWER(?)
    """

    params = [f'%{author_name}%']

    calibre_rating = min_rating * 2 if min_rating > 0 else 0
    if calibre_rating > 0:
        query += " AND ratings.rating >= ?"
        params.append(calibre_rating)

    if rating is not None:
        if rating == 0:
            query += " AND ratings.rating IS NULL"
        else:
            query += " AND ratings.rating = ?"
            params.append(rating * 2)

    if exclude_tags:
        placeholders = ', '.join(['LOWER(?)' for _ in exclude_tags])
        query += f"""
        AND NOT EXISTS (
            SELECT 1 FROM books_tags_link btl_excl
            INNER JOIN tags t_excl ON btl_excl.tag = t_excl.id
            WHERE btl_excl.book = books.id
            AND LOWER(t_excl.name) IN ({placeholders})
        )
        """
        params.extend(exclude_tags)

    query += " GROUP BY books.id ORDER BY ratings.rating DESC, books.title"

    cursor = conn.execute(query, params)
    rows = cursor.fetchall()

    books = []
    for row in rows:
        entry = _build_book_entry(row, library_path, include_rating=True)
        if entry:
            books.append(entry)

    conn.close()
    return books


def get_books_by_ids(library_path: Path, calibre_ids: List[int]) -> List[Dict[str, Any]]:
    """
    Get specific books by their Calibre numeric IDs.

    Args:
        library_path: Path to Calibre library
        calibre_ids: List of Calibre book IDs (the 4-digit numbers shown in Calibre)

    Returns:
        List of book dictionaries with metadata and file paths
    """
    db_path = library_path / "metadata.db"

    if not db_path.exists():
        raise FileNotFoundError(f"Calibre database not found: {db_path}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    placeholders = ', '.join(['?' for _ in calibre_ids])
    query = f"""
    SELECT
        books.id,
        books.title,
        books.path,
        GROUP_CONCAT(authors.name, ' & ') as author
    FROM books
    LEFT JOIN books_authors_link ON books.id = books_authors_link.book
    LEFT JOIN authors ON books_authors_link.author = authors.id
    WHERE books.id IN ({placeholders})
    GROUP BY books.id
    ORDER BY books.id
    """

    cursor = conn.execute(query, calibre_ids)
    rows = cursor.fetchall()
    conn.close()

    found_ids = {row['id'] for row in rows}
    missing = set(calibre_ids) - found_ids
    if missing:
        print(f"⚠️  IDs not found in Calibre: {', '.join(str(i) for i in sorted(missing))}")

    books = []
    for row in rows:
        entry = _build_book_entry(row, library_path)
        if entry:
            books.append(entry)
        else:
            print(f"⚠️  No supported format found for ID {row['id']}: {row['title']}")

    return books


def get_all_calibre_ids(library_path: Path) -> set:
    """
    Return the set of ALL Calibre book IDs (as strings) via direct SQLite.
    Legacy fallback used only when no adapter is available.
    """
    db_path = library_path / "metadata.db"
    if not db_path.exists():
        raise FileNotFoundError(f"Calibre database not found: {db_path}")
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.execute("SELECT id FROM books")
        return {str(row[0]) for row in cursor.fetchall()}
    finally:
        conn.close()


def cleanup_orphans(
    rag: archillesRAG,
    library_path: Path,
    dry_run: bool = False,
    adapter=None,
) -> Dict[str, Any]:
    """
    Remove LanceDB entries for books that no longer exist in the library.

    Compares every book_id in the index against the full unfiltered library
    and deletes chunks for any book that has been removed.

    Uses the adapter (if provided) for library ID discovery so that
    non-Calibre backends (Folder, Obsidian, Zotero) are handled correctly.
    Falls back to direct SQLite access for legacy Calibre-only setups.

    Args:
        rag: Initialized archillesRAG instance
        library_path: Path to the library directory
        dry_run: If True, report orphans without deleting anything
        adapter: SourceAdapter instance (preferred over direct DB access)

    Returns:
        Dict with 'orphans_found' and 'orphans_removed' counts.
    """
    print("\n🔍 Scanning for orphaned index entries...")

    if adapter is not None:
        docs = adapter.list_documents()
        library_ids = {doc.doc_id for doc in docs}
        print(f"   Library ({adapter.adapter_type}): {len(library_ids)} documents")
    else:
        library_ids = get_all_calibre_ids(library_path)
        print(f"   Calibre library: {len(library_ids)} books (legacy mode)")

    # alias for the rest of the function (was calibre_ids)
    calibre_ids = library_ids

    all_chunks = rag.store.get_book_ids_for_skip_check()
    indexed_ids = {chunk['book_id'] for chunk in all_chunks}
    print(f"   LanceDB index:   {len(indexed_ids)} books")

    orphan_ids = indexed_ids - calibre_ids

    if not orphan_ids:
        print("   ✅ No orphans found — index is clean")
        return {'orphans_found': 0, 'orphans_removed': 0}

    print(f"\n   ⚠️  Found {len(orphan_ids)} orphaned book(s):")
    for book_id in sorted(orphan_ids, key=lambda x: x.zfill(20)):
        chunks = rag.store.get_by_book_id(book_id, limit=1)
        title = chunks[0].get('book_title', '?') if chunks else '?'
        author = chunks[0].get('author', '?') if chunks else '?'
        print(f"      [{book_id}] {author}: {title}")

    if dry_run:
        print(f"\n   ℹ️  DRY RUN — no deletions performed")
        return {'orphans_found': len(orphan_ids), 'orphans_removed': 0}

    removed = 0
    for book_id in sorted(orphan_ids, key=lambda x: x.zfill(20)):
        deleted = rag.store.delete_by_book_id(book_id)
        print(f"   🗑️  Deleted {deleted} chunks for book_id={book_id}")
        removed += 1

    print(f"\n   ✅ Cleanup complete: {removed} orphaned book(s) removed from index")
    return {'orphans_found': len(orphan_ids), 'orphans_removed': removed}


def _adapter_list_books(
    adapter,
    tag_filter: Optional[str] = None,
    exclude_tags: Optional[List[str]] = None,
    author_filter: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """List books via a SourceAdapter, returning dicts compatible with batch_index().

    This replaces the Calibre-specific get_all_books/get_books_by_tag/get_books_by_author
    for non-Calibre adapters.
    """
    docs = adapter.list_documents(tag_filter=tag_filter)

    # Apply exclude_tags (adapter only supports single exclude_tag)
    if exclude_tags:
        for etag in exclude_tags:
            docs = [d for d in docs if etag not in d.tags]

    # Apply author filter (partial, case-insensitive)
    if author_filter:
        def _author_matches(doc):
            for af in author_filter:
                af_lower = af.lower()
                for a in doc.authors:
                    if af_lower in a.lower():
                        return True
            return False
        docs = [d for d in docs if _author_matches(d)]

    books = []
    for doc in docs:
        # Skip documents without a file
        if not doc.file_path or not str(doc.file_path) or str(doc.file_path) == '.':
            continue
        if not doc.file_path.is_file():
            continue

        fmt = doc.file_format.upper() if doc.file_format else ""
        if not fmt:
            continue

        books.append({
            'id': doc.doc_id,
            'title': doc.title,
            'author': ' & '.join(doc.authors) if doc.authors else 'Unknown',
            'path': str(doc.file_path.parent),
            'formats': [{'format': fmt, 'path': str(doc.file_path)}],
            'best_format': {'format': fmt, 'path': str(doc.file_path)},
        })

    return books


def create_book_id(book: Dict[str, Any]) -> str:
    """
    Create a unique book ID for indexing.

    Uses the Calibre ID directly for easy cross-referencing.
    Example: "8127" (matches Calibre's "Id" column)
    """
    return str(book['id'])


def get_indexed_book_ids(
    rag: archillesRAG,
    reindex_before: datetime = None,
    reindex_missing_labels: bool = False,
    db_path: str = None
) -> set:
    """
    Get set of already indexed book IDs from RAG database.

    Args:
        rag: Initialized archillesRAG instance
        reindex_before: If provided, exclude books indexed before this date
                       (so they will be re-indexed)
        reindex_missing_labels: If True, exclude books with missing page labels
                               (so they will be re-indexed)
        db_path: Path to LanceDB database (for missing labels check)

    Returns:
        Set of book_id strings that are already in the index
        (excluding books that should be re-indexed)
    """
    # Get books with missing labels if requested
    books_missing_labels = set()
    if reindex_missing_labels and db_path:
        print("🔍 Checking for books with missing page labels...")
        missing = find_books_missing_labels(db_path)
        books_missing_labels = set(missing.keys())
        if books_missing_labels:
            print(f"   Found {len(books_missing_labels)} books needing page label re-indexing")
        else:
            print("   All books have proper page labels!")

    try:
        # Load only the minimal columns required (book_id, chunk_type, indexed_at).
        # This avoids reading the large 'text' and 'vector' columns and is 10-50x
        # faster than get_all(limit=100000) on large databases.
        all_chunks = rag.store.get_book_ids_for_skip_check()

        # Extract unique book_ids — only count books with actual CONTENT chunks
        # (not just phase1_metadata or calibre_comment)
        content_types = {'content', 'child', 'parent'}
        book_ids = set()
        for chunk in all_chunks:
            if not chunk or 'book_id' not in chunk:
                continue

            # Only count content chunks as "fully indexed"
            chunk_type = chunk.get('chunk_type', 'content')
            if chunk_type not in content_types:
                continue

            book_id = chunk['book_id']

            # Check if this book should be re-indexed due to missing labels
            if reindex_missing_labels and book_id in books_missing_labels:
                continue  # Don't add to set (will be re-indexed)

            # Check if this book should be re-indexed based on date
            if reindex_before:
                indexed_at_str = chunk.get('indexed_at')
                if indexed_at_str:
                    try:
                        indexed_at = datetime.fromisoformat(indexed_at_str)
                        if indexed_at < reindex_before:
                            continue
                    except (ValueError, AttributeError):
                        continue
                else:
                    continue

            book_ids.add(book_id)

        return book_ids
    except Exception as e:
        print(f"⚠️  Could not read existing index: {e}")
        return set()


def batch_reindex_comments(
    books: List[Dict[str, Any]],
    rag: archillesRAG,
    dry_run: bool = False,
    log_file: Optional[Path] = None,
    checkpoint_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Re-index only calibre_comment chunks for the given books.

    Fast: reads Calibre metadata (no PDF/EPUB extraction, no new embeddings
    for content chunks). Deletes existing comment chunks and rebuilds them
    using the structured HTML parser (H1/H2 split, bold/H3/H4 as key_passages).

    Use after editing Calibre comments or after upgrading the comment indexing logic.

    Supports resuming an interrupted run via checkpoint_path. Already-processed
    book_ids are written to the checkpoint file after each success; the file is
    deleted automatically when the run completes without errors.
    """
    import gc
    import numpy as np

    # ── Checkpoint setup ──────────────────────────────────────────
    if checkpoint_path is None:
        checkpoint_path = Path('.archilles_reindex_checkpoint.json')

    done_ids: set = set()
    if checkpoint_path.exists():
        try:
            with open(checkpoint_path, encoding='utf-8') as f:
                done_ids = set(json.load(f))
            print(f"  ↩  Resuming — {len(done_ids)} books already done (checkpoint: {checkpoint_path})")
        except Exception:
            done_ids = set()

    stats = {'updated': 0, 'skipped': 0, 'failed': 0, 'errors': []}

    remaining = [b for b in books if create_book_id(b) not in done_ids]
    total = len(books)

    print(f"\n{'='*60}")
    print(f"  Re-indexing comment chunks only (no full-text re-extraction)")
    print(f"  Books total: {total}  |  Remaining: {len(remaining)}")
    if dry_run:
        print(f"  Mode: DRY RUN")
    print(f"{'='*60}\n")

    offset = total - len(remaining)  # for display numbering

    for i, book in enumerate(remaining, 1):
        book_id = create_book_id(book)
        file_info = book.get('best_format', {})
        book_path = Path(file_info.get('path', ''))
        print(f"[{offset + i}/{total}] {book['author']}: {book['title']}")

        if dry_run:
            print(f"         [dry-run] would rebuild comment chunks")
            stats['updated'] += 1
            continue

        if not book_path.exists():
            print(f"         ⚠️  File not found: {book_path}")
            stats['skipped'] += 1
            done_ids.add(book_id)
            continue

        try:
            # Only read Calibre DB — skip PDF/EPUB file extraction entirely
            book_metadata = rag._extract_calibre_metadata(book_path)
            has_comments = bool(
                book_metadata.get('comments') or book_metadata.get('comments_html')
            )
            if not has_comments:
                print(f"         — No comments, skipping")
                stats['skipped'] += 1
                done_ids.add(book_id)
                continue

            deleted = rag.store.delete_by_book_id_and_type(book_id, 'calibre_comment')
            meta_hash = rag._compute_metadata_hash(book_metadata)
            book_format = file_info.get('format', '').lower()

            comment_chunks, comment_embeddings = rag._build_comment_chunks(
                book_metadata=book_metadata,
                book_id=book_id,
                book_format=book_format,
                metadata_hash=meta_hash,
            )

            if comment_chunks:
                rag.store.add_chunks(comment_chunks, np.array(comment_embeddings))
                print(f"         ✓ {deleted} old → {len(comment_chunks)} new chunk(s)")
                stats['updated'] += 1
            else:
                print(f"         — No comment content after parsing")
                stats['skipped'] += 1

            done_ids.add(book_id)

        except Exception as e:
            print(f"         ❌ {e}")
            stats['failed'] += 1
            stats['errors'].append({'title': book['title'], 'error': str(e)})

        if i % 20 == 0:
            if not dry_run:
                with open(checkpoint_path, 'w', encoding='utf-8') as f:
                    json.dump(list(done_ids), f)
            gc.collect()
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except Exception:
                pass

    # Final checkpoint flush
    if not dry_run:
        with open(checkpoint_path, 'w', encoding='utf-8') as f:
            json.dump(list(done_ids), f)

    print(f"\n{'='*60}")
    print(f"  Updated: {stats['updated']}")
    print(f"  Skipped: {stats['skipped']}")
    print(f"  Failed:  {stats['failed']}")
    print(f"{'='*60}\n")

    if stats['failed'] == 0 and checkpoint_path.exists():
        checkpoint_path.unlink()
        print(f"  ✓ Checkpoint removed (run complete)")

    if log_file:
        with open(log_file, 'w', encoding='utf-8') as f:
            json.dump(stats, f, indent=2, ensure_ascii=False)
        print(f"📝 Log written to: {log_file}")

    return stats


def batch_prepare(
    books: List[Dict[str, Any]],
    rag: archillesRAG,
    output_dir: str = './prepared_chunks',
    dry_run: bool = False,
    prefer_format: str = 'PDF',
) -> Dict[str, Any]:
    """
    Prepare multiple books (extract + chunk, no embedding).
    Writes one JSONL per book to output_dir.
    """
    stats = {
        'total': len(books),
        'prepared': 0,
        'skipped': 0,
        'failed': 0,
        'errors': [],
    }

    print(f"\n{'='*60}")
    print(f"  ARCHILLES BATCH PREPARE (no embedding)")
    print(f"{'='*60}")
    print(f"  Books to process: {len(books)}")
    print(f"  Output directory: {output_dir}")
    print(f"  Mode: {'DRY RUN' if dry_run else 'PREPARING'}")
    print(f"{'='*60}\n")

    for i, book in enumerate(books, 1):
        book_id = create_book_id(book)
        best = _select_best_format(book['formats'], prefer_format)

        print(f"\n[{i}/{len(books)}] {book['author']}: {book['title']}")
        print(f"         Format: {best['format']} | ID: {book_id}")

        if dry_run:
            print(f"         Would prepare: {best['path']}")
            continue

        try:
            result = rag.prepare_book(best['path'], book_id, output_dir=output_dir)
            if result.get('status') == 'already_prepared':
                stats['skipped'] += 1
            else:
                stats['prepared'] += 1
        except Exception as e:
            print(f"         FAILED: {e}")
            stats['failed'] += 1
            stats['errors'].append({'book_id': book_id, 'error': str(e)})

    print(f"\n{'='*60}")
    print(f"  Prepared: {stats['prepared']}, Skipped: {stats['skipped']}, Failed: {stats['failed']}")
    print(f"{'='*60}\n")
    return stats


def batch_index(
    books: List[Dict[str, Any]],
    rag: archillesRAG,
    dry_run: bool = False,
    skip_existing: bool = False,
    reindex_before: datetime = None,
    reindex_missing_labels: bool = False,
    force: bool = False,
    log_file: Optional[Path] = None,
    safe_indexer: Optional[SafeIndexer] = None,
    phase: str = 'phase2',
    db_path: str = None,
    prefer_format: str = 'PDF',
) -> Dict[str, Any]:
    """
    Index multiple books into the RAG database.

    Args:
        books: List of book dictionaries from get_books_by_tag/author
        rag: Initialized archillesRAG instance
        dry_run: If True, only show what would be indexed
        skip_existing: If True, skip books that are already indexed
        reindex_before: If provided, re-index books indexed before this date
        reindex_missing_labels: If True, re-index books with missing page labels
        log_file: Optional path to write detailed log
        safe_indexer: Optional SafeIndexer for crash-safety and progress tracking
        phase: 'phase1' (metadata only) or 'phase2' (full content)
        db_path: Path to LanceDB database

    Returns:
        Dictionary with indexing statistics

    Note on very large files:
        For extremely large PDFs (>100 MB of dense text, e.g. 1500+ pages),
        indexing can take several hours depending on hardware. There is no
        timeout by design — the indexer will work through large files given
        enough time. If a book appears to hang indefinitely, move the
        problematic file temporarily into a subfolder (e.g. ``data/``) within
        the Calibre book directory so that a smaller format (EPUB) is picked
        up instead. After the batch run completes, move the file back and
        re-index that single book with ``--force``.
    """
    stats = {
        'total': len(books),
        'indexed': 0,
        'skipped': 0,
        'failed': 0,
        'errors': [],
        'needs_ocr': [],
        'start_time': datetime.now().isoformat(),
        'books_processed': []
    }

    # Get already indexed books if skip_existing is enabled
    # If reindex_before is set, exclude old books from the existing set
    # Also check progress tracker if available
    should_check = skip_existing or reindex_before or reindex_missing_labels
    if safe_indexer:
        # Check progress tracker for indexed books
        existing_ids_from_tracker = set(safe_indexer.tracker.get_indexed_books(phase))
        existing_ids_from_lancedb = get_indexed_book_ids(
            rag, reindex_before, reindex_missing_labels, db_path
        ) if should_check else set()
        existing_ids = existing_ids_from_tracker | existing_ids_from_lancedb
    else:
        existing_ids = get_indexed_book_ids(
            rag, reindex_before, reindex_missing_labels, db_path
        ) if should_check else set()

    # When --skip-existing is set (without reindex flags), pre-filter the book
    # list so already-indexed books are never passed to index_book() at all.
    # This lets the loop jump directly to unindexed books rather than checking
    # every single book via a LanceDB read.
    if skip_existing and existing_ids and not reindex_before and not reindex_missing_labels:
        books = [b for b in books if create_book_id(b) not in existing_ids]

    print(f"\n{'='*60}")
    print(f"📚 ARCHILLES BATCH INDEXER")
    print(f"{'='*60}")
    print(f"  Books to process: {len(books)}")
    if skip_existing:
        print(f"  Already indexed (skipped): {len(existing_ids)}")
    if reindex_before:
        reindex_count = len(books) - len(existing_ids)
        print(f"  📅 Re-indexing books indexed before: {reindex_before.strftime('%Y-%m-%d')}")
        print(f"     → {reindex_count} books will be re-indexed")
    if reindex_missing_labels:
        print(f"  📄 Re-indexing books with missing page labels")
    print(f"  Mode: {'DRY RUN' if dry_run else 'INDEXING'}")
    print(f"{'='*60}\n")

    for i, book in enumerate(books, 1):
        # Check for shutdown request
        if safe_indexer and safe_indexer.should_shutdown():
            print(f"\n⏸️  Shutdown requested - stopping after {stats['indexed']} books")
            break

        book_id = create_book_id(book)

        # Build ordered format list: preferred first, alternatives as fallbacks
        best = _select_best_format(book['formats'], prefer_format)
        ordered_formats = [best] + [f for f in book['formats'] if f['path'] != best['path']]

        file_path = best['path']
        format_type = best['format']

        # Progress header
        print(f"\n[{i}/{len(books)}] {book['author']}: {book['title']}")
        print(f"         Format: {format_type} | ID: {book_id}")

        should_force = force or reindex_before is not None or reindex_missing_labels

        if dry_run:
            print(f"         🔍 Would index: {file_path}")
            stats['books_processed'].append({
                'id': book_id,
                'title': book['title'],
                'status': 'dry_run'
            })
            continue

        # Try each format in order, falling back on extraction failure
        result = None
        elapsed = 0.0
        last_exc = None

        for fmt_entry in ordered_formats:
            try:
                start_time = time.time()
                result = rag.index_book(fmt_entry['path'], book_id, force=should_force, phase=phase)
                elapsed = time.time() - start_time
                file_path = fmt_entry['path']
                format_type = fmt_entry['format']
                last_exc = None
                break  # success — stop trying further formats
            except Exception as e:
                last_exc = e
                remaining = ordered_formats[ordered_formats.index(fmt_entry) + 1:]
                if remaining:
                    print(f"         ⚠️  {fmt_entry['format']} failed ({e}), trying {remaining[0]['format']}...")

        # All formats exhausted without success
        if last_exc is not None:
            error_msg = str(last_exc)
            tried = ', '.join(f['format'] for f in ordered_formats)
            print(f"         ❌ FAILED (tried: {tried}): {error_msg}")

            if safe_indexer:
                safe_indexer.record_book(
                    book_id=book_id,
                    phase=phase,
                    status='failed',
                    error=error_msg[:500],
                )

            stats['failed'] += 1
            stats['errors'].append({
                'book_id': book_id,
                'title': book['title'],
                'error': error_msg,
            })
            stats['books_processed'].append({
                'id': book_id,
                'title': book['title'],
                'status': 'failed',
                'error': error_msg,
            })
            continue

        # Handle already-indexed books (from LanceDB check, not progress tracker)
        if result.get('status') == 'already_indexed':
            print(f"         ⏭️  SKIPPED (already in LanceDB: {result['chunks_indexed']} chunks)")
            stats['skipped'] += 1
            if safe_indexer:
                safe_indexer.record_book(book_id, phase, 'skipped')
            stats['books_processed'].append({
                'id': book_id,
                'title': book['title'],
                'status': 'skipped',
                'reason': 'already in LanceDB'
            })
            continue

        # Handle metadata-only updates (no full re-index needed)
        if result.get('status') == 'metadata_updated':
            print(f"         📝 Metadata updated in {result.get('total_time', 0):.1f}s (content unchanged)")
            stats['indexed'] += 1
            if safe_indexer:
                safe_indexer.record_book(book_id, phase, 'success',
                                       chunks=result.get('chunks_indexed', 0),
                                       duration=result.get('total_time', 0))
            stats['books_processed'].append({
                'id': book_id,
                'title': book['title'],
                'status': 'metadata_updated',
                'time': result.get('total_time', 0)
            })
            continue

        # Regular indexing completed
        if should_force:
            print(f"         ♻️  Re-indexed {result['chunks_indexed']} chunks in {elapsed:.1f}s")
        else:
            print(f"         ✅ Indexed {result['chunks_indexed']} chunks in {elapsed:.1f}s")
        if format_type != best['format']:
            print(f"         ↩️  Used fallback format: {format_type} (primary {best['format']} failed)")

        # Record success in progress tracker
        if safe_indexer:
            safe_indexer.record_book(
                book_id=book_id,
                phase=phase,
                status='success',
                chunks=result.get('chunks_indexed', 0),
                duration=elapsed
            )

        stats['indexed'] += 1
        if result.get('needs_ocr'):
            stats['needs_ocr'].append({'id': book_id, 'title': book['title']})
        stats['books_processed'].append({
            'id': book_id,
            'title': book['title'],
            'status': 'success',
            'chunks': result['chunks_indexed'],
            'time': elapsed
        })

    # Final summary
    stats['end_time'] = datetime.now().isoformat()

    print(f"\n{'='*60}")
    print(f"📊 INDEXING COMPLETE")
    print(f"{'='*60}")
    print(f"  Total books:     {stats['total']}")
    print(f"  Successfully indexed: {stats['indexed']}")
    print(f"  Skipped:         {stats['skipped']}")
    print(f"  Failed:          {stats['failed']}")

    if stats['errors']:
        print(f"\n⚠️  Errors:")
        for err in stats['errors']:
            print(f"    - {err['title']}: {err['error'][:50]}...")

    if stats['needs_ocr']:
        print(f"\n🔍 Scanned PDFs (no text extracted — re-index with --enable-ocr):")
        for book in stats['needs_ocr']:
            print(f"    - [{book['id']}] {book['title']}")

    print(f"{'='*60}\n")

    # Write log file if specified
    if log_file:
        with open(log_file, 'w', encoding='utf-8') as f:
            json.dump(stats, f, indent=2, ensure_ascii=False)
        print(f"📝 Log written to: {log_file}")

    return stats


def main():
    parser = argparse.ArgumentParser(
        description="Batch index books from Calibre library into ARCHILLES RAG",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Index ALL books in the library (no filter required)
  python scripts/batch_index.py --all

  # Use a specific hardware profile (minimal/balanced/maximal)
  python scripts/batch_index.py --all --profile minimal
  python scripts/batch_index.py --all --profile balanced

  # Index all books tagged "Leit-Literatur"
  python scripts/batch_index.py --tag "Leit-Literatur"

  # Dry run (preview without indexing)
  python scripts/batch_index.py --tag "Leit-Literatur" --dry-run

  # Index only first 5 books (for testing)
  python scripts/batch_index.py --tag "Leit-Literatur" --limit 5

  # Skip already indexed books
  python scripts/batch_index.py --tag "Leit-Literatur" --skip-existing

  # Index all books by an author
  python scripts/batch_index.py --author "Arendt"

  # Recover from corrupted database (after CTRL+C)
  python scripts/batch_index.py --tag "Leit-Literatur" --reset-db

  # Re-index old books (e.g., indexed before Dec 1st with old code)
  python scripts/batch_index.py --tag "Leit-Literatur" --reindex-before 2024-12-01

  # Exclude machine-translated books
  python scripts/batch_index.py --tag "Leit-Literatur" --exclude-tag "DeepL" --exclude-tag "Übersetzung"

  # Filter by minimum rating (1-5 stars, inclusive)
  python scripts/batch_index.py --tag "Leit-Literatur" --min-rating 4

  # Filter by exact rating (0 = no rating / NULL in Calibre)
  python scripts/batch_index.py --tag "Leit-Literatur" --rating 0   # only unrated
  python scripts/batch_index.py --tag "Leit-Literatur" --rating 5   # only 5-star books

  # Filter by author(s) — combinable with --tag, --all, or --author (OR logic)
  python scripts/batch_index.py --tag "Leit-Literatur" --filter-author "Arendt"
  python scripts/batch_index.py --tag "Leit-Literatur" --rating 0 --filter-author "Arendt" --filter-author "Benjamin"
  python scripts/batch_index.py --all --filter-author "Tucholsky"

Profiles:
  minimal  - CPU-only, resource-efficient (laptops, <6GB VRAM)
  balanced - GPU-accelerated, good quality (6-12GB VRAM)
  maximal  - Full GPU, maximum quality (>12GB VRAM)
        """
    )

    # Selection criteria (mutually exclusive; not required when --cleanup-orphans is used alone)
    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument('--all', action='store_true',
                       help='Index ALL books in the library (no tag/author filter)')
    group.add_argument('--tag', help='Index books with this tag')
    group.add_argument('--author', help='Index books by this author (partial match)')
    group.add_argument('--ids', metavar='ID[,ID,...]',
                       help='Comma-separated Calibre book IDs (e.g. --ids 1234,5678,9012). '
                            'Use --force to re-index already indexed books.')

    # Rating filters (mutually exclusive)
    rating_group = parser.add_mutually_exclusive_group()
    rating_group.add_argument('--min-rating', type=int, choices=[1, 2, 3, 4, 5], default=None,
                              help='Minimum star rating (1-5, inclusive)')
    rating_group.add_argument('--rating', type=int, choices=[0, 1, 2, 3, 4, 5],
                              help='Exact star rating to filter by. '
                                   '0 = only books without any rating (Calibre: NULL); '
                                   '1-5 = only books with exactly that many stars.')

    # Exclude filter (can be used multiple times)
    parser.add_argument('--exclude-tag', action='append', dest='exclude_tags', metavar='TAG',
                        help='Exclude books with this tag (can be used multiple times). '
                             'Added on top of the default excludes.')
    parser.add_argument('--include-excluded', action='store_true',
                        help=f'Override default tag exclusions ({", ".join(DEFAULT_EXCLUDED_TAGS)}) '
                             'and include those books. User-specified --exclude-tag values still apply.')

    # Author filter — additional, not mutually exclusive with --tag / --all / --author
    parser.add_argument('--filter-author', action='append', dest='filter_authors', metavar='AUTHOR',
                        help='Only include books where at least one author matches this fragment '
                             '(partial, case-insensitive). Can be repeated for multiple authors '
                             '(OR logic). Works alongside --tag, --all, and --author. '
                             'Example: --filter-author "Arendt" --filter-author "Benjamin"')

    # Options
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be indexed without actually indexing')
    parser.add_argument('--force', action='store_true',
                        help='Force re-indexing of ALL books (delete old chunks first). '
                             'Use after extractor upgrades (e.g. pdfplumber → PyMuPDF).')
    parser.add_argument('--skip-existing', action='store_true',
                        help='Skip books that are already in the index')
    parser.add_argument('--reindex-before', metavar='DATE',
                        help='Re-index books indexed before this date (YYYY-MM-DD). '
                             'Useful for re-indexing old books with improved code.')
    parser.add_argument('--reindex-missing-labels', action='store_true',
                        help='Re-index books with missing page labels (indexed before '
                             'page label extraction was implemented)')
    parser.add_argument('--reindex-comments', action='store_true',
                        help='Re-index only calibre_comment chunks (no full-text re-extraction). '
                             'Use after editing Calibre comments or upgrading comment indexing.')
    parser.add_argument('--start-after', metavar='AUTHOR',
                        help='Skip all books until an author matching this fragment is found '
                             '(case-insensitive, last match wins across rating tiers). E.g. "Bauman".')
    parser.add_argument('--skip', type=int, metavar='N',
                        help='Skip the first N books (use displayed position minus 1 to resume).')
    parser.add_argument('--limit', type=int,
                        help='Limit number of books to index (for testing)')
    parser.add_argument('--log', metavar='FILE',
                        help='Write detailed log to JSON file')
    parser.add_argument('--db-path', default=None,
                        help='RAG database path (default: CALIBRE_LIBRARY/.archilles/rag_db)')
    parser.add_argument('--reset-db', action='store_true',
                        help='Reset corrupted database (WARNING: deletes all indexed data)')
    parser.add_argument('--phase1-only', action='store_true',
                        help='Phase 1: Quick indexing of metadata, comments, and annotations only (5-10 min)')
    parser.add_argument('--non-interactive', action='store_true',
                        help='Run in non-interactive mode (auto-resume sessions, no prompts)')
    parser.add_argument('--enable-ocr', action='store_true',
                        help='Enable OCR for scanned PDFs (auto-detect)')
    parser.add_argument('--force-ocr', action='store_true',
                        help='Force OCR even for digital PDFs')
    parser.add_argument('--profile', choices=['minimal', 'balanced', 'maximal'],
                        help='Hardware profile to use (auto-detects if not specified)')
    parser.add_argument('--show-profiles', action='store_true',
                        help='Show available profiles and exit')
    parser.add_argument('--hierarchical', action='store_true',
                        help='Enable parent-child chunking (parents ~2048, children ~512 tokens)')
    parser.add_argument('--use-modular-pipeline', action='store_true',
                        help='Use ModularPipeline architecture (parser -> chunker -> embedder)')
    parser.add_argument('--prefer-format', choices=['pdf', 'epub', 'mobi', 'azw3'],
                        default='pdf',
                        help='Preferred file format when a book has multiple formats '
                             '(default: pdf). Use "epub" to prefer EPUB over PDF — '
                             'faster indexing, no page-number citations.')
    parser.add_argument('--cleanup-orphans', action='store_true',
                        help='Remove index entries for books deleted from Calibre. '
                             'Can be used standalone or combined with an indexing run. '
                             'Use --dry-run to preview orphans without deleting.')
    parser.add_argument('--prepare-only', action='store_true',
                        help='Extract and chunk books without embedding (Phase 1 of two-phase indexing). '
                             'Writes JSONL files to --output-dir. No GPU required.')
    parser.add_argument('--output-dir', default='./prepared_chunks',
                        help='Output directory for --prepare-only JSONL files (default: ./prepared_chunks)')

    args = parser.parse_args()

    # Handle --show-profiles
    if args.show_profiles:
        list_profiles()
        sys.exit(0)

    # Validate: require --all/--tag/--author/--ids unless --cleanup-orphans is the sole operation
    if not args.all and not args.tag and not args.author and not args.ids and not args.cleanup_orphans:
        parser.error("one of the arguments --all --tag --author --cleanup-orphans is required")

    # Parse reindex-before date if specified
    reindex_before = None
    if args.reindex_before:
        try:
            reindex_before = datetime.strptime(args.reindex_before, '%Y-%m-%d')
        except ValueError:
            print(f"❌ Invalid date format: {args.reindex_before}")
            print("   Use YYYY-MM-DD format (e.g., 2024-12-01)")
            sys.exit(1)

    # Get library path and create adapter
    library_path = get_library_path()
    adapter = None
    try:
        from src.adapters import create_adapter
        adapter = create_adapter(library_path)
        print(f"📚 Library: {library_path} (adapter: {adapter.adapter_type})")
    except Exception:
        print(f"📚 Library: {library_path} (no adapter — legacy mode)")

    # Determine hardware profile
    if args.profile:
        # User specified profile explicitly
        profile_name = args.profile
        profile = get_profile(profile_name)
        print(f"⚙️  Using profile: {profile_name.upper()} (user-specified)")
    elif args.non_interactive:
        # Non-interactive mode: auto-detect and use recommended
        hw = detect_hardware()
        profile_name = hw.recommend_profile()
        profile = get_profile(profile_name)
        print(f"⚙️  Using profile: {profile_name.upper()} (auto-detected)")
    else:
        # Interactive mode: show hardware detection and let user choose
        profile_name = select_profile_interactive()
        profile = get_profile(profile_name)

    print(f"    Model: {profile.embedding_model}")
    print(f"    Device: {profile.embedding_device}")
    print(f"    Chunk size: {profile.chunk_size} tokens")

    # Get books based on criteria
    min_rating = args.min_rating or 0
    rating = args.rating
    filter_authors = args.filter_authors

    # Build effective exclude list: defaults + user additions, unless --include-excluded
    base_excludes = [] if args.include_excluded else list(DEFAULT_EXCLUDED_TAGS)
    effective_excludes = base_excludes + (args.exclude_tags or [])

    if args.include_excluded:
        print(f"  Default excludes overridden (--include-excluded)")
    if effective_excludes:
        print(f"  Excluding tags: {', '.join(effective_excludes)}")

    # Determine RAG database path
    if args.db_path is None:
        args.db_path = str(library_path / ".archilles" / "rag_db")

    print(f"💾 RAG database: {args.db_path}")

    # Initialize RAG
    # DummyRAG only for pure dry-run without skip-existing and without cleanup-orphans
    needs_real_rag = args.skip_existing or args.cleanup_orphans or not args.dry_run
    if not needs_real_rag:
        class DummyRAG:
            def __init__(self):
                self.collection = type('obj', (object,), {'count': lambda: 0})()
        rag = DummyRAG()
    else:
        try:
            rag = archillesRAG(
                db_path=args.db_path,
                reset_db=args.reset_db,
                enable_ocr=args.enable_ocr,
                force_ocr=args.force_ocr,
                profile=profile_name,
                hierarchical=args.hierarchical,
                use_modular_pipeline=args.use_modular_pipeline,
                adapter=adapter,
                skip_model=getattr(args, 'prepare_only', False),
            )
        except LanceDBError as e:
            print(f"\n{'='*60}")
            print(f"❌ DATABASE ERROR")
            print(f"{'='*60}\n")
            print(str(e))
            print(f"\n{'='*60}\n")
            sys.exit(1)

    # Book selection + indexing (skipped when --cleanup-orphans is used standalone)
    use_adapter = adapter is not None and adapter.adapter_type != "calibre"
    stats = {'indexed': 0, 'failed': 0}
    if args.all or args.tag or args.author or args.ids:
        if use_adapter:
            # Non-Calibre adapter: use adapter for book discovery
            tag = args.tag if args.tag else None
            print(f"📚 Listing documents via {adapter.adapter_type} adapter")
            if tag:
                print(f"  Tag filter: {tag}")
            if filter_authors:
                print(f"  Author filter: {', '.join(filter_authors)}")
            books = _adapter_list_books(
                adapter,
                tag_filter=tag,
                exclude_tags=effective_excludes or None,
                author_filter=filter_authors if (filter_authors or args.author) else None,
            )
            # --author mode: filter by author name
            if args.author and not filter_authors:
                books = _adapter_list_books(
                    adapter,
                    exclude_tags=effective_excludes or None,
                    author_filter=[args.author],
                )
        elif args.all:
            print(f"📚 Indexing ALL books in the library")
            if filter_authors:
                print(f"  Author filter: {', '.join(filter_authors)}")
            books = get_all_books(library_path, author_filter=filter_authors, exclude_tags=effective_excludes or None)
        elif args.tag:
            print(f"  Filtering by tag: {args.tag}")
            if min_rating > 0:
                print(f"  Minimum rating: {'*' * min_rating} ({min_rating}+ stars)")
            if rating is not None:
                if rating == 0:
                    print(f"  Exact rating: no rating (NULL)")
                else:
                    print(f"  Exact rating: {'*' * rating} ({rating} stars)")
            if filter_authors:
                print(f"  Author filter: {', '.join(filter_authors)}")
            books = get_books_by_tag(library_path, args.tag, min_rating=min_rating, exclude_tags=effective_excludes or None, rating=rating, author_filter=filter_authors)
        elif args.author:
            print(f"  Filtering by author: {args.author}")
            if min_rating > 0:
                print(f"  Minimum rating: {'*' * min_rating} ({min_rating}+ stars)")
            if rating is not None:
                if rating == 0:
                    print(f"  Exact rating: no rating (NULL)")
                else:
                    print(f"  Exact rating: {'*' * rating} ({rating} stars)")
            if filter_authors:
                print(f"  Additional author filter: {', '.join(filter_authors)}")
            books = get_books_by_author(library_path, args.author, min_rating=min_rating, rating=rating, exclude_tags=effective_excludes or None)
        elif args.ids:
            try:
                calibre_ids = [int(i.strip()) for i in args.ids.split(',') if i.strip()]
            except ValueError:
                print(f"❌ Invalid --ids value: '{args.ids}' — use comma-separated integers, e.g. --ids 1234,5678")
                sys.exit(1)
            print(f"  Indexing {len(calibre_ids)} specific book(s) by Calibre ID: {calibre_ids}")
            books = get_books_by_ids(library_path, calibre_ids)

        if not books:
            print("❌ No books found matching criteria")
            if not args.cleanup_orphans:
                return

        else:
            print(f"📖 Found {len(books)} books")

            if args.limit:
                books = books[:args.limit]
                print(f"📊 Limited to first {args.limit} books")

            # --reindex-comments: fast path, no full-text extraction
            if args.reindex_comments:
                log_file = Path(args.log) if args.log else None
                reindex_books = books
                if getattr(args, 'skip', None):
                    n = args.skip
                    if n >= len(books):
                        print(f"⚠️  --skip {n} exceeds total books ({len(books)}). Nothing to do.")
                        return
                    print(f"  ↩  Skipping {n} books, starting at [{n+1}] {books[n]['author']}: {books[n]['title']}")
                    reindex_books = books[n:]
                elif getattr(args, 'start_after', None):
                    fragment = args.start_after.lower()
                    # Use last match so the author is found in the correct rating tier
                    matches = [i for i, b in enumerate(books)
                               if fragment in b.get('author', '').lower()]
                    if not matches:
                        print(f"⚠️  --start-after: no author matching '{args.start_after}' found. Processing all books.")
                    else:
                        idx = matches[-1]
                        print(f"  ↩  Skipping {idx} books, starting at [{idx+1}] {books[idx]['author']}: {books[idx]['title']}")
                        reindex_books = books[idx:]
                batch_reindex_comments(
                    books=reindex_books,
                    rag=rag,
                    dry_run=args.dry_run,
                    log_file=log_file,
                )
                return

            # --prepare-only: extract and chunk without embedding
            if getattr(args, 'prepare_only', False):
                stats = batch_prepare(
                    books=books,
                    rag=rag,
                    output_dir=args.output_dir,
                    dry_run=args.dry_run,
                    prefer_format=args.prefer_format,
                )
                if stats['failed'] > 0:
                    sys.exit(1)
                return

            # Initialize SafeIndexer for crash-safety
            safe_indexer = None
            if not args.dry_run:
                safe_indexer = SafeIndexer(
                    db_path=Path(args.db_path),
                    backup_interval=50,
                    max_backups=2
                )
                phase = 'phase1' if args.phase1_only else 'phase2'
                interactive = None if not args.non_interactive else False
                session_id = safe_indexer.start_session(phase, interactive=interactive)

            # Run batch indexing
            log_file = Path(args.log) if args.log else None
            stats = batch_index(
                books=books,
                rag=rag,
                dry_run=args.dry_run,
                skip_existing=args.skip_existing,
                reindex_before=reindex_before,
                reindex_missing_labels=args.reindex_missing_labels,
                force=args.force,
                log_file=log_file,
                safe_indexer=safe_indexer,
                phase=phase if safe_indexer else 'phase2',
                db_path=args.db_path,
                prefer_format=args.prefer_format,
            )

            # End session (if not dry run)
            if safe_indexer:
                status = 'completed' if not safe_indexer.should_shutdown() else 'interrupted'
                safe_indexer.end_session(status)

            # Create FTS index if we indexed something new
            if not args.dry_run and stats['indexed'] > 0:
                print("\n📇 Creating full-text search index...")
                try:
                    rag.store.create_fts_index()
                    print("   ✅ FTS index created - keyword search now available")
                except Exception as e:
                    print(f"   ⚠️  FTS index creation failed: {e}")
                    print("   Keyword search may not work. Run: python scripts/rag_demo.py create-index")

            if stats['failed'] > 0:
                sys.exit(1)

    # Orphan cleanup (after indexing, or standalone)
    if args.cleanup_orphans:
        cleanup_orphans(rag, library_path, dry_run=args.dry_run, adapter=adapter)


if __name__ == '__main__':
    main()
