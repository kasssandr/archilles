# Text Extraction Guide

**Last updated:** November 2026

This guide describes the extractor layer (`src/extractors/`): where a book's text comes from, what an extraction returns, and how to call it yourself. Indexing uses this layer for every book; you only need the API below if you want to inspect an extraction or build on it. For the design behind it, see [ARCHITECTURE.md](ARCHITECTURE.md), section 2.

---

## Overview

`UniversalExtractor` takes a file and returns its text, cut into chunks that each carry their address: page, printed page label, chapter, section type. It picks the extraction method itself:

```
0. Scriptor master → the prepared text of a PDF, read instead of the PDF
   └─ Markdown whose metadata block names a format_version

1. Native extractors → fast and precise
   ├─ PDF  (PyMuPDF, pdfplumber as fallback, optional OCR)
   ├─ EPUB (ebooklib)
   ├─ TXT, Markdown, reStructuredText
   └─ HTML

2. Calibre conversion → everything else
   └─ MOBI, AZW3, DJVU, DOC, DOCX, RTF, ODT, CHM, FB2, LIT, ...
      → converted to EPUB or PDF with ebook-convert, then extracted
```

If a native extractor fails on a file, the Calibre conversion is tried before the extraction gives up.

---

## Where the text of a PDF comes from

A PDF has two possible text sources.

**The Scriptor bundle.** Where a book has a bundle in `<library>/.archilles/scriptor/<book id>/`, indexing reads the bundle's master (`book.md`) instead of the PDF. [archilles-scriptor](https://github.com/kasssandr/archilles-scriptor) made that text from the PDF: paragraphs rejoined, running heads removed, footnotes bound to their sentences, the printed page label at every page break, and bibliography, index and notes sections named as regions. `ScriptorExtractor` reads the master and its pagination sidecar and cuts the chunks. It parses no marker itself; the grammar is Scriptor's (`scriptor.document`).

**The PDF itself.** For every PDF without a bundle, `PDFExtractor` reads the file with PyMuPDF. This path is frozen as the fallback: it works as before and is not developed further. Improvements to PDF text arrive through Scriptor.

The swap happens in indexing (`Indexer._text_source`), not in this layer. `UniversalExtractor` extracts the file you hand it. Hand it a PDF and you get the built-in path; hand it a bundle's master and you get the prepared text.

