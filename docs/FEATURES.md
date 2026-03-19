# ARCHILLES — Feature Catalog

**Version:** 0.9 Beta (March 2026)
**Purpose:** Comprehensive reference of all implemented features. Basis for documentation, PR writing, and onboarding.

---

## 1. Search

### 1.1 Hybrid Search
Combines dense vector search (semantic) with BM25 keyword search, fused via **Reciprocal Rank Fusion (RRF)**. The system's default mode. Finds conceptually related passages *and* exact terms in a single query.

Three explicit modes available:
- `hybrid` — RRF fusion (default, recommended)
- `semantic` — dense vector only (BGE-M3); best for concept and theme searches
- `keyword` — BM25 only; best for exact names, Latin phrases, technical terms

### 1.2 Two-Stage Retrieval
Stage 1 (always active): LanceDB native hybrid search (dense + sparse vector fusion).
Stage 2 (optional): **Cross-encoder reranking** via BAAI/bge-reranker-v2-m3. Evaluates each query–document pair jointly rather than independently. Significantly more accurate ranking at the cost of additional inference time. Runs on CPU by default; graceful fallback if system memory is insufficient. First use downloads ~560 MB.

Enabled via `.archilles/config.json`:
```json
{ "enable_reranking": true, "reranker_device": "cpu" }
```

### 1.3 Exact Phrase Search
`--exact` flag (CLI) or `mode: keyword` (MCP). Suitable for Latin quotes, verbatim citations, or unique technical terms that must appear literally in the text.

### 1.4 Language Filtering
Filter results by language code (`de`, `en`, `la`, `fr`, `el`, etc.). Multiple languages combinable. Based on per-chunk language detection (Lingua, 75+ languages). Essential for multilingual libraries to reduce noise.

### 1.5 Tag Filtering
Restrict search to books carrying specific Calibre tags. Multiple tags combinable (AND logic in CLI, array in MCP).

### 1.6 Section Filtering
Default: `section_filter='main'` excludes front matter, bibliography, index, and back matter from results. Eliminates bibliography noise without manual intervention. Configurable per query.

### 1.7 Context Expansion (Small-to-Big Retrieval)
Each chunk stores a surrounding `window_text` for context expansion. When `expand_context=True` (MCP) or requested, the surrounding passage is returned alongside the matched chunk, giving the LLM more context to work with.

### 1.8 Result Diversification
`max_per_book` parameter prevents a single book from dominating results. Default distributes results across multiple titles.

### 1.9 Minimum Similarity Threshold
Configurable threshold filters out low-confidence matches before they reach the consumer.

### 1.10 Research Interest Boosting
`set_research_interests` MCP tool registers a list of keywords that receive an additive score boost during retrieval — without requiring re-indexing. Boosts are applied at query time. Configured boost factor is adjustable (default: 0.15 per matching keyword). Current interests stored in `research_interests.json` inside the library.

### 1.11 Smart Boosting (automatic)
`calibre_comment` matches receive a 1.2× score boost; tag matches receive 1.15×. Reflects the higher epistemic quality of user-curated fields vs. raw full text.

---

## 2. Indexing

### 2.1 Format Support
30+ formats via a multi-tier extractor stack:

| Format | Extractor | Notes |
|--------|-----------|-------|
| PDF | PyMuPDF (primary) + pdfplumber (fallback) | Page numbers, CropBox filtering |
| EPUB 2/3 | ebooklib + custom TOC parser | Section classification |
| MOBI, AZW3, DJVU | CalibreConverter → intermediate | Via Calibre ebook-convert |
| TXT | TXTExtractor | Encoding detection |
| HTML | HTMLExtractor | — |
| Scanned PDFs | OCRExtractor (Tesseract) | VLM upgrade path prepared |

### 2.2 PDF Extraction Quality
- **CropBox filtering**: eliminates headers, footers, and running page numbers before chunking
- **Page label extraction**: maps printed page numbers (e.g. "xiv", "47") to chunks for citation-accurate references
- **TOC-aware chunking**: `chapter` and `section_title` populated from the PDF's table of contents. Junk TOCs (scanner artifacts) are auto-detected and ignored
- **Running footer removal**: detects and removes repeated footer lines (page numbers, publisher names, URLs) while preserving footnotes
- **Footer detection with footnote disambiguation**: retains footnotes, removes page-bottom noise
- **Scanned PDF detection**: per-page word-count heuristics trigger OCR path automatically
- **Multi-tier fallback**: PyMuPDF → pdfplumber → OCR

