# ARCHILLES Session Handshake - Search Quality Investigation

**Session Date:** 2026-01-02
**Branch:** `claude/fix-indexing-resume-gEatY`
**Status:** ✅ Major features implemented and tested

---

## Executive Summary

**User's Original Problem:**
German medieval term "Lehen" (fief) search returned irrelevant results. Investigation revealed multiple root causes and led to architectural improvements.

**Key Discoveries:**
1. ❌ "Lehen" doesn't exist in corpus (confirmed with word-boundary matching)
2. ❌ Substring matching bug: "lehen" matched "flehen" (to beg) - FIXED
3. ❌ BGE-M3 semantic search returns noise (Suns of God, religious books) for domain-specific queries
4. ✅ **Solution:** Chunk type filtering - search curated Calibre comments separately from content
5. ✅ English query terms work better than German for cross-lingual semantic search

---

## What We Accomplished

### 1. Fixed Critical Bugs

**A. Substring Matching Bug** (`quick_db_check.py`)
- **Problem:** `if 'lehen' in doc_lower` matched "flehen", "belehnen"
- **Fix:** Word boundary regex: `r'\blehen\b'`
- **Impact:** False positives eliminated, accurate term counting

**B. quick_search.py Mode Parameter Bug**
- **Problem:** `python quick_search.py "lehen" keyword` treated "keyword" as part of query
- **Fix:** Parse mode as 2nd argument, validate choices
- **Impact:** Keyword/semantic/hybrid modes now work correctly

### 2. Implemented Chunk Type Filtering ⭐

**Files Modified:**
- `scripts/rag_demo.py`: Added `chunk_type_filter` parameter throughout
- `scripts/quick_search.py`: Added chunk_type as 4th positional argument

**Architecture:**
```python
# Search ONLY Calibre comments (curated, high-quality)
query(query_text, chunk_type_filter='phase1_metadata')

# Search ONLY book content (full text)
query(query_text, chunk_type_filter='content')

# Search everything (default - includes noise)
query(query_text)  # No filter
```

**Why This Matters:**
- Separates curated metadata from raw content
- Eliminates semantic search noise (Suns of God no longer appears)
- Solves weighting problem (apples vs oranges)
- User's Calibre comments ARE domain-specific context that BGE-M3 lacks

### 3. Validated Search Quality

**Test Results:**
- ✅ Chunk type filtering (`phase1_metadata`) - **Clean results, no noise!**
- ✅ Tag filtering (`--tag-filter Mittelalter Adel`) - **Works!**
- ✅ Combined filtering - **Works!**
- ❌ Search everything (default) - **Still has noise** (expected - BGE-M3 limitation)

---

## Current State

### Corpus Statistics
```
Total chunks: 1671
├─ phase1_metadata: 78 (Calibre comments)
├─ content: 1591 (full book text)
└─ calibre_comment: 2

German medieval terms found:
├─ mittelalter: 17 books
├─ adel: 15 books
├─ vasallen: 2 books
├─ lehen: 0 books ❌ (doesn't exist!)
└─ feudal: 1 book
```

### Search Modes
1. **Semantic** (BGE-M3) - Understands meaning, multilingual, BUT general-purpose (noise)
2. **Keyword** (BM25) - Exact term matching, fast, BUT requires term to exist
3. **Hybrid** (RRF fusion) - Combines both, balanced

### Known Issues & Limitations

**1. BGE-M3 Cross-Lingual Asymmetry**
- ✅ English queries → Find German/French sources (works well!)
- ❌ German queries → More noise, weaker results
- **Workaround:** Use English terms in queries when possible

**2. Semantic Search Noise (Unfixed)**
- "Suns of God" appears for feudalism queries when searching full content
- **Root cause:** BGE-M3 sees spurious similarity (power structures, hierarchies)
- **Solution:** Use `chunk_type_filter='phase1_metadata'` for domain-specific queries

**3. BM25 Enriched Documents**
- BM25 index includes tags, titles, authors in searchable text
- **Why:** Helps find books by metadata
- **Side effect:** Can match tags when user expects text-only
- **Current behavior:** This is intentional (feature, not bug)

---

