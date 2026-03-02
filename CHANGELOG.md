# Changelog

All notable changes to Archilles are documented here.

## [0.9-beta] — 2026-03-02

First public release.

### Core features
- **Hybrid search** — dense vector (BGE-M3, 1024-dim) + BM25 keyword search, fused via Reciprocal Rank Fusion
- **Multilingual** — BGE-M3 supports 75+ languages; stop-word removal for EN, DE, FR, ES, IT, PT, NL, LA, RU, EL, HE, AR
- **Format support** — PDF (PyMuPDF + pdfplumber fallback), EPUB, AZW3, MOBI, TXT, HTML, DJVU; OCR fallback for scanned PDFs
- **Calibre integration** — reads Calibre metadata (tags, comments, ratings, custom fields) without touching the library
- **Annotation indexing** — Calibre Viewer highlights and notes are indexed alongside book content
- **MCP server** — 12 tools for Claude Desktop and other MCP clients (search, metadata, citations, annotations, stats)
- **Academic citations** — BibTeX, RIS, EndNote, JSON, CSV export; precise page-level citations
- **Cross-encoder reranking** — optional BAAI/bge-reranker-v2-m3 for higher-precision result ordering
- **Research interest boosting** — keyword-based scoring boost without re-indexing
- **Web UI** — Streamlit-based companion interface with similarity threshold slider
- **Hardware profiles** — `minimal` / `balanced` / `maximal` batch sizes; CUDA, Apple Silicon MPS, and CPU support

### Batch indexing
- Tag-filter, author-filter, and `--all` modes
- Checkpoint/resume with crash-safe progress tracking (`progress.db`)
- `--skip-existing` pre-filters already-indexed books before the loop (fast resume)
- `--cleanup-orphans` removes LanceDB entries for books deleted from Calibre
- `--prefer-format` selects PDF or EPUB when a book has both
- `--reindex-missing-labels` targets books without page number extraction
- Automatic exclusion of `exclude` and `Übersetzung` tags by default
- Backup rotation (every 50 books, 2 backups retained)

### Extraction quality
- Footer and header page number detection with footnote disambiguation
- Section classification (`main` / `front_matter` / `back_matter`) to filter bibliography noise
- Scanned PDF detection with per-page word-count heuristics
- Small-to-Big retrieval via `window_text` (surrounding context stored per chunk)
- `metadata_hash` deduplication prevents duplicate chunks on re-index

### Architecture
- LanceDB as sole vector store (ChromaDB removed February 2026)
- Registry pattern for parsers, chunkers, and embedders
- `ArchillesService` facade used by MCP server, Web UI, and CLI
- MCP server carefully isolates stdout/stderr to avoid JSON-RPC protocol corruption
