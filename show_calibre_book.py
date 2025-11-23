"""
Show all metadata for a specific book in Calibre library.
"""

import sqlite3
import sys
from pathlib import Path

if len(sys.argv) < 2:
    print("Usage: python show_calibre_book.py <path_to_book_file>")
    print("\nExample:")
    print('  python show_calibre_book.py "D:\\Calibre-Bibliothek\\Author\\Book\\book.pdf"')
    exit(1)

book_path = Path(sys.argv[1])

if not book_path.exists():
    print(f"❌ Book file not found: {book_path}")
    exit(1)

# Find Calibre library
current = book_path.parent
library_path = None

for _ in range(5):
    if (current / "metadata.db").exists():
        library_path = current
        break
    if current.parent == current:
        break
    current = current.parent

if not library_path:
    print(f"❌ Not in Calibre library (no metadata.db found)")
    exit(1)

db_path = library_path / "metadata.db"
print(f"📚 Library: {library_path}")
print(f"📖 Book:    {book_path.name}\n")
print("=" * 60)

# Extract book folder path
try:
    rel_path = book_path.relative_to(library_path)
except ValueError:
    print(f"❌ File not in library")
    exit(1)

if len(rel_path.parts) < 2:
    print(f"❌ Invalid Calibre structure")
    exit(1)

book_folder = str(Path(rel_path.parts[0]) / rel_path.parts[1])
print(f"Book folder: {book_folder}\n")

# Query database
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

query = """
SELECT * FROM books WHERE path = ?
"""
cursor = conn.execute(query, (book_folder,))
book = cursor.fetchone()

if not book:
    print(f"❌ Book not found in database")
    exit(1)

book_id = book['id']

print("📋 BASIC INFO:")
print("=" * 60)
print(f"ID:           {book['id']}")
print(f"Title:        {book['title']}")
print(f"Sort:         {book['sort']}")
print(f"Timestamp:    {book['timestamp']}")
print(f"Pub Date:     {book['pubdate']}")
print(f"Last Modified: {book['last_modified']}")
print(f"Path:         {book['path']}")
print(f"UUID:         {book['uuid']}")

# Authors
print("\n👤 AUTHORS:")
print("=" * 60)
cursor = conn.execute("""
    SELECT authors.name, authors.sort
    FROM authors
    JOIN books_authors_link ON authors.id = books_authors_link.author
    WHERE books_authors_link.book = ?
""", (book_id,))
for row in cursor:
    print(f"  {row['name']} (sort: {row['sort']})")

# Publishers
print("\n🏢 PUBLISHERS:")
print("=" * 60)
cursor = conn.execute("""
    SELECT publishers.name
    FROM publishers
    JOIN books_publishers_link ON publishers.id = books_publishers_link.publisher
    WHERE books_publishers_link.book = ?
""", (book_id,))
for row in cursor:
    print(f"  {row['name']}")

# Tags
print("\n🏷️  TAGS:")
print("=" * 60)
cursor = conn.execute("""
    SELECT tags.name
    FROM tags
    JOIN books_tags_link ON tags.id = books_tags_link.tag
    WHERE books_tags_link.book = ?
    ORDER BY tags.name
""", (book_id,))
tags = cursor.fetchall()
if tags:
    for row in tags:
        print(f"  • {row['name']}")
else:
    print("  (none)")

# Identifiers
print("\n🔢 IDENTIFIERS (ISBN, etc.):")
print("=" * 60)
cursor = conn.execute("""
    SELECT type, val FROM identifiers WHERE book = ?
""", (book_id,))
identifiers = cursor.fetchall()
if identifiers:
    for row in identifiers:
        print(f"  {row['type']:15s} {row['val']}")
else:
    print("  (none)")

# Languages
print("\n🌍 LANGUAGES:")
print("=" * 60)
cursor = conn.execute("""
    SELECT languages.lang_code
    FROM languages
    JOIN books_languages_link ON languages.id = books_languages_link.lang_code
    WHERE books_languages_link.book = ?
""", (book_id,))
for row in cursor:
    print(f"  {row['lang_code']}")

# Series
print("\n📚 SERIES:")
print("=" * 60)
cursor = conn.execute("""
    SELECT series.name, books.series_index
    FROM series
    JOIN books_series_link ON series.id = books_series_link.series
    JOIN books ON books_series_link.book = books.id
    WHERE books.id = ?
""", (book_id,))
row = cursor.fetchone()
if row:
    print(f"  {row['name']} #{row['series_index']}")
else:
    print("  (not in series)")

# Comments/Description
print("\n📝 COMMENTS/DESCRIPTION:")
print("=" * 60)
cursor = conn.execute("""
    SELECT text FROM comments WHERE book = ?
""", (book_id,))
row = cursor.fetchone()
if row and row['text']:
    comment = row['text'][:200]
    if len(row['text']) > 200:
        comment += "..."
    print(f"  {comment}")
else:
    print("  (none)")

# Custom Columns
print("\n⚙️  CUSTOM COLUMNS:")
print("=" * 60)
cursor = conn.execute("SELECT id, label, name, datatype FROM custom_columns")
custom_cols = cursor.fetchall()

if custom_cols:
    for col in custom_cols:
        col_id = col['id']
        col_label = col['label']
        col_name = col['name']
        col_type = col['datatype']

        # Query custom column value
        table_name = f"custom_column_{col_id}"
        try:
            cursor = conn.execute(f"""
                SELECT value FROM {table_name} WHERE book = ?
            """, (book_id,))
            row = cursor.fetchone()
            if row and row['value']:
                print(f"  #{col_label:20s} ({col_name})")
                print(f"    Value: {row['value']}")
                print(f"    Type:  {col_type}")
        except:
            pass
else:
    print("  (no custom columns defined)")

# File formats
print("\n💾 FILES:")
print("=" * 60)
cursor = conn.execute("""
    SELECT format, name, uncompressed_size FROM data WHERE book = ?
""", (book_id,))
for row in cursor:
    size_mb = row['uncompressed_size'] / (1024*1024) if row['uncompressed_size'] else 0
    print(f"  {row['format']:10s} {row['name']} ({size_mb:.2f} MB)")

conn.close()

print("\n" + "=" * 60)
print("✅ Done!")