## Recommended Workflows

### For Domain-Specific Queries (Medieval, Feudalism, etc.)
```bash
# High precision - curated comments only
python scripts/quick_search.py "feudal nobility vassals" semantic 10 phase1_metadata

# With tag filter for even higher precision
python scripts/rag_demo.py query "feudalism" \
  --chunk-type phase1_metadata \
  --tag-filter Mittelalter Adel \
  --mode semantic
```

### For General/Exploratory Queries
```bash
# Search full content (accept some noise)
python scripts/quick_search.py "Byzantine Empire" semantic 10 content

# Or use hybrid mode
python scripts/rag_demo.py query "evangelista" --mode hybrid
```

### For Exact Term Matching
```bash
# Latin quotes, technical terms
python scripts/rag_demo.py query "evangelista et a presbyteris" \
  --mode keyword \
  --exact

# German terms that exist in corpus
python scripts/quick_search.py "mittelalter" keyword 10
```

---

## File Changes Summary

### New Files
- `scripts/check_tags.py` - Diagnostic: where does "lehen" appear (text/tags/title)?

### Modified Files
1. **`scripts/quick_db_check.py`**
   - Fixed substring matching with word boundaries
   - More accurate term counting

2. **`scripts/quick_search.py`**
   - Fixed mode parameter parsing
   - Added chunk_type parameter (4th positional arg)
   - Usage: `python quick_search.py "query" [mode] [top_k] [chunk_type]`

3. **`scripts/rag_demo.py`** (Major changes)
   - Added `chunk_type_filter` parameter to:
     - `query()` method
     - `_semantic_search()`
     - `_keyword_search()`
     - `_exact_phrase_search()`
     - `_hybrid_search()`
     - `_build_where_clause()`
   - Added `--chunk-type` CLI argument
   - Full filtering for semantic (ChromaDB where clause) and keyword (BM25 post-filter)

---

## Key Insights for Future Work

### 1. User's Tagging is Imperfect (Intentional)
- User expects ARCHILLES to find poorly tagged/commented sources
- Tags should be **optional filter**, not required
- Chunk type filtering addresses this - searches curated content but doesn't require perfect tags

### 2. Separate Searches are Architecturally Superior
- Mixing content + metadata creates weighting problems
- Different use cases require different search targets
- Future UI should have separate search modes by default:
  - "Search my notes/comments" (phase1_metadata)
  - "Search book content" (content)
  - "Search annotations" (future chunk type)

### 3. Cross-Lingual Semantic Search Has Directional Bias
- English → German/French/Italian works well (BGE-M3 strength)
- German → multilingual less reliable (more noise)
- **Recommendation:** Document this for users, suggest English queries

### 4. Domain-Specific Embeddings Needed (Long-term)
- BGE-M3 is general-purpose → spurious similarities
- Medieval/classical studies need specialized embeddings
- **Alternatives to explore:**
  - Fine-tune BGE-M3 on historical texts
  - Use domain-specific models (if available)
  - Hybrid approach: keyword for domain terms + semantic for general concepts

---

## Testing Checklist for Next Session

If resuming or validating:

```bash
# 1. Verify chunk type filtering works
python scripts/quick_search.py "feudal nobility" semantic 5 phase1_metadata
# Expected: Medieval books, NO "Suns of God"

# 2. Verify tag filtering works
python scripts/rag_demo.py query "feudalism" \
  --tag-filter Mittelalter \
  --mode semantic
# Expected: Only medieval-tagged books

# 3. Verify combined filtering works
python scripts/rag_demo.py query "nobility medieval" \
  --chunk-type phase1_metadata \
  --tag-filter Mittelalter Adel \
  --mode semantic
# Expected: High precision, curated results only

# 4. Verify cross-lingual query works
python scripts/quick_search.py "fief feudo vassals" semantic 10 phase1_metadata
# Expected: Find German/French books about feudalism

# 5. Verify diagnostic accuracy
python scripts/quick_db_check.py
# Expected: lehen: 0 books (word boundary matching)
```

---

## Unresolved Questions / Future Work

