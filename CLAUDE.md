# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ARCHILLES is a privacy-first, local-first RAG (Retrieval-Augmented Generation) system for semantic search across Calibre e-book libraries. It provides hybrid vector+BM25 search with academic-grade citations, MCP integration for Claude Desktop; it will provide MCP intergration for other LLMs soon, and finally a Streamlit web UI.

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
streamlit run scripts/web_ui.py
```

### MCP Server (Claude Desktop)
```bash
python mcp_server.py
```

## Conventions

### Language in code: English only

All source code — comments, docstrings, identifiers, log/error messages and test prose — is written in **English**. This keeps the public repository consistent and accessible to contributors who don't read German.

German is allowed only where it is **data, not code**:
- **User-facing / locale strings**: translations and language-specific content (e.g. `src/archilles/i18n.py`, the German locale entries in `kindle_provider.py`).
- **Docs under `docs/`**: `DECISIONS.md` (the German *Entscheidungsarchiv*), `ROADMAP.md`, etc. are intentionally German.

Note: parts of the codebase still carry German comments/docstrings from before this rule. New or touched code must be English; a repo-wide cleanup is a separate task.

## Architecture

Non-obvious constraints and entry points (the rest of the layout is best read from the code):

- **`src/calibre_db.py`** — Read-only access to Calibre's `metadata.db` (SQLite). This is an absolute boundary: never write to the Calibre library.
- **`src/service/archilles_service.py`** — Single facade used by MCP server, web UI, and CLI. Start here when adding new features.
- **`src/archilles/engine/`** — Core RAG engine (`ArchillesRAG` facade composing `Indexer`, `Searcher`, `PromptBuilder`). Start here for engine changes.
- **`src/calibre_mcp/server.py`** — MCP server. Carefully manages stdout/stderr: any stray write corrupts the JSON-RPC protocol.

### Search Architecture (Two-Stage)

1. **Hybrid Search** in LanceDB: dense vector (BGE-M3, semantic) + BM25 (keyword), fused via RRF
2. **Optional Cross-Encoder Reranking**: BAAI bge-reranker-v2-m3 rescores top-k candidates; gracefully disabled if not configured

Search modes: `hybrid` (default), `semantic`, `keyword`.

### Configuration

Runtime config at `.archilles/config.json` inside the Calibre library:
```json
{
  "enable_reranking": true,
  "reranker_device": "cpu",
  "rag_db_path": ".archilles/rag_db",
  "embedder": {
    "mode": "remote",
    "host": "http://192.168.1.50:8900",
    "port": 8900,
    "token": "…",
    "batch_size": 100,
    "use_gzip": true
  }
}
```

The optional `embedder` block supplies defaults for the `embed` command (Phase 2 of two-phase indexing); CLI flags override it. Omit it for local embedding.

Environment variable: `ARCHILLES_LIBRARY_PATH` (legacy: `CALIBRE_LIBRARY_PATH` also accepted).

## Registry Pattern

Parsers use a registry pattern (`parsers/registry.py`, built on the generic `BaseRegistry[T]` in `src/archilles/registry.py`) because parser selection is a real dispatch by file format. When adding a new extractor/parser, register it in `ParserRegistry` rather than modifying pipeline logic directly.

Chunkers and embedders are selected directly (chunker by frontmatter strategy in `pipeline._select_chunker`; embedder by profile in `pipeline._create_embedder_from_profile`). Their openness comes from the `TextChunker`/`TextEmbedder` ABCs — a new variant is a single class. (A config-driven embedder selection layer, e.g. local ↔ remote GPU via `config.json`, is a deferred idea, not yet implemented.)

## Chunk Schema

Non-obvious default: sections are filtered to `section_type == "main"` by default, which excludes front matter, bibliography and index noise from search results.

## Important Docs

- `docs/ARCHITECTURE.md` — Technical deep-dive
- `docs/internal/IMPLEMENTATION_STATUS.md` — Current implementation state
- `docs/internal/HANDOVER_2026-02-06.md` — Session handover notes
- `SETUP_GUIDE_FOR_WINDOWS.md` — Windows-specific setup
