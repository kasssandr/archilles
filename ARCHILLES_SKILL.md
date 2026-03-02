# ARCHILLES_SKILL.md — Usage Guide for AI Assistants

> **Who is this document for?**
> For any AI model connected to ARCHILLES via MCP — from Haiku to Opus.
> It explains what ARCHILLES is, what the database contains, what tools are available, and how to use them for research.
> This document is intentionally generic and applies to any ARCHILLES user.
> User-specific additions belong in ARCHILLES_USER.md.

---

## 1. What is ARCHILLES?

ARCHILLES is a semantic research system for a personal Calibre library. It makes thousands of titles accessible through natural-language search: in the full text of books, in the user's curated metadata, and in their personal annotations.

The system uses BGE-M3 embeddings with hybrid vector and BM25 search. Results are delivered with complete citation details (author, title, year, page number or chapter) and are suitable for academic use.

**ARCHILLES is a tool for thinking *with* a research library.** Not every query expects a fully synthesized answer. Sometimes a well-structured list of materials is right, sometimes a comparative analysis, sometimes a single targeted find. The model should not impose itself — it provides material and thinks along when asked.

---

## 2. Content types — what is in the database?

ARCHILLES uses **a single LanceDB database** with different content classes (`chunk_type`). There are no separate databases — the distinction is made by filtering within the shared table.

| chunk_type | What it contains | Epistemic status |
|---|---|---|
| `content` | Full text of books (chapters, sections) | What the *book says* |
| `calibre_comment` | Publisher blurbs, back-cover text, reviews, personal excerpts, notes and analysis collected by the user | What the user has gathered about the book or thought themselves — curated second-order knowledge |
| `annotation` | Highlights and notes from the Calibre viewer (EPUB) and PDF readers | What the user marked as relevant while reading — curated first-order knowledge |

**On weighting:** The presence of a `calibre_comment` entry is a weak signal of user interest in a title. The *length* of this field is not a reliable indicator — it may be inflated by copied publisher blurbs, translated secondary texts, or other non-evaluative content. Do not apply automatic weighting based on field length.

Annotations typically represent more curated knowledge than publisher blurbs: they show what the user found significant during active reading. Note, however, that the `calibre_comment` field may also contain personal excerpts and the user's own thoughts — it is thus not epistemically inferior to annotations, only more heterogeneous.

---

## 3. Available MCP tools

### 3.1 Main search in book content

**`search_books_with_citations`**

Hybrid search across all book content with citable results.

Parameters:
- `query` (required): Natural-language query. Precise, substantive phrasing yields better results than bare keyword lists.
- `mode`: `hybrid` (default, recommended), `semantic` (conceptual, good for related terms and thematic searches), `keyword` (exact match, good for names, titles, technical terms)
- `top_k`: Number of results (default: 5; 10–15 recommended for broad research)
- `tags`: Filter by Calibre tags, e.g. `["History", "Philosophy"]`
- `language`: Language filter, e.g. `"de"`, `"en"`, `"la"`
- `expand_context`: If `true`, larger text passages surrounding the match are returned (Small-to-Big retrieval)

This tool searches only main text by default (`section_filter: main`), excluding bibliographies, indexes, and front matter. This is intentional.

**Important limitation:** `search_books_with_citations` is a *full-text and semantic search*, not a metadata query. An author is only found if their name appears in an indexed text chunk. For short texts (articles, book chapters in anthologies), the author name often appears only on the title page — which may not be a separate chunk in the index. For metadata queries (all books by an author, all titles with a tag), use the tools in section 3.3.

### 3.2 Searching annotations

**`search_annotations`**

Searches the user's highlights and notes semantically via LanceDB, covering both `annotation` and `calibre_comment` chunk types.

Parameters:
- `query`: Search query

Annotations are often the most revealing entry point: they show what the user has found relevant, and can inform the direction of a full-text search — without predetermining it.

### 3.3 Library navigation and metadata

These tools work directly against Calibre metadata, not the vector index. For questions like "all books by author X" or "all titles with tag Y" they are the right approach — not `search_books_with_citations`.

**`list_books_by_author`** — All titles by an author directly from the Calibre database. Partial name match (case-insensitive), optional tag and year filter. *This is the fastest and most reliable tool for the question "Which books by author X do I have?"* — especially important for short texts (articles, book chapters) that are easily missed in vector search because the author name does not appear in indexed chunks.

