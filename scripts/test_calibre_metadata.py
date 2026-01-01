#!/usr/bin/env python3
"""
Test if Calibre metadata extraction is working
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.rag_demo import archillesRAG
from src.calibre_db import CalibreDB
import os

# Get Calibre library path
library_path = os.getenv('CALIBRE_LIBRARY')
if not library_path:
    print("❌ CALIBRE_LIBRARY environment variable not set")
    sys.exit(1)

library_path = Path(library_path)
print(f"📚 Calibre Library: {library_path}\n")

# Test CalibreDB connection
print("="*70)
print("TESTING CALIBRE DB CONNECTION:")
print("="*70)

try:
    with CalibreDB(library_path) as calibre:
        # Get a few books
        cursor = calibre.conn.cursor()
        cursor.execute("""
            SELECT b.id, b.title, b.path,
                   (SELECT name FROM authors WHERE id = (SELECT author FROM books_authors_link WHERE book = b.id LIMIT 1)) as author,
                   c.text as comments
            FROM books b
            LEFT JOIN comments c ON b.id = c.book
            LIMIT 10
        """)

        books = cursor.fetchall()

        print(f"\n✅ Successfully connected to Calibre DB!")
        print(f"   Found {len(books)} sample books\n")

        print("="*70)
        print("SAMPLE BOOKS WITH COMMENTS:")
        print("="*70)

        for book_id, title, path, author, comments in books:
            print(f"\n[{book_id}] {title}")
            print(f"    Author: {author}")
            print(f"    Path: {path}")
            if comments:
                comment_preview = comments[:200].replace('\n', ' ')
                print(f"    Comments: {comment_preview}...")
            else:
                print(f"    Comments: (none)")
            print("-"*70)

        # Now test if we can find these books by path
        print("\n" + "="*70)
        print("TESTING PATH-BASED LOOKUP:")
        print("="*70)

        for book_id, title, path, author, comments in books[:3]:
            # Construct full path
            book_path = library_path / path

            # Try to find it using get_book_by_path
            book_data = calibre.get_book_by_path(book_path)

            print(f"\n[{book_id}] {title}")
            print(f"    Looking for path: {book_path}")
            if book_data:
                print(f"    ✅ FOUND via get_book_by_path!")
                print(f"    Has comments: {'Yes' if book_data.get('comments') else 'No'}")
            else:
                print(f"    ❌ NOT FOUND via get_book_by_path!")
            print("-"*70)

except Exception as e:
    print(f"\n❌ ERROR connecting to Calibre DB:")
    print(f"   {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
