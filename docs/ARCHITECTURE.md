# ARCHILLES – Architecture

**Last updated:** March 2026 (source adapters, TOC-aware PDF chunking, running footer removal, DialogueChunker)

This document describes *how* ARCHILLES is built. For *why* these choices were made, see [DECISIONS.md](DECISIONS.md).

* * *

## System Overview

ARCHILLES is a local-first RAG (Retrieval-Augmented Generation) system that transforms Calibre e-book libraries into semantically searchable knowledge bases. It runs entirely on the user's machine—no cloud services, no telemetry, no data leaving the device unless the user explicitly connects to an external LLM.

The system is built around three principles: privacy by architecture (not by policy), academic-grade citations with verifiable source references, and modular extensibility through formal registries that anticipate future components without over-engineering the present.

```
                        ┌──────────────────────────┐
                        │      Calibre Library      │
                        │  (metadata.db + books +   │
                        │   annotations + comments) │
                        └────────────┬─────────────┘
                                     │
                          ┌──────────▼──────────┐
                          │    Calibre DB Layer  │
                          │   (read-only access) │
                          └──────────┬──────────┘
                                     │
                     ┌───────────────▼───────────────┐
                     │         Extractors Layer       │
                     │  ┌────────┐ ┌────────┐ ┌────┐ │
                     │  │  PDF   │ │  EPUB  │ │OCR │ │
                     │  │PyMuPDF │ │ebooklib│ │(T) │ │
                     │  └───┬────┘ └───┬────┘ └─┬──┘ │
                     └──────┼──────────┼────────┼────┘
                            │          │        │
                     ┌──────▼──────────▼────────▼────┐
                     │       Modular Pipeline         │
                     │  Parser → Chunker → Embedder   │
                     │  (Registry-based component     │
                     │   selection per profile)        │
                     └───────────────┬────────────────┘
                                     │
                    ┌────────────────▼────────────────┐
                    │         Storage Layer            │
                    │  ┌──────────────────────────┐   │
                    │  │  LanceDB ("chunks" table) │   │
                    │  │  book content, annotations│   │
                    │  │  calibre comments         │   │
                    │  │  BGE-M3 embeddings        │   │
                    │  │  (chunk_type field filters│   │
                    │  │   content vs annotations) │   │
                    │  └──────────────────────────┘   │
                    └────────────────┬────────────────┘
                                     │
                    ┌────────────────▼────────────────┐
                    │         Retriever Layer          │
                    │                                  │
                    │  Stage 1: LanceDB Hybrid Search  │
                    │    (dense vectors + BM25 FTS)    │
                    │              │                    │
                    │  Stage 2: Cross-Encoder Reranker │
                    │    (optional, BAAI bge-reranker)  │
                    └────────────────┬────────────────┘
                                     │
                    ┌────────────────▼────────────────┐
                    │        ArchillesService          │
                    │  (central business logic facade) │
                    └──┬─────────────┬─────────────┬──┘
                       │             │             │
                  ┌────▼────┐  ┌────▼────┐  ┌────▼────┐
                  │   MCP   │  │ Web UI  │  │   CLI   │
                  │ Server  │  │Streamlit│  │rag_demo │
                  └─────────┘  └─────────┘  └─────────┘
```

* * *

## Core Components

### 1\. Source Adapter Layer (`src/adapters/`)

ARCHILLES supports multiple library backends through a common adapter interface. Each adapter implements `list_books()`, `get_metadata()`, and `resolve_file()`. The batch indexer auto-detects the appropriate adapter from the library structure.

| Adapter | Backend | Detection |
| --- | --- | --- |
| `CalibreAdapter` | Calibre library (`metadata.db`) | Default, detects `metadata.db` |
| `ZoteroAdapter` | Zotero library (`zotero.sqlite`) | Detects `zotero.sqlite` |
| `ObsidianAdapter` | Obsidian vault (Markdown + YAML frontmatter) | Detects `.obsidian/` directory |
| `FolderAdapter` | Plain directory of files | Fallback when no specific backend detected |

