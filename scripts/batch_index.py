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
"""

import sys
import argparse
import sqlite3
import json
import time
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional
import os

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.rag_demo import archillesRAG, ChromaDBCorruptionError
from scripts.safe_indexer import SafeIndexer
from scripts.import_calibre_annotations import import_annotations, find_latest_export
from scripts.find_books_missing_labels import find_books_missing_labels

# Hardware-adaptive profile system
from src.archilles.hardware import detect_hardware, print_hardware_detection, select_profile_interactive
from src.archilles.profiles import get_profile, list_profiles, IndexingProfile, create_index_metadata


def get_calibre_library_path() -> Path:
    """Get Calibre library path from environment variable.

    Raises:
        SystemExit: If CALIBRE_LIBRARY_PATH is not set
    """
    library_path = os.environ.get('CALIBRE_LIBRARY_PATH')
    if not library_path:
        print("\n" + "="*60)
        print("ERROR: CALIBRE_LIBRARY_PATH not set")
        print("="*60 + "\n")
        print("Please set the environment variable to your Calibre library:\n")
        print("  Windows (PowerShell):")
        print('    $env:CALIBRE_LIBRARY_PATH = "C:\\path\\to\\Calibre-Library"\n')
        print("  Linux/macOS:")
        print('    export CALIBRE_LIBRARY_PATH="/path/to/Calibre-Library"\n')
        sys.exit(1)
    return Path(library_path)


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
        book_path = library_path / row['path']

        # Find available formats (prefer PDF, then EPUB)
        formats = []
        for ext in ['.pdf', '.epub', '.mobi', '.azw3']:
            for file in book_path.glob(f'*{ext}'):
                formats.append({
                    'format': ext[1:].upper(),
                    'path': str(file)
                })

        if formats:
            rating = row['rating'] // 2 if row['rating'] else 0
            books.append({
                'id': row['id'],
                'title': row['title'],
                'author': row['author'] or 'Unknown',
                'rating': rating,
                'path': str(book_path),
                'formats': formats,
                # Prefer PDF > EPUB > others
                'best_format': next(
                    (f for f in formats if f['format'] == 'PDF'),
                    next((f for f in formats if f['format'] == 'EPUB'), formats[0])
                )
            })

    conn.close()
    return books


def get_all_books(library_path: Path, author_filter: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """
    Get ALL books from Calibre database (no filtering).

    Uses GROUP_CONCAT to handle multi-author books correctly.

    Args:
        library_path: Path to Calibre library
        author_filter: Optional list of author name fragments; only books where at least one
                       author matches ANY of the fragments (partial, case-insensitive) are
                       returned.

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

    if author_filter:
        or_clauses = ' OR '.join(['LOWER(af.name) LIKE LOWER(?)' for _ in author_filter])
        query += f"""
    WHERE EXISTS (
        SELECT 1 FROM books_authors_link bal_f
        INNER JOIN authors af ON bal_f.author = af.id
        WHERE bal_f.book = books.id
        AND ({or_clauses})
    )
        """
        params.extend([f'%{a}%' for a in author_filter])

    query += " GROUP BY books.id ORDER BY books.id"

    cursor = conn.execute(query, params)
    rows = cursor.fetchall()

    books = []
    for row in rows:
        book_path = library_path / row['path']

        # Find available formats
        formats = []
        for ext in ['.pdf', '.epub', '.mobi', '.azw3']:
            for file in book_path.glob(f'*{ext}'):
                formats.append({
                    'format': ext[1:].upper(),
                    'path': str(file)
                })

        if formats:
            books.append({
                'id': row['id'],
                'title': row['title'],
                'author': row['author'] or 'Unknown',
                'path': str(book_path),
                'formats': formats,
                'best_format': next(
                    (f for f in formats if f['format'] == 'PDF'),
                    next((f for f in formats if f['format'] == 'EPUB'), formats[0])
                )
            })

    conn.close()
    return books


