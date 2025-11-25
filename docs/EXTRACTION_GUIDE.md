# Universal Text Extraction Guide

## Overview

The ARCHILLES Universal Text Extractor can extract text from **20+ e-book formats** using a robust multi-tier fallback strategy:

```
1. Native Extractors → Fast & Precise
   ├─ PDF (pdfplumber/PyMuPDF)
   ├─ EPUB (ebooklib)
   ├─ TXT (native Python)
   └─ HTML (BeautifulSoup)

2. Calibre Conversion → Reliable & Comprehensive
   └─ MOBI, AZW3, DJVU, DOC, DOCX, RTF, ODT, CHM, FB2, LIT, etc.
      → Convert to EPUB/PDF → Extract

3. Pandoc Fallback → For Legacy Formats
   └─ WordPerfect, LaTeX, etc.
```

---

## Supported Formats

### Tier 1: Native Extraction (Highest Quality)

| Format | Extension | Library | Notes |
|--------|-----------|---------|-------|
| PDF | `.pdf` | pdfplumber, PyMuPDF | Layout-aware, preserves page numbers, coordinates for citations |
| EPUB | `.epub` | ebooklib | Extracts chapters, TOC, metadata |
| TXT | `.txt`, `.md`, `.rst` | Native Python | Automatic encoding detection |
| HTML | `.html`, `.htm`, `.xhtml` | BeautifulSoup | Preserves structure, extracts headings |

**Features:**
- ✅ Fastest extraction
- ✅ Best quality (preserves structure)
- ✅ Page/chapter information
- ✅ Table of contents
- ✅ Metadata (author, title, year)

### Tier 2: Calibre Conversion (Most Comprehensive)

