# ARCHILLES Search Workflows

**Multiple strategies for different research needs**

---

## 🎯 Overview

ARCHILLES supports **iterative, multi-strategy search** to match different research workflows:

1. **Discovery Mode** - Find books about a topic (search Calibre comments)
2. **Deep Dive Mode** - Find specific passages within a book (search content)
3. **Hybrid Mode** - Search both simultaneously (when appropriate)

---

## 📚 Workflow 1: Book Discovery → Deep Dive

**Use Case:** "I want to find books about Roman military tactics, then explore relevant passages."

### Step 1: Discover Relevant Books

```powershell
# Search Calibre comments (book descriptions, summaries, your notes)
python scripts/rag_demo.py query "Roman Military tactics" --chunk-type calibre_comment --top-k 10
```

**What you get:**
- Book descriptions and summaries
- Your Calibre comments/notes about the books
- High-level overviews

**Results show:** `[1] Roman Warfare [CALIBRE_COMMENT]`

### Step 2: Deep Dive Into Promising Book

```powershell
# Search ONLY inside "Roman Warfare" for relevant passages
python scripts/rag_demo.py query "legion cohort maniple tactics" --book-id "Roman Warfare" --chunk-type content --top-k 10
```

**What you get:**
- Actual chapter text discussing tactics
- Specific passages with citations
- Page numbers and sections

**Results show:** `[1] Roman Warfare, FIVE` (Chapter 5)

### Step 3: Refine Your Search

```powershell
# More specific concept
python scripts/rag_demo.py query "siege warfare fortifications" --book-id "Roman Warfare" --chunk-type content

# Only main content (skip front matter, index)
python scripts/rag_demo.py query "tactics" --book-id "Roman Warfare" --section main --chunk-type content

# Export for note-taking
python scripts/rag_demo.py query "tactics" --book-id "Roman Warfare" --chunk-type content --export notes.md
```

---

## 🔍 Workflow 2: Direct Content Search

**Use Case:** "I know what I'm looking for, show me relevant passages from all books."

### Search All Indexed Books

```powershell
# Search actual book content (NOT descriptions)
python scripts/rag_demo.py query "testudo formation shield wall" --chunk-type content --top-k 10
```

**What you get:**
- Passages from ALL indexed books
- Max 2 results per book (diversity)
- Actual text discussing the concept

### Add Filters

```powershell
# Only German language books
python scripts/rag_demo.py query "Herrschaftslegitimation" --chunk-type content --language de

# Only books with specific tags
python scripts/rag_demo.py query "political theory" --chunk-type content --tag-filter Geschichte Philosophie

# Only main content (skip indexes, TOC, etc.)
python scripts/rag_demo.py query "legitimacy" --chunk-type content --section main
```

---

## 🎨 Workflow 3: Comparative Research

**Use Case:** "I want to compare what different books say about a topic."

### Step 1: Wide Search

```powershell
# Search with high top-k and unlimited results per book
python scripts/rag_demo.py query "Roman citizenship expansion" --chunk-type content --top-k 20 --max-per-book 999
```

**What you get:**
- Multiple passages from multiple books
- Compare different perspectives

### Step 2: Narrow by Language or Tag

```powershell
# Only German-language scholarship
python scripts/rag_demo.py query "citizenship" --chunk-type content --language de --top-k 20

# Only specific academic tags
python scripts/rag_demo.py query "citizenship" --chunk-type content --tag-filter "Antike" "Politikwissenschaft"
```

---

## 📝 Workflow 4: Searching Your Own Notes

**Use Case:** "What did I write about this topic in my Calibre comments?"

### Search Only Your Comments

```powershell
# Search ONLY Calibre comments (your curated notes and descriptions)
python scripts/rag_demo.py query "important primary source" --chunk-type calibre_comment --top-k 10
```

**What you get:**
- Your own comments and notes
- Book descriptions you've added
- Summaries and annotations

### Combine with Book Filter

```powershell
# What did I note about "Roman Warfare"?
python scripts/rag_demo.py query "tactics strategy" --book-id "Roman Warfare" --chunk-type calibre_comment
```

