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
            # Construct book folder path
            book_folder = library_path / path

            print(f"\n[{book_id}] {title}")
            print(f"    Book folder: {book_folder}")

            # Find actual book file (look for epub, pdf, etc.)
            book_file = None
            if book_folder.exists():
                for ext in ['.epub', '.pdf', '.mobi', '.azw3']:
                    # Try different possible filenames
                    possible_files = list(book_folder.glob(f"*{ext}"))
                    if possible_files:
                        book_file = possible_files[0]
                        break

            if book_file:
                print(f"    Book file: {book_file}")

                # DEBUG: Show what get_book_by_path will search for
                try:
                    rel_path = book_file.relative_to(library_path)
                    book_folder_search = str(Path(rel_path.parts[0]) / rel_path.parts[1])
                    print(f"    Will search for: '{book_folder_search}'")
                    print(f"    DB has path: '{path}'")
                    print(f"    Match: {book_folder_search == path}")
                except Exception as e:
                    print(f"    Error constructing search path: {e}")

                # Try to find it using get_book_by_path
                book_data = calibre.get_book_by_path(book_file)

                if book_data:
                    print(f"    ✅ FOUND via get_book_by_path!")
                    print(f"    Has comments: {'Yes' if book_data.get('comments') else 'No'}")
                    if book_data.get('comments'):
                        comment_preview = book_data['comments'][:150].replace('\n', ' ')
                        print(f"    Comments preview: {comment_preview}...")
                else:
                    print(f"    ❌ NOT FOUND via get_book_by_path!")
            else:
                print(f"    ❌ No book file found in folder!")
            print("-"*70)

except Exception as e:
    print(f"\n❌ ERROR connecting to Calibre DB:")
    print(f"   {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
