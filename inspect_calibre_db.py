"""
Inspect Calibre database structure to understand how to query it.
"""

import sqlite3
import sys
from pathlib import Path

if len(sys.argv) < 2:
    print("Usage: python inspect_calibre_db.py <path_to_metadata.db>")
    print("\nExample:")
    print('  python inspect_calibre_db.py "D:\\Calibre-Bibliothek\\metadata.db"')
    exit(1)

db_path = Path(sys.argv[1])

if not db_path.exists():
    print(f"❌ Database not found: {db_path}")
    exit(1)

print(f"Inspecting: {db_path}\n")
print("=" * 60)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# List all tables
print("\n📋 TABLES:")
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = cursor.fetchall()
for table in tables:
    print(f"  - {table[0]}")

# Show identifiers table structure (for ISBNs)
print("\n\n📖 IDENTIFIERS TABLE (ISBNs):")
print("=" * 60)
cursor.execute("PRAGMA table_info(identifiers)")
columns = cursor.fetchall()
for col in columns:
    print(f"  {col[1]:20s} {col[2]:10s}")

print("\nSample data:")
cursor.execute("SELECT * FROM identifiers LIMIT 3")
rows = cursor.fetchall()
for row in rows:
    print(f"  {row}")

# Show books table structure
print("\n\n📚 BOOKS TABLE:")
print("=" * 60)
cursor.execute("PRAGMA table_info(books)")
columns = cursor.fetchall()
for col in columns:
    print(f"  {col[1]:20s} {col[2]:10s}")

# Show data table structure (file paths)
print("\n\n💾 DATA TABLE (file paths):")
print("=" * 60)
cursor.execute("PRAGMA table_info(data)")
columns = cursor.fetchall()
for col in columns:
    print(f"  {col[1]:20s} {col[2]:10s}")

print("\nSample data:")
cursor.execute("SELECT * FROM data LIMIT 3")
rows = cursor.fetchall()
for row in rows:
    print(f"  {row}")

# Show how to join them
print("\n\n🔗 JOIN EXAMPLE (Book with ISBN):")
print("=" * 60)
query = """
SELECT
    books.id,
    books.title,
    books.path,
    data.name,
    data.format,
    identifiers.type,
    identifiers.val
FROM books
LEFT JOIN data ON books.id = data.book
LEFT JOIN identifiers ON books.id = identifiers.book
WHERE identifiers.type = 'isbn'
LIMIT 3
"""
cursor.execute(query)
rows = cursor.fetchall()
for row in rows:
    print(f"\n  Book ID: {row[0]}")
    print(f"  Title:   {row[1]}")
    print(f"  Path:    {row[2]}")
    print(f"  File:    {row[3]}.{row[4]}")
    print(f"  ISBN:    {row[6]}")

conn.close()

print("\n" + "=" * 60)
print("✅ Inspection complete!")
