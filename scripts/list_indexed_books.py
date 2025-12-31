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

import sys
import argparse
import os
from pathlib import Path
from datetime import datetime
from collections import defaultdict
import csv

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.rag_demo import archillesRAG, ChromaDBCorruptionError


def get_indexed_books(rag: archillesRAG) -> dict:
    """
    Get all indexed books with metadata and timestamps.

    Returns:
        Dictionary mapping book_id to book info:
        {
            'book_id': str,
            'title': str,
            'author': str,
            'chunks': int,
            'indexed_at': datetime,
            'format': str,
            'tags': str
        }
    """
    print("📊 Analyzing indexed books...")

    # Fetch all data in batches to avoid SQLite variable limit
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

    print(f"  Loaded {len(all_metadatas)} chunks")

    # Group by book_id
    books = defaultdict(lambda: {
        'chunks': 0,
        'indexed_at': None,
        'title': None,
        'author': None,
        'format': None,
        'tags': None
    })

    for metadata in all_metadatas:
        book_id = metadata.get('book_id', 'unknown')

        # Count chunks
        books[book_id]['chunks'] += 1

        # Get earliest indexing timestamp for this book
        indexed_at_str = metadata.get('indexed_at')
        if indexed_at_str:
            try:
                indexed_at = datetime.fromisoformat(indexed_at_str)
                if books[book_id]['indexed_at'] is None or indexed_at < books[book_id]['indexed_at']:
                    books[book_id]['indexed_at'] = indexed_at
            except (ValueError, AttributeError):
                pass

        # Get book metadata (same for all chunks of a book)
        if not books[book_id]['title']:
            books[book_id]['title'] = metadata.get('book_title', 'Unknown')
        if not books[book_id]['author']:
            books[book_id]['author'] = metadata.get('author', 'Unknown')
        if not books[book_id]['format']:
            books[book_id]['format'] = metadata.get('format', 'Unknown')
        if not books[book_id]['tags']:
            books[book_id]['tags'] = metadata.get('tags', '')

    # Convert to list of dicts
    result = []
    for book_id, info in books.items():
        result.append({
            'book_id': book_id,
            'title': info['title'],
            'author': info['author'],
            'chunks': info['chunks'],
            'indexed_at': info['indexed_at'],
            'format': info['format'],
            'tags': info['tags']
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
        print(f"\n📅 Showing books indexed before {before_date.strftime('%Y-%m-%d')}\n")

    if not books:
        print("❌ No books found matching criteria")
        return

    print(f"\n{'='*100}")
    print(f"📚 INDEXED BOOKS ({len(books)} total)")
    print(f"{'='*100}\n")

    # Table header
    print(f"{'Indexed At':<18} {'Chunks':<8} {'Author':<20} {'Title':<40}")
    print(f"{'-'*18} {'-'*8} {'-'*20} {'-'*40}")

    # Table rows
    for book in books:
        date_str = format_date(book['indexed_at'])
        chunks_str = str(book['chunks'])
        author_str = (book['author'] or 'Unknown')[:19]
        title_str = (book['title'] or 'Unknown')[:39]

        print(f"{date_str:<18} {chunks_str:<8} {author_str:<20} {title_str:<40}")

    print(f"\n{'='*100}\n")

    # Summary statistics
    total_chunks = sum(b['chunks'] for b in books)
    print(f"📊 Statistics:")
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
            'book_id', 'title', 'author', 'chunks', 'indexed_at', 'format', 'tags'
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

    print(f"📝 Exported {len(books)} books to: {output_file}\n")


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
            print(f"❌ Invalid date format: {args.before}")
            print("   Use YYYY-MM-DD format (e.g., 2024-12-01)")
            sys.exit(1)

    try:
        # Initialize RAG
        rag = archillesRAG(db_path=args.db_path)

        # Get all indexed books
        books = get_indexed_books(rag)

        # Sort books
        if args.sort_by == 'date':
            # Sort by date, oldest first (put None dates at end)
            books.sort(key=lambda b: b['indexed_at'] or datetime.max)
        elif args.sort_by == 'chunks':
            books.sort(key=lambda b: b['chunks'], reverse=True)
        elif args.sort_by == 'title':
            books.sort(key=lambda b: (b['title'] or 'Unknown').lower())
        elif args.sort_by == 'author':
            books.sort(key=lambda b: (b['author'] or 'Unknown').lower())

        # Export to CSV if requested
        if args.output:
            export_to_csv(books, args.output)

        # Print table
        print_books_table(books, before_date)

    except ChromaDBCorruptionError as e:
        print(f"\n{'='*60}")
        print(f"❌ DATABASE CORRUPTION DETECTED")
        print(f"{'='*60}\n")
        print(str(e))
        print(f"\n{'='*60}\n")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