### 2.3 EPUB Extraction Quality
- **TOC-based section classification**: content automatically labeled as `front_matter`, `main`, or `back_matter` using semantic titles (H1 text or TOC titles), never raw filenames
- **Introduction as main content**: introductions/Einleitungen are deliberately classified as main_content, not front_matter
- Structural HTML preserved through extraction; chapter boundaries recognized
- Significantly faster than PDF; no page numbers (chapter/section references instead)

### 2.4 Batch Indexing (`batch_index.py`)
Selection modes:

| Flag | Function |
|------|----------|
| `--all` | Index all books in the library |
| `--tag TAG` | Index books with a specific Calibre tag |
| `--author NAME` | Index books by author (partial match) |
| `--ids 123,456` | Index specific Calibre book IDs |

Filtering/refinement:

| Flag | Function |
|------|----------|
| `--filter-author NAME` | Further filter selected books by author (combinable with --tag/--all) |
| `--min-rating N` | Only books rated N stars or higher (1–5) |
| `--rating N` | Only books with exactly N stars (0 = unrated) |
| `--exclude-tag TAG` | Exclude books with this tag (repeatable) |
| `--include-excluded` | Override default exclusion of `exclude` and `Übersetzung` tags |
| `--prefer-format pdf\|epub` | When a book has multiple formats, prefer this one |
| `--limit N` | Process only the first N books (for testing) |
| `--dry-run` | Preview what would be indexed, no actual indexing |

Resume and maintenance:

| Flag | Function |
|------|----------|
| `--skip-existing` | Pre-filters already-indexed books before the loop (fast resume) |
| `--force` | Re-index even already-indexed books |
| `--reindex-before DATE` | Force re-index of books indexed before this date |
| `--reindex-missing-labels` | Re-index books where page label extraction failed |
| `--cleanup-orphans` | Remove index entries for books deleted from Calibre |
| `--reset-db` | Reset the database (use with caution) |
| `--non-interactive` | Suppress confirmation prompts (for scripts and automation) |

Operational:

| Flag | Function |
|------|----------|
| `--profile minimal\|balanced\|maximal` | Hardware profile (batch size) |
| `--log FILE` | Write indexing progress to JSON log file |
| `--enable-ocr` | Enable OCR for scanned PDFs |

### 2.5 Checkpoint-Based Resume
Long batch runs use `progress.db` for crash-safe progress tracking. Individual book progress (chunks processed, errors, timing) is checkpointed. Interrupted runs resume from the last checkpoint via `--skip-existing`.

### 2.6 Backup Rotation
Automatic LanceDB backup every 50 books during batch indexing. Retains 2 recent backups. Protects against index corruption during long indexing sessions.

### 2.7 Metadata Deduplication
`metadata_hash` per chunk prevents duplicate entries when re-indexing a book that has not changed. Only changed books produce new chunks.

### 2.8 Hardware Profiles
Three pre-defined profiles, all using BGE-M3 for consistent quality:

| Profile | Recommended for | Batch size | Speed |
|---------|-----------------|------------|-------|
| `minimal` | 4–6 GB VRAM (Quadro T1000, GTX 1650) | 8 | ~2 min/book |
| `balanced` | 8–12 GB VRAM (RTX 3060, RTX 2070) | 32 | ~30s/book |
| `maximal` | 16+ GB VRAM (RTX 3090, RTX 4080) | 64 | ~15s/book |

Hardware auto-detection selects the appropriate profile when none is specified. Supports NVIDIA CUDA, Apple Silicon MPS, and CPU.

### 2.9 Single-Book Indexing (CLI)
```bash
python scripts/rag_demo.py index "/path/to/book.pdf"
python scripts/rag_demo.py index "/path/to/book.pdf" --book-id "Arendt_VitaActiva"
```

---

### 2.10 Source Adapters
ARCHILLES supports multiple library backends, auto-detected from the directory structure:

| Adapter | Backend | Detection |
|---------|---------|-----------|
| `CalibreAdapter` | Calibre library | Detects `metadata.db` (default) |
| `ZoteroAdapter` | Zotero library | Detects `zotero.sqlite` |
| `ObsidianAdapter` | Obsidian vault | Detects `.obsidian/` directory |
| `FolderAdapter` | Plain directory | Fallback for any supported file collection |

### 2.11 DialogueChunker
Specialized chunker for chat and Q&A exports (ChatGPT, Gemini, Grok, NotebookLM). Recognizes turn markers (`## User`, `## Assistant`, `**Q:**`, etc.) and chunks per turn or turn-pair, preserving `speaker` metadata. Registered in `ChunkerRegistry`, auto-activated when dialogue structure is detected.

### 2.12 Chunk Inspector (`scripts/chunk_inspector.py`)
Diagnostic CLI tool for analyzing chunk quality. Reports chunk statistics, metadata coverage, boundary analysis (truncation detection), and TOC alignment for both PDFs and EPUBs. Supports `--calibre-id`, `--toc`, `--summary-only`, and `--export` for Markdown reports.

---

## 3. Calibre Integration

### 3.1 Read-Only Library Access
Reads `metadata.db` directly. Never writes to the Calibre library. All ARCHILLES data lives in `.archilles/` within the library folder.

### 3.2 Metadata Extraction
Per book: title, author(s), publisher, publication date, ISBN/identifiers, language, series, file formats and paths, cover path, reading progress.

### 3.3 Custom Field Discovery
Queries Calibre's `custom_columns` table at startup and maps all user-defined fields (e.g. `research_project`, `source_reliability`, `century`) to searchable metadata automatically — no manual configuration.

### 3.4 Tag Integration
All Calibre tags are indexed and available as filters in both CLI and MCP tools.

### 3.5 Comments Field
Calibre's comments field is treated as first-class content: publisher blurbs, personal reading notes, NotebookLM analyses, collected reviews. Indexed as `chunk_type='calibre_comment'` with BGE-M3 embeddings. Receives a 1.2× search boost.

### 3.6 Annotation Indexing
Highlights, notes, and bookmarks from the Calibre E-book Viewer (EPUB) and PDF annotations are indexed alongside book content as `chunk_type='annotation'`. No separate indexing step — annotations are processed automatically during regular book indexing (Phase 2).

### 3.7 Duplicate Detection
`detect_duplicates` MCP tool identifies duplicate books by title+author, ISBN, or exact title. Also surfaces books tagged with "Doublette".

---

## 4. Embeddings and Storage

### 4.1 BGE-M3 Embeddings
BAAI/BGE-M3, 1024 dimensions, multilingual (75+ languages). Native support for Dense, Sparse, and ColBERT retrieval in a single model. One-time download ~2.2 GB.

### 4.2 LanceDB Vector Store
Single `chunks` table stores all content types (book text, annotations, comments). Apache Arrow-based, disk-efficient, no memory bottleneck for large corpora. Native hybrid search (dense + BM25 FTS) via `RRFReranker`. IVF-PQ indexing for corpora exceeding 256 chunks. Automatic schema migration for new columns.

### 4.3 Stop-Word Removal
Multi-language stop-word removal applied during BM25 indexing and query processing. Supported: EN, DE, FR, ES, IT, PT, NL, LA, RU, EL, HE, AR.

### 4.4 Language Detection
Lingua library, 75+ languages, ISO 639-1 codes. Applied per extracted text chunk. Enables reliable language filtering across multilingual libraries.

---

## 5. MCP Server (Claude Desktop Integration)

### 5.1 Protocol
JSON-RPC 2.0 over stdio. Careful stdout/stderr isolation to prevent JSON-RPC protocol corruption. Entry point: `mcp_server.py` in project root.

### 5.2 Tool List (12 tools)

