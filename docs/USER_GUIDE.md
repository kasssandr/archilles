# User Guide

> **Status**: Documentation in progress

## Introduction

Archilles brings semantic search to your Calibre library. This guide covers search strategies, filtering, and best practices.

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
4. **Experiment with modes** – Different queries benefit from different approaches

## Next Steps

- Understand [Architecture](ARCHITECTURE.md) for deeper insights
- Set up [MCP Integration](MCP_GUIDE.md) for Claude Desktop
- Check [FAQ](FAQ.md) for common questions
