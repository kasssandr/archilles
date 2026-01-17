# Iterative Search - Quick Start Guide

**Based on your feedback: "It would be good to have several different strategies for search and to be able to use them to get results in an iterative process."**

---

## ✅ What I Just Fixed

### 1. **Display Consistency** ✨
**Your request:** "Q3: would be nice to have [CALIBRE_COMMENT indicators]"

**What changed:**
- ✅ ALL Calibre comment results now show `[CALIBRE_COMMENT]` suffix
- ✅ Markdown exports use 📝 emoji for visual clarity
- ✅ Consistent across terminal and file exports

**Test it:**
```powershell
# All 10 results will now show [CALIBRE_COMMENT]
python scripts/rag_demo.py query "Roman Military tactics" --chunk-type calibre_comment --top-k 10
```

---

## 🚀 Your Iterative Workflow (Works NOW!)

### **Workflow Pattern You Described:**

> "I wonder if, once I've found a certain book with generally promising content, I can in an iterative approach ask explicitly to suggest me a couple of relevant passages."

**YES! Here's exactly how:**

### **Step 1: Find Promising Books**
```powershell
# Search Calibre comments (descriptions, summaries, your notes)
python scripts/rag_demo.py query "Roman Military tactics" --chunk-type calibre_comment --top-k 10
```

**Result:** "Roman Warfare by Adrian Goldsworthy looks promising!"

### **Step 2: Get Relevant Passages from That Book**
```powershell
# Now search ONLY inside "Roman Warfare" for relevant passages
python scripts/rag_demo.py query "legion cohort tactics formations" --book-id "Roman Warfare" --chunk-type content --top-k 10
```

**Result:** 10 relevant passages from that specific book!

### **Step 3: Refine Further**
```powershell
# More specific concept
python scripts/rag_demo.py query "siege warfare fortifications" --book-id "Roman Warfare" --chunk-type content

# Or focus on main chapters only (skip front matter, index)
python scripts/rag_demo.py query "tactics" --book-id "Roman Warfare" --section main --chunk-type content
```

---

## 🎯 Your Questions Answered

### **Q1: Option A or B?**
> "Option A for searches in comments field / option A+B weighed for queries in books"

**Already implemented!**
- Calibre comments: Matches descriptions/summaries (overview language)
- Book content: Hybrid search (semantic + keyword) finds both concepts and exact terms

**No action needed** - this is how it works by default!

### **Q2: Discovery vs Deep Reading?**
> "It depends - it would be good to use both ways, knowing how to address the former or the latter."

**You can!** See the workflow above:
- **Discovery:** `--chunk-type calibre_comment` (find books)
- **Deep Reading:** `--book-id "BookName" --chunk-type content` (find passages)

### **Q3: Show [CALIBRE_COMMENT]?**
> "would be nice to have"

**✅ DONE!** All Calibre comment results now show the indicator.

---

## 📚 Complete Workflow Documentation

I created **`docs/SEARCH_WORKFLOWS.md`** with:

✅ **6 workflow patterns:**
1. Book Discovery → Deep Dive (what you described!)
2. Direct Content Search (search all books)
3. Comparative Research (multiple books)
4. Searching Your Own Notes (Calibre comments only)
5. Exact Phrase Matching (Latin quotes, technical terms)
6. Iterative Refinement (broad → narrow → specific)

✅ **When to use each mode:**
- `--mode semantic` - Find related concepts
- `--mode keyword` - Find exact terms (your custom vocabulary)
- `--mode hybrid` - Best of both (DEFAULT)

✅ **Content type guide:**
- `--chunk-type content` - Book text (DEFAULT)
- `--chunk-type calibre_comment` - Descriptions and your notes
- `--chunk-type all` - Both (rarely needed)

✅ **Pro tips and examples**

---

## 🎁 Ready-to-Use Commands

### **Discovery → Deep Dive (Your Main Workflow)**

```powershell
# 1. Find books about a topic
python scripts/rag_demo.py query "legitimacy of rule political authority" --chunk-type calibre_comment --top-k 10

# 2. You find "The Making of a Christian Empire" looks good
# 3. Get relevant passages from that book:
python scripts/rag_demo.py query "legitimacy divine right imperial authority" --book-id "The Making of a Christian Empire" --chunk-type content --top-k 10

# 4. Refine to specific concept:
python scripts/rag_demo.py query "Lactantius Constantine legitimacy" --book-id "The Making of a Christian Empire" --chunk-type content --section main

# 5. Export your findings:
python scripts/rag_demo.py query "Lactantius legitimacy" --book-id "The Making of a Christian Empire" --chunk-type content --export research-notes.md
```

### **Search Your Own Notes**

```powershell
# What did I write about this topic in my Calibre comments?
python scripts/rag_demo.py query "primary source important" --chunk-type calibre_comment --top-k 10
```