Parameters:
- `author` (required): Author name, partial match (e.g. "Mason" finds "Steve Mason")
- `tags` (optional): List of tags as AND filter (e.g. `["Articles"]`)
- `year_from` / `year_to` (optional): Publication year range
- `sort_by`: `title` (default, alphabetical) or `year` (descending)

**`export_bibliography`** — Bibliography in BibTeX, RIS, EndNote, JSON, or CSV. Filterable by author (partial name), tag, and publication year. For a simple author list, `list_books_by_author` is faster; `export_bibliography` is the right choice when a formatted bibliography is needed.

**`list_tags`** — All Calibre tags with book counts. Useful for orientation about the library's organizational structure. Recommended before a tag-filtered search to verify the exact spelling of a tag.

**`list_annotated_books`** — All books with existing annotations. Gives a quick overview of the active reading corpus.

**`get_book_annotations`** — All annotations for a specific book (file path required).

**`get_book_details`** — Complete Calibre metadata for a title given its Calibre ID. Useful when a Calibre ID is known from another search result.

### 3.4 System utilities

**`detect_duplicates`** — Finds duplicate titles in the library.

**`compute_annotation_hash`** — Computes a content hash for an annotation (for deduplication purposes).

**`get_doublette_tag_instruction`** — Returns instructions for handling duplicate-tagged entries in the library.

---

## 4. Tool selection: metadata vs. full text

This is the most important decision at the start of a query:

| Question | Right tool |
|---|---|
| "What do my books say about X?" | `search_books_with_citations` |
| "All books by author X" | `list_books_by_author` |
| "All articles by author X" | `list_books_by_author` (tags: `["Articles"]`) |
| "All titles with tag Y" | `export_bibliography` (tag filter) |
| "All titles with tag Y by author X" | `list_books_by_author` (author + tags) |
| "Export bibliography as BibTeX" | `export_bibliography` |
| "What have I annotated about X?" | `search_annotations` |
| "What tags exist?" | `list_tags` |
| "Which books have I actively read?" | `list_annotated_books` |

**Rule of thumb:** As soon as a query begins with "all", "which", "list" or an author name without a substantive question, `list_books_by_author` or `export_bibliography` is the right entry point — not vector search. `list_books_by_author` is preferred when an author name is known; `export_bibliography` when a formatted bibliography or a pure tag filter without an author is needed.

---

## 5. Before searching: clarify intent

Before starting a search, briefly clarify what the user needs in this session — unless their intent is clearly evident from the query.

**Ask about:**

*What is the goal of this research?*
- (a) Gain an overview of a topic
- (b) Test a specific argument or thesis
- (c) Gather material for a text
- (d) Metadata query: all titles by an author, all titles with a tag
- (e) Find a specific piece of content
- (f) Other — please describe

*Which content should be searched first?*
- (a) Own prior work first (annotations + comments), then full text
- (b) Directly into the full text of the library
- (c) Metadata (author, tag, year) — without full text

*What format should the response take?*
- (a) Synthesis with interpretation
- (b) Material list with citations
- (c) Finds and citation references only, without commentary

Not all three questions need to be asked every time. For clear queries, a brief confirmation or a single follow-up is enough. The goal is clarity, not bureaucracy.

---

## 6. Research strategies

### Two-phase research (recommended for open-ended substantive questions)

**Phase 1 — Reconstruct prior knowledge:** Use `search_annotations` and `search_books_with_citations` to capture what the user has already worked on regarding this topic. This gives a picture of their existing research state.

**Phase 2 — Explore the corpus:** Use `search_books_with_citations` in the full text. Explicitly remain open to content that Phase 1 does *not* point toward. Annotations and comments show what the user already knows — Phase 2 also searches for what they have not yet found.

**Important:** Phase 1 must not constrain Phase 2. Searching only in directions suggested by your own markings means circling in a mirror of your existing understanding. Prior work is a starting point, not a boundary.

### Metadata research (for bibliographic overviews)

`list_books_by_author` for author queries (with optional tag filter). `export_bibliography` for pure tag queries or when a formatted bibliography (BibTeX, RIS, etc.) is needed. Both tools work directly against the Calibre database — more reliable than full-text search for author names.

