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

#### Batch indexing — selection modes

```bash
# All books in the library
python scripts/batch_index.py --all

# All books with a specific Calibre tag
python scripts/batch_index.py --tag "Key-Literature"

# All books by an author (partial match)
python scripts/batch_index.py --author "Arendt"

# Specific books by Calibre ID
python scripts/batch_index.py --ids 1234,5678,9012
```

#### Batch indexing — filtering

```bash
# Further filter by author within a tag selection
python scripts/batch_index.py --tag "Key-Literature" --filter-author "Arendt"
python scripts/batch_index.py --tag "Key-Literature" --filter-author "Arendt" --filter-author "Benjamin"

# Only books rated 4 stars or higher
python scripts/batch_index.py --tag "Key-Literature" --min-rating 4

# Only books with exactly this rating (0 = unrated)
python scripts/batch_index.py --tag "Key-Literature" --rating 0

# Exclude books with a specific tag
python scripts/batch_index.py --all --exclude-tag "DeepL" --exclude-tag "Übersetzung"

# Include books normally excluded by default (exclude / Übersetzung tags)
python scripts/batch_index.py --tag "Translations" --include-excluded

# Preview (what would be indexed?)
python scripts/batch_index.py --tag "Key-Literature" --dry-run

# First N books only (for testing)
python scripts/batch_index.py --tag "Philosophy" --limit 5
```

#### Batch indexing — resume and maintenance

```bash
# Resume after interruption (fast: pre-filters already-indexed books)
python scripts/batch_index.py --tag "Key-Literature" --skip-existing

# Force re-index (even already-indexed books)
python scripts/batch_index.py --tag "Key-Literature" --force

# Re-index books indexed before a date (e.g. after a major pipeline improvement)
python scripts/batch_index.py --tag "Key-Literature" --reindex-before 2026-01-01

# Re-index books where page label extraction was missing
python scripts/batch_index.py --tag "Key-Literature" --reindex-missing-labels

# Remove index entries for books deleted from Calibre (with dry-run preview)
python scripts/batch_index.py --cleanup-orphans --dry-run
python scripts/batch_index.py --cleanup-orphans

# Reset the database entirely (caution — requires full re-index)
python scripts/batch_index.py --tag "Key-Literature" --reset-db
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

**Switching already-indexed books:** The format preference is not applied automatically to already-indexed books — they are skipped on the next run. To switch to EPUB for all previously indexed books:
```bash
python scripts/batch_index.py --tag "Key-Literature" --prefer-format epub --reindex-before 2099-01-01
```

#### Indexing mode (hardware-adaptive)

Archilles detects your hardware automatically and picks a sensible indexing path —
by default you configure nothing. If you want control, there is a single variable,
`mode`, set in `.archilles/config.json` or overridden per run with `--mode`:

```bash
# Auto-detect hardware and pick the path (default — nothing to set)
python scripts/batch_index.py --tag "Key-Literature"