### **Exact Latin Quotes**

```powershell
# Find exact phrase (handles line breaks)
python scripts/rag_demo.py query "evangelista et a presbyteris" --exact --chunk-type content --language la
```

### **German Academic Terms**

```powershell
# Your custom German compound words
python scripts/rag_demo.py query "Herrschaftslegitimation" --mode keyword --chunk-type content --language de
```

---

## 📊 What We've Accomplished Today

### ✅ **Fixes Applied:**

1. **Calibre Comments Separated** (your critical issue)
   - Default: book text only
   - Explicitly request comments with `--chunk-type calibre_comment`
   - No more mixing that causes weighting problems

2. **Display Consistency**
   - All Calibre comments show `[CALIBRE_COMMENT]` indicator
   - Both terminal and markdown exports

3. **Better Defaults**
   - 10 results (was 5)
   - Max 2 per book (was 3)

4. **Clickable Citations**
   - file:// URIs for direct access
   - calibre:// URIs to open in Calibre

### 📚 **Documentation Created:**

1. **`SEARCH_WORKFLOWS.md`** - Complete workflow guide
2. **`IMPLEMENTATION_STATUS.md`** - Feature inventory
3. **`FIXES_APPLIED.md`** - Today's changes explained
4. **`SETUP_GUIDE_FOR_WINDOWS.md`** - Windows/Linux bridge

---

## 🎯 Your Current System Status

**Index:**
- ✅ 85 books indexed (before today)
- ⏳ 56 "New-Books" indexing (running now)
- **Total after completion:** ~141 books!

**Features:**
- ✅ Hybrid search (semantic + keyword)
- ✅ Iterative workflows (discovery → deep dive)
- ✅ Calibre comments separated from content
- ✅ Multiple search strategies
- ✅ Language filtering (de, en, la, etc.)
- ✅ Tag filtering
- ✅ Export to markdown

---

## 🚀 Next Steps (After Your Indexing Finishes)

### **1. Test the New Display**

```powershell
# Should show [CALIBRE_COMMENT] on ALL results
python scripts/rag_demo.py query "Roman Military" --chunk-type calibre_comment --top-k 3
```

### **2. Try the Iterative Workflow**

```powershell
# Step 1: Find books
python scripts/rag_demo.py query "your research topic" --chunk-type calibre_comment --top-k 10

# Step 2: Deep dive into the best one
python scripts/rag_demo.py query "specific concept" --book-id "BookYouFound" --chunk-type content --top-k 10
```

### **3. Merge the Fixes to Main**

```powershell
# After testing, merge to your main branch:
git checkout main
git merge claude/read-handover-docs-qpqjd
```

### **4. Read the Full Workflow Guide**

Check out **`docs/SEARCH_WORKFLOWS.md`** for:
- 6 different workflow patterns
- When to use each search mode
- Pro tips and examples
- Quick reference table

---

## 💡 Pro Tips for Your Research

### **Tip 1: Start Broad, Narrow Down**

```powershell
# Broad: Find books
query "topic" --chunk-type calibre_comment

# Narrow: Focus on best book
query "specific concept" --book-id "Book" --chunk-type content

# Precise: Exact sub-concept
query "detailed term" --book-id "Book" --section main --chunk-type content
```

### **Tip 2: Use Different Query Language**

**For descriptions (comments):**
- Use overview language: "history of Roman tactics"

**For book content:**
- Use specific terms that appear in text: "legion cohort centurion"

### **Tip 3: Export at Each Stage**

```powershell
# Discovery stage
query "topic" --chunk-type calibre_comment --export discovery.md

# Deep dive stage
query "concept" --book-id "Book" --chunk-type content --export passages.md
```

---

## ❓ FAQ

**Q: Why do Calibre comment searches have higher scores than content searches?**
A: Because descriptions use overview language that matches your queries better. This is expected! The ranking is what matters, not absolute scores.

**Q: Should I use --chunk-type all?**
A: Rarely. Usually better to search separately (comments for discovery, content for passages).

**Q: How do I know which books are indexed?**
A: Run `python scripts/list_indexed_books.py`

**Q: Can I search multiple specific books?**
A: Use tag filters instead: `--tag-filter "YourTag"`

---

## 🎉 Bottom Line

**You now have:**
- ✅ Iterative search workflow (discovery → deep dive)
- ✅ Multiple search strategies for different needs
- ✅ Proper separation of comments and content
- ✅ Consistent display with [CALIBRE_COMMENT] indicators
- ✅ Complete documentation

**Your vision:**
> "several different strategies for search and to be able to use them to get results in an iterative process"

**Status:** ✅ **IMPLEMENTED AND DOCUMENTED!**

---

**Enjoy your research! 🚀**

After your indexing finishes, test the workflows and let me know how it goes!
