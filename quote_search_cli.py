#!/usr/bin/env python3
"""
Calibre Quote Tracker - CLI Interface
Search for quotes and passages in your Calibre library
"""

import argparse
import sys
from pathlib import Path
import sqlite3
from calibre_analyzer import CalibreAnalyzer
from text_extractor import CalibreTextExtractor
from search_engine import SearchEngine
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class QuoteSearchCLI:
    """
    Command-line interface for searching quotes in Calibre library
    """

    def __init__(self, calibre_library_path, search_index_path="quote_search_index.db"):
        """
        Initialize CLI

        Args:
            calibre_library_path: Path to Calibre library
            search_index_path: Path to search index database
        """
        self.library_path = Path(calibre_library_path)
        if not self.library_path.exists():
            raise FileNotFoundError(f"Calibre library not found: {calibre_library_path}")

        self.metadata_db = self.library_path / "metadata.db"
        if not self.metadata_db.exists():
            raise FileNotFoundError(f"Calibre metadata.db not found: {self.metadata_db}")

        self.search_index_path = search_index_path
        self.text_extractor = CalibreTextExtractor(calibre_library_path)

    def index_library(self, tag_filter=None, limit=None):
        """
        Index books from Calibre library

        Args:
            tag_filter: Optional tag to filter books
            limit: Optional limit on number of books to index
        """
        print("=" * 70)
        print("INDEXING CALIBRE LIBRARY")
        print("=" * 70)

        with CalibreAnalyzer(str(self.metadata_db)) as analyzer:
            # Get books to index
            if tag_filter:
                # Get books with specific tag
                query = """
                    SELECT DISTINCT books.id, books.title, authors.name as author
                    FROM books
                    JOIN books_authors_link ON books.id = books_authors_link.book
                    JOIN authors ON books_authors_link.author = authors.id
                    JOIN books_tags_link ON books.id = books_tags_link.book
                    JOIN tags ON books_tags_link.tag = tags.id
                    WHERE tags.name = ?
                """
                cursor = analyzer.conn.execute(query, (tag_filter,))
            else:
                # Get all books
                query = """
                    SELECT DISTINCT books.id, books.title, authors.name as author
                    FROM books
                    JOIN books_authors_link ON books.id = books_authors_link.book
                    JOIN authors ON books_authors_link.author = authors.id
                """
                if limit:
                    query += f" LIMIT {limit}"
                cursor = analyzer.conn.execute(query)

            books = cursor.fetchall()
            print(f"\nFound {len(books)} books to index")

            if not books:
                print("No books found!")
                return

        # Index books
        with SearchEngine(self.search_index_path) as engine:
            indexed_count = 0
            failed_count = 0

            for book in books:
                book_id = book['id']
                title = book['title']
                author = book['author']

                print(f"\n[{indexed_count + failed_count + 1}/{len(books)}] Processing: '{title}' by {author}")

                # Extract text
                text, format_used = self.text_extractor.extract_book_text(book_id, author, title)

                if text:
                    # Index the text
                    engine.index_book(book_id, author, title, format_used, text)
                    indexed_count += 1
                    print(f"  ✓ Indexed ({format_used}, {len(text):,} chars)")
                else:
                    failed_count += 1
                    print(f"  ✗ Failed to extract text")

            # Show summary
            print("\n" + "=" * 70)
            print("INDEXING COMPLETE")
            print("=" * 70)
            print(f"Successfully indexed: {indexed_count} books")
            print(f"Failed: {failed_count} books")
            print()

            # Show index stats
            stats = engine.get_stats()
            print("Index Statistics:")
            print(f"  Total books: {stats['total_books']}")
            print(f"  Total characters: {stats['total_characters']:,}")
            print(f"  Formats:")
            for fmt in stats['formats']:
                print(f"    - {fmt['format']}: {fmt['count']} books")
            print()

    def search(self, query, context_type='sentences', context_size=3, max_results=20):
        """
        Search for query in indexed library

        Args:
            query: Search query string
            context_type: 'sentences' or 'words'
            context_size: Number of sentences/words for context
            max_results: Maximum number of results to show
        """
        print("=" * 70)
        print(f"SEARCHING FOR: '{query}'")
        print("=" * 70)

        with SearchEngine(self.search_index_path) as engine:
            # Perform search
            results = engine.search(query, limit=max_results)

            if not results:
                print("\nNo results found.")
                return

            print(f"\nFound {len(results)} results:\n")

            # Display results with context
            for idx, result in enumerate(results, 1):
                print(f"\n{'─' * 70}")
                print(f"Result {idx}:")
                print(f"{'─' * 70}")
                print(f"Book: {result['title']}")
                print(f"Author: {result['author']}")
                print(f"Format: {result['format']}")
                print(f"Relevance: {abs(result['rank']):.2f}")
                print()

                # Get detailed context
                contexts = engine.get_context_around_match(
                    result['book_id'],
                    query,
                    context_type=context_type,
                    context_size=context_size
                )

                if contexts:
                    # Show first context (can be extended to show all)
                    context = contexts[0]['context']
                    # Convert <mark> tags to terminal highlighting
                    context_display = context.replace('<mark>', '\033[1;33m').replace('</mark>', '\033[0m')
                    print("Context:")
                    print(f"  {context_display}")
                else:
                    # Fallback to snippet
                    snippet = result['snippet']
                    snippet_display = snippet.replace('<mark>', '\033[1;33m').replace('</mark>', '\033[0m')
                    print("Snippet:")
                    print(f"  {snippet_display}")

            print("\n" + "=" * 70)

    def show_stats(self):
        """Display index statistics"""
        with SearchEngine(self.search_index_path) as engine:
            stats = engine.get_stats()

            print("=" * 70)
            print("INDEX STATISTICS")
            print("=" * 70)
            print(f"Total books indexed: {stats['total_books']}")
            print(f"Total characters: {stats['total_characters']:,}")
            print()
            print("Formats:")
            for fmt in stats['formats']:
                print(f"  - {fmt['format']}: {fmt['count']} books")
            print("=" * 70)

    def clear_index(self):
        """Clear the search index"""
        with SearchEngine(self.search_index_path) as engine:
            engine.clear_index()
            print("Search index cleared.")