def get_books_by_author(library_path: Path, author_name: str, min_rating: int = 0, rating: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Get all books by a specific author from Calibre database.

    Args:
        library_path: Path to Calibre library
        author_name: Author name to filter by (partial match, case-insensitive)
        min_rating: Minimum star rating (1-5, 0 = no filter). Mutually exclusive with rating.
        rating: Exact star rating to filter by (0 = no rating / NULL, 1-5 = exact star count).
                Mutually exclusive with min_rating.

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

    query += " GROUP BY books.id ORDER BY ratings.rating DESC, books.title"

    cursor = conn.execute(query, params)
    rows = cursor.fetchall()

    books = []
    for row in rows:
        book_path = library_path / row['path']

        # Find available formats
        formats = []
        for ext in ['.pdf', '.epub', '.mobi', '.azw3']:
            for file in book_path.glob(f'*{ext}'):
                formats.append({
                    'format': ext[1:].upper(),
                    'path': str(file)
                })

        if formats:
            rating_val = row['rating'] // 2 if row['rating'] else 0
            books.append({
                'id': row['id'],
                'title': row['title'],
                'author': row['author'] or 'Unknown',
                'rating': rating_val,
                'path': str(book_path),
                'formats': formats,
                'best_format': next(
                    (f for f in formats if f['format'] == 'PDF'),
                    next((f for f in formats if f['format'] == 'EPUB'), formats[0])
                )
            })

    conn.close()
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
    db_path: str = None
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
        existing_ids_from_chromadb = get_indexed_book_ids(
            rag, reindex_before, reindex_missing_labels, db_path
        ) if should_check else set()
        existing_ids = existing_ids_from_tracker | existing_ids_from_chromadb
    else:
        existing_ids = get_indexed_book_ids(
            rag, reindex_before, reindex_missing_labels, db_path
        ) if should_check else set()

    print(f"\n{'='*60}")
    print(f"📚 ARCHILLES BATCH INDEXER")
    print(f"{'='*60}")
    print(f"  Books to process: {len(books)}")
    if skip_existing:
        print(f"  Already indexed: {len(existing_ids)}")
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
        file_path = book['best_format']['path']
        format_type = book['best_format']['format']

        # Progress header
        print(f"\n[{i}/{len(books)}] {book['author']}: {book['title']}")
        print(f"         Format: {format_type} | ID: {book_id}")

        # Skip logic:
        # --force: never skip, always re-index everything
        # --skip-existing: pass to index_book() which checks metadata/annotation hashes
        #   → unchanged books are skipped, changed metadata/annotations get a fast update
        # default (neither): let index_book() decide (it skips if chunks exist)
        force_reindex = force or reindex_before or reindex_missing_labels

        if dry_run:
            print(f"         🔍 Would index: {file_path}")
            stats['books_processed'].append({
                'id': book_id,
                'title': book['title'],
                'status': 'dry_run'
            })
            continue

        # Actually index the book
        try:
            start_time = time.time()
            # Use force=True when re-indexing old books, missing labels, or --force
            should_force = force or reindex_before is not None or reindex_missing_labels
            result = rag.index_book(file_path, book_id, force=should_force, phase=phase)
            elapsed = time.time() - start_time

            # Handle already-indexed books (from ChromaDB check, not progress tracker)
            if result.get('status') == 'already_indexed':
                print(f"         ⏭️  SKIPPED (already in ChromaDB: {result['chunks_indexed']} chunks)")
                stats['skipped'] += 1
                if safe_indexer:
                    safe_indexer.record_book(book_id, phase, 'skipped')
                stats['books_processed'].append({
                    'id': book_id,
                    'title': book['title'],
                    'status': 'skipped',
                    'reason': 'already in ChromaDB'
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
            if force_reindex:
                print(f"         ♻️  Re-indexed {result['chunks_indexed']} chunks in {elapsed:.1f}s")
            else:
                print(f"         ✅ Indexed {result['chunks_indexed']} chunks in {elapsed:.1f}s")

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
            stats['books_processed'].append({
                'id': book_id,
                'title': book['title'],
                'status': 'success',
                'chunks': result['chunks_indexed'],
                'time': elapsed
            })

        except Exception as e:
            error_msg = str(e)
            print(f"         ❌ FAILED: {error_msg}")

            # Record failure in progress tracker
            if safe_indexer:
                safe_indexer.record_book(
                    book_id=book_id,
                    phase=phase,
                    status='failed',
                    error=error_msg[:500]  # Limit error message length
                )

            stats['failed'] += 1
            stats['errors'].append({
                'book_id': book_id,
                'title': book['title'],
                'error': error_msg
            })
            stats['books_processed'].append({
                'id': book_id,
                'title': book['title'],
                'status': 'failed',
                'error': error_msg
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

    # Selection criteria (mutually exclusive)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--all', action='store_true',
                       help='Index ALL books in the library (no tag/author filter)')
    group.add_argument('--tag', help='Index books with this tag')
    group.add_argument('--author', help='Index books by this author (partial match)')

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
                        help='Exclude books with this tag (can be used multiple times, e.g., --exclude-tag "DeepL" --exclude-tag "Übersetzung")')

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

    args = parser.parse_args()

    # Handle --show-profiles
    if args.show_profiles:
        list_profiles()
        sys.exit(0)

    # Parse reindex-before date if specified
    reindex_before = None
    if args.reindex_before:
        try:
            reindex_before = datetime.strptime(args.reindex_before, '%Y-%m-%d')
        except ValueError:
            print(f"❌ Invalid date format: {args.reindex_before}")
            print("   Use YYYY-MM-DD format (e.g., 2024-12-01)")
            sys.exit(1)

    # Get library path
    library_path = get_calibre_library_path()
    print(f"📚 Calibre library: {library_path}")

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
    min_rating = getattr(args, 'min_rating', None) or 0
    rating = getattr(args, 'rating', None)
    filter_authors = getattr(args, 'filter_authors', None)
    if getattr(args, 'all', False):
        print(f"📚 Indexing ALL books in the library")
        if filter_authors:
            print(f"  Author filter: {', '.join(filter_authors)}")
        books = get_all_books(library_path, author_filter=filter_authors)
    elif args.tag:
        print(f"  Filtering by tag: {args.tag}")
        if min_rating > 0:
            print(f"  Minimum rating: {'*' * min_rating} ({min_rating}+ stars)")
        if rating is not None:
            if rating == 0:
                print(f"  Exact rating: no rating (NULL)")
            else:
                print(f"  Exact rating: {'*' * rating} ({rating} stars)")
        exclude_tags = getattr(args, 'exclude_tags', None)
        if exclude_tags:
            print(f"  Excluding tags: {', '.join(exclude_tags)}")
        if filter_authors:
            print(f"  Author filter: {', '.join(filter_authors)}")
        books = get_books_by_tag(library_path, args.tag, min_rating=min_rating, exclude_tags=exclude_tags, rating=rating, author_filter=filter_authors)
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
        books = get_books_by_author(library_path, args.author, min_rating=min_rating, rating=rating)

    if not books:
        print("❌ No books found matching criteria")
        return

    print(f"📖 Found {len(books)} books")

    # Apply limit if specified
    if args.limit:
        books = books[:args.limit]
        print(f"📊 Limited to first {args.limit} books")

    # Determine RAG database path
    if args.db_path is None:
        args.db_path = str(library_path / ".archilles" / "rag_db")

    print(f"💾 RAG database: {args.db_path}")

    # Initialize RAG (unless dry run with no skip-existing check needed)
    if args.dry_run and not args.skip_existing:
        # For pure dry run, create minimal object
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
                hierarchical=getattr(args, 'hierarchical', False),
                use_modular_pipeline=getattr(args, 'use_modular_pipeline', False)
            )
        except ChromaDBCorruptionError as e:
            # ChromaDB is corrupted - show helpful error message
            print(f"\n{'='*60}")
            print(f"❌ DATABASE CORRUPTION DETECTED")
            print(f"{'='*60}\n")
            print(str(e))
            print(f"\n{'='*60}\n")
            sys.exit(1)

    # Initialize SafeIndexer for crash-safety
    safe_indexer = None
    if not args.dry_run:
        safe_indexer = SafeIndexer(
            db_path=Path(args.db_path),
            backup_interval=50,  # Backup every 50 books
            max_backups=2         # Keep 2 most recent backups
        )

        # Determine phase
        phase = 'phase1' if args.phase1_only else 'phase2'

        # Start indexing session (auto-detect interactive mode unless --non-interactive)
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
        db_path=args.db_path
    )

    # End session (if not dry run)
    if safe_indexer:
        status = 'completed' if not safe_indexer.should_shutdown() else 'interrupted'
        safe_indexer.end_session(status)

    # Create FTS index for keyword search (if not dry run and we indexed something)
    if not args.dry_run and stats['indexed'] > 0:
        print("\n📇 Creating full-text search index...")
        try:
            rag.store.create_fts_index()
            print("   ✅ FTS index created - keyword search now available")
        except Exception as e:
            print(f"   ⚠️  FTS index creation failed: {e}")
            print("   Keyword search may not work. Run: python scripts/rag_demo.py create-index")

    # Exit with error code if any failures
    if stats['failed'] > 0:
        sys.exit(1)


if __name__ == '__main__':
    main()
