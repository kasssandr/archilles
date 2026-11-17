# User Guide

**Last updated:** November 2026

## Introduction

Archilles brings semantic search to your library. This guide covers searching from the command line: modes, filters, how to read a result, and how far to trust a page number. Most people search through an AI assistant instead; the same options exist there as tool parameters (see [MCP Integration](MCP_GUIDE.md)). Indexing, including Scriptor bundles, is covered in the [Usage Guide](USAGE.md).

## Basic Search

### Hybrid Search (Recommended)

Combines semantic understanding with keyword precision:

```bash
python scripts/rag_demo.py query "trade networks in medieval Europe"
```

### Search Modes

- **Hybrid** (default): Best of both worlds
- **Semantic**: Concept-based, finds similar meanings
- **Keyword**: Exact term matching (BM25)

```bash
# Semantic only
python scripts/rag_demo.py query "consciousness" --mode semantic

# Keyword only (precise terms)
python scripts/rag_demo.py query "Herrschaftslegitimation" --mode keyword
```

## Filtering Results

### By Language

```bash
# Single language
python scripts/rag_demo.py query "Rex" --language la

# Multiple languages
python scripts/rag_demo.py query "kings" --language de,en
```

### By Tags

```bash
python scripts/rag_demo.py query "political theory" --tag-filter Philosophy History
```

### By Book

```bash
python scripts/rag_demo.py query "Marcion" --book-id "von_Harnack"
```

### By Section

By default a search returns passages from the main text only. Front matter, bibliography, index and notes sections are left out, because a search that answers from the index instead of the book is a bad search.

```bash
# Search the apparatus on purpose
python scripts/rag_demo.py query "Mommsen" --section back_matter

# Search everything
python scripts/rag_demo.py query "Mommsen" --all-sections
```

For a book indexed from a Scriptor bundle these sections are named in the text by Scriptor, not guessed from position. Prefaces and appendices count as main text.

### By Kind of Text

```bash
# Book text only (default)
python scripts/rag_demo.py query "sovereignty"

# Your Calibre comments
python scripts/rag_demo.py query "sovereignty" --chunk-type calibre_comment

# Both
python scripts/rag_demo.py query "sovereignty" --chunk-type all
```

### How Many Results

```bash
# More results, and more than two per book
python scripts/rag_demo.py query "Reformation" --top-k 20 --max-per-book 5
```

## Reading a Result

Each result names author, title and year, and where the passage stands: a page for a PDF, a chapter or section for an EPUB.

**The page number.** Archilles cites the page label as printed, so a preface stays `p. xiv`. How reliable the label is depends on where the text came from:

- **A book with a Scriptor bundle** knows for every page whether its number was read off the page or calculated from the pages around it. A calculated number is shown as *inferred*. Check it against the book before you cite it.
- **A PDF without a bundle** cites what the file's own page labels say. For most born-digital books that is right; for older scans it can be the position in the file.
- **An EPUB** has no pages unless it carries a page list. Cite it by chapter, and quote a short passage verbatim so the place can be found.

**Checking a citation.** Through an AI assistant, `verify_citation` asks one book whether a quotation still stands on the page a citation names. Use it before quoting something you did not just retrieve. `open_original` opens the book itself, a PDF at the cited page.

## Advanced Features

### Exact Phrase Matching

For precise quotes (useful for Latin, citations):

```bash
python scripts/rag_demo.py query "evangelista et a presbyteris" --exact
```

### Export to Markdown

```bash
python scripts/rag_demo.py query "your query" --export results.md
```

## Search Tips

### For Historians
- Use hybrid mode for broad concepts
- Use keyword mode for specific names and dates
- Filter by language when working with primary sources

### For Literary Scholars
- Semantic mode excels at finding thematic connections
- Use tags to organize by genre, period, or theme
- Export results to build research notes

### For Philosophers
- Hybrid mode balances technical terms with conceptual search
- Author filtering helps compare perspectives
- Custom Calibre fields can track philosophical traditions

## Best Practices

1. **Tag your library well** – Tags become powerful filters
2. **Use Calibre comments** – These get boosted in search results
3. **Index incrementally** – Start with key books, expand gradually
4. **Build bundles for the books you cite from** – A Scriptor bundle gives a PDF checked page numbers and keeps index and bibliography out of your results (see [Usage Guide](USAGE.md#scriptor-bundles-pdf))
5. **Experiment with modes** – Different queries benefit from different approaches

## Next Steps

- [Usage Guide](USAGE.md) for indexing, bundles and all MCP tools
- [MCP Integration](MCP_GUIDE.md) for Claude Desktop and other assistants
- [Architecture](ARCHITECTURE.md) for deeper insights
- [FAQ](FAQ.md) for common questions
