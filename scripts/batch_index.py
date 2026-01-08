#!/usr/bin/env python3
"""
ARCHILLES Batch Indexer

Index multiple books from Calibre library by tag, author, or all books.

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

    # Run in non-interactive mode (auto-resume sessions, no prompts)
    python scripts/batch_index.py --tag "Leit-Literatur" --non-interactive
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

# Hardware-adaptive profile system
from src.archilles.hardware import detect_hardware, print_hardware_detection, select_profile_interactive
from src.archilles.profiles import (
    get_profile, list_profiles, IndexingProfile, create_index_metadata,
    save_index_metadata, load_index_metadata, check_index_compatibility, print_index_info
)


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


def get_books_by_tag(library_path: Path, tag_name: str) -> List[Dict[str, Any]]:
    """
    Get all books with a specific tag from Calibre database.

    IMPORTANT: Uses Calibre book ID as primary key to avoid duplicate
    processing of multi-author books. Each book is returned exactly once,
    regardless of how many authors it has.

    Args:
        library_path: Path to Calibre library
        tag_name: Tag to filter by (case-insensitive)

    Returns:
        List of book dictionaries with metadata and file paths
    """
    db_path = library_path / "metadata.db"

    if not db_path.exists():
        raise FileNotFoundError(f"Calibre database not found: {db_path}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Get UNIQUE book IDs first - this is the critical fix!
    # Multi-author books must only appear once in the result.
    query = """
    SELECT DISTINCT
        books.id,
        books.title,
        books.path
    FROM books
    INNER JOIN books_tags_link ON books.id = books_tags_link.book
    INNER JOIN tags ON books_tags_link.tag = tags.id
    WHERE LOWER(tags.name) = LOWER(?)
    ORDER BY books.id
    """

    cursor = conn.execute(query, (tag_name,))
    rows = cursor.fetchall()

    books = []
    for row in rows:
        book_id = row['id']
        book_path = library_path / row['path']

        # Get ALL authors for this book (aggregated, not iterated)
        authors = _get_authors_for_book(conn, book_id)

        # Find available formats (prefer PDF, then EPUB)
        formats = []
        for ext in ['.pdf', '.epub', '.mobi', '.azw3']:
            for file in book_path.glob(f'*{ext}'):
                formats.append({
                    'format': ext[1:].upper(),
                    'path': str(file)
                })

        if formats:
            books.append({
                'id': book_id,
                'title': row['title'],
                'author': authors,  # All authors as single string
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


def _get_authors_for_book(conn: sqlite3.Connection, book_id: int) -> str:
    """
    Get all authors for a book as a single string.

    This helper ensures we aggregate authors instead of iterating over them,
    preventing duplicate processing of multi-author books.

    Args:
        conn: SQLite connection to Calibre database
        book_id: Calibre book ID

    Returns:
        Authors joined with " & " (e.g., "Mason & Rives & Edmondson")
    """
    query = """
    SELECT authors.name
    FROM authors
    INNER JOIN books_authors_link ON authors.id = books_authors_link.author
    WHERE books_authors_link.book = ?
    ORDER BY books_authors_link.id
    """
    cursor = conn.execute(query, (book_id,))
    author_rows = cursor.fetchall()

    if author_rows:
        return ' & '.join([row['name'] for row in author_rows])
    return 'Unknown'


def get_all_books(library_path: Path) -> List[Dict[str, Any]]:
    """
    Get ALL books from Calibre database (no filtering).

    IMPORTANT: Uses Calibre book ID as primary key to avoid duplicate
    processing of multi-author books. Each book is returned exactly once.

    Args:
        library_path: Path to Calibre library

    Returns:
        List of book dictionaries with metadata and file paths
    """
    db_path = library_path / "metadata.db"

    if not db_path.exists():
        raise FileNotFoundError(f"Calibre database not found: {db_path}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Get all books by unique ID
    query = """
    SELECT
        books.id,
        books.title,
        books.path
    FROM books
    ORDER BY books.id
    """

    cursor = conn.execute(query)
    rows = cursor.fetchall()

    books = []
    for row in rows:
        book_id = row['id']
        book_path = library_path / row['path']

        # Get ALL authors for this book (aggregated, not iterated)
        authors = _get_authors_for_book(conn, book_id)

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
                'id': book_id,
                'title': row['title'],
                'author': authors,
                'path': str(book_path),
                'formats': formats,
                'best_format': next(
                    (f for f in formats if f['format'] == 'PDF'),
                    next((f for f in formats if f['format'] == 'EPUB'), formats[0])
                )
            })

    conn.close()
    return books


def get_books_by_calibre_ids(library_path: Path, calibre_ids: List[int]) -> List[Dict[str, Any]]:
    """
    Get books by their Calibre IDs.

    Used for retrying failed books.

    Args:
        library_path: Path to Calibre library
        calibre_ids: List of Calibre book IDs to retrieve

    Returns:
        List of book dictionaries with metadata and file paths
    """
    if not calibre_ids:
        return []

    db_path = library_path / "metadata.db"

    if not db_path.exists():
        raise FileNotFoundError(f"Calibre database not found: {db_path}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Get books by IDs
    placeholders = ','.join('?' * len(calibre_ids))
    query = f"""
    SELECT
        books.id,
        books.title,
        books.path
    FROM books
    WHERE books.id IN ({placeholders})
    ORDER BY books.id
    """

    cursor = conn.execute(query, calibre_ids)
    rows = cursor.fetchall()

    books = []
    for row in rows:
        book_id = row['id']
        book_path = library_path / row['path']

        # Get ALL authors for this book (aggregated, not iterated)
        authors = _get_authors_for_book(conn, book_id)

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
                'id': book_id,
                'title': row['title'],
                'author': authors,
                'path': str(book_path),
                'formats': formats,
                'best_format': next(
                    (f for f in formats if f['format'] == 'PDF'),
                    next((f for f in formats if f['format'] == 'EPUB'), formats[0])
                )
            })

    conn.close()
    return books


def get_books_by_author(library_path: Path, author_name: str) -> List[Dict[str, Any]]:
    """
    Get all books by a specific author from Calibre database.

    IMPORTANT: Uses Calibre book ID as primary key to avoid duplicate
    processing of multi-author books. Each book is returned exactly once,
    regardless of how many authors it has.

    Args:
        library_path: Path to Calibre library
        author_name: Author name to filter by (partial match, case-insensitive)

    Returns:
        List of book dictionaries with metadata and file paths
    """
    db_path = library_path / "metadata.db"

    if not db_path.exists():
        raise FileNotFoundError(f"Calibre database not found: {db_path}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Get UNIQUE book IDs first - this is the critical fix!
    # Multi-author books must only appear once in the result.
    query = """
    SELECT DISTINCT
        books.id,
        books.title,
        books.path
    FROM books
    INNER JOIN books_authors_link ON books.id = books_authors_link.book
    INNER JOIN authors ON books_authors_link.author = authors.id
    WHERE LOWER(authors.name) LIKE LOWER(?)
    ORDER BY books.id
    """

    cursor = conn.execute(query, (f'%{author_name}%',))
    rows = cursor.fetchall()

    books = []
    for row in rows:
        book_id = row['id']
        book_path = library_path / row['path']

        # Get ALL authors for this book (aggregated, not iterated)
        authors = _get_authors_for_book(conn, book_id)

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
                'id': book_id,
                'title': row['title'],
                'author': authors,  # All authors as single string
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
    Create a unique, readable book ID for indexing.

    Format: AuthorLastName_ShortTitle_CalibreID
    Example: Arendt_VitaActiva_1234
    """
    # Extract last name from author
    author = book['author']
    if ',' in author:
        # "LastName, FirstName" format
        last_name = author.split(',')[0].strip()
    else:
        # "FirstName LastName" format
        parts = author.split()
        last_name = parts[-1] if parts else 'Unknown'

    # Clean last name (remove special chars)
    last_name = ''.join(c for c in last_name if c.isalnum())

    # Create short title (first 20 chars, alphanumeric only)
    title = book['title']
    short_title = ''.join(c for c in title if c.isalnum() or c.isspace())[:20]
    short_title = short_title.replace(' ', '')

    return f"{last_name}_{short_title}_{book['id']}"


