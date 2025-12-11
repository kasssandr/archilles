#!/usr/bin/env python3
"""
Calibre Metadata Analyzer
A tool to analyze and evaluate Calibre library metadata.
"""

import sqlite3
import argparse
import sys
from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime
import json


class CalibreAnalyzer:
    """Analyzes Calibre library metadata from metadata.db"""

    def __init__(self, db_path):
        """
        Initialize the analyzer with the path to Calibre's metadata.db

        Args:
            db_path: Path to the metadata.db file
        """
        self.db_path = Path(db_path)
        if not self.db_path.exists():
            raise FileNotFoundError(f"Database file not found: {db_path}")

        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.conn.close()

    def get_total_books(self):
        """Get total number of books in the library"""
        cursor = self.conn.execute("SELECT COUNT(*) as count FROM books")
        return cursor.fetchone()['count']

    def get_authors_stats(self):
        """Get statistics about authors"""
        query = """
        SELECT authors.name, COUNT(books.id) as book_count
        FROM authors
        JOIN books_authors_link ON authors.id = books_authors_link.author
        JOIN books ON books_authors_link.book = books.id
        GROUP BY authors.id
        ORDER BY book_count DESC
        """
        cursor = self.conn.execute(query)
        return [dict(row) for row in cursor.fetchall()]

    def get_publishers_stats(self):
        """Get statistics about publishers"""
        query = """
        SELECT publishers.name, COUNT(books.id) as book_count
        FROM publishers
        JOIN books_publishers_link ON publishers.id = books_publishers_link.publisher
        JOIN books ON books_publishers_link.book = books.id
        GROUP BY publishers.id
        ORDER BY book_count DESC
        """
        cursor = self.conn.execute(query)
        return [dict(row) for row in cursor.fetchall()]

    def get_tags_stats(self):
        """Get statistics about tags/genres"""
        query = """
        SELECT tags.name, COUNT(books.id) as book_count
        FROM tags
        JOIN books_tags_link ON tags.id = books_tags_link.tag
        JOIN books ON books_tags_link.book = books.id
        GROUP BY tags.id
        ORDER BY book_count DESC
        """
        cursor = self.conn.execute(query)
        return [dict(row) for row in cursor.fetchall()]

    def get_languages_stats(self):
        """Get statistics about languages"""
        query = """
        SELECT languages.lang_code, COUNT(books.id) as book_count
        FROM languages
        JOIN books_languages_link ON languages.id = books_languages_link.lang_code
        JOIN books ON books_languages_link.book = books.id
        GROUP BY languages.id
        ORDER BY book_count DESC
        """
        cursor = self.conn.execute(query)
        return [dict(row) for row in cursor.fetchall()]

    def get_series_stats(self):
        """Get statistics about series"""
        query = """
        SELECT series.name, COUNT(books.id) as book_count
        FROM series
        JOIN books_series_link ON series.id = books_series_link.series
        JOIN books ON books_series_link.book = books.id
        GROUP BY series.id
        ORDER BY book_count DESC
        """
        cursor = self.conn.execute(query)
        return [dict(row) for row in cursor.fetchall()]

    def get_ratings_distribution(self):
        """Get distribution of ratings"""
        query = """
        SELECT ratings.rating / 2.0 as rating_stars, COUNT(books.id) as book_count
        FROM ratings
        JOIN books_ratings_link ON ratings.id = books_ratings_link.rating
        JOIN books ON books_ratings_link.book = books.id
        GROUP BY ratings.rating
        ORDER BY ratings.rating DESC
        """
        cursor = self.conn.execute(query)
        return [dict(row) for row in cursor.fetchall()]

    def get_publication_years(self):
        """Get distribution of publication years"""
        query = """
        SELECT strftime('%Y', pubdate) as year, COUNT(*) as book_count
        FROM books
        WHERE pubdate IS NOT NULL AND pubdate != ''
        GROUP BY year
        ORDER BY year DESC
        """
        cursor = self.conn.execute(query)
        return [dict(row) for row in cursor.fetchall()]

    def get_format_stats(self):
        """Get statistics about file formats"""
        query = """
        SELECT format, COUNT(*) as count
        FROM data
        GROUP BY format
        ORDER BY count DESC
        """
        cursor = self.conn.execute(query)
        return [dict(row) for row in cursor.fetchall()]

    def get_books_without_metadata(self):
        """Find books with missing metadata"""
        query = """
        SELECT
            books.id,
            books.title,
            CASE WHEN NOT EXISTS (
                SELECT 1 FROM books_authors_link WHERE book = books.id
            ) THEN 1 ELSE 0 END as missing_author,
            CASE WHEN NOT EXISTS (
                SELECT 1 FROM books_tags_link WHERE book = books.id
            ) THEN 1 ELSE 0 END as missing_tags,
            CASE WHEN NOT EXISTS (
                SELECT 1 FROM books_publishers_link WHERE book = books.id
            ) THEN 1 ELSE 0 END as missing_publisher,
            CASE WHEN books.pubdate IS NULL OR books.pubdate = ''
                THEN 1 ELSE 0 END as missing_pubdate
        FROM books
        """
        cursor = self.conn.execute(query)
        results = []
        for row in cursor.fetchall():
            row_dict = dict(row)
            missing_fields = []
            if row_dict['missing_author']:
                missing_fields.append('author')
            if row_dict['missing_tags']:
                missing_fields.append('tags')
            if row_dict['missing_publisher']:
                missing_fields.append('publisher')
            if row_dict['missing_pubdate']:
                missing_fields.append('publication_date')

            if missing_fields:
                results.append({
                    'id': row_dict['id'],
                    'title': row_dict['title'],
                    'missing_fields': missing_fields
                })
        return results

    def get_complete_analysis(self):
        """Get complete analysis of the library"""
        return {
            'total_books': self.get_total_books(),
            'authors': self.get_authors_stats(),
            'publishers': self.get_publishers_stats(),
            'tags': self.get_tags_stats(),
            'languages': self.get_languages_stats(),
            'series': self.get_series_stats(),
            'ratings': self.get_ratings_distribution(),
            'publication_years': self.get_publication_years(),
            'formats': self.get_format_stats(),
            'incomplete_metadata': self.get_books_without_metadata()
        }

    def print_summary(self):
        """Print a human-readable summary of the library"""
        analysis = self.get_complete_analysis()

        print("=" * 60)
        print("CALIBRE LIBRARY ANALYSIS")
        print("=" * 60)
        print()

        print(f"📚 Total Books: {analysis['total_books']}")
        print()

        # Authors
        print("👥 Top 10 Authors:")
        for author in analysis['authors'][:10]:
            print(f"  • {author['name']}: {author['book_count']} books")
        if len(analysis['authors']) > 10:
            print(f"  ... and {len(analysis['authors']) - 10} more authors")
        print()

        # Publishers
        if analysis['publishers']:
            print("🏢 Top 10 Publishers:")
            for pub in analysis['publishers'][:10]:
                print(f"  • {pub['name']}: {pub['book_count']} books")
            if len(analysis['publishers']) > 10:
                print(f"  ... and {len(analysis['publishers']) - 10} more publishers")
            print()

        # Tags
        if analysis['tags']:
            print("🏷️  Top 10 Tags:")
            for tag in analysis['tags'][:10]:
                print(f"  • {tag['name']}: {tag['book_count']} books")
            if len(analysis['tags']) > 10:
                print(f"  ... and {len(analysis['tags']) - 10} more tags")
            print()

        # Languages
        if analysis['languages']:
            print("🌍 Languages:")
            for lang in analysis['languages']:
                print(f"  • {lang['lang_code']}: {lang['book_count']} books")
            print()

        # Series
        if analysis['series']:
            print(f"📖 Series: {len(analysis['series'])} series found")
            print("  Top 5 series:")
            for series in analysis['series'][:5]:
                print(f"  • {series['name']}: {series['book_count']} books")
            print()

        # Ratings
        if analysis['ratings']:
            print("⭐ Ratings Distribution:")
            for rating in analysis['ratings']:
                stars = '★' * int(rating['rating_stars'])
                print(f"  {stars} ({rating['rating_stars']:.1f}): {rating['book_count']} books")
            print()

        # Publication years
        if analysis['publication_years']:
            print("📅 Publication Years:")
            print(f"  Most recent: {analysis['publication_years'][0]['year']} ({analysis['publication_years'][0]['book_count']} books)")
            print(f"  Oldest: {analysis['publication_years'][-1]['year']} ({analysis['publication_years'][-1]['book_count']} books)")
            print()

        # Formats
        if analysis['formats']:
            print("📄 File Formats:")
            for fmt in analysis['formats']:
                print(f"  • {fmt['format']}: {fmt['count']} files")
            print()

        # Incomplete metadata
        if analysis['incomplete_metadata']:
            print(f"⚠️  Books with Incomplete Metadata: {len(analysis['incomplete_metadata'])}")
            print("  Examples:")
            for book in analysis['incomplete_metadata'][:5]:
                missing = ', '.join(book['missing_fields'])
                print(f"  • '{book['title']}' missing: {missing}")
            if len(analysis['incomplete_metadata']) > 5:
                print(f"  ... and {len(analysis['incomplete_metadata']) - 5} more")
            print()

        print("=" * 60)