Recommended sequence: call `list_tags` first to verify the exact spelling of the desired tag, then `list_books_by_author` or `export_bibliography` with verified parameters.

### Direct full-text research (for specific substantive questions)

`search_books_with_citations` with a precise query, `mode: hybrid`, `top_k: 10`. For proper names, technical terms, or titles, also test `mode: keyword`.

### Cross-language search

BGE-M3 is multilingual. Queries in German, English, Latin, and other languages work without an explicit language filter. For targeted narrowing: use the `language` parameter.

---

## 7. Result formats — what fits when

ARCHILLES is a tool for thinking *with* a library. Very different output formats are equally legitimate:

A **pure material list with citations** is appropriate when the user wants to continue thinking themselves. The model provides structured raw material without interpretive overlay — this is not less, but often more.

A **synthesis with interpretation** is appropriate when the user wants an assessment, an overview, or a framing. Here the model brings sources together, names agreements and contradictions, and shows connections.

A **citation collection** (finds and page references only) is appropriate for immediate work on one's own text.

The model should not decide on its own which format is correct — it asks (→ Section 5) or orients itself by the explicit request. Anticipating the user's interpretation is a mistake.

**Citation style for ARCHILLES sources:**
```
(Author, Title [Year], p. page_number)       — for PDF sources
(Author, Title [Year], ch. Chapter_name)     — for EPUB sources without page number
```

**Required for EPUB sources — original-language quote for findability:**

EPUB files have no physical page numbers. A chapter reference alone is not enough to find the passage in the document. Therefore:

For every citation from an EPUB source (and any other source without physical page numbers), a short verbatim quote in the **original language of the text** **must** be included. The quote must be sufficiently distinctive (5–15 words) so the user can find it with Ctrl+F in their e-reader and land at exactly the right spot.

**Why original language?** If the text is in Latin, English, Ancient Greek, or another language, the quote must be in that language — not in translation. Only then does text search in the original document work.

Examples:
```
(Eusebius, Church History, Ch. III.4 — "τὴν τῶν ἀποστόλων διαδοχὴν")
(Blumenberg, Die Legitimität der Neuzeit [1966], Ch. 2.1 — "die Selbstbehauptung der Vernunft")
(Gibbon, Decline and Fall [1776], Ch. XV — "the union and discipline of the Christian republic")
```

This rule applies to all output formats (synthesis, material list, citation collection). For PDF sources with page numbers, the original-language quote is optional but recommended for long passages or when the exact location within the page matters.

---

## 8. System behavior and quirks

**Section filtering:** By default, only main text is searched. Bibliographies, indexes, front matter, and appendices are excluded. This is a deliberate design decision against bibliographic noise.

**Chunk size:** Results are text sections of typically 300–600 words. They are taken out of context — always read and communicate the title, chapter, and publication year alongside them.

**Vector search ≠ metadata query:** `search_books_with_citations` only reliably finds authors and titles when they appear in the full text of indexed chunks. Short texts (articles, book chapters) often have the author name only on the title page — which may not be a separate chunk in the index. Always prefer `export_bibliography` or `list_books_by_author` for author and tag listings.

**Not in the index:** Books that have not yet been indexed are not findable. Missing results on an expected topic may mean the relevant titles are not yet in the index — not that they are absent from the library.

**Languages:** BGE-M3 processes all European languages as well as Latin reliably.

**Boosting:** `calibre_comment` chunks and tag matches receive slightly elevated relevance scores. This reflects the fact that user-curated fields are generally more relevant than full-text noise.

---

## 9. Quick-start protocol

1. Is an **ARCHILLES_USER.md** present? If so, read it first.
2. **Determine the type of query:** Metadata query with author → `list_books_by_author`. Metadata query with tag only → `export_bibliography`. Formatted bibliography → `export_bibliography`. Substantive question → continue to step 3.
3. **Clarify intent** — unless clearly evident from the query (→ Section 5).
4. Depending on the chosen mode: **Phase 1** (annotations + comments) or directly **full-text search**.
5. For two-phase research: consciously keep Phase 2 open — do not search only in directions suggested by Phase 1.
6. **Output results in the desired format** (→ Section 7).
7. If unclear during the process: brief follow-up question, no assumptions.

---

*ARCHILLES_SKILL.md — generic version, valid from v0.9 Beta*
*User-specific additions → ARCHILLES_USER.md*
