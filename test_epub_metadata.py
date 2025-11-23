"""
Test EPUB metadata extraction.

This demonstrates what metadata can be extracted from EPUB files
using Dublin Core standards.
"""

try:
    from ebooklib import epub
    EBOOKLIB_AVAILABLE = True
except ImportError:
    EBOOKLIB_AVAILABLE = False
    print("❌ ebooklib not installed")
    print("Install with: pip install ebooklib")
    exit(1)

import sys
from pathlib import Path

def test_epub_metadata(epub_path):
    """Extract and display EPUB metadata."""
    print(f"Testing EPUB metadata extraction: {epub_path}\n")
    print("=" * 60)

    try:
        book = epub.read_epub(str(epub_path))

        # Author
        author = book.get_metadata('DC', 'creator')
        if author and author[0]:
            print(f"Author:      {author[0][0]}")

        # Title
        title = book.get_metadata('DC', 'title')
        if title and title[0]:
            print(f"Title:       {title[0][0]}")

        # Publisher
        publisher = book.get_metadata('DC', 'publisher')
        if publisher and publisher[0]:
            print(f"Publisher:   {publisher[0][0]}")

        # Language
        language = book.get_metadata('DC', 'language')
        if language and language[0]:
            print(f"Language:    {language[0][0]}")

        # Date/Year
        date = book.get_metadata('DC', 'date')
        if date and date[0]:
            print(f"Date:        {date[0][0]}")
            # Try to extract year
            import re
            date_str = str(date[0][0])
            year_match = re.search(r'(\d{4})', date_str)
            if year_match:
                print(f"  → Year:    {year_match.group(1)}")

        # ISBN and other identifiers
        identifier = book.get_metadata('DC', 'identifier')
        if identifier:
            print(f"\nIdentifiers:")
            isbn_found = False
            for id_tuple in identifier:
                id_str = str(id_tuple[0]).strip()
                if 'isbn' in id_str.lower():
                    # Extract clean ISBN
                    isbn_clean = id_str.lower().replace('isbn:', '').replace('isbn', '').strip()
                    print(f"  ISBN:      {isbn_clean}")
                    isbn_found = True
                elif id_str.replace('-', '').replace(' ', '').isdigit() and len(id_str.replace('-', '').replace(' ', '')) in [10, 13]:
                    print(f"  ISBN:      {id_str} (numeric)")
                    isbn_found = True
                else:
                    print(f"  Other:     {id_str}")

        # Subject
        subject = book.get_metadata('DC', 'subject')
        if subject:
            print(f"\nSubjects:")
            for s in subject:
                if s:
                    print(f"  - {s[0]}")

        # Description
        description = book.get_metadata('DC', 'description')
        if description and description[0]:
            desc_text = str(description[0][0])
            # Truncate if too long
            if len(desc_text) > 200:
                desc_text = desc_text[:200] + "..."
            print(f"\nDescription:")
            print(f"  {desc_text}")

        print("\n" + "=" * 60)
        print("✅ Metadata extraction successful!")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_epub_metadata.py <path_to_epub_file>")
        print("\nExample:")
        print('  python test_epub_metadata.py "D:/Books/example.epub"')
        exit(1)

    epub_path = Path(sys.argv[1])

    if not epub_path.exists():
        print(f"❌ File not found: {epub_path}")
        exit(1)

    if epub_path.suffix.lower() != '.epub':
        print(f"⚠ Warning: File doesn't have .epub extension: {epub_path}")

    test_epub_metadata(epub_path)