**Requires:** Calibre installed ([Download](https://calibre-ebook.com/download))

| Format | Extension | Common Use Case |
|--------|-----------|-----------------|
| Kindle | `.mobi`, `.azw`, `.azw3`, `.azw4` | Amazon Kindle books |
| Scanned Books | `.djvu`, `.djv` | Old academic scans, critical editions |
| Word Documents | `.doc`, `.docx` | Manuscripts, dissertations |
| Rich Text | `.rtf` | Legacy documents |
| OpenDocument | `.odt` | LibreOffice documents |
| FictionBook | `.fb2` | Russian e-books |
| Microsoft Reader | `.lit` | Old Microsoft format |
| Palm | `.pdb`, `.pml`, `.prc` | Palm Pilot era |
| Help Files | `.chm` | Microsoft Help files |
| Comic Books | `.cbr`, `.cbz` | Comics (image-based) |

**How it works:**
1. Detects unsupported format
2. Converts to EPUB or PDF using Calibre's `ebook-convert`
3. Extracts text using native extractors

**Performance:**
- ⏱ Slower (conversion overhead)
- ✅ Very reliable
- ✅ Handles complex/exotic formats

### Tier 3: Legacy Formats (Planned)

| Format | Extension | Notes |
|--------|-----------|-------|
| WordPerfect | `.wpd`, `.wps` | Via Pandoc or wvWare |
| LaTeX | `.tex` | Via Pandoc |

---

## Installation

### 1. Install Python Dependencies

```bash
cd achilles
pip install -r requirements.txt
```

### 2. Install Calibre (Optional but Recommended)

**For maximum format support, install Calibre:**

- **macOS:** `brew install calibre`
- **Ubuntu/Debian:** `sudo apt install calibre`
- **Windows:** [Download installer](https://calibre-ebook.com/download)

**Verify installation:**
```bash
ebook-convert --version
```

### 3. Install Tesseract OCR (Optional)

**For scanned PDFs/DJVUs that need OCR:**

- **macOS:** `brew install tesseract`
- **Ubuntu/Debian:** `sudo apt install tesseract-ocr`
- **Windows:** [Download installer](https://github.com/tesseract-ocr/tesseract/wiki)

---

## Quick Start

### Extract Single File

```python
from src.extractors import UniversalExtractor

# Initialize extractor
extractor = UniversalExtractor()

# Extract text
result = extractor.extract("path/to/book.pdf")

# Access results
print(f"Total words: {result.metadata.total_words:,}")
print(f"Total chunks: {result.metadata.total_chunks}")
print(f"First chunk: {result.chunks[0]['text']}")
```

### Extract with Custom Settings

```python
extractor = UniversalExtractor(
    chunk_size=512,      # Target chunk size in tokens
    overlap=128,         # Overlap between chunks
    enable_ocr=True,     # Enable OCR for scanned PDFs
)

result = extractor.extract("scanned_book.djvu")
```

### Batch Extraction

```python
from pathlib import Path

# Find all PDFs and EPUBs
files = list(Path("~/Calibre Library").glob("**/*.{pdf,epub}"))

# Extract from all files
results = extractor.extract_batch(files, skip_errors=True)

# Process results
for file_path, extracted_text, error in results:
    if extracted_text:
        print(f"✓ {file_path.name}: {extracted_text.metadata.total_chunks} chunks")
    else:
        print(f"✗ {file_path.name}: {error}")
```

---

## Advanced Usage

### Access Metadata

```python
result = extractor.extract("book.epub")

# File metadata
print(f"Format: {result.metadata.detected_format}")
print(f"Method: {result.metadata.extraction_method}")
print(f"Pages: {result.metadata.total_pages}")

# Content metadata
for chunk in result.chunks:
    meta = chunk['metadata']
    print(f"Page {meta['page']}, Chapter: {meta['chapter']}")
    print(f"Author: {meta['author']}, Title: {meta['title']}")
```

### Work with Table of Contents

```python
result = extractor.extract("textbook.pdf")

# Print TOC
for entry in result.toc:
    indent = "  " * entry['level']
    print(f"{indent}{entry['title']} (p. {entry.get('page', '?')})")
```

### Export to JSON

```python
import json

result = extractor.extract("book.epub")

# Convert to dict
data = result.to_dict()

# Save to JSON
with open("extracted.json", 'w', encoding='utf-8') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
```

### Handle Errors Gracefully

```python
from src.extractors.exceptions import (
    UnsupportedFormatError,
    ExtractionError,
    CalibreNotFoundError,
)

try:
    result = extractor.extract("unknown.xyz")
except UnsupportedFormatError as e:
    print(f"Format not supported: {e}")
except CalibreNotFoundError as e:
    print(f"Calibre required but not found: {e}")
except ExtractionError as e:
    print(f"Extraction failed: {e}")
```

---

## Format-Specific Features

### PDF

**Features:**
- Page number tracking (including roman numerals)
- PDF coordinates for clickable citations
- Footnote detection (heuristic-based)
- TOC extraction
- Multi-column layout support (planned)
- OCR fallback for scanned pages

**Example:**
```python
extractor = PDFExtractor(enable_ocr=True)
result = extractor.extract("scanned_book.pdf")

# Each chunk has page information
for chunk in result.chunks:
    page = chunk['metadata']['page']
    coords = chunk['metadata'].get('pdf_coords')  # {x, y, width, height}
    print(f"Page {page}, Coords: {coords}")
```

### EPUB

**Features:**
- Chapter detection
- TOC extraction
- Metadata (author, title, language)
- Handles EPUB 2 and EPUB 3
- Fallback to manual ZIP extraction

**Example:**
```python
result = extractor.extract("novel.epub")

# Access chapters
for chunk in result.chunks:
    chapter = chunk['metadata'].get('chapter')
    print(f"Chapter: {chapter}")
```

### DJVU (via Calibre)

**Use case:** Old academic scans, critical editions

**Process:**
1. DJVU → PDF (via Calibre)
2. PDF → Text (via pdfplumber)
3. Optional: OCR for low-quality scans

**Example:**
```python
# DJVU will be automatically converted
result = extractor.extract("critical_edition.djvu")

# Check conversion warnings
for warning in result.metadata.warnings:
    print(warning)
# Output: "Converted from .djvu to pdf using Calibre"
```

---

## Performance Optimization

### Chunking Strategies

**For RAG systems:**
```python
# Default: Balanced
extractor = UniversalExtractor(chunk_size=512, overlap=128)

# Long context (for philosophical texts)
extractor = UniversalExtractor(chunk_size=1024, overlap=256)

# Short chunks (for quick retrieval)
extractor = UniversalExtractor(chunk_size=256, overlap=64)
```

**Overlap importance:**
- Preserves context across chunk boundaries
- Critical for humanities (argumentative structure)
- Recommended: 20-25% of chunk_size

### Batch Processing

**For large libraries:**
```python
import multiprocessing

# Process files in parallel (advanced)
from concurrent.futures import ProcessPoolExecutor

def extract_file(file_path):
    extractor = UniversalExtractor()
    return extractor.extract(file_path)

with ProcessPoolExecutor(max_workers=4) as executor:
    results = list(executor.map(extract_file, file_paths))
```

---

## Troubleshooting

### "Calibre not available" Error

**Solution:**
```bash
# Install Calibre
brew install calibre  # macOS
sudo apt install calibre  # Ubuntu

# Verify
ebook-convert --version
```

### PDF Extraction Quality Issues

**Problem:** Garbled text, missing characters

**Solutions:**
1. Try different library:
   ```python
   # Force PyMuPDF instead of pdfplumber
   from src.extractors.pdf_extractor import PDFExtractor
   extractor = PDFExtractor()
   ```

2. Enable OCR for scanned PDFs:
   ```python
   extractor = UniversalExtractor(enable_ocr=True)
   ```

3. Convert to EPUB first (Calibre):
   ```bash
   ebook-convert problematic.pdf better.epub
   ```

### EPUB "Calibre hash path" Issues

**Context:** Calibre stores EPUB files with hashed directory names

**Solution:** Already handled! The extractor reads directly from EPUB ZIP structure, no path resolution needed.

### Memory Issues with Large Files

**For files >500 MB:**
```python
# Process in chunks (coming in Phase 2)
# Current workaround: Convert to smaller files
ebook-convert huge.pdf split1.epub --max-chapters 50
```

---

## Integration with Calibre Library

### Extract from Calibre Books

```python
import sqlite3
from pathlib import Path

# Connect to Calibre DB
calibre_db = Path("~/Calibre Library/metadata.db").expanduser()
conn = sqlite3.connect(calibre_db)

# Get all books
cursor = conn.execute("SELECT id, title, path FROM books")

for book_id, title, book_path in cursor:
    # Find PDF or EPUB
    book_dir = Path("~/Calibre Library") / book_path

    for file in book_dir.glob("*"):
        if file.suffix in ['.pdf', '.epub', '.mobi']:
            result = extractor.extract(file)
            print(f"{title}: {result.metadata.total_chunks} chunks")
            break
```

---

## API Reference

### UniversalExtractor

```python
class UniversalExtractor:
    def __init__(
        self,
        chunk_size: int = 512,
        overlap: int = 128,
        enable_ocr: bool = False,
        calibre_path: Optional[str] = None,
    ):
        """Initialize universal extractor."""

    def extract(self, file_path: Path | str) -> ExtractedText:
        """Extract text from file."""

    def extract_batch(
        self,
        file_paths: List[Path | str],
        skip_errors: bool = True
    ) -> List[tuple]:
        """Extract from multiple files."""

    def get_supported_formats(self) -> dict:
        """Get supported formats info."""
```

### ExtractedText

```python
@dataclass
class ExtractedText:
    full_text: str
    chunks: List[Dict[str, Any]]
    metadata: ExtractionMetadata
    toc: List[Dict[str, Any]]
    footnotes: List[Dict[str, Any]]

    def get_chunk_by_page(self, page: int) -> List[Dict]:
        """Get chunks from specific page."""

    def get_context_window(self, chunk_index: int, window_size: int = 2) -> str:
        """Get chunk with surrounding context."""
```

---

## Next Steps

1. **Phase 1:** Use extraction for Calibre library indexing
2. **Phase 2:** Integrate with BGE-M3 embeddings
3. **Phase 3:** Add to RAG pipeline with Ollama

See `SPEC.md` for full roadmap.