def main():
    """Main entry point for the CLI"""
    parser = argparse.ArgumentParser(
        description='Analyze Calibre library metadata',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s /path/to/Calibre/metadata.db
  %(prog)s ~/Calibre\ Library/metadata.db --output json
  %(prog)s metadata.db --format json > analysis.json
        """
    )

    parser.add_argument(
        'database',
        help='Path to Calibre metadata.db file'
    )

    parser.add_argument(
        '-o', '--output',
        choices=['summary', 'json'],
        default='summary',
        help='Output format (default: summary)'
    )

    parser.add_argument(
        '-f', '--filter',
        choices=['authors', 'publishers', 'tags', 'languages', 'series',
                 'ratings', 'years', 'formats', 'incomplete'],
        help='Show only specific statistics'
    )

    args = parser.parse_args()

    try:
        with CalibreAnalyzer(args.database) as analyzer:
            if args.output == 'json':
                if args.filter:
                    # Get only specific data
                    method_map = {
                        'authors': analyzer.get_authors_stats,
                        'publishers': analyzer.get_publishers_stats,
                        'tags': analyzer.get_tags_stats,
                        'languages': analyzer.get_languages_stats,
                        'series': analyzer.get_series_stats,
                        'ratings': analyzer.get_ratings_distribution,
                        'years': analyzer.get_publication_years,
                        'formats': analyzer.get_format_stats,
                        'incomplete': analyzer.get_books_without_metadata
                    }
                    data = method_map[args.filter]()
                else:
                    data = analyzer.get_complete_analysis()
                print(json.dumps(data, indent=2, ensure_ascii=False))
            else:
                analyzer.print_summary()

    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except sqlite3.DatabaseError as e:
        print(f"Database error: {e}", file=sys.stderr)
        print("Make sure the file is a valid Calibre metadata database.", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