1. **Make phase1_metadata default for semantic search?**
   - Pro: Eliminates noise by default
   - Con: Misses content that wasn't curated
   - **Recommendation:** Add `--default-chunk-type` config option

2. **Re-ranking to downweight noise?**
   - Implement post-processing to demote "Suns of God" type results
   - Boost phase1_metadata results in "search everything" mode
   - **Complexity:** Requires tuning, may introduce new biases

3. **Better cross-lingual handling?**
   - Automatic query translation?
   - Synonym expansion (Lehen → fief → feudo)?
   - **Research needed:** How do other RAG systems handle this?

4. **Annotations and highlights?**
   - Future chunk types for user annotations
   - Separate search target: "Search my highlights"
   - **Prerequisite:** Annotation extraction pipeline

---

## Important Context for Next Claude Instance

### User's Research Domain
- Ancient history, medieval studies, classical texts
- Multilingual corpus (German, English, French, Latin, Italian)
- Academic/scholarly sources from Calibre library

### User's Workflow
- Uses Calibre for library management
- Tags and comments books manually (imperfect by design)
- Wants ARCHILLES to discover connections across poorly tagged sources
- Prefers semantic search over keyword matching (context > exact terms)

### Technical Constraints
- Windows environment (PowerShell)
- Calibre library on D:\Calibre-Bibliothek
- ChromaDB 0.4.22
- BGE-M3 embedding model (multilingual but general-purpose)
- 1671 chunks indexed (78 phase1_metadata + 1591 content)

### Communication Style
- User is technically sophisticated
- Values transparency about limitations
- Appreciates architectural discussions
- Expects clear explanations of trade-offs

---

## Git Status

**Current branch:** `claude/fix-indexing-resume-gEatY`

**Recent commits:**
```
51b8083 feat: Add chunk_type filtering for separate content/metadata search
df167cd fix: Use word boundary matching to prevent false substring matches
0aaeca4 fix: Add mode and top_k parameter support to quick_search.py
2abae7d feat: Add diagnostic to investigate BM25 keyword search behavior
dd253c3 fix: Correct collection name to 'archilles_books'
```

**All changes committed and pushed:** ✅

---

## How to Resume

1. **Checkout branch:**
   ```bash
   git checkout claude/fix-indexing-resume-gEatY
   git pull origin claude/fix-indexing-resume-gEatY
   ```

2. **Verify environment:**
   ```bash
   echo $env:CALIBRE_LIBRARY  # Should be D:\Calibre-Bibliothek
   python scripts/quick_search.py  # Should work
   ```

3. **Review this document** for context

4. **Run test checklist** (see above) to validate current state

5. **Ask user** what they want to tackle next:
   - Make phase1_metadata default?
   - Implement re-ranking?
   - Explore better embedding models?
   - Add annotation support?
   - Performance optimization?

---

## Session Continuation Prompt

**For next Claude instance:**

> "I'm continuing from the previous session on ARCHILLES search quality. I've reviewed the handshake document (SESSION_HANDSHAKE.md) and understand:
>
> 1. We implemented chunk_type filtering - searches curated Calibre comments separately from content
> 2. This solved the semantic search noise problem (Suns of God no longer appears)
> 3. English queries work better than German for cross-lingual search
> 4. All changes are committed to branch claude/fix-indexing-resume-gEatY
>
> What would you like to work on next?"

---

## Final Notes

**User feedback on chunk_type filtering:**
- ✅ "good results: 1.ab + 2. Search ONLY ... (noise cancelled!)"
- ✅ "Test Cases A B C" all passed
- ❌ "Search Everything" still has noise (expected - BGE-M3 limitation)

**Key quote from user:**
> "Tags should be an option but not a condition. My tagging is by far not perfect and I hope Archilles will find many poorly tagged and commented sources!"

This drove the architectural decision for chunk_type filtering - enables searching curated content WITHOUT requiring perfect tags.

**Cross-lingual asymmetry observation:**
> "results were better with english terms in query (finding also german or french sources) - but bad results with german queries. So we must deal with it I guess until there is something better available."

This is a known BGE-M3 characteristic - document for users and recommend English queries when possible.

---

**End of Handshake Document**
**Next session should start by reviewing this file!**