# Pin a mode explicitly (overrides config.json)
python scripts/batch_index.py --tag "Key-Literature" --mode light
python scripts/batch_index.py --tag "Key-Literature" --mode full-local
python scripts/batch_index.py --tag "Key-Literature" --mode full-external
```

```jsonc
// .archilles/config.json
{ "mode": "auto" }   // auto | light | full-local | full-external
```

The internal hardware classes collapse onto three understandable ways:

| Mode | For | What it does |
|---|---|---|
| **light** | weak hardware, trying it out | flat chunks, local embedding, free — searchable immediately, no Small-to-Big |
| **full-local** | capable GPU / Apple Silicon | hierarchical (Small-to-Big) chunks, local embedding — the quality default |
| **full-external** | weak hardware that wants full quality | hierarchical chunks prepared locally, embedded on a stronger machine |

Under `auto` (the default), capable hardware → `full-local`, weak hardware → `light`.
Auto never silently requires external embedding, so there is no surprise cost or setup.

The embedding model and vector dimension (BGE-M3, 1024) never change between modes,
so databases stay compatible across machines — only throughput and chunk layout
differ. A flat (`light`) database still works; at retrieval time its chunks fall
back to the surrounding `window_text` instead of a parent chunk.

> ⚠️ **After an external corpus embed, set `full-external` explicitly.** `auto`
> never resolves to `full-external` (by design — it never imposes surprise setup).
> If you embedded your library externally (hierarchical chunks on a stronger
> machine) but leave `mode` on `auto`, then on weak hardware the daily watchdog
> resolves to `light` and indexes every **new** title flat *and unmarked* — it is
> searchable, but silently lower quality, and nothing ever queues it for the
> external upgrade. Set `"mode": "full-external"` in each library's
> `.archilles/config.json` (Calibre **and** Zotero) once the externally embedded
> corpus is live, so new titles are indexed provisionally light **and marked** for
> the `--prepare-pending-external` trickle upgrade.

##### Advanced

**Legacy profile override.** The old `minimal`/`balanced`/`maximal` profiles still
exist as a power-user override that bypasses `--mode`/auto detection (they differ
only in batch size):

```bash
python scripts/batch_index.py --tag "Key-Literature" --profile minimal    # 4–6 GB VRAM
python scripts/batch_index.py --tag "Key-Literature" --profile balanced   # 8–12 GB VRAM
python scripts/batch_index.py --tag "Key-Literature" --profile maximal    # 16+ GB VRAM
```

**Internal hardware classes.** `auto` classifies your machine into one of five
classes — `cpu-only`, `apple-mps`, `gpu-small` (<8 GB VRAM), `gpu-mid` (8–16 GB),
`gpu-large` (≥16 GB) — which drive batch size, the embedding device, and the
reranker device (CPU on weak hardware, GPU from `gpu-mid` up). You never name these
directly; they exist only so `auto` can choose well.

**full-external workflow.** In `full-external`, bulk indexing is automatically
prepare-only: it writes JSONL chunks to `--output-dir`, which you embed on a
stronger machine (`local-first`: only text chunks leave your machine, never the
books or the library DB):

```bash
# 1. Prepare locally (no GPU needed)
python scripts/batch_index.py --tag "Key-Literature" --mode full-external
# 2. Embed the prepared chunks (here against a remote embedding server)
python scripts/rag_demo.py embed --input-dir ./prepared_chunks --mode remote --host http://…
```

For the ongoing trickle of new titles, the watchdog indexes them *provisionally
light* (flat, local — searchable at once) and marks them. Drain that backlog later
and replace the flat chunks with externally embedded hierarchical ones:

```bash
# Re-prepare the provisionally-light books hierarchically …
python scripts/batch_index.py --prepare-pending-external
# … then embed externally; marked books are replaced automatically (no --force)
python scripts/rag_demo.py embed --input-dir ./prepared_chunks --mode remote --host http://…
```

**Full offload (LAN).** Embedding-only offload (above) is the data-sparse default.
For a fully offloaded run, run all of Archilles on a strong machine in your LAN
against a copy/share of the library and copy the finished `rag_db` back — a
documented operational scenario, not a cloud feature.

#### Logging and automation

```bash
# Write indexing progress to a JSON log
python scripts/batch_index.py --tag "History" --log indexing_log.json

# Suppress confirmation prompts (for scripts)
python scripts/batch_index.py --tag "History" --non-interactive

# Enable OCR for scanned PDFs
python scripts/batch_index.py --tag "Scanned" --enable-ocr
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

After correct configuration, the following **12 tools** are available in Claude Desktop.

### Search tools

**`search_books_with_citations`** — Full-text hybrid search across all indexed book content.

Example prompts:
- *"Search my books for discussions of political legitimacy"*
- *"Find passages about medieval trade, in German only"*
- *"What do my sources say about the Council of Nicaea?"*

Parameters:
- `query`: Search term (required)
- `top_k`: Number of results (default: 5; 10–15 for broad research)
- `mode`: `'hybrid'`, `'semantic'`, or `'keyword'`
- `language`: Language filter (`'de'`, `'en'`, `'la'`, etc.)
- `tags`: Array of Calibre tags to filter by
- `expand_context`: Returns surrounding passage for each match (Small-to-Big)

**`search_annotations`** — Semantic search across your Calibre highlights, notes, and book comments.

Example prompts:
- *"Search my annotations for 'consciousness'"*
- *"What did I highlight about freedom?"*
- *"Search my notes for anything about Hannah Arendt"*

Parameters:
- `query`: Search term (required)
- `max_results`: Maximum results (default: 30)
- `max_per_book`: Max results per book (prevents one book dominating)

**`set_research_interests`** — Register keywords that receive a score boost in all future searches, without re-indexing.

Example prompts:
- *"Set my research interests to: Josephus, Mithras, priestly elite"*
- *"Show my current research interest keywords"*
- *"Clear my research interests"*

Parameters:
- `action`: `'get'` (view current) or `'set'` (update)
- `keywords`: List of keywords to boost
- `boost_factor`: Additive score boost per matching keyword (default: 0.15)