The adapter layer sits above the Calibre DB layer and generalizes library access. For Calibre libraries, the `CalibreAdapter` delegates to `calibre_db.py`.

### 1b\. Calibre Database Layer (`src/calibre_db.py`)

Read-only interface to Calibre's `metadata.db`. This component never modifies the database—a firm architectural boundary documented in DECISIONS.md (ADR-005).

**What it extracts:**

Per book: title, author(s), publisher, publication date, ISBN/identifiers, language, series information, file formats and paths, cover path, and reading progress. Tags and custom columns are extracted generically—the system discovers and indexes any user-defined custom fields without manual configuration.

The comments field deserves special attention. In many researchers' Calibre libraries, comments contain far more than publisher blurbs: NotebookLM deep-dive analyses, personal reading notes, collected reviews, and structured research summaries. ARCHILLES treats this as a first-class data source, routing it to the separate annotations database (see Storage Architecture below).

**Custom field discovery** works by querying Calibre's `custom_columns` table at startup and mapping each field to the appropriate search metadata. This means a user who has created fields like `research_project`, `source_reliability`, or `century` gets those fields indexed automatically without touching any configuration.

### 2\. Extractors Layer (`src/extractors/`)

Each extractor is responsible for turning a book file into structured text with metadata. The extractors are modular and independently deployable, coordinated by a `UniversalExtractor` that delegates to the appropriate format-specific extractor. A `FormatDetector` identifies file types, and a `LanguageDetector` (Lingua, 75+ languages) assigns language codes to extracted text.

**Available extractors:**

| Extractor | File | Formats | Notes |
| --- | --- | --- | --- |
| `PDFExtractor` | `pdf_extractor.py` | PDF | Primary: PyMuPDF (fitz); fallback: pdfplumber; OCR path |
| `EPUBExtractor` | `epub_extractor.py` | EPUB 2/3 | ebooklib with custom TOC parser |
| `TXTExtractor` | `txt_extractor.py` | TXT | Plain text with encoding detection |
| `HTMLExtractor` | `html_extractor.py` | HTML | HTML documents |
| `OCRExtractor` | `ocr_extractor.py` | Scanned PDFs | Tesseract baseline; VLM upgrade path prepared |
| `CalibreConverter` | `calibre_converter.py` | MOBI, DJVU, etc. | Delegates to Calibre's `ebook-convert` |

Common infrastructure: `base.py` (base class), `models.py` (dataclasses), `exceptions.py` (error types).

#### PDF Extractor (`pdf_extractor.py`)

Primary extractor for PDF files, built on PyMuPDF (fitz). PDF is the preferred format because it provides reliable page number mapping—essential for citable references.

Key capabilities: CropBox filtering eliminates headers, footers, and running page numbers before the text reaches the chunker, which significantly improves embedding quality. Page label extraction maps printed page numbers (which may differ from internal PDF page indices) to chunks, enabling citations like "p. 47" that match what a reader sees in the physical or digital book. Footer detection with footnote disambiguation ensures that footnotes are preserved while page-bottom noise is removed.

**TOC-aware chunking** (March 2026): `_build_page_toc_map(toc)` maps the PDF's table of contents to page ranges. Level-1 entries become `chapter`, level-2+ entries become `section_title`. Junk TOCs from scanner PDFs are automatically detected and ignored (pattern matching for artifacts like "scan 1", threshold checks for entries count and page diversity). `_section_type_from_toc_title()` derives `section_type` from TOC titles with comprehensive DE/EN keyword matching, falling back to the existing position heuristic when no TOC is available.

**Running footer removal**: `_detect_running_footers()` mirrors the existing header detection but targets the last 3 lines per page. Uses a higher occurrence threshold (5% of pages, minimum 10) to avoid false positives with variable content lines.