| Tool | Category | Description |
|------|----------|-------------|
| `search_books_with_citations` | Search | Hybrid full-text search with citation-ready output |
| `search_annotations` | Search | Hybrid search across highlights, notes, and comments |
| `set_research_interests` | Search | Register keywords for score boosting without re-indexing |
| `list_books_by_author` | Metadata | Direct Calibre DB query: all books by an author |
| `list_annotated_books` | Metadata | All books with indexed annotations |
| `get_book_annotations` | Metadata | All annotations for a specific book (by path) |
| `get_book_details` | Metadata | Full Calibre metadata for a book ID |
| `list_tags` | Metadata | All Calibre tags with book counts |
| `export_bibliography` | Output | Bibliography in BibTeX, RIS, EndNote, JSON, CSV |
| `detect_duplicates` | Utility | Find duplicate books by title+author, ISBN, or exact title |
| `compute_annotation_hash` | Utility | Compute content hash for annotation deduplication |
| `get_doublette_tag_instruction` | Utility | Helper for the Calibre duplicate-tagging workflow |

### 5.3 Citation Output
Each search result includes: author, title, year, and either page number/page label (PDF) or chapter/section (EPUB). Suitable for academic citation. EPUB results should include a verbatim original-language quote for Ctrl+F findability.

### 5.4 calibre:// URI Links
Search results include both `file://` URIs (for Markdown apps like Joplin/Obsidian) and `calibre://` URIs that open the book in Calibre directly at the correct page.

---

## 6. CLI

### 6.1 Search (`rag_demo.py query`)
```bash
python scripts/rag_demo.py query "QUERY" [options]
```
Options: `--mode`, `--language`, `--tag-filter`, `--top-k`, `--exact`, `--export FILE`

### 6.2 Index Statistics
```bash
python scripts/rag_demo.py stats
```
Reports: total chunks, indexed books, formats, languages, index health.

### 6.3 Markdown Export
```bash
python scripts/rag_demo.py query "Late Antique senators" --export results.md
```
For Joplin, Obsidian, or any Markdown workflow.

---

## 7. Web UI (Streamlit, experimental)

Companion interface for users without Claude Desktop. Search with tag filtering, language selection, mode selection, context expansion, similarity threshold slider, and Markdown export. Positioned as secondary interface; primary interface is MCP + Claude Desktop.

---

## 8. Bibliography Export

Formats: BibTeX (`.bib`), RIS, EndNote, JSON, CSV. Filterable by author (partial name), tag, and publication year. Available via both MCP (`export_bibliography`) and CLI.

---

## 9. Architecture

### 9.1 Service Layer
`ArchillesService` is the central facade used by MCP server, Web UI, and CLI. Handles lazy initialization, stdout redirection for MCP safety, and cross-encoder orchestration.

### 9.2 Registry Pattern
Formal registries for parsers, chunkers, and embedders (`ParserRegistry`, `ChunkerRegistry`, `EmbedderRegistry`). New components implement the ABC and register at runtime. Foundation for Special Editions.

### 9.3 Privacy by Architecture
No network calls during normal operation. Only exceptions: initial BGE-M3 download (~2.2 GB) and optional reranker (~560 MB), both from Hugging Face on first run. No telemetry, no analytics.

### 9.4 Platform Support
Python 3.11+. Cross-platform: Windows (primary), macOS (including Apple Silicon MPS), Linux. All paths via `pathlib.Path`.

---

## 10. Configuration Reference

**`.archilles/config.json`** (inside Calibre library):

| Key | Default | Description |
|-----|---------|-------------|
| `enable_reranking` | `false` | Cross-encoder reranking |
| `reranker_device` | `"cpu"` | `"cpu"` or `"cuda"` |
| `rag_db_path` | `.archilles/rag_db` | Custom DB path |

**Environment variables:**

| Variable | Description |
|----------|-------------|
| `ARCHILLES_LIBRARY_PATH` | Path to library root — Calibre, Zotero, Obsidian, or folder (required) |
| `CALIBRE_LIBRARY_PATH` | Legacy alias |
| `RAG_DB_PATH` | Override LanceDB path |
| `CUDA_VISIBLE_DEVICES` | GPU selection |

---

*See [ARCHITECTURE.md](ARCHITECTURE.md) for technical implementation details.*
*See [DECISIONS.md](DECISIONS.md) for the rationale behind these choices.*
*See [USAGE.md](USAGE.md) for practical workflows.*
