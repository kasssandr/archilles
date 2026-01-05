#!/usr/bin/env python3
"""
Delete books from RAG database by tag.

Usage:
    python scripts/delete_tag_books.py --tag "Leit-Literatur"
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.batch_index import get_books_by_tag, create_book_id, get_calibre_library_path
from scripts.rag_demo import archillesRAG
import argparse


def delete_books_by_tag(tag_name: str, db_path: str = None):
    """Delete all books with a specific tag from the RAG database."""

    # Get library path
    library_path = get_calibre_library_path()
    print(f"📚 Calibre library: {library_path}")

    # Get books with tag
    print(f"🏷️  Finding books with tag: {tag_name}")
    books = get_books_by_tag(library_path, tag_name)

    if not books:
        print("❌ No books found with this tag")
        return

    print(f"📖 Found {len(books)} books to delete from index")

    # Determine RAG database path
    if db_path is None:
        db_path = str(library_path / ".archilles" / "rag_db")

    print(f"💾 RAG database: {db_path}")

    # Initialize RAG (without reset)
    print(f"\n🔄 Connecting to RAG database...")

    # Temporarily skip the hanging count() by setting a flag
    import os
    os.environ['SKIP_CHROMADB_COUNT'] = '1'

    try:
        rag = archillesRAG(db_path=db_path, reset_db=False)
    except Exception as e:
        print(f"❌ Failed to connect: {e}")
        return

    # Delete each book
    print(f"\n{'='*60}")
    print(f"🗑️  DELETING BOOKS FROM INDEX")
    print(f"{'='*60}\n")

    deleted_count = 0
    failed_count = 0

    for i, book in enumerate(books, 1):
        book_id = create_book_id(book)
        print(f"[{i}/{len(books)}] {book['author']}: {book['title']}")
        print(f"         Book ID: {book_id}")

        try:
            # Delete all chunks for this book_id
            # ChromaDB delete by metadata filter
            result = rag.collection.delete(
                where={"book_id": book_id}
            )
            print(f"         ✅ Deleted chunks for this book")
            deleted_count += 1
        except Exception as e:
            print(f"         ⚠️  Failed to delete: {e}")
            failed_count += 1

    print(f"\n{'='*60}")
    print(f"📊 DELETION COMPLETE")
    print(f"{'='*60}")
    print(f"  Total books: {len(books)}")
    print(f"  Successfully deleted: {deleted_count}")
    print(f"  Failed: {failed_count}")
    print(f"{'='*60}\n")

    print("✅ You can now re-index these books with:")
    print(f'   python scripts/batch_index.py --tag "{tag_name}"')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description="Delete books from RAG database by tag"
    )
    parser.add_argument('--tag', required=True, help='Tag of books to delete')
    parser.add_argument('--db-path', default=None, help='RAG database path')

    args = parser.parse_args()

    print(f"\n⚠️  WARNING: This will delete all indexed data for books with tag '{args.tag}'")
    response = input("Continue? [y/N]: ").strip().lower()

    if response == 'y':
        delete_books_by_tag(args.tag, args.db_path)
    else:
        print("Cancelled.")