The multi-tier fallback system activates pdfplumber when PyMuPDF's extraction quality falls below threshold (measured by character density and encoding coherence). For scanned PDFs without embedded text, the system falls through to the OCR path.

#### EPUB Extractor (`epub_extractor.py`)

Built on ebooklib with custom TOC parsing. EPUBs provide richer structural information than PDFs: the table of contents maps directly to chapter boundaries, and the internal HTML structure enables section-level metadata extraction.

Section metadata classification automatically labels content as Front Matter (foreword, table of contents), Main Content (the actual text, including introductions), or Back Matter (bibliography, index, appendices). Classification uses only semantically meaningful titles (H1 text or TOC entry titles) — never raw EPUB filenames, which caused false positives (e.g., `index_split_001.html` matching "index"). Introduction/Einleitung is deliberately classified as main_content, not front_matter. This classification powers the `section_filter` parameter in search—by default set to `'main'`, which excludes bibliography and index noise from results.

#### OCR Extractor (`ocr_extractor.py`)

Tesseract serves as the baseline for modern printed text. The interface is designed for drop-in replacement with VLM-based OCR systems (LightOnOCR-2, GOT-OCR 2.0) as they mature. The `ArchillesService` exposes `ocr_backend` configuration (auto/tesseract/lighton/olmocr) to select backends.

### 3\. Modular Pipeline (`src/archilles/`)

The `src/archilles/` package implements the modular processing pipeline with formal Registry patterns. This is the core infrastructure for document processing, separate from the extractors which handle raw text extraction.

#### Architecture: Parser → Chunker → Embedder

The pipeline is orchestrated by `ModularPipeline` (`pipeline.py`), which chains three stages:

1.  **Parsers** (`parsers/`): Convert files into `ParsedDocument` objects with structural metadata. `PyMuPDFParser` and `EPUBParser` are registered in `ParserRegistry`.
    
2.  **Chunkers** (`chunkers/`): Split parsed text into `TextChunk` objects. Three chunkers registered in `ChunkerRegistry`:
    - `FixedSizeChunker`: Simple token/character-based splitting
    - `SemanticChunker`: Sentence-boundary-aware, with Markdown heading detection (H1/H2 force chunk breaks) and oversized paragraph splitting
    - `DialogueChunker`: Specialized for chat/Q&A exports (ChatGPT, Gemini, Grok, NotebookLM). Recognizes turn markers (`## User`, `**Q:**`, etc.) and chunks per turn or turn-pair, preserving `speaker` metadata.
    Configuration via `ChunkerConfig` (chunk_size, chunk_overlap, size_unit, respect_sentences, respect_paragraphs).
    
3.  **Embedders** (`embedders/`): Generate vector representations. `BGEEmbedder` supports bge-small (384 dim), bge-base (768 dim), and bge-m3 (1024 dim, multilingual). Registered in `EmbedderRegistry`.
    

Each registry provides `register()`, `get()`, `list_*()`, and `get_default()`. Factory functions like `create_chunker_for_profile()` select and configure components based on hardware profiles.

#### Hardware Profiles (`profiles.py`)

Three pre-defined profiles adapt indexing to available hardware. All use BGE-M3 for consistent embedding quality—only batch size and speed differ:

| Profile | GPU VRAM | Batch Size | Speed | Use Case |
| --- | --- | --- | --- | --- |
| `minimal` | 4–6 GB | 8   | ~2 min/book | Quadro T1000, GTX 1650 |
| `balanced` | 8–12 GB | 32  | ~30s/book | RTX 3060, RTX 2070 |
| `maximal` | 16+ GB | 64  | ~15s/book | RTX 3090, RTX 4080 |

Hardware detection (`hardware.py`) auto-selects the appropriate profile when none is specified.

#### Indexing Checkpoints (`indexer/checkpoint.py`)

