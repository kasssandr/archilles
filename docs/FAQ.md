# Frequently Asked Questions

## General

### What is Archilles?

Archilles is a semantic search system for Calibre libraries. It uses RAG (Retrieval-Augmented Generation) technology to let you search your books by meaning, not just keywords. Ask a natural-language question and get relevant passages with full citations — from across your entire library, in any language.

### Is it free?

Yes. Archilles core is MIT licensed and free to use. Future "Special Editions" (discipline-specific extensions) may be offered as commercial add-ons. The core will always remain free and open source.

### Does it work offline?

Yes. Everything runs locally on your machine. The only network access is downloading the BGE-M3 embedding model on first run (~2.2 GB, cached permanently afterwards). Once downloaded, Archilles works fully offline.

### Do you collect any data?

No. Zero telemetry, no analytics, no tracking of any kind. Your library and your research stay on your machine.

---

## Installation

### What are the system requirements?

- Python 3.11 or higher
- 8 GB RAM minimum (16 GB recommended for large libraries)
- ~5 GB free disk space (model ~2.2 GB + index storage)
- Calibre with an existing library

See [INSTALLATION.md](INSTALLATION.md) for the full guide.

### Does it work on Windows, macOS, and Linux?

**Windows** is the primary supported platform (tested on Windows 11). **macOS and Linux** should work — the code is cross-platform — but are not officially tested. If you run into platform-specific issues, please open a GitHub issue.

### Does it work on Apple Silicon (M1/M2/M3/M4)?

Yes. Archilles automatically detects Apple MPS (Metal Performance Shaders) and uses it for GPU-accelerated indexing on Apple Silicon Macs. No configuration needed.

### Can I use it without Claude Desktop?

Yes. The command-line interface (`scripts/rag_demo.py`) works completely standalone. The MCP integration for Claude Desktop is optional — it's the recommended way to use Archilles, but not required.

---

## Indexing

### How long does indexing take?

It depends on your hardware and book length:

| Hardware | Typical speed |
|----------|--------------|
| NVIDIA GPU (≥4 GB VRAM) | ~2 min/book |
| Apple Silicon (MPS) | ~3–5 min/book |
| CPU only | ~15 min/book |

The first run also downloads the BGE-M3 model (~2.2 GB). After that, only the book processing time applies.

### Does indexing modify my Calibre library?

No. Archilles reads from Calibre but never writes to it. Your Calibre library and its `metadata.db` are strictly read-only.

### What happens if indexing is interrupted?

Nothing is lost. LanceDB writes are atomic per chunk. Use `--skip-existing` to resume where you left off:
```bash
python scripts/batch_index.py --tag "History" --skip-existing
```

### Can I index books not in Calibre?

Not currently. Archilles requires the Calibre library structure (it reads metadata directly from Calibre's `metadata.db`).

### What file formats are supported?

PDF (primary), EPUB, MOBI, DJVU, HTML, TXT, and more — 30+ formats via PyMuPDF and format-specific extractors. Scanned PDFs are supported via Tesseract OCR (Linux requires `tesseract-ocr` installed separately).

---

## Search

### Which search mode should I use?

- **Hybrid** (default): Best for most queries — combines semantic and keyword search
- **Semantic**: Better for broad concepts, thematic searches, and cross-language queries
- **Keyword**: Best for exact names, dates, technical terms, and Latin phrases

### What languages are supported?

75+ languages with automatic detection. BGE-M3 is multilingual — you can search in German, English, Latin, Greek, French, or any combination without changing settings. Use `--language la` to restrict results to a specific language.

### Why isn't my search finding results?

Common reasons:
1. The book hasn't been indexed yet — run `rag_demo.py stats` to see what's in the index
2. Wrong language filter — try removing `--language`
3. Too-specific a query — try hybrid mode or broaden the phrasing
4. The passage is in a bibliography, index, or front matter — these are excluded by default to reduce noise

### Can I search my annotations and highlights?

Yes. Annotations (Calibre highlights and notes) and Calibre comments are indexed as separate chunk types and searchable via `search_annotations` in the MCP interface, or via `query --mode hybrid` in the CLI.

### Can I search multiple libraries?

Not currently. Multi-library support is planned for a future release.

---

## Technical

### Which embedding model does it use?

BGE-M3 (`BAAI/bge-m3`) — state-of-the-art multilingual embeddings with 1024 dimensions. It handles 75+ languages and performs well on both short and long texts.

### Does it use GPU acceleration?

Yes, automatically:
- **NVIDIA CUDA**: detected and used automatically if PyTorch with CUDA is installed
- **Apple Silicon MPS**: detected and used automatically on M1/M2/M3/M4 Macs
- **CPU fallback**: always available if no GPU is detected

### Where is the vector database stored?

By default in `.archilles/rag_db/` inside your Calibre library folder. The path is configurable via `.archilles/config.json`:
```json
{ "rag_db_path": "/custom/path/to/rag_db" }
```

### Does it support cross-encoder reranking?

Yes, optionally. Enable it in `.archilles/config.json`:
```json
{ "enable_reranking": true }
```
This downloads an additional ~560 MB model (`bge-reranker-v2-m3`) and improves result ranking quality. Disabled by default.

---

## Privacy & Legal

### Is my library data sent anywhere?

No. All processing — text extraction, embedding, search — happens locally on your machine. Nothing is uploaded anywhere.

### Is it legal to index copyrighted books?

Indexing for personal research use is generally covered by fair use / fair dealing in most jurisdictions. You are responsible for compliance with copyright law in your jurisdiction. Archilles is designed for searching your own legally acquired library.

### Can I use it for commercial research?

The software is MIT licensed (free for commercial use). Compliance with copyright law for the content you index is your responsibility.

---

## Roadmap

### What's planned for v1.0?

- Improved embedding models (domain-specific options)
- VLM-based OCR for better scanned PDF support
- Graph RAG (entity relationships)

See [docs/ROADMAP.md](ROADMAP.md) for the full roadmap.

### What are "Special Editions"?

Planned discipline-specific commercial extensions (Historical, Literary, Legal, Musical). The core will remain MIT licensed. See [EDITIONS.md](EDITIONS.md) for details.

### Can I contribute?

Yes. See [CONTRIBUTING.md](../CONTRIBUTING.md) for how to report bugs, request features, and submit pull requests.

---

## Troubleshooting

For specific error messages and common issues, see [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

---

*Didn't find your answer? Ask in [GitHub Discussions](https://github.com/kasssandr/archilles/discussions) or open an [issue](https://github.com/kasssandr/archilles/issues).*
