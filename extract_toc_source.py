"""
Extract TOC from the source PDF and use it for cross-validation.
"""

import fitz  # PyMuPDF
from pathlib import Path

# Source PDF path
pdf_path = r"D:\Calibre-Bibliothek\Adolf von Harnack\Marcion_ Das Evangelium vom fremden (8322)\Marcion_ Das Evangelium vom fre - Adolf von Harnack.pdf"

print("="*80)
print("EXTRACTING TABLE OF CONTENTS FROM SOURCE PDF")
print("="*80 + "\n")

print(f"Opening: {pdf_path}\n")

if not Path(pdf_path).exists():
    print(f"✗ File not found: {pdf_path}")
    print("\nMake sure the path is correct and accessible.")
    exit(1)

# Open PDF
doc = fitz.open(pdf_path)

print(f"✓ PDF opened: {doc.page_count} pages\n")

# Extract TOC
toc = doc.get_toc()

if not toc:
    print("✗ No embedded TOC found in PDF")
    print("\nThis PDF might not have bookmarks/outline metadata.")
    print("Proceeding with header-only extraction...")
else:
    print(f"✓ Found TOC with {len(toc)} entries\n")
    print("="*80)
    print("TABLE OF CONTENTS")
    print("="*80 + "\n")

    for level, title, page in toc:
        indent = "  " * (level - 1)
        print(f"{indent}{title:70s} → PDF page {page}")

    print("\n" + "="*80)
    print("KEY SECTIONS")
    print("="*80 + "\n")

    # Find important sections
    for level, title, page in toc:
        title_lower = title.lower()
        if 'beilage' in title_lower or 'appendix' in title_lower:
            print(f"  {title:50s} → PDF page {page}")
        elif 'einleitung' in title_lower or 'introduction' in title_lower:
            print(f"  {title:50s} → PDF page {page}")
        elif 'inhalt' in title_lower or 'contents' in title_lower:
            print(f"  {title:50s} → PDF page {page}")

doc.close()

print("\n" + "="*80)
print("NEXT STEPS")
print("="*80)
print("Now run: python scripts/extract_page_numbers.py")
print("The script will use this TOC for cross-validation!")