`IndexingCheckpoint` provides checkpoint-based resume for long-running batch operations, tracking per-book progress (chunks processed, errors, timing) with JSON persistence.

### 4\. Storage Layer (`src/storage/`)

#### LanceDB Store (`lancedb_store.py`)

The central storage backend for book content. `LanceDBStore` provides:

- **Hybrid search**: Native vector + BM25 full-text search with RRF (Reciprocal Rank Fusion) reranking via `lancedb.rerankers.RRFReranker`
- **Vector search**: Pure semantic similarity
- **Full-text search**: BM25 keyword matching for exact terms
- **SQL-like filtering**: By book_id, calibre_id, section_type, chunk_type, language
- **Schema migration**: Automatic addition of new columns to existing tables (page_label, window_text, parent_id, etc.)
- **IVF-PQ indexing**: For corpora exceeding 256 chunks, with configurable partitions

**Database schema** (LanceDB table "chunks"):

| Column | Type | Purpose |
| --- | --- | --- |
| `id` | str | Unique chunk identifier |
| `text` | str | Chunk text content |
| `vector` | float\[1024\] | BGE-M3 embedding |
| `book_id`, `book_title`, `author`, `publisher`, `year` | —   | Book metadata |
| `calibre_id` | int | Calibre internal book ID |
| `tags`, `language` | str | Calibre tags, detected language |
| `chunk_index`, `chunk_type` | —   | Position and type (content/parent/child/calibre_comment/annotation) |
| `page_number`, `page_label` | —   | Physical page + printed label ("xiv", "62") |
| `chapter`, `section`, `section_title`, `section_type` | —   | Structural metadata |
| `char_start`, `char_end`, `window_text` | —   | Context expansion (Small-to-Big) |
| `parent_id` | str | Parent chunk reference (hierarchical chunking) |
| `source_file`, `format`, `indexed_at` | —   | Technical metadata |

The `add_processed_documents()` method bridges `ProcessedDocument` objects from the modular pipeline directly into LanceDB storage.

#### Annotations Storage (LanceDB, unified)