---

### Metadata tools

**`list_books_by_author`** — Direct query against Calibre metadata. Reliable for finding all books by an author, including short texts where the author name may not appear in indexed chunks.

Example prompts:
- *"List all books by Hannah Arendt in my library"*
- *"Which articles by Mason do I have tagged 'Josephus'?"*

Parameters:
- `author`: Author name, partial match (e.g. `"Mason"` matches `"Steve Mason"`)
- `tags`: Optional tag filter (AND logic)
- `year_from` / `year_to`: Publication year range
- `sort_by`: `'title'` (default) or `'year'`

**`list_tags`** — All Calibre tags with book counts. Recommended before a tag-filtered search to verify the exact spelling of a tag.

**`list_annotated_books`** — All books with indexed annotations. Quick overview of your actively-read corpus.

**`get_book_annotations`** — All annotations for a specific book (file path required).

**`get_book_details`** — Full Calibre metadata for a given book ID.

---

### Output tools

**`export_bibliography`** — Bibliography export in BibTeX, RIS, EndNote, JSON, or CSV. Filterable by author (partial name), tag, and publication year.

Example prompts:
- *"Export all my Philosophy books as BibTeX"*
- *"Give me a RIS bibliography of books by Foucault published after 1970"*

---

### Utility tools

| Tool | Function |
|------|----------|
| `detect_duplicates` | Find duplicate books by title+author, ISBN, or exact title |
| `compute_annotation_hash` | Compute content hash for annotation deduplication |
| `get_doublette_tag_instruction` | Helper for the Calibre duplicate-tagging workflow |

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

### Workflow 6: Metadata + bibliography

In Claude Desktop:
```
1. "List all books by Agamben in my library"
2. "Filter those to the ones tagged 'Core Literature'"
3. "Export a BibTeX bibliography of those titles"
```

### Workflow 7: Tune search for an ongoing project

In Claude Desktop:
```
1. "Set my research interests to: prosopography, late antique senators, cursus honorum"
2. [Future searches now automatically boost results containing these terms]
3. "Search my books for the role of the senatorial class in 5th century Rome"
```

---

## Tips & Best Practices

### Indexing

- **Choose your format:** PDF for precise page citations, EPUB for faster indexing and cleaner chunks (see `--prefer-format`)
- **Run overnight:** ~10 min per book (CPU), ~2 min per book (GPU); 50 books ≈ 1–8 hours
- **Use `--skip-existing`:** Resume after interruptions without re-indexing
- **Use tags strategically:** Index thematic collections rather than everything at once
- **Use `--dry-run` first:** Verify what will be indexed before starting a long run
- **Clean up after deleting books:** Run `--cleanup-orphans` periodically
- **Re-index after pipeline improvements:** Use `--reindex-before DATE` to refresh older entries

### Search

- **Hybrid mode for general questions:** Combines concepts + exact words
- **Keyword mode for technical terms:** "Herrschaftslegitimation", "prosopography"
- **Exact mode for quotes:** Latin phrases, verbatim quotations
- **Language filter in multilingual libraries:** Reduces noise significantly
- **Use `list_books_by_author` for author queries:** More reliable than full-text search for short texts (articles, book chapters)
- **Check `list_tags` first:** Verify exact tag spelling before filtering

### Research Interest Boosting

- Register project-specific keywords at the start of a research session
- Boosting is additive and non-destructive — general searches still work normally
- Update keywords as your research focus shifts; no re-indexing required

### Cross-Encoder Reranking

- Enable in `.archilles/config.json` for more accurate result ordering
- Downloads ~560 MB on first use
- Runs on CPU by default (GPU is typically occupied by BGE-M3)
- Most useful for broad queries where Stage 1 results have mixed relevance

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

### Missing page numbers in results
→ Run `python scripts/batch_index.py --tag "YOUR-TAG" --reindex-missing-labels` to reprocess affected books.

### Wrong format being indexed
→ Use `--prefer-format epub` or `--prefer-format pdf` explicitly.
→ To switch all previously indexed books: add `--reindex-before 2099-01-01` to force re-index.

---

## Further Documentation

- [README.md](../README.md) — Project overview
- [FEATURES.md](FEATURES.md) — Complete feature catalog
- [ARCHITECTURE.md](ARCHITECTURE.md) — Technical details
- [MCP_GUIDE.md](MCP_GUIDE.md) — Claude Desktop configuration
- [TROUBLESHOOTING.md](TROUBLESHOOTING.md) — Common issues