def get_indexed_book_ids(rag: archillesRAG, reindex_before: datetime = None) -> set:
    """
    Get set of already indexed book IDs from RAG database.

    Args:
        rag: Initialized archillesRAG instance
        reindex_before: If provided, exclude books indexed before this date
                       (so they will be re-indexed)

    Returns:
        Set of book_id strings that are already in the index
        (excluding books that should be re-indexed)
    """
    try:
        # Get all metadata from collection in batches
        all_metadatas = []
        batch_size = 500
        offset = 0

        while True:
            batch = rag.collection.get(limit=batch_size, offset=offset)
            if not batch['ids']:
                break
            all_metadatas.extend(batch['metadatas'])
            offset += batch_size
            if len(batch['ids']) < batch_size:
                break

        # Extract unique book_ids
        book_ids = set()
        for metadata in all_metadatas:
            if metadata and 'book_id' in metadata:
                book_id = metadata['book_id']

                # Check if this book should be re-indexed based on date
                if reindex_before:
                    indexed_at_str = metadata.get('indexed_at')
                    if indexed_at_str:
                        try:
                            indexed_at = datetime.fromisoformat(indexed_at_str)
                            # If book was indexed before the cutoff date, don't add to set
                            # (so it will be re-indexed)
                            if indexed_at < reindex_before:
                                continue
                        except (ValueError, AttributeError):
                            # If we can't parse the date, treat as old (re-index)
                            continue
                    else:
                        # No timestamp = old book (re-index)
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
    log_file: Optional[Path] = None,
    safe_indexer: Optional[SafeIndexer] = None,
    phase: str = 'phase2'
) -> Dict[str, Any]:
    """
    Index multiple books into the RAG database.

    Args:
        books: List of book dictionaries from get_books_by_tag/author
        rag: Initialized archillesRAG instance
        dry_run: If True, only show what would be indexed
        skip_existing: If True, skip books that are already indexed
        reindex_before: If provided, re-index books indexed before this date
        log_file: Optional path to write detailed log
        safe_indexer: Optional SafeIndexer for crash-safety and progress tracking
        phase: 'phase1' (metadata only) or 'phase2' (full content)

    Returns:
        Dictionary with indexing statistics
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
    if safe_indexer:
        # Check progress tracker for indexed books
        existing_ids_from_tracker = set(safe_indexer.tracker.get_indexed_books(phase))
        existing_ids_from_chromadb = get_indexed_book_ids(rag, reindex_before) if skip_existing or reindex_before else set()
        existing_ids = existing_ids_from_tracker | existing_ids_from_chromadb
    else:
        existing_ids = get_indexed_book_ids(rag, reindex_before) if skip_existing or reindex_before else set()

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

        # Check if already indexed (skip or progress tracker)
        # BUT: Don't skip if reindex_before is set (force reindex mode)
        if safe_indexer and safe_indexer.is_book_indexed(book_id, phase) and not reindex_before:
            print(f"         ⏭️  SKIPPED (already indexed in {phase})")
            stats['skipped'] += 1
            if safe_indexer:
                safe_indexer.record_book(book_id, phase, 'skipped')
            continue
        elif skip_existing and book_id in existing_ids and not reindex_before:
            print(f"         ⏭️  SKIPPED (already indexed)")
            stats['skipped'] += 1
            stats['books_processed'].append({
                'id': book_id,
                'title': book['title'],
                'status': 'skipped',
                'reason': 'already indexed'
            })
            if safe_indexer:
                safe_indexer.record_book(book_id, phase, 'skipped')
            continue

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
            # Use force=True when re-indexing old books
            force_reindex = reindex_before is not None
            result = rag.index_book(file_path, book_id, force=force_reindex, phase=phase)
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

Profiles:
  minimal  - CPU-only, resource-efficient (laptops, <6GB VRAM)
  balanced - GPU-accelerated, good quality (6-12GB VRAM)
  maximal  - Full GPU, maximum quality (>12GB VRAM)
        """
    )

    # Selection criteria (mutually exclusive, but not required if using --retry-failed or --list-failed)
    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument('--all', action='store_true',
                       help='Index ALL books in the library (no tag/author filter required)')
    group.add_argument('--tag', help='Index books with this tag')
    group.add_argument('--author', help='Index books by this author (partial match)')

    # Options
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be indexed without actually indexing')
    parser.add_argument('--skip-existing', action='store_true',
                        help='Skip books that are already in the index')
    parser.add_argument('--reindex-before', metavar='DATE',
                        help='Re-index books indexed before this date (YYYY-MM-DD). '
                             'Useful for re-indexing old books with improved code.')
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
    parser.add_argument('--profile', choices=['minimal', 'balanced', 'maximal'],
                        help='Hardware profile to use (auto-detects if not specified)')
    parser.add_argument('--show-profiles', action='store_true',
                        help='Show available profiles and exit')
    parser.add_argument('--retry-failed', action='store_true',
                        help='Retry only previously failed books (ignores --tag/--author/--all)')
    parser.add_argument('--list-failed', action='store_true',
                        help='List all failed books and exit')

    args = parser.parse_args()

    # Validate: need at least one selection criteria unless using special modes
    if not (args.all or args.tag or args.author or args.retry_failed or args.list_failed or args.show_profiles):
        parser.error('one of the arguments --all --tag --author --retry-failed --list-failed --show-profiles is required')

    # Handle --show-profiles
    if args.show_profiles:
        list_profiles()
        sys.exit(0)

    # Handle --list-failed (list failed books and exit)
    if args.list_failed:
        library_path = get_calibre_library_path()
        db_path = args.db_path or str(library_path / ".archilles" / "rag_db")
        progress_db_path = Path(db_path).parent / "progress.db"

        if not progress_db_path.exists():
            print("No progress database found. No indexing has been done yet.")
            sys.exit(0)

        from scripts.progress_tracker import ProgressTracker
        tracker = ProgressTracker(progress_db_path)
        phase = 'phase1' if args.phase1_only else 'phase2'
        failed = tracker.get_failed_books(phase=phase)

        if not failed:
            print(f"No failed books found for {phase}.")
            sys.exit(0)

        print(f"\n{'='*70}")
        print(f"  FAILED BOOKS ({len(failed)} total)")
        print(f"{'='*70}")
        for i, book in enumerate(failed, 1):
            print(f"  [{i}] {book['book_id']}")
            print(f"      Error: {book['error'][:60]}...")
            print(f"      Phase: {book['phase']} | Session: {book['session_id']}")
            print()
        print(f"{'='*70}")
        print(f"\nTo retry failed books, run:")
        print(f"  python scripts/batch_index.py --retry-failed")
        sys.exit(0)

    # Handle --retry-failed (retry only failed books)
    if args.retry_failed:
        library_path = get_calibre_library_path()
        db_path = args.db_path or str(library_path / ".archilles" / "rag_db")
        progress_db_path = Path(db_path).parent / "progress.db"

        if not progress_db_path.exists():
            print("No progress database found. No indexing has been done yet.")
            sys.exit(0)

        from scripts.progress_tracker import ProgressTracker
        tracker = ProgressTracker(progress_db_path)
        phase = 'phase1' if args.phase1_only else 'phase2'
        failed = tracker.get_failed_books(phase=phase)

        if not failed:
            print(f"No failed books found for {phase}. Nothing to retry.")
            sys.exit(0)

        print(f"\n📋 Found {len(failed)} failed books to retry")

        # Get book IDs and clear their failed status
        failed_book_ids = [book['book_id'] for book in failed]
        tracker.clear_failed_status(failed_book_ids, phase=phase)

        # Now we need to find the actual book files
        # The book_id format is: AuthorLastName_ShortTitle_CalibreID
        # Extract Calibre IDs and get book info
        calibre_ids = []
        for book_id in failed_book_ids:
            parts = book_id.rsplit('_', 1)
            if len(parts) == 2:
                try:
                    calibre_ids.append(int(parts[1]))
                except ValueError:
                    print(f"  Warning: Could not extract Calibre ID from {book_id}")

        if not calibre_ids:
            print("Could not extract Calibre IDs from failed books.")
            sys.exit(1)

        # Get books by Calibre IDs
        books = get_books_by_calibre_ids(library_path, calibre_ids)
        if not books:
            print("Could not find books in library.")
            sys.exit(1)

        print(f"📚 Retrying {len(books)} books\n")

        # Continue with normal indexing flow using these books
        args.db_path = db_path
        # Fall through to normal indexing with 'books' already set
        # Skip the normal book selection below

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

    # Get books based on criteria (skip if --retry-failed already set books)
    if not args.retry_failed:
        if args.all:
            print(f"📚 Indexing ALL books in the library")
            books = get_all_books(library_path)
        elif args.tag:
            print(f"🏷️  Filtering by tag: {args.tag}")
            books = get_books_by_tag(library_path, args.tag)
        elif args.author:
            print(f"✍️  Filtering by author: {args.author}")
            books = get_books_by_author(library_path, args.author)

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

    # Check index compatibility with current profile
    if not args.dry_run and not args.reset_db:
        compat = check_index_compatibility(args.db_path, profile)
        if compat['existing_metadata']:
            print(f"\n📋 Existing index found (profile: {compat['existing_metadata'].profile_name})")
        if not compat['compatible']:
            print(f"\n{'='*60}")
            print(f"❌ INDEX INCOMPATIBILITY DETECTED")
            print(f"{'='*60}")
            for warning in compat['warnings']:
                print(f"  {warning}")
            print(f"\nTo fix, either:")
            print(f"  1. Use --profile {compat['existing_metadata'].profile_name} to match existing index")
            print(f"  2. Use --reset-db to start fresh with new profile (DELETES ALL DATA)")
            print(f"{'='*60}\n")
            sys.exit(1)
        elif compat['warnings']:
            print(f"\n⚠️  Compatibility notices:")
            for warning in compat['warnings']:
                print(f"    {warning}")
            print()

    # Initialize RAG (unless dry run with no skip-existing check needed)
    if args.dry_run and not args.skip_existing:
        # For pure dry run, create minimal object
        class DummyRAG:
            def __init__(self):
                self.collection = type('obj', (object,), {'count': lambda: 0})()
        rag = DummyRAG()
    else:
        try:
            rag = archillesRAG(db_path=args.db_path, reset_db=args.reset_db)

            # Save index metadata if this is a new index or reset
            existing_meta = load_index_metadata(args.db_path)
            if not existing_meta or args.reset_db:
                index_meta = create_index_metadata(profile, version="0.2.0")
                save_index_metadata(args.db_path, index_meta)
                print(f"📝 Saved index metadata (profile: {profile.name})")

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
            backup_interval=10,  # Backup every 10 books
            max_backups=5        # Keep 5 most recent backups
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
        log_file=log_file,
        safe_indexer=safe_indexer,
        phase=phase if safe_indexer else 'phase2'
    )

    # End session (if not dry run)
    if safe_indexer:
        status = 'completed' if not safe_indexer.should_shutdown() else 'interrupted'
        safe_indexer.end_session(status)

    # Exit with error code if any failures
    if stats['failed'] > 0:
        sys.exit(1)


if __name__ == '__main__':
    main()