Annotations (highlights, notes from Calibre's E-book Viewer and PDF readers) are stored directly in the main LanceDB `chunks` table using `chunk_type='annotation'`. Calibre book comments use `chunk_type='calibre_comment'`. Both use the same BGE-M3 embeddings (1024 dimensions) as book content chunks, enabling cross-type hybrid search without model incompatibility.

The `search_annotations` MCP tool queries both types via the `'annotations_and_comments'` composite filter in `LanceDBStore._build_filter()`. Annotation indexing happens automatically as Phase 2 of the regular `index_book()` pipeline — no separate indexing step required.

**Annotation infrastructure:**
- `src/calibre_mcp/annotations.py` — File-based annotation extraction, hash-to-book mapping (100+ path variants), text/keyword search (text-only fallback when LanceDB unavailable)
- `src/calibre_mcp/calibre_analyzer.py` — Calibre metadata analysis and statistics


### 5\. Retriever Layer (`src/retriever/`)

#### Search Logic

The hybrid search logic is implemented across two layers:

- **`LanceDBStore.hybrid_search()`** handles the database-level search: vector similarity + BM25 full-text search with RRF fusion, section/chunk/language filtering
- **`archillesRAG.query()`** in `scripts/rag_demo.py` orchestrates the high-level search: mode selection (semantic/keyword/hybrid), exact phrase matching, tag filtering, result diversification (max_per_book), minimum similarity thresholds, and context expansion

There is no separate `hybrid.py` file—the retrieval logic is distributed between the storage layer and the RAG class, unified through the service layer.

**Section filtering** applies at query time: `section_filter='main'` (the default) restricts results to main body content, excluding front matter, back matter, bibliography, and index sections. Users can override this for specific searches where those sections are relevant.

**Smart boosting** applies configurable multipliers: Calibre comments matches receive a 1.2x boost, tag matches 1.15x. These weights are tunable in configuration.

#### Cross-Encoder Reranking (`reranker.py`, optional)

When enabled, the top candidates from Stage 1 are re-scored by a cross-encoder model (BAAI/bge-reranker-v2-m3, configurable) that evaluates each query-document pair jointly rather than independently. This produces significantly more accurate relevance ranking at the cost of additional inference time. The reranker runs on CPU by default (since GPU is typically occupied by BGE-M3 embeddings) and falls back gracefully if system memory is insufficient. First use downloads the model (~560 MB).

Configuration via `.archilles/config.json`:

```json
{
  "enable_reranking": true,
  "reranker_device": "cpu"
}
```

### 6\. Service Layer (`src/service/archilles_service.py`)

Introduced in February 2026 to solve a growing consistency problem: the Web UI, MCP server, and CLI all imported the RAG class directly, meaning every change to search logic had to be replicated in three places.

`ArchillesService` is the central facade that all consumers use. It exposes:

- `search()` — with mode, filters, reranking, diversification, similarity thresholds
- `search_with_citations()` — generates XML-structured prompts with citation metadata
- `get_index_status()` — database statistics (chunks, books, formats, languages)
- `get_book_list()` — all indexed books with chunk counts
- `get_chunk_by_id()` — single chunk retrieval (for parent-child lookup)

The service handles lazy initialization (RAG loading deferred to first use), stdout redirection (critical for MCP JSON-RPC safety), and cross-encoder reranking orchestration. When reranking is enabled, the service fetches more raw results from the RAG layer, applies the cross-encoder, then diversifies.

### 7\. Client Interfaces

#### MCP Server (`src/calibre_mcp/server.py`, entry point: `mcp_server.py`)

The primary interface. Implements the Model Context Protocol for integration with Claude Desktop and other MCP-compatible AI assistants. Communication uses JSON-RPC 2.0 over stdio, with the entry point `mcp_server.py` in the project root.

**Exposed tools** (10 tools via `create_mcp_tools()`):

| Tool | Description |
| --- | --- |
| `search_books_with_citations` | Hybrid search over book content with citation-ready output |
| `search_annotations` | Hybrid search in LanceDB across highlights, notes, and Calibre comments |
| `list_annotated_books` | Lists all books with indexed annotations |
| `get_book_annotations` | Get annotations for a specific book by path |
| `get_book_details` | Full metadata for a specific Calibre book ID |
| `export_bibliography` | Bibliography in BibTeX, RIS, EndNote, JSON, CSV |
| `detect_duplicates` | Find duplicate books by title+author, ISBN, or exact title |
| `list_tags` | All Calibre tags with book counts |
| `compute_annotation_hash` | Compute Calibre annotation hash for a book path |
| `get_doublette_tag_instruction` | Helper for Calibre duplicate tagging workflow |

Each search result includes sufficient metadata for academic citation: author, title, year, and either page number/page label (PDF) or chapter/section (EPUB).

#### Web UI (`scripts/web_ui.py`)

Streamlit-based interface for users without Claude Desktop. Provides search with tag filtering, language selection, mode selection (semantic/keyword/hybrid), context expansion, and Markdown export. Positioned as a companion tool, not the primary interface.

#### CLI (`scripts/rag_demo.py`, `scripts/batch_index.py`)

`rag_demo.py` provides the `archillesRAG` class (the core RAG implementation) and a CLI for single-book indexing, search queries, and result export.

`batch_index.py` handles batch indexing operations with tag-based filtering (`--tag`), author filtering (`--author`), dry-run previews, skip-existing for interrupted sessions, forced re-indexing (`--force`), hardware profile selection (`--profile`), checkpoint-based resume for long-running operations, format preference (`--prefer-format pdf|epub|mobi|azw3`), and orphan cleanup (`--cleanup-orphans` removes index entries for books deleted from Calibre).

* * *

## Data Flow

### Indexing Flow

```
Book file (PDF/EPUB/TXT/HTML/...)
        │
        ▼
FormatDetector → select appropriate Extractor
        │
        ▼
Text extraction with metadata enrichment
  • PDF: CropBox filtering, page label extraction, footnote detection,
         TOC-to-page mapping (chapter/section_title), running footer removal
  • EPUB: TOC parsing, section classification (front/main/back matter, title-based)
  • TXT: YAML frontmatter stripping (for Obsidian vault imports)
  • Other: CalibreConverter → intermediate format → extraction
        │
        ▼
Calibre metadata lookup (read-only from metadata.db)
  • title, author, year, publisher, tags, custom fields
  • language auto-detection via Lingua on extracted text
        │
        ▼
Chunking (SemanticChunker or FixedSizeChunker via Registry)
  • Configurable size (default: 512 tokens in profiles, 1000 in legacy)
  • window_text for context expansion
  • section_type assigned per chunk
  • page_label mapped per chunk (PDF)
        │
        ▼
BGE-M3 embedding generation (1024 dimensions)
  • GPU-accelerated when available (profile-based batch size)
  • Automatic CPU fallback
        │
        ▼
LanceDB storage
  • archilles_books table: full-text chunks + embeddings + metadata
  • IVF-PQ + FTS indexes created after bulk ingestion
```

### Search Flow

```
User query (natural language)
        │
        ▼
ArchillesService.search()
        │
        ├──── LanceDBStore ──────────────────────┐
        │                                         │
        ▼                                         ▼
   BGE-M3 encode query              BM25 keyword expansion
        │                                         │
        └──────────┬──────────────────────────────┘
                   │
                   ▼
        LanceDB native hybrid search
        (dense + sparse vector fusion via RRFReranker)
                   │
                   ▼
        Section filtering (default: main only)
        Tag filtering, language filtering
                   │
                   ▼
        [Optional] Cross-encoder reranking
        (BAAI/bge-reranker-v2-m3, top candidates)
                   │
                   ▼
        Per-book diversification (max_per_book)
        Minimum similarity threshold
                   │
                   ▼
        Context expansion (Small-to-Big)
        Retrieve window_text for surrounding passages
                   │
                   ▼
        Formatted results with citations
        → MCP: structured JSON with source metadata
        → CLI: formatted text or Markdown export
        → Web UI: interactive result display
```

* * *

## Technology Stack

| Component | Implementation | Notes |
| --- | --- | --- |
| Vector database | LanceDB | Native hybrid search, IVF-PQ, Arrow-based |
| Annotations | LanceDB (same table) | chunk_type='annotation'/'calibre_comment' in chunks table |
| Embeddings (all) | BGE-M3 (BAAI) | 1024 dimensions, multilingual, GPU |
| Reranker | bge-reranker-v2-m3 | Optional cross-encoder, CPU default |
| PDF extraction | PyMuPDF (fitz) | Primary; pdfplumber as fallback |
| EPUB extraction | ebooklib | With custom TOC parser |
| OCR | Tesseract | Baseline; VLM upgrade path prepared |
| Language detection | Lingua | 75+ languages, ISO 639-1 codes |
| MCP protocol | JSON-RPC 2.0 / stdio | Claude Desktop integration |
| Web UI | Streamlit | Companion interface |
| Configuration | JSON | `.archilles/config.json` in library |
| Runtime | Python 3.11+ | Cross-platform: macOS, Windows/WSL, Linux |

* * *

## Directory Structure

```
archilles/
├── mcp_server.py                  # MCP entry point (Claude Desktop calls this)
├── requirements.txt
├── README.md
│
├── src/
│   ├── adapters/                  # Source library backends
│   │   ├── __init__.py            # get_adapter() auto-detection
│   │   ├── base.py                # BaseAdapter ABC
│   │   ├── calibre_adapter.py     # Calibre library
│   │   ├── zotero_adapter.py      # Zotero library
│   │   ├── obsidian_adapter.py    # Obsidian vault (Markdown + YAML)
│   │   └── folder_adapter.py      # Plain directory fallback
│   │
│   ├── archilles/                 # Modular pipeline infrastructure
│   │   ├── pipeline.py            # ModularPipeline orchestration
│   │   ├── profiles.py            # Hardware profiles (minimal/balanced/maximal)
│   │   ├── hardware.py            # Hardware detection (GPU, VRAM)
│   │   ├── parsers/
│   │   │   ├── base.py            # DocumentParser ABC, ParsedDocument
│   │   │   ├── pymupdf_parser.py  # PDF parser
│   │   │   ├── epub_parser.py     # EPUB parser
│   │   │   └── registry.py        # ParserRegistry
│   │   ├── chunkers/
│   │   │   ├── base.py            # TextChunker ABC, TextChunk, ChunkerConfig
│   │   │   ├── fixed.py           # FixedSizeChunker
│   │   │   ├── semantic.py        # SemanticChunker (sentence + heading aware)
│   │   │   ├── dialogue.py        # DialogueChunker (chat/Q&A exports)
│   │   │   └── registry.py        # ChunkerRegistry
│   │   ├── embedders/
│   │   │   ├── base.py            # TextEmbedder ABC, EmbeddingResult
│   │   │   ├── bge.py             # BGEEmbedder (bge-small/base/m3)
│   │   │   └── registry.py        # EmbedderRegistry
│   │   └── indexer/
│   │       └── checkpoint.py      # IndexingCheckpoint (resume support)
│   │
│   ├── extractors/                # Text extraction from book files
│   │   ├── base.py                # BaseExtractor interface (+ oversized para splitting)
│   │   ├── universal_extractor.py # Delegates to format-specific extractors
│   │   ├── pdf_extractor.py       # PyMuPDF: CropBox, page labels, TOC mapping, footer removal
│   │   ├── epub_extractor.py      # ebooklib: TOC + section metadata (title-based classification)
│   │   ├── txt_extractor.py       # Plain text (+ YAML frontmatter stripping)
│   │   ├── html_extractor.py      # HTML document extraction
│   │   ├── ocr_extractor.py       # Tesseract OCR integration
│   │   ├── calibre_converter.py   # Calibre ebook-convert bridge
│   │   ├── format_detector.py     # File format identification
│   │   ├── language_detector.py   # Lingua-based language detection
│   │   ├── models.py              # ChunkMetadata, ExtractionMetadata, ExtractedText
│   │   └── exceptions.py          # ExtractionError hierarchy
│   │
│   ├── storage/
│   │   └── lancedb_store.py       # LanceDBStore (all chunks: content + annotations)
│   │
│   ├── retriever/
│   │   └── reranker.py            # CrossEncoderReranker (optional)
│   │
│   ├── service/
│   │   └── archilles_service.py   # ArchillesService (central facade)
│   │
│   ├── calibre_mcp/               # MCP server + annotation infrastructure
│   │   ├── server.py              # CalibreMCPServer + create_mcp_tools()
│   │   ├── annotations.py         # Annotation extraction, hash mapping, text search
│   │   └── calibre_analyzer.py    # Library statistics and analysis
│   │
│   └── calibre_db.py              # Read-only Calibre metadata.db access
│
├── scripts/
│   ├── rag_demo.py                # archillesRAG class + CLI (search, index, export)
│   ├── web_ui.py                  # Streamlit Web UI
│   ├── batch_index.py             # Batch indexing with tag/author filters
│   └── chunk_inspector.py         # Diagnostic: chunk quality, boundaries, TOC alignment
│
├── .archilles/                    # Per-library data (inside library folder)
│   ├── config.json                # User configuration
│   └── rag_db/                    # LanceDB database (all chunks: content + annotations)
│
└── docs/
    ├── DECISIONS.md               # Strategic + technical decision log
    ├── ARCHITECTURE.md            # This document
    └── ...
```

* * *

## Configuration Reference

All configuration is stored in `.archilles/config.json` inside the user's Calibre library directory. This keeps configuration portable with the library.

| Key | Default | Description |
| --- | --- | --- |
| `enable_reranking` | `false` | Enable cross-encoder reranking (Stage 2) |
| `reranker_device` | `"cpu"` | Device for reranker (`"cpu"` or `"cuda"`) |
| `rag_db_path` | `.archilles/rag_db` | Custom path for LanceDB database |
| `library_path` | (env var) | Override for ARCHILLES_LIBRARY_PATH |

Environment variables:

| Variable | Default | Description |
| --- | --- | --- |
| `ARCHILLES_LIBRARY_PATH` | (required) | Path to library root (Calibre, Zotero, or folder) |
| `CALIBRE_LIBRARY_PATH` | — | Legacy alias for ARCHILLES_LIBRARY_PATH |
| `RAG_DB_PATH` | `$ARCHILLES_LIBRARY_PATH/.archilles/rag_db` | Override LanceDB location |
| `CUDA_VISIBLE_DEVICES` | —   | GPU selection for embeddings/reranking |

* * *

## Security and Privacy

ARCHILLES makes no network calls during normal operation. The only exceptions are the initial download of the BGE-M3 model (~2.2 GB) and optionally the cross-encoder model (~560 MB), both fetched from Hugging Face on first run.

There is no telemetry, no analytics, no usage tracking. The system reads Calibre's metadata.db but never writes to it. All ARCHILLES data lives in the `.archilles` directory within the user's Calibre library folder, making it easy to back up, move, or delete.

When connected to an external LLM via MCP, the search results (text chunks with metadata) are sent to the LLM—this is the intended use case. But the user controls which LLM they connect to, and the connection is initiated by the user's MCP client (e.g., Claude Desktop), not by ARCHILLES.

* * *

## Extension Points

The architecture is designed with explicit extension zones for future development:

**Extractors:** New format support (specialized XML schemas, proprietary formats) can be added by implementing the `BaseExtractor` interface and registering with `UniversalExtractor`. `CalibreConverter` already bridges to 30+ formats via Calibre's ebook-convert.

**Pipeline components:** The Registry pattern in `src/archilles/` allows runtime registration of new parsers, chunkers, and embedders. New components implement the ABC (`DocumentParser`, `TextChunker`, `TextEmbedder`) and register via the corresponding registry.

**Embedding models:** BGE-M3 is the current default. The `BGEEmbedder` already supports multiple BGE variants; evaluation of multilingual-e5 and jina-embeddings-v3 is planned for Q2 2026.

**Chunking strategies:** `SemanticChunker` (sentence-boundary-aware) and `FixedSizeChunker` are available. Parent-child hierarchies (index small chunks for precision, deliver large context for comprehension) are supported via `parent_id` and `chunk_type` fields.

**Search backends:** The LanceDB abstraction supports plugging in alternative search strategies. Graph RAG via LightRAG is planned for evaluation in Q2 2026.

**The `.archilles` folder** serves as the defined extension zone per library. Configuration, databases, cached models, and any future plugin data live here—cleanly separated from Calibre's own data.

* * *

## Platform Compatibility

ARCHILLES targets cross-platform operation across macOS, Windows (native and WSL), and Linux. Key implementation rules:

All file paths use `pathlib.Path`, never string concatenation. All file I/O defaults to UTF-8 encoding. Dependencies are chosen for platform-agnostic availability—no OS-specific libraries in the core stack.

* * *

*For the rationale behind these architectural decisions, see [DECISIONS.md](DECISIONS.md).*
*For user-facing documentation, see the [README](../README.md).*
