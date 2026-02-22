#!/usr/bin/env python3
"""
List all indexed books with timestamps

Shows when each book was indexed and how many chunks it has.
Useful for identifying old books that need re-indexing with improved code.

Usage:
    # List all indexed books
    python scripts/list_indexed_books.py

    # Export to CSV
    python scripts/list_indexed_books.py --output books.csv

    # Filter books indexed before a certain date
    python scripts/list_indexed_books.py --before 2024-12-01

    # Sort by date (oldest first)
    python scripts/list_indexed_books.py --sort-by date

    # Sort by chunks (largest first)
    python scripts/list_indexed_books.py --sort-by chunks
"""

import argparse
import csv
import os
import sys
from datetime import datetime
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.rag_demo import archillesRAG, ChromaDBCorruptionError


def get_indexed_books(rag: archillesRAG) -> list:
    """
    Get all indexed books with metadata and timestamps.

    Returns:
        List of book dictionaries with keys:
        book_id, title, author, chunks, indexed_at, format, tags, calibre_id
    """
    print("Analyzing indexed books...")

    indexed_books = rag.store.get_indexed_books()
    print(f"  Found {len(indexed_books)} books")

    total_chunks = sum(b.get('chunks', 0) for b in indexed_books)
    print(f"  Loaded {total_chunks} chunks")

    result = []
    for book in indexed_books:
        # Parse indexed_at timestamp
        indexed_at = None
        indexed_at_raw = book.get('indexed_at')
        if indexed_at_raw:
            try:
                indexed_at = (
                    datetime.fromisoformat(indexed_at_raw)
                    if isinstance(indexed_at_raw, str)
                    else indexed_at_raw
                )
            except (ValueError, AttributeError, TypeError):
                pass

        result.append({
            'book_id': book.get('book_id', 'unknown'),
            'title': book.get('title', 'Unknown'),
            'author': book.get('author', 'Unknown'),
            'chunks': book.get('chunks', 0),
            'indexed_at': indexed_at,
            'format': book.get('format', 'Unknown'),
            'tags': book.get('tags', ''),
            'calibre_id': book.get('calibre_id', ''),
        })

    return result


def format_date(dt):
    """Format datetime for display."""
    if dt is None:
        return 'Unknown'
    return dt.strftime('%Y-%m-%d %H:%M')


def print_books_table(books: list, before_date: datetime = None):
    """Print books in a formatted table."""
    # Filter by date if specified
    if before_date:
        books = [b for b in books if b['indexed_at'] and b['indexed_at'] < before_date]
        print(f"\nShowing books indexed before {before_date.strftime('%Y-%m-%d')}\n")

    if not books:
        print("No books found matching criteria")
        return

    print(f"\n{'='*110}")
    print(f"INDEXED BOOKS ({len(books)} total)")
    print(f"{'='*110}\n")

    # Table header
    print(f"{'Indexed At':<18} {'Chunks':<8} {'ID':<6} {'Author':<20} {'Title':<40}")
    print(f"{'-'*18} {'-'*8} {'-'*6} {'-'*20} {'-'*40}")

    # Table rows
    for book in books:
        date_str = format_date(book['indexed_at'])
        chunks_str = str(book['chunks'])
        calibre_id_str = (str(book['calibre_id']) if book['calibre_id'] else '-')[:5]
        author_str = (book['author'] or 'Unknown')[:19]
        title_str = (book['title'] or 'Unknown')[:39]

        print(f"{date_str:<18} {chunks_str:<8} {calibre_id_str:<6} {author_str:<20} {title_str:<40}")

    print(f"\n{'='*110}\n")

    # Summary statistics
    total_chunks = sum(b['chunks'] for b in books)
    print(f"Statistics:")
    print(f"  Total books: {len(books)}")
    print(f"  Total chunks: {total_chunks:,}")
    print(f"  Average chunks per book: {total_chunks // len(books) if books else 0}")

    # Date range
    dated_books = [b for b in books if b['indexed_at']]
    if dated_books:
        earliest = min(b['indexed_at'] for b in dated_books)
        latest = max(b['indexed_at'] for b in dated_books)
        print(f"  Earliest: {format_date(earliest)}")
        print(f"  Latest: {format_date(latest)}")

    print()


def export_to_csv(books: list, output_file: str):
    """Export books to CSV file."""
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'book_id', 'calibre_id', 'title', 'author', 'chunks', 'indexed_at', 'format', 'tags'
        ])
        writer.writeheader()

        for book in books:
            # Convert datetime to string for CSV
            book_copy = book.copy()
            if book_copy['indexed_at']:
                book_copy['indexed_at'] = book_copy['indexed_at'].isoformat()
            else:
                book_copy['indexed_at'] = ''
            writer.writerow(book_copy)

    print(f"Exported {len(books)} books to: {output_file}\n")


def main():
    parser = argparse.ArgumentParser(
        description="List all indexed books with timestamps",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List all indexed books
  python scripts/list_indexed_books.py

  # Show only books indexed before a certain date
  python scripts/list_indexed_books.py --before 2024-12-01

  # Sort by date (oldest first, for re-indexing old books)
  python scripts/list_indexed_books.py --sort-by date

  # Sort by number of chunks (largest books first)
  python scripts/list_indexed_books.py --sort-by chunks

  # Export to CSV for further analysis
  python scripts/list_indexed_books.py --output indexed_books.csv
        """
    )

    parser.add_argument('--db-path', default=None,
                        help='Database path (default: CALIBRE_LIBRARY/.archilles/rag_db)')
    parser.add_argument('--before', metavar='DATE',
                        help='Show only books indexed before this date (YYYY-MM-DD)')
    parser.add_argument('--sort-by', choices=['date', 'chunks', 'title', 'author'],
                        default='date',
                        help='Sort by field (default: date)')
    parser.add_argument('--output', metavar='FILE',
                        help='Export to CSV file')

    args = parser.parse_args()

    # Determine default database path if not specified
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

    # Parse before date if specified
    before_date = None
    if args.before:
        try:
            before_date = datetime.strptime(args.before, '%Y-%m-%d')
        except ValueError:
            print(f"ERROR: Invalid date format: {args.before}")
            print("   Use YYYY-MM-DD format (e.g., 2024-12-01)")
            sys.exit(1)

    try:
        # Initialize RAG
        rag = archillesRAG(db_path=args.db_path)

        # Get all indexed books
        books = get_indexed_books(rag)

        # Sort books
        sort_keys = {
            'date': (lambda b: b['indexed_at'] or datetime.max, False),
            'chunks': (lambda b: b['chunks'], True),
            'title': (lambda b: (b['title'] or 'Unknown').lower(), False),
            'author': (lambda b: (b['author'] or 'Unknown').lower(), False),
        }
        key_fn, reverse = sort_keys[args.sort_by]
        books.sort(key=key_fn, reverse=reverse)

        # Export to CSV if requested
        if args.output:
            export_to_csv(books, args.output)

        # Print table
        print_books_table(books, before_date)

    except ChromaDBCorruptionError as e:
        print(f"\n{'='*60}")
        print(f"DATABASE CORRUPTION DETECTED")
        print(f"{'='*60}\n")
        print(str(e))
        print(f"\n{'='*60}\n")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
