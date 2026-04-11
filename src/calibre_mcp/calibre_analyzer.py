#!/usr/bin/env python3
"""
Calibre Metadata Analyzer
A tool to analyze and evaluate Calibre library metadata.
"""

import argparse
import json
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

_RE_NON_WORD = re.compile(r'[^\w\s]')
_RE_WHITESPACE = re.compile(r'\s+')


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

    def get_book_details(self, book_id):
        """Get detailed information about a specific book."""
        results = self._get_books_batch([book_id])
        return results.get(book_id)

    def _get_books_batch(self, book_ids: list[int]) -> dict[int, dict]:
        """Fetch full details for multiple books in 5 queries (not 4×N).

        Returns a dict mapping book_id → details dict.
        """
        if not book_ids:
            return {}

        placeholders = ",".join("?" * len(book_ids))

        # 1. Basic info
        cursor = self.conn.execute(
            f"SELECT id, title, pubdate, path, has_cover FROM books WHERE id IN ({placeholders})",
            book_ids,
        )
        books: dict[int, dict] = {}
        for row in cursor.fetchall():
            d = dict(row)
            d["authors"] = []
            d["tags"] = []
            d["identifiers"] = {}
            d["formats"] = []
            books[d["id"]] = d

        if not books:
            return {}

        # 2. Authors
        cursor = self.conn.execute(
            f"""SELECT bal.book, a.name
                FROM authors a
                JOIN books_authors_link bal ON a.id = bal.author
                WHERE bal.book IN ({placeholders})
                ORDER BY bal.book, bal.id""",
            book_ids,
        )
        for row in cursor.fetchall():
            if row["book"] in books:
                books[row["book"]]["authors"].append(row["name"])

        # 3. Tags
        cursor = self.conn.execute(
            f"""SELECT btl.book, t.name
                FROM tags t
                JOIN books_tags_link btl ON t.id = btl.tag
                WHERE btl.book IN ({placeholders})""",
            book_ids,
        )
        for row in cursor.fetchall():
            if row["book"] in books:
                books[row["book"]]["tags"].append(row["name"])

        # 4. Identifiers
        cursor = self.conn.execute(
            f"SELECT book, type, val FROM identifiers WHERE book IN ({placeholders})",
            book_ids,
        )
        for row in cursor.fetchall():
            if row["book"] in books:
                books[row["book"]]["identifiers"][row["type"]] = row["val"]

        # 5. Formats
        cursor = self.conn.execute(
            f"SELECT book, format FROM data WHERE book IN ({placeholders})",
            book_ids,
        )
        for row in cursor.fetchall():
            if row["book"] in books:
                books[row["book"]]["formats"].append(row["format"])

        return books

    def _get_publishers_batch(self, book_ids: list[int]) -> dict[int, str]:
        """Fetch publisher names for multiple books in one query."""
        if not book_ids:
            return {}
        placeholders = ",".join("?" * len(book_ids))
        cursor = self.conn.execute(
            f"""SELECT bpl.book, p.name
                FROM publishers p
                JOIN books_publishers_link bpl ON p.id = bpl.publisher
                WHERE bpl.book IN ({placeholders})""",
            book_ids,
        )
        return {row["book"]: row["name"] for row in cursor.fetchall()}

    def normalize_title(self, title):
        """Normalize title for comparison (remove articles, punctuation, lowercase)."""
        if not title:
            return ""

        title = title.lower()

        articles = ['the ', 'a ', 'an ', 'der ', 'die ', 'das ', 'ein ', 'eine ',
                    'le ', 'la ', 'les ', 'un ', 'une ', 'el ', 'la ', 'los ', 'las ']
        for article in articles:
            if title.startswith(article):
                title = title[len(article):]

        title = _RE_NON_WORD.sub('', title)
        title = _RE_WHITESPACE.sub(' ', title).strip()
        return title

    def detect_duplicates(self, method='title_author', include_doublette_tag=True,
                         similarity_threshold=0.9):
        """
        Detect duplicate books in the library.

        Args:
            method: Detection method - 'title_author', 'isbn', 'exact_title', or 'fuzzy'
            include_doublette_tag: If True, also show books tagged with "Doublette"
            similarity_threshold: Threshold for fuzzy matching (0.0-1.0)

        Returns:
            Dictionary with duplicate groups and statistics
        """
        duplicates = []

        # Collect all book_ids first, then batch-fetch details once
        groups: list[tuple[str, str, list[int]]] = []  # (match_type, match_value, ids)

        if method == 'isbn':
            query = """
            SELECT i1.book as book1, i2.book as book2, i1.val as isbn
            FROM identifiers i1
            JOIN identifiers i2 ON i1.val = i2.val AND i1.type = i2.type
            WHERE i1.book < i2.book
            AND i1.type IN ('isbn', 'isbn13', 'isbn10')
            """
            cursor = self.conn.execute(query)
            isbn_map = defaultdict(set)
            for row in cursor.fetchall():
                isbn_map[row['isbn']].update([row['book1'], row['book2']])
            for isbn, ids in isbn_map.items():
                if len(ids) > 1:
                    groups.append(('isbn', isbn, sorted(ids)))

        elif method == 'exact_title':
            query = """
            SELECT title, GROUP_CONCAT(id) as book_ids
            FROM books
            GROUP BY LOWER(title)
            HAVING COUNT(*) > 1
            """
            cursor = self.conn.execute(query)
            for row in cursor.fetchall():
                ids = [int(x) for x in row['book_ids'].split(',')]
                groups.append(('exact_title', row['title'], ids))

        elif method == 'title_author':
            query = """
            SELECT
                b.id,
                b.title,
                GROUP_CONCAT(a.name, '|') as authors
            FROM books b
            LEFT JOIN books_authors_link bal ON b.id = bal.book
            LEFT JOIN authors a ON bal.author = a.id
            GROUP BY b.id
            """
            cursor = self.conn.execute(query)
            title_author_map = defaultdict(list)
            for row in cursor.fetchall():
                normalized_title = self.normalize_title(row['title'])
                authors = row['authors'] if row['authors'] else ''
                author_list = sorted([a.strip().lower() for a in authors.split('|')])
                key = (normalized_title, tuple(author_list))
                title_author_map[key].append(row['id'])
            for (norm_title, authors), ids in title_author_map.items():
                if len(ids) > 1:
                    groups.append(('title_author', f"{norm_title} by {', '.join(authors)}", ids))

        # Doublette-tagged books
        doublette_ids: list[int] = []
        if include_doublette_tag:
            query = """
            SELECT b.id
            FROM books b
            JOIN books_tags_link btl ON b.id = btl.book
            JOIN tags t ON btl.tag = t.id
            WHERE LOWER(t.name) = 'doublette'
            """
            cursor = self.conn.execute(query)
            doublette_ids = [row['id'] for row in cursor.fetchall()]

        # Single batch fetch for ALL referenced book_ids
        all_ids = set(doublette_ids)
        for _, _, ids in groups:
            all_ids.update(ids)
        details = self._get_books_batch(sorted(all_ids))

        # Build result
        duplicates = []
        for match_type, match_value, ids in groups:
            books = [details[bid] for bid in ids if bid in details]
            duplicates.append({
                'match_type': match_type,
                'match_value': match_value,
                'books': books,
                'count': len(books),
            })

        doublette_books = [details[bid] for bid in doublette_ids if bid in details]

        return {
            'method': method,
            'duplicate_groups': duplicates,
            'total_duplicate_groups': len(duplicates),
            'total_duplicate_books': sum(d['count'] for d in duplicates),
            'doublette_tagged_books': doublette_books,
            'doublette_count': len(doublette_books),
        }

    def add_doublette_tag(self, book_id):
        """
        Add the 'Doublette' tag to a book.

        Note: This is a read-only operation in this implementation.
        To actually modify the database, use Calibre's calibredb command:
        calibredb set_metadata <book_id> --field tags:+Doublette

        Args:
            book_id: ID of the book to tag

        Returns:
            Dictionary with instructions for manual tagging
        """
        book = self.get_book_details(book_id)
        if not book:
            return {'error': f'Book with ID {book_id} not found'}

        return {
            'book_id': book_id,
            'title': book['title'],
            'authors': book['authors'],
            'current_tags': book['tags'],
            'instruction': f'To add "Doublette" tag, run: calibredb set_metadata {book_id} --field tags:"+Doublette"'
        }

    def export_bibliography(self, format='bibtex', author=None, tag=None,
                           year_from=None, year_to=None, max_books=None):
        """
        Export bibliography in various formats.

        Args:
            format: Export format - 'bibtex', 'ris', 'endnote', 'json', 'csv'
            author: Filter by author name (case-insensitive partial match)
            tag: Filter by tag name (case-insensitive partial match)
            year_from: Filter books published from this year
            year_to: Filter books published up to this year
            max_books: Maximum number of books to export

        Returns:
            Dictionary with exported data and metadata
        """
        # Build query with filters
        query = """
        SELECT DISTINCT
            b.id,
            b.title,
            b.pubdate,
            b.path,
            b.isbn
        FROM books b
        """

        conditions = []
        params = []

        # Add author filter
        if author:
            query += """
            JOIN books_authors_link bal ON b.id = bal.book
            JOIN authors a ON bal.author = a.id
            """
            conditions.append("LOWER(a.name) LIKE ?")
            params.append(f"%{author.lower()}%")

        # Add tag filter
        if tag:
            query += """
            JOIN books_tags_link btl ON b.id = btl.book
            JOIN tags t ON btl.tag = t.id
            """
            conditions.append("LOWER(t.name) LIKE ?")
            params.append(f"%{tag.lower()}%")

        # Add year filters
        if year_from:
            conditions.append("strftime('%Y', b.pubdate) >= ?")
            params.append(str(year_from))

        if year_to:
            conditions.append("strftime('%Y', b.pubdate) <= ?")
            params.append(str(year_to))

        # Combine conditions
        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        # Add limit
        if max_books:
            query += f" LIMIT {int(max_books)}"

        cursor = self.conn.execute(query, params)
        book_ids = [row['id'] for row in cursor.fetchall()]

        # Batch fetch details + publishers for all matched books
        details = self._get_books_batch(book_ids)
        publishers = self._get_publishers_batch(book_ids)
        books = [details[bid] for bid in book_ids if bid in details]

        exporters = {
            'bibtex': self._export_bibtex,
            'ris': self._export_ris,
            'endnote': self._export_endnote,
            'json': lambda b, _p: json.dumps(b, indent=2, ensure_ascii=False),
            'csv': self._export_csv,
        }

        exporter = exporters.get(format)
        if not exporter:
            return {'error': f'Unsupported format: {format}'}

        exported = exporter(books, publishers)

        return {
            'format': format,
            'book_count': len(books),
            'filters': {
                'author': author,
                'tag': tag,
                'year_from': year_from,
                'year_to': year_to
            },
            'data': exported
        }

    def _export_bibtex(self, books, publishers: dict[int, str]):
        """Export books in BibTeX format"""
        entries = []

        for book in books:
            author_part = book['authors'][0].split()[-1] if book['authors'] else 'Unknown'
            year_part = book['pubdate'][:4] if book['pubdate'] else 'NODATE'
            title_part = ''.join(c for c in book['title'][:20] if c.isalnum())
            cite_key = f"{author_part}{year_part}{title_part}"

            entry = f"@book{{{cite_key},\n"
            entry += f"  title = {{{book['title']}}},\n"

            if book['authors']:
                authors = ' and '.join(book['authors'])
                entry += f"  author = {{{authors}}},\n"

            if book['pubdate']:
                entry += f"  year = {{{book['pubdate'][:4]}}},\n"

            publisher = publishers.get(book['id'], '')
            if publisher:
                entry += f"  publisher = {{{publisher}}},\n"

            if book['identifiers'].get('isbn'):
                entry += f"  isbn = {{{book['identifiers']['isbn']}}},\n"

            if book['tags']:
                keywords = ', '.join(book['tags'])
                entry += f"  keywords = {{{keywords}}},\n"

            entry += "}\n"
            entries.append(entry)

        return '\n'.join(entries)

    def _export_ris(self, books, publishers: dict[int, str]):
        """Export books in RIS format"""
        entries = []

        for book in books:
            entry = "TY  - BOOK\n"
            entry += f"TI  - {book['title']}\n"

            for author in book['authors']:
                entry += f"AU  - {author}\n"

            if book['pubdate']:
                entry += f"PY  - {book['pubdate'][:4]}\n"

            publisher = publishers.get(book['id'], '')
            if publisher:
                entry += f"PB  - {publisher}\n"

            if book['identifiers'].get('isbn'):
                entry += f"SN  - {book['identifiers']['isbn']}\n"

            for tag in book['tags']:
                entry += f"KW  - {tag}\n"

            entry += "ER  - \n"
            entries.append(entry)

        return '\n'.join(entries)

    def _export_endnote(self, books, publishers: dict[int, str]):
        """Export books in EndNote format"""
        entries = []

        for book in books:
            entry = "%0 Book\n"
            entry += f"%T {book['title']}\n"

            for author in book['authors']:
                entry += f"%A {author}\n"

            if book['pubdate']:
                entry += f"%D {book['pubdate'][:4]}\n"

            publisher = publishers.get(book['id'], '')
            if publisher:
                entry += f"%I {publisher}\n"

            if book['identifiers'].get('isbn'):
                entry += f"%@ {book['identifiers']['isbn']}\n"

            for tag in book['tags']:
                entry += f"%K {tag}\n"

            entries.append(entry)

        return '\n'.join(entries)

    def _export_csv(self, books, publishers: dict[int, str]):
        """Export books in CSV format"""
        import csv
        from io import StringIO

        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(['ID', 'Title', 'Authors', 'Year', 'Publisher', 'ISBN', 'Tags', 'Formats'])

        for book in books:
            writer.writerow([
                book['id'],
                book['title'],
                '; '.join(book['authors']),
                book['pubdate'][:4] if book['pubdate'] else '',
                publishers.get(book['id'], ''),
                book['identifiers'].get('isbn', ''),
                '; '.join(book['tags']),
                '; '.join(book['formats'])
            ])

        return output.getvalue()

    def list_books_by_author(self, author, tags=None, year_from=None, year_to=None,
                             sort_by='title'):
        """
        List all books by an author with optional filtering.

        Direct metadata query against Calibre's metadata.db (not the vector index).
        Useful for finding all works by an author, especially short texts (articles,
        book chapters) where vector search is unreliable.

        Args:
            author: Author name (case-insensitive partial match, required)
            tags: Optional list of tag names to filter by (AND logic, case-insensitive)
            year_from: Optional minimum publication year
            year_to: Optional maximum publication year
            sort_by: Sort order - 'title' (default) or 'year'

        Returns:
            Dictionary with matched books and metadata
        """
        # Build query
        query = """
        SELECT DISTINCT
            b.id,
            b.title,
            b.pubdate
        FROM books b
        JOIN books_authors_link bal ON b.id = bal.book
        JOIN authors a ON bal.author = a.id
        """

        conditions = ["LOWER(a.name) LIKE ?"]
        params = [f"%{author.lower()}%"]

        # Add tag filters (AND logic: all tags must match)
        if tags:
            for i, tag_name in enumerate(tags):
                alias = f"btl{i}"
                tag_alias = f"t{i}"
                query += f"""
                JOIN books_tags_link {alias} ON b.id = {alias}.book
                JOIN tags {tag_alias} ON {alias}.tag = {tag_alias}.id
                """
                conditions.append(f"LOWER({tag_alias}.name) LIKE ?")
                params.append(f"%{tag_name.lower()}%")

        # Add year filters
        if year_from:
            conditions.append("strftime('%Y', b.pubdate) >= ?")
            params.append(str(year_from))
        if year_to:
            conditions.append("strftime('%Y', b.pubdate) <= ?")
            params.append(str(year_to))

        query += " WHERE " + " AND ".join(conditions)

        # Sort order
        if sort_by == 'year':
            query += " ORDER BY b.pubdate DESC, b.title ASC"
        else:
            query += " ORDER BY b.title ASC"

        cursor = self.conn.execute(query, params)
        rows = cursor.fetchall()
        book_ids = [row['id'] for row in rows]

        # Batch fetch authors and tags (2 queries instead of 2×N)
        details = self._get_books_batch(book_ids)

        books = []
        for row in rows:
            d = details.get(row['id'], {})
            year = row['pubdate'][:4] if row['pubdate'] else None
            books.append({
                'calibre_id': row['id'],
                'title': row['title'],
                'authors': d.get('authors', []),
                'year': year,
                'tags': d.get('tags', []),
            })

        return {
            'author_query': author,
            'filters': {
                'tags': tags,
                'year_from': year_from,
                'year_to': year_to
            },
            'sort_by': sort_by,
            'book_count': len(books),
            'books': books
        }

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

    def print_duplicates(self, method='title_author'):
        """Print a human-readable summary of duplicates"""
        result = self.detect_duplicates(method=method)

        print("=" * 60)
        print("DUPLICATE DETECTION RESULTS")
        print("=" * 60)
        print()
        print(f"Detection method: {result['method']}")
        print(f"Duplicate groups found: {result['total_duplicate_groups']}")
        print(f"Total duplicate books: {result['total_duplicate_books']}")
        print()

        if result['duplicate_groups']:
            print("Duplicate Groups:")
            print("-" * 60)
            for i, group in enumerate(result['duplicate_groups'], 1):
                print(f"\nGroup {i}: {group['match_type']} - {group['match_value']}")
                print(f"  {group['count']} books:")
                for book in group['books']:
                    authors = ', '.join(book['authors']) if book['authors'] else 'Unknown'
                    tags = ', '.join(book['tags']) if book['tags'] else 'No tags'
                    formats = ', '.join(book['formats']) if book['formats'] else 'No formats'
                    print(f"    ID {book['id']}: {book['title']}")
                    print(f"      Authors: {authors}")
                    print(f"      Tags: {tags}")
                    print(f"      Formats: {formats}")
                    print(f"      Path: {book['path']}")
        else:
            print("No duplicates found!")

        # Show Doublette-tagged books
        if result['doublette_count'] > 0:
            print()
            print("=" * 60)
            print(f"Books tagged with 'Doublette': {result['doublette_count']}")
            print("-" * 60)
            for book in result['doublette_tagged_books']:
                authors = ', '.join(book['authors']) if book['authors'] else 'Unknown'
                print(f"  ID {book['id']}: {book['title']}")
                print(f"    Authors: {authors}")
                print(f"    Path: {book['path']}")

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
  %(prog)s ~/Calibre\\ Library/metadata.db --output json
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
                 'ratings', 'years', 'formats', 'incomplete', 'duplicates'],
        help='Show only specific statistics'
    )

    parser.add_argument(
        '--duplicates',
        action='store_true',
        help='Find duplicate books in the library'
    )

    parser.add_argument(
        '--duplicate-method',
        choices=['title_author', 'isbn', 'exact_title'],
        default='title_author',
        help='Duplicate detection method (default: title_author)'
    )

    args = parser.parse_args()

    try:
        with CalibreAnalyzer(args.database) as analyzer:
            # Handle duplicates detection
            if args.duplicates or args.filter == 'duplicates':
                if args.output == 'json':
                    data = analyzer.detect_duplicates(method=args.duplicate_method)
                    print(json.dumps(data, indent=2, ensure_ascii=False))
                else:
                    analyzer.print_duplicates(method=args.duplicate_method)
            elif args.output == 'json':
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