What a bundle is, how it is built and what admits it: [FEATURES.md §2.2](FEATURES.md) and [USAGE.md](USAGE.md#scriptor-bundles-pdf).

---

## Supported Formats

### Scriptor master

| Format | Recognised by | Notes |
|--------|---------------|-------|
| Prepared document (`.md`) | A metadata block that names a `format_version` | Printed page labels with their provenance, named regions, footnotes bound per chunking strategy. A master written under a newer major version of the format is refused |

Any other Markdown file is read as plain text.

### Native extraction

| Format | Extension | Library | Notes |
|--------|-----------|---------|-------|
| PDF | `.pdf` | PyMuPDF, pdfplumber | Page numbers and printed page labels, outline as chapter and section, running head and footer removal |
| EPUB | `.epub` | ebooklib | Chapters from the table of contents, section classification, page labels where the EPUB carries a page list |
| Text | `.txt`, `.md`, `.rst` | Native Python | Encoding detection, YAML frontmatter stripped |
| HTML | `.html`, `.htm`, `.xhtml` | BeautifulSoup | Headings and structure |

### Calibre conversion

**Requires:** Calibre installed ([Download](https://calibre-ebook.com/download))

| Format | Extension | Common use |
|--------|-----------|------------|
| Kindle | `.mobi`, `.azw`, `.azw3`, `.azw4` | Amazon Kindle books |
| Scanned books | `.djvu`, `.djv` | Older academic scans, critical editions |
| Word documents | `.doc`, `.docx` | Manuscripts, dissertations |
| Rich Text | `.rtf` | Legacy documents |
| OpenDocument | `.odt` | LibreOffice documents |
| FictionBook | `.fb2` | Russian e-books |
| Microsoft Reader | `.lit` | Old Microsoft format |
| Palm | `.pdb`, `.pml`, `.prc` | Palm era |
| Help files | `.chm` | Microsoft Help |

The file is converted to EPUB or PDF with Calibre's `ebook-convert` and then read by the native extractor. Slower, because of the conversion, and reliable.

---

## Installation

```bash
cd archilles
pip install -r requirements.txt
```

This installs `archilles-scriptor` from GitHub (git required). The extractors import it for the prepared format, the outline model and the region vocabulary, so it is needed for PDFs and EPUBs as well, not only for bundles.

**Calibre** (optional, for the conversion formats):

- **macOS:** `brew install calibre`
- **Ubuntu/Debian:** `sudo apt install calibre`
- **Windows:** [Download installer](https://calibre-ebook.com/download)

Verify with `ebook-convert --version`.

**Tesseract** (optional, for scanned PDFs without a text layer):

- **macOS:** `brew install tesseract`
- **Ubuntu/Debian:** `sudo apt install tesseract-ocr`
- **Windows:** [Download installer](https://github.com/tesseract-ocr/tesseract/wiki)

---

## Quick Start

### Extract a single file

```python
from src.extractors import UniversalExtractor

extractor = UniversalExtractor()
result = extractor.extract("path/to/book.pdf")

print(f"Method: {result.metadata.extraction_method}")
print(f"Words:  {result.metadata.total_words:,}")
print(f"Chunks: {result.metadata.total_chunks}")
print(result.chunks[0]['text'])
```

### Extract a bundle's master

```python
result = extractor.extract("/path/to/library/.archilles/scriptor/01234/book.md")

for chunk in result.chunks[:5]:
    meta = chunk['metadata']
    print(meta['page_label'], meta['label_source'], meta['region'], meta['chapter'])
```

The sidecars are found beside the master. Without the pagination sidecar the text is still read, but `label_source` stays empty.

### Settings

```python
extractor = UniversalExtractor(
    chunk_size=512,          # target chunk size in tokens
    overlap=128,             # overlap between chunks
    enable_ocr=True,         # OCR for scanned PDFs, detected per page
    ocr_language="deu+eng",  # Tesseract language codes
)
```

`force_ocr`, `ocr_backend` and `calibre_path` are the remaining options. For a Scriptor master, a chunk never spans two regions or sections, and overlap is by whole sentences.

---

## What an extraction returns

`extract()` returns an `ExtractedText`:

| Field | Contents |
|-------|----------|
| `full_text` | The whole text |
| `chunks` | A list of dicts, each with `text` and `metadata` |
| `metadata` | `ExtractionMetadata`: detected format, extraction method, timing, counts (`total_pages`, `total_words`, `total_chunks`), warnings and errors, whether OCR was applied |
| `toc` | The table of contents as the extractor read it |
| `footnotes` | Footnotes where the extractor separates them |

The metadata of a chunk (`ChunkMetadata`):

| Field | Contents |
|-------|----------|
| `page`, `page_label` | Physical page and the label as printed (`xiv`, `62`) |
| `chapter`, `section`, `section_title` | Place in the volume's division |
| `section_type` | `front_matter`, `main_content` or `back_matter`; search excludes all but main content by default |
| `region` | The region name where one is known (`bibliography`, `index`, `preface`, ...). Scriptor masters carry it from their region markers, EPUB chunks from their titles |
| `label_source` | Scriptor masters only: the witness behind the page label (`printed`, `link`, `toc`, `catalogue`, `computed`) |
| `producer_version` | Scriptor masters only: the format version of the master |
| `char_start`, `char_end` | Offsets into `full_text` |
| `language` | Detected per chunk |
| `source_file`, `format` | Technical metadata |

```python
result = extractor.extract("book.epub")

print(f"Format: {result.metadata.detected_format}")
for warning in result.metadata.warnings:
    print(warning)

for chunk in result.chunks:
    meta = chunk['metadata']
    print(f"p. {meta['page_label']}  {meta['chapter']}  [{meta['section_type']}]")
```

### Errors

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

`UnsupportedFormatError` and `CalibreNotFoundError` are subclasses of `ExtractionError`, so catch them first.

---

## Format notes

### Scriptor master

- The printed page label comes from the page markers in the text (`[p. 88]`), the physical page and the witness from the pagination sidecar.
- A region marker governs the text after it. Apparatus regions (`bibliography`, `index`, `abbreviations`, `notes`, `lists`) become `back_matter`; `front-matter` and `contents` become `front_matter`; everything else, including `preface`, `appendix` and any unknown name, is `main_content`.
- Under the `scientific` chunking strategy each footnote definition is appended to the paragraph that carries its anchor. `basic` leaves the definitions out.
- Markers are removed from the chunk text after they have been read.

### PDF

- Printed page labels from the PDF's own page labels, roman numerals included.
- The outline as a tree: chapter, section title and the designator chain of a section. An outline that is a scanner artefact is recognised and ignored.
- Running heads and footers are removed; footnotes are kept.
- OCR for pages without a text layer, if enabled.

A PDF read on this path cites what the file's labels say. Whether a label was printed on the page or merely counted is only known for a bundle.

### EPUB

- Chapters from the table of contents, sections classified by their titles.
- Printed page labels where the EPUB has a page list. An EPUB whose page list names every printed page is indexed before the book's PDF.
- EPUB 2 and EPUB 3.

### DJVU (via Calibre)

DJVU is converted to PDF by Calibre and then read like a PDF. The conversion is noted in `result.metadata.warnings`.

---

## Troubleshooting

### "Calibre not available"

Install Calibre and check that `ebook-convert --version` runs. If it is installed outside the PATH, pass `calibre_path` to `UniversalExtractor`.

### Garbled PDF text, running heads in the chunks, wrong page numbers

1. For a PDF with a text layer, build a Scriptor bundle (`python scripts/scriptor_prepare.py --ids <id>`). It is the remedy for running heads, footnotes in mid-sentence and page numbers that are positions in the file.
2. For a scan without a text layer, enable OCR: `UniversalExtractor(enable_ocr=True)`.
3. If the book also exists as an EPUB, index that instead (`--prefer-format epub`).

### A bundle exists but the PDF was read

`UniversalExtractor` reads the file you give it. The bundle is chosen in indexing, by book ID. If indexing reads the PDF although a bundle folder exists, the folder holds no usable master: none at all, a dead link, or two prepared documents, of which none is taken.

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
        force_ocr: bool = False,
        ocr_backend: OCRBackend = OCRBackend.AUTO,
        ocr_language: str = "deu+eng",
        calibre_path: Optional[str] = None,
    ):
        """Initialize the extractor."""

    def extract(self, file_path: Path | str) -> ExtractedText:
        """Extract text from a file of any supported format."""
```

### ExtractedText

```python
@dataclass
class ExtractedText:
    full_text: str
    chunks: List[Dict[str, Any]]
    metadata: Optional[ExtractionMetadata]
    toc: List[Dict[str, Any]]
    footnotes: List[Dict[str, Any]]
```

---

## Further reading

- [ARCHITECTURE.md](ARCHITECTURE.md) — the extractor layer in the system, the Scriptor seam
- [FEATURES.md](FEATURES.md) — what each path extracts
- [USAGE.md](USAGE.md) — indexing commands, building bundles
- [PREPARED_FORMAT_SPEC](https://github.com/kasssandr/archilles-scriptor/blob/main/docs/PREPARED_FORMAT_SPEC.md) — the format of a Scriptor master