def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(
        description='Calibre Quote Tracker - Search for quotes and passages in your library',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Index your entire library
  %(prog)s /path/to/Calibre-Library --index

  # Index only books with a specific tag
  %(prog)s ~/Calibre-Library --index --tag "Leit-Literatur"

  # Index limited number of books for testing
  %(prog)s ~/Calibre-Library --index --limit 10

  # Search for a quote
  %(prog)s ~/Calibre-Library --search "Josephus"

  # Search with word-based context (±200 words)
  %(prog)s ~/Calibre-Library --search "ancient Rome" --context-type words --context-size 200

  # Show index statistics
  %(prog)s ~/Calibre-Library --stats

  # Clear the index
  %(prog)s ~/Calibre-Library --clear
        """
    )

    parser.add_argument(
        'library',
        help='Path to Calibre library directory'
    )

    parser.add_argument(
        '--index',
        action='store_true',
        help='Index the library for searching'
    )

    parser.add_argument(
        '--search',
        type=str,
        help='Search query'
    )

    parser.add_argument(
        '--tag',
        type=str,
        help='Filter books by tag when indexing'
    )

    parser.add_argument(
        '--limit',
        type=int,
        help='Limit number of books to index (for testing)'
    )

    parser.add_argument(
        '--context-type',
        choices=['sentences', 'words'],
        default='sentences',
        help='Type of context extraction (default: sentences)'
    )

    parser.add_argument(
        '--context-size',
        type=int,
        default=3,
        help='Size of context (sentences or words) before/after match (default: 3)'
    )

    parser.add_argument(
        '--max-results',
        type=int,
        default=20,
        help='Maximum number of search results to show (default: 20)'
    )

    parser.add_argument(
        '--stats',
        action='store_true',
        help='Show index statistics'
    )

    parser.add_argument(
        '--clear',
        action='store_true',
        help='Clear the search index'
    )

    parser.add_argument(
        '--index-path',
        type=str,
        default='quote_search_index.db',
        help='Path to search index database (default: quote_search_index.db)'
    )

    args = parser.parse_args()

    try:
        cli = QuoteSearchCLI(args.library, args.index_path)

        if args.index:
            cli.index_library(tag_filter=args.tag, limit=args.limit)

        elif args.search:
            cli.search(
                args.search,
                context_type=args.context_type,
                context_size=args.context_size,
                max_results=args.max_results
            )

        elif args.stats:
            cli.show_stats()

        elif args.clear:
            cli.clear_index()

        else:
            parser.print_help()
            print("\nError: Please specify --index, --search, --stats, or --clear")
            sys.exit(1)

    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
