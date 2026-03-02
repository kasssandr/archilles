# Archilles Usage Guide

A practical guide to using Archilles day-to-day.

---

## Table of Contents

1. [Overview: Two Search Systems](#overview-two-search-systems)
2. [CLI Commands](#cli-commands)
3. [MCP Tools in Claude Desktop](#mcp-tools-in-claude-desktop)
4. [Typical Workflows](#typical-workflows)
5. [Tips & Best Practices](#tips--best-practices)

---

## Overview: Two Search Systems

Archilles provides two complementary search systems:

| System | Searches | Tool | When to use |
|--------|----------|------|-------------|
| **Full-text search** | PDF/EPUB content (chunks) | `search_books_with_citations` | "What do my books say about X?" |
| **Annotation search** | Calibre highlights and notes | `search_annotations` | "What did I mark or note about X?" |

Both systems use:
- **Semantic search**: Finds conceptually similar content
- **Keyword search**: Finds exact word matches
- **Hybrid mode**: Combines both (recommended)

---

## CLI Commands

### Indexing

#### Index a single book
```bash
python scripts/rag_demo.py index "D:\Calibre Library\Author\Book (ID)\file.pdf"
```

With a custom ID:
```bash
python scripts/rag_demo.py index "path/to/book.pdf" --book-id "Arendt_VitaActiva"
```

#### Batch indexing by tag
```bash
# Preview (what would be indexed?)
python scripts/batch_index.py --tag "Key-Literature" --dry-run

# Actually index
python scripts/batch_index.py --tag "Key-Literature"

# With logging
python scripts/batch_index.py --tag "History" --log indexing_log.json

# First N books only (for testing)
python scripts/batch_index.py --tag "Philosophy" --limit 5

# Resume after interruption
python scripts/batch_index.py --tag "Key-Literature" --skip-existing
```

#### Batch indexing by author
```bash
python scripts/batch_index.py --author "Arendt"
python scripts/batch_index.py --author "Foucault" --dry-run
```

#### Format preference (`--prefer-format`)

If a book has multiple formats (e.g. PDF + EPUB), `--prefer-format` determines which gets indexed. Default is `pdf`.

```bash
# Prefer PDF (default) — exact page numbers, scientific citability
python scripts/batch_index.py --tag "Key-Literature"

# Prefer EPUB — faster indexing, cleaner chunks
python scripts/batch_index.py --tag "Key-Literature" --prefer-format epub
```

**PDF** provides exact page numbers for citations (`p. 47`) and matches the printed edition. Downside: scanned PDFs produce OCR noise; multi-column layouts and headers/footers often mix into chunks, reducing search quality.

**EPUB** produces cleaner chunks because the text is structured HTML — paragraphs stay paragraphs, chapter boundaries are recognized, and extraction is significantly faster. Downside: no page numbers; citations reference chapters rather than pages.

If the preferred format is not available, the next available format is used automatically.

**Switching already-indexed books:** The format preference is not applied automatically to already-indexed books — they are skipped on the next run. For a complete switch to EPUB:
```bash
python scripts/batch_index.py --tag "Key-Literature" --prefer-format epub --reindex-before 2099-01-01
```

#### Remove orphan entries

When books are deleted from Calibre, their chunks remain in the index. Use `--cleanup-orphans` to remove them:

```bash
# Preview what would be removed
python scripts/batch_index.py --cleanup-orphans --dry-run

# Actually remove
python scripts/batch_index.py --cleanup-orphans
```

#### Index statistics
```bash
python scripts/rag_demo.py stats
```

---

### Search

#### Basic search
```bash
# Hybrid (default, recommended)
python scripts/rag_demo.py query "political legitimacy in the Middle Ages"

# Semantic only (concept-based)
python scripts/rag_demo.py query "power and authority" --mode semantic

# Keyword only (exact words)
python scripts/rag_demo.py query "Herrschaftslegitimation" --mode keyword
```

#### Exact phrase search
Especially useful for Latin, quotes, and technical terms:
```bash
python scripts/rag_demo.py query "evangelista et a presbyteris" --exact
```

#### Language filter
```bash
# German texts only
python scripts/rag_demo.py query "König" --language de

# Latin texts only
python scripts/rag_demo.py query "Rex" --language la

# Multiple languages
python scripts/rag_demo.py query "king" --language de,en,la
```

#### Tag filter
```bash
python scripts/rag_demo.py query "consciousness" --tag-filter Philosophy
python scripts/rag_demo.py query "trade" --tag-filter History Economics
```

#### More results
```bash
python scripts/rag_demo.py query "Reformation" --top-k 20
```

#### Export to Markdown
For Joplin, Obsidian, or other Markdown apps:
```bash
python scripts/rag_demo.py query "Late Antique senators" --export research.md
```

---

## MCP Tools in Claude Desktop

After correct configuration, the following tools are available in Claude Desktop:

### Full-text search: `search_books_with_citations`

Searches indexed PDF/EPUB content.

**Example prompts:**
- *"Search my books for discussions of political legitimacy"*
- *"Find passages about medieval trade, in German only"*
- *"What do my sources say about the Council of Nicaea?"*

**Parameters:**
- `query`: Search term (required)
- `top_k`: Number of results (default: 10)
- `mode`: 'hybrid', 'semantic', or 'keyword'
- `language`: Language filter ('de', 'en', 'la', etc.)

### Annotation search: `search_annotations`

Searches your Calibre highlights, notes, and book comments.

**Example prompts:**
- *"Search my annotations for 'consciousness'"*
- *"What did I highlight about freedom?"*
- *"Search my notes for anything about Hannah Arendt"*

**Parameters:**
- `query`: Search term (required)
- `max_results`: Maximum results (default: 30)
- `max_per_book`: Max results per book (prevents one book dominating)

### Other MCP tools

| Tool | Function |
|------|----------|
| `list_annotated_books` | Shows all books with annotations |
| `get_book_annotations` | Annotations for a specific book |
| `get_book_details` | Full metadata for a Calibre book ID |
| `list_tags` | All Calibre tags with book counts |
| `detect_duplicates` | Finds duplicate books in the library |
| `export_bibliography` | Exports citations in BibTeX, RIS, Chicago, APA |

---

## Typical Workflows

### Workflow 1: Open up a new book collection

```bash
# 1. Identify books with the relevant tag (dry run)
python scripts/batch_index.py --tag "Dissertation-Project" --dry-run

# 2. Start indexing (possibly overnight)
python scripts/batch_index.py --tag "Dissertation-Project" --log diss_index.json

# 3. After completion: restart Claude Desktop

# 4. Research in Claude Desktop:
# "Search my books for [research question]"
```

### Workflow 2: Thematic research

In Claude Desktop:
```
1. "Search my books for 'the relationship between church and state in the Middle Ages'"
2. "Also show me what I've annotated on this topic"
3. "Export the most relevant passages as Markdown"
```

### Workflow 3: Find a quote

```bash
# Search for an exact phrase (e.g. a Latin quote)
python scripts/rag_demo.py query "in necessariis unitas" --exact

# Or in Claude Desktop:
# "Find the exact quote 'in necessariis unitas' in my books"
```

### Workflow 4: Comparative analysis

In Claude Desktop:
```
1. "What does Arendt write about power?"
2. "And what does Foucault say about it?"
3. "Compare the two positions based on the passages you found"
```

### Workflow 5: Annotation-driven research

In Claude Desktop:
```
1. "What did I highlight about the concept of sovereignty?"
2. "Are there any notes I made about Schmitt in relation to this?"
3. "Combine my annotations with relevant passages from the books themselves"
```

---

## Tips & Best Practices

### Indexing

- **Choose your format:** PDF for precise page citations, EPUB for faster indexing and cleaner chunks (see `--prefer-format`)
- **Run overnight:** ~10 min per book (CPU), ~2 min per book (GPU); 50 books ≈ 1–8 hours
- **Use `--skip-existing`:** Resume after interruptions
- **Use tags strategically:** Index thematic collections rather than everything at once
- **Clean up after deleting books:** Run `--cleanup-orphans` periodically

### Search

- **Hybrid mode for general questions:** Combines concepts + exact words
- **Keyword mode for technical terms:** "Herrschaftslegitimation", "prosopography"
- **Exact mode for quotes:** Latin phrases, verbatim quotations
- **Language filter in multilingual libraries:** Reduces noise significantly

### Claude Desktop

- **Restart after indexing:** The MCP server loads the database at startup
- **Give clear instructions:** "Search my *books*" vs. "Search my *annotations*"
- **Validate results:** Check page numbers, especially in older PDFs

### Data organization

```
D:\Calibre Library\
├── .archilles\
│   ├── rag_db\          # LanceDB index (all content + annotations)
│   └── config.json      # Optional configuration
├── Author 1\
│   └── Book (ID)\
└── Author 2\
    └── Book (ID)\
```

---

## Troubleshooting

### "Tool ran without output"
→ MCP response format issue. Make sure you have the current version.

### Search returns no results
→ Check with `python scripts/rag_demo.py stats` whether books are indexed.
→ Check the DB path (should be in `.archilles/rag_db`).

### Claude Desktop doesn't find tools
→ Check `claude_desktop_config.json` syntax.
→ Restart Claude Desktop completely.
→ Check log: `~/.archilles/mcp_server.log`

### Indexing aborts
→ Resume with `--skip-existing`.
→ Check disk space and RAM.

---

## Further Documentation

- [README.md](../README.md) — Project overview
- [ARCHITECTURE.md](ARCHITECTURE.md) — Technical details
- [MCP_GUIDE.md](MCP_GUIDE.md) — Claude Desktop configuration
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) — Common issues