---

## ⚡ Workflow 5: Quick Exact Phrase Matching

**Use Case:** "Find exact Latin quotes or specific technical terms."

### Exact Phrase Search

```powershell
# Find exact phrase (case-insensitive, handles line breaks)
python scripts/rag_demo.py query "evangelista et a presbyteris" --exact --chunk-type content
```

**What you get:**
- ONLY chunks containing the exact phrase
- Handles line breaks in text
- Great for Latin quotes, technical terms

### Combine with Keyword Mode

```powershell
# Exact word matching (BM25 algorithm)
python scripts/rag_demo.py query "Herrschaftslegitimation" --mode keyword --chunk-type content
```

**When to use:**
- Custom terms you invented
- Specific German compound words
- Technical terminology

---

## 🔄 Workflow 6: Iterative Refinement

**Use Case:** "Start broad, narrow down, then deep dive."

### Iteration 1: Broad Discovery

```powershell
python scripts/rag_demo.py query "legitimacy of rule" --chunk-type calibre_comment --top-k 15
```

**Result:** Find 5 relevant books

### Iteration 2: Narrow to Best Book

```powershell
# Pick the most relevant book from Iteration 1
python scripts/rag_demo.py query "legitimacy consent authority" --book-id "The Making of a Christian Empire" --chunk-type content --top-k 10
```

**Result:** Find 10 relevant passages

### Iteration 3: Refine Concept

```powershell
# Drill down into specific sub-concept
python scripts/rag_demo.py query "divine right imperial authority" --book-id "The Making of a Christian Empire" --chunk-type content --section main
```

**Result:** Highly targeted passages

### Iteration 4: Export for Writing

```powershell
# Save your findings
python scripts/rag_demo.py query "divine right" --book-id "The Making of a Christian Empire" --chunk-type content --export research-notes.md
```

---

## 🎯 Search Modes Explained

### Mode 1: Semantic Search (`--mode semantic`)

**How it works:**
- Uses BGE-M3 embeddings to find conceptually similar passages
- Finds synonyms and related concepts
- Language-agnostic (finds concepts across languages)

**Best for:**
- Exploring topics broadly
- Finding related concepts
- Cross-language research

**Example:**
```powershell
python scripts/rag_demo.py query "legitimacy of rule" --mode semantic
# Finds: "Herrschaftslegitimation", "imperial authority", "divine right"
```

### Mode 2: Keyword Search (`--mode keyword`)

**How it works:**
- Uses BM25 algorithm for exact word matching
- Finds documents containing specific terms
- Case-insensitive

**Best for:**
- Custom terminology
- Specific technical terms
- German compound words
- Your own coined phrases

**Example:**
```powershell
python scripts/rag_demo.py query "Herrschaftslegitimation" --mode keyword
# Finds: Only passages with "Herrschaftslegitimation"
```

### Mode 3: Hybrid Search (`--mode hybrid`, DEFAULT)

**How it works:**
- Combines semantic + keyword using Reciprocal Rank Fusion
- Gets best of both worlds
- Boosts results that match tags

**Best for:**
- Most searches (this is the default!)
- Finding concepts AND exact terms
- General-purpose research

**Example:**
```powershell
python scripts/rag_demo.py query "Roman tactics formations" --mode hybrid
# Finds: Conceptually related passages + exact term matches
```

---

## 🏷️ Content Types Explained

### Content Type 1: Book Text (`--chunk-type content`, DEFAULT)

**What it includes:**
- Actual book chapters
- Main narrative and arguments
- Primary source quotes
- Footnotes and endnotes

**When to use:** 99% of searches (this is the default!)

**Results show:** `[1] Roman Warfare, FIVE`

### Content Type 2: Calibre Comments (`--chunk-type calibre_comment`)

**What it includes:**
- Book descriptions and summaries
- Your personal Calibre comments
- Publisher descriptions
- Back cover text

**When to use:**
- Finding books about a topic (discovery mode)
- Searching your own notes
- Overview/summary searches

