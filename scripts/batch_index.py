#!/usr/bin/env python3
"""
ARCHILLES Batch Indexer

Index multiple books from Calibre library by tag, author, or other criteria.

Usage:
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

from scripts.rag_demo import archillesRAG


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

    query = """
    SELECT
        books.id,
        books.title,
        books.path,
        authors.name as author
    FROM books
    INNER JOIN books_tags_link ON books.id = books_tags_link.book
    INNER JOIN tags ON books_tags_link.tag = tags.id
    LEFT JOIN books_authors_link ON books.id = books_authors_link.book
    LEFT JOIN authors ON books_authors_link.author = authors.id
    WHERE LOWER(tags.name) = LOWER(?)
    ORDER BY authors.name, books.title
    """

    cursor = conn.execute(query, (tag_name,))
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
            books.append({
                'id': row['id'],
                'title': row['title'],
                'author': row['author'] or 'Unknown',
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


def get_books_by_author(library_path: Path, author_name: str) -> List[Dict[str, Any]]:
    """
    Get all books by a specific author from Calibre database.

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

    query = """
    SELECT
        books.id,
        books.title,
        books.path,
        authors.name as author
    FROM books
    LEFT JOIN books_authors_link ON books.id = books_authors_link.book
    LEFT JOIN authors ON books_authors_link.author = authors.id
    WHERE LOWER(authors.name) LIKE LOWER(?)
    ORDER BY books.title
    """

    cursor = conn.execute(query, (f'%{author_name}%',))
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


def get_indexed_book_ids(rag: archillesRAG) -> set:
    """
    Get set of already indexed book IDs from RAG database.

    Returns:
        Set of book_id strings that are already in the index
    """
    try:
        # Get all metadata from collection
        all_data = rag.collection.get()

        # Extract unique book_ids
        book_ids = set()
        for metadata in all_data.get('metadatas', []):
            if metadata and 'book_id' in metadata:
                book_ids.add(metadata['book_id'])

        return book_ids
    except Exception as e:
        print(f"⚠️  Could not read existing index: {e}")
        return set()


def batch_index(
    books: List[Dict[str, Any]],
    rag: archillesRAG,
    dry_run: bool = False,
    skip_existing: bool = False,
    log_file: Optional[Path] = None
) -> Dict[str, Any]:
    """
    Index multiple books into the RAG database.

    Args:
        books: List of book dictionaries from get_books_by_tag/author
        rag: Initialized archillesRAG instance
        dry_run: If True, only show what would be indexed
        skip_existing: If True, skip books that are already indexed
        log_file: Optional path to write detailed log

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
    existing_ids = get_indexed_book_ids(rag) if skip_existing else set()

    print(f"\n{'='*60}")
    print(f"📚 ARCHILLES BATCH INDEXER")
    print(f"{'='*60}")
    print(f"  Books to process: {len(books)}")
    if skip_existing:
        print(f"  Already indexed: {len(existing_ids)}")
    print(f"  Mode: {'DRY RUN' if dry_run else 'INDEXING'}")
    print(f"{'='*60}\n")

    for i, book in enumerate(books, 1):
        book_id = create_book_id(book)
        file_path = book['best_format']['path']
        format_type = book['best_format']['format']

        # Progress header
        print(f"\n[{i}/{len(books)}] {book['author']}: {book['title']}")
        print(f"         Format: {format_type} | ID: {book_id}")

        # Check if already indexed
        if skip_existing and book_id in existing_ids:
            print(f"         ⏭️  SKIPPED (already indexed)")
            stats['skipped'] += 1
            stats['books_processed'].append({
                'id': book_id,
                'title': book['title'],
                'status': 'skipped',
                'reason': 'already indexed'
            })
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
            result = rag.index_book(file_path, book_id)
            elapsed = time.time() - start_time

            print(f"         ✅ Indexed {result['chunks_indexed']} chunks in {elapsed:.1f}s")

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
        """
    )

    # Selection criteria (mutually exclusive)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--tag', help='Index books with this tag')
    group.add_argument('--author', help='Index books by this author (partial match)')

    # Options
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be indexed without actually indexing')
    parser.add_argument('--skip-existing', action='store_true',
                        help='Skip books that are already in the index')
    parser.add_argument('--limit', type=int,
                        help='Limit number of books to index (for testing)')
    parser.add_argument('--log', metavar='FILE',
                        help='Write detailed log to JSON file')
    parser.add_argument('--db-path', default=None,
                        help='RAG database path (default: CALIBRE_LIBRARY/.archilles/rag_db)')

    args = parser.parse_args()

    # Get library path
    library_path = get_calibre_library_path()
    print(f"📚 Calibre library: {library_path}")

    # Get books based on criteria
    if args.tag:
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

    # Initialize RAG (unless dry run with no skip-existing check needed)
    if args.dry_run and not args.skip_existing:
        # For pure dry run, create minimal object
        class DummyRAG:
            def __init__(self):
                self.collection = type('obj', (object,), {'count': lambda: 0})()
        rag = DummyRAG()
    else:
        rag = archillesRAG(db_path=args.db_path)

    # Run batch indexing
    log_file = Path(args.log) if args.log else None
    stats = batch_index(
        books=books,
        rag=rag,
        dry_run=args.dry_run,
        skip_existing=args.skip_existing,
        log_file=log_file
    )

    # Exit with error code if any failures
    if stats['failed'] > 0:
        sys.exit(1)


if __name__ == '__main__':
    main()
