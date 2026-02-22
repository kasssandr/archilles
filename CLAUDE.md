# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ARCHILLES is a privacy-first, local-first RAG (Retrieval-Augmented Generation) system for semantic search across Calibre e-book libraries. It provides hybrid vector+BM25 search with academic-grade citations, MCP integration for Claude Desktop, and a Streamlit web UI.

## Commands

### Installation
```bash
pip install -r requirements.txt
```

### Indexing
```bash
python scripts/rag_demo.py index "/path/to/book.pdf" --book-id "AuthorName"
python scripts/batch_index.py --tag "Your-Tag" [--dry-run] [--skip-existing]
```

### Searching
```bash
python scripts/rag_demo.py query "search term" [--mode hybrid|semantic|keyword]
python scripts/rag_demo.py query "text" --language de --tag-filter History
python scripts/rag_demo.py stats
python scripts/rag_demo.py list-indexed
```

### Web UI
```bash
python scripts/web_ui.py
```

### MCP Server (Claude Desktop)
```bash
python mcp_server.py
```

### Code Quality
```bash
black src/ scripts/    # formatting
flake8 src/ scripts/   # linting
pytest                 # tests
```

## Architecture

The system follows a layered pipeline:

```
Calibre Library (read-only SQLite)
    ↓
Extractors (PDF/EPUB/TXT/HTML/MOBI/DJVU/OCR)
    ↓
Modular Pipeline: ParserRegistry → ChunkerRegistry → EmbedderRegistry
    ↓
LanceDB (hybrid: dense vectors + BM25 FTS)
    ↓
Retriever (RRF fusion + optional cross-encoder reranking)
    ↓
ArchillesService (central facade)
    ↓
Consumers: MCP Server | Web UI (Streamlit) | CLI
```

### Key Modules

- **`src/calibre_db.py`** — Read-only access to Calibre's `metadata.db` (SQLite). This is an absolute boundary: never write to the Calibre library.
- **`src/extractors/`** — Format-specific extractors. PDF uses PyMuPDF primary with pdfplumber fallback. EPUB uses ebooklib with TOC-based section classification.
- **`src/archilles/pipeline.py`** — `ModularPipeline` orchestrates Parser → Chunker → Embedder using registry-based components.
- **`src/storage/lancedb_store.py`** — LanceDB backend. Stores 1024-dim BGE-M3 vectors with rich metadata. Two tables: `chunks` (main content) and `annotations` (user highlights/notes).
- **`src/service/archilles_service.py`** — Single facade used by MCP server, web UI, and CLI. Start here when adding new features.
- **`src/calibre_mcp/server.py`** — MCP server exposing 10 tools (search, metadata, citations, annotations, stats). Carefully manages stdout/stderr to avoid JSON-RPC protocol corruption.
- **`mcp_server.py`** — Entry point for Claude Desktop MCP integration.
- **`scripts/rag_demo.py`** — Primary CLI (2,479 lines). Index, query, stats, list-indexed.

### Search Architecture (Two-Stage)

1. **Hybrid Search** in LanceDB: dense vector (BGE-M3, semantic) + BM25 (keyword), fused via RRF
2. **Optional Cross-Encoder Reranking**: BAAI bge-reranker-v2-m3 rescores top-k candidates; gracefully disabled if not configured

Search modes: `hybrid` (default), `semantic`, `keyword`.

### Embeddings

BGE-M3 via sentence-transformers: 1024 dimensions, multilingual (75+ languages). Three hardware profiles in `src/archilles/profiles.py`: `minimal` (batch=8), `balanced` (batch=16), `maximal` (batch=32).

### Configuration

Runtime config at `.archilles/config.json` inside the Calibre library:
```json
{
  "enable_reranking": true,
  "reranker_device": "cpu",
  "rag_db_path": ".archilles/rag_db"
}
```

Environment variable: `CALIBRE_LIBRARY_PATH` (defaults to `D:/Calibre-Bibliothek` on Windows).

## Registry Pattern

Parsers, chunkers, and embedders all use a registry pattern (`registry.py` in each subpackage). When adding a new extractor or chunker, register it in the appropriate registry rather than modifying pipeline logic directly.

## Chunk Schema

Each chunk stored in LanceDB includes: calibre_id, title, author, tags, language, page_number, page_label, section_type (`main`/`front_matter`/`back_matter`), section_title, window_text (for Small-to-Big retrieval), and metadata_hash for deduplication. Sections are filtered to `main` by default to exclude bibliography/index noise.

## Important Docs

- `docs/ARCHITECTURE.md` — Technical deep-dive
- `docs/internal/IMPLEMENTATION_STATUS.md` — Current implementation state
- `docs/internal/HANDOVER_2026-02-06.md` — Session handover notes
- `SETUP_GUIDE_FOR_WINDOWS.md` — Windows-specific setup
