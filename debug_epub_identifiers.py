"""
Debug script: Show ALL identifiers from EPUB metadata.
"""

try:
    from ebooklib import epub
except ImportError:
    print("❌ ebooklib not installed")
    exit(1)

import sys
from pathlib import Path

if len(sys.argv) < 2:
    print("Usage: python debug_epub_identifiers.py <path_to_epub>")
    exit(1)

epub_path = Path(sys.argv[1])

if not epub_path.exists():
    print(f"❌ File not found: {epub_path}")
    exit(1)

print(f"Reading: {epub_path.name}\n")

book = epub.read_epub(str(epub_path))

# Get ALL identifiers
identifier = book.get_metadata('DC', 'identifier')

print("DC:identifier metadata (RAW):")
print("=" * 60)

if identifier:
    for i, id_tuple in enumerate(identifier):
        print(f"\n[{i}] Tuple: {id_tuple}")
        print(f"    Value: {repr(id_tuple[0])}")
        print(f"    Type:  {type(id_tuple[0])}")

        id_str = str(id_tuple[0]).strip()
        print(f"    As string: '{id_str}'")

        # Check what it looks like
        if 'isbn' in id_str.lower():
            print(f"    → Contains 'isbn' ✓")
        else:
            print(f"    → Does NOT contain 'isbn'")

        # Check if numeric
        numeric_part = id_str.replace('-', '').replace(' ', '')
        if numeric_part.isdigit():
            print(f"    → Numeric part: {numeric_part} (length: {len(numeric_part)})")
else:
    print("No DC:identifier metadata found!")

print("\n" + "=" * 60)