**Results show:** `[1] Roman Warfare [CALIBRE_COMMENT]`

### Content Type 3: All (`--chunk-type all`)

**What it includes:**
- Both book text AND Calibre comments mixed

**When to use:**
- Rarely! Usually better to search separately
- Only when you want maximum coverage and don't care about weighting issues

---

## 📊 Results Control

### Top-K (Number of Results)

```powershell
# Default: 10 results
python scripts/rag_demo.py query "tactics"

# More results
python scripts/rag_demo.py query "tactics" --top-k 20

# Fewer results
python scripts/rag_demo.py query "tactics" --top-k 5
```

### Max Per Book (Diversity)

```powershell
# Default: max 2 results per book (for diversity)
python scripts/rag_demo.py query "tactics"

# Allow more from same book
python scripts/rag_demo.py query "tactics" --max-per-book 5

# Get ALL results from each book (no diversity limit)
python scripts/rag_demo.py query "tactics" --max-per-book 999
```

**When to increase:**
- Deep diving into a single book
- Comparative analysis within same work
- Building comprehensive notes

**When to keep low:**
- Broad discovery across many books
- Want diverse perspectives
- Survey research

---

## 💡 Pro Tips

### Tip 1: Query Language Matters

**For Calibre Comments (descriptions):**
```powershell
# Use overview/summary language
python scripts/rag_demo.py query "history of Roman military tactics" --chunk-type calibre_comment
```

**For Book Content:**
```powershell
# Use specific terms that appear in text
python scripts/rag_demo.py query "legion cohort centurion maniple" --chunk-type content
```

### Tip 2: Combine Filters

```powershell
# German books about history, main content only, max 3 per book
python scripts/rag_demo.py query "Herrschaft" \
  --language de \
  --tag-filter Geschichte \
  --section main \
  --chunk-type content \
  --max-per-book 3
```

### Tip 3: Export for Workflows

```powershell
# Step 1: Find books
python scripts/rag_demo.py query "Roman tactics" --chunk-type calibre_comment --export step1.md

# Step 2: Deep dive
python scripts/rag_demo.py query "tactics" --book-id "Roman Warfare" --chunk-type content --export step2.md

# Now you have both saved for reference
```

### Tip 4: Use Exact Matching for Precision

```powershell
# When you need exact quotes
python scripts/rag_demo.py query "qui autem rex" --exact --chunk-type content --language la
```

---

## 🚀 Quick Reference

| Goal | Command Template |
|------|------------------|
| **Find books about topic** | `query "topic" --chunk-type calibre_comment` |
| **Deep dive in book** | `query "concept" --book-id "BookName" --chunk-type content` |
| **Search all content** | `query "concept" --chunk-type content` |
| **Exact phrase** | `query "exact phrase" --exact --chunk-type content` |
| **Custom terms** | `query "MyTerm" --mode keyword --chunk-type content` |
| **German books only** | `query "Begriff" --language de --chunk-type content` |
| **Export results** | `query "topic" --export notes.md` |
| **More diversity** | `query "topic" --top-k 20 --max-per-book 1` |
| **Focus on one book** | `query "topic" --book-id "Book" --max-per-book 999` |

---

## ❓ FAQ

**Q: Should I search comments or content?**
A: Start with comments to find books, then search content within the book.

**Q: What's the difference between hybrid and semantic mode?**
A: Hybrid (default) combines semantic + keyword. Use hybrid for most searches.

**Q: Why are my relevance scores low?**
A: Absolute scores don't matter - focus on ranking. Lower scores just mean the query language differs from text language.

**Q: How do I search only my own notes?**
A: Use `--chunk-type calibre_comment` - this includes your comments.

**Q: Can I search multiple books at once?**
A: Yes! Just don't use `--book-id` filter, or use tag filters instead.

**Q: What does [CALIBRE_COMMENT] mean?**
A: This result comes from a Calibre comment/description, not book text.

---

**Next:** See [USAGE.md](USAGE.md) for command-line syntax and [EXAMPLES.md](EXAMPLES.md) for real-world research scenarios.
