# Frequently Asked Questions

> **Status**: Documentation in progress

## General

### What is Archilles?

Archilles is a semantic search system for Calibre libraries. It uses RAG (Retrieval-Augmented Generation) to let you search by meaning, not just keywords.

### Is it free?

Yes! Archilles core is MIT licensed and free to use. Future "Special Editions" (discipline-specific extensions) will be commercial add-ons.

### Does it work offline?

Yes! Everything runs locally. The only network access is downloading the BGE-M3 model on first run (~500 MB).

### Do you collect any data?

No. Zero telemetry, no analytics, no tracking. Your library stays on your machine.

## Installation

### What are the system requirements?

- Python 3.8+
- 8 GB RAM minimum (16 GB recommended for large libraries)
- ~2 GB disk space for embeddings model
- Storage for vector database (varies by library size)

### Does it work on Windows/Mac/Linux?

Yes, all three platforms are supported.

### Can I use it without Claude Desktop?

Yes! The command-line interface works standalone. MCP integration is optional.

## Usage

### How long does indexing take?

Depends on book size and your hardware:
- Small book (200 pages): ~30 seconds
- Large book (800 pages): ~2 minutes
- Entire library (1000 books): Varies, can be done incrementally

### Does it modify my Calibre library?

No. Archilles only reads from Calibre. Your library is never modified.

### Can I index books not in Calibre?

Not yet. Currently requires Calibre library structure. Standalone file support is planned.

### What languages are supported?

75+ languages with automatic detection. Search works across languages simultaneously.

## Search

### Which search mode should I use?

- **Hybrid** (default): Best for most queries
- **Semantic**: Good for broad concepts, thematic searches
- **Keyword**: Best for specific names, dates, technical terms

### Why isn't my search finding results?

Common reasons:
1. Book not indexed yet
2. Using wrong language filter
3. Query too specific (try hybrid mode)
4. Typo in search terms (semantic mode is more forgiving)

### Can I search multiple libraries?

Not yet. Multi-library support is planned for v1.0.

## Technical

### Which embedding model does it use?

BGE-M3 (BAAI/bge-m3) – state-of-the-art multilingual embeddings with 1024 dimensions.

### Can I use a different embedding model?

Not currently. Model selection is planned for future releases.

### Does it support GPU acceleration?

Yes, automatically if PyTorch with CUDA is installed. Otherwise falls back to CPU.

### Where is the vector database stored?

By default in `./achilles_rag_db/`. Configurable via `--db-path`.

## Privacy & Legal

### Is my library data sent anywhere?

No. All processing happens locally on your machine.

### Is it legal to index copyrighted books?

Indexing for personal research use is generally legal under fair use/fair dealing. You are responsible for compliance with copyright law in your jurisdiction.

### Can I use it for commercial research?

The software is MIT licensed (free for commercial use), but ensure your use of copyrighted materials complies with applicable law.

## Roadmap

### When will annotations be supported?

Planned for v1.0 (Q1 2025).

### What are "Special Editions"?

Discipline-specific commercial extensions. See [EDITIONS.md](EDITIONS.md) for details.

### Can I contribute?

Yes! See [CONTRIBUTING.md](../CONTRIBUTING.md) for how to get involved.

## Troubleshooting

For specific issues, see [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

---

**Didn't find your answer?** Ask in [GitHub Discussions](https://github.com/archilles/archilles/discussions).
