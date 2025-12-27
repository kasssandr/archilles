# Annotation Matching Strategy

## Problem

Calibre creates annotation file names by hashing the **full book path**:
```
annotation_file_name = SHA256(full_path).hex + ".json"
```

For example:
```
full_path = "E:\Calibre-Bibliothek\Thomas Romer\Die Erfindung Gottes (7150)\book.epub"
hash = SHA256("E:\Calibre-Bibliothek\Thomas Romer\Die Erfindung Gottes (7150)\book.epub")
annotation_file = "{hash}.json"
```

This creates two problems when the library is migrated:

### Problem 1: Base Path Changes
- **Original**: `E:\Calibre-Bibliothek\Author\Title (ID)\book.epub`
- **Current**: `D:\Calibre-Bibliothek\Author\Title (ID)\book.epub`
- **Result**: Hash doesn't match, annotation file can't be found

### Problem 2: Book Metadata Changes
If you rename a book's title or author in Calibre, the folder structure changes:
- **Original**: `E:\Calibre-Bibliothek\Author\Old Title (7150)\book.epub`
- **After rename**: `E:\Calibre-Bibliothek\Author\New Title (7150)\book.epub`
- **Result**: Even with same base path, hash doesn't match

**Key insight**: The book ID (e.g., `7150`) is the only stable identifier!

## Solution

### Implemented: Comprehensive Path Variant Testing

The `AnnotationsIndexer` now tests **300+ path combinations** per book:

1. **All drive letters** (A-Z) with current path structure
2. **Common library locations**:
   - `C:\Calibre-Bibliothek`
   - `D:\Users\tomra\Calibre-Bibliothek`
   - `E:\Users\tomra\Documents\Calibre-Bibliothek`
   - etc.

3. **Multiple library name variants**:
   - `Calibre-Bibliothek` (German)
   - `Calibre Library` (English)
   - `Calibre`, `Books`, `eBooks`

4. **Path normalization variants**:
   - Backslashes: `E:\Calibre-Bibliothek\Author\...`
   - Forward slashes: `E:/Calibre-Bibliothek/Author/...`
   - Platform normalized: `Path()` normalization

This solves **Problem 1** (base path changes) for most scenarios.

### Fallback: Fuzzy Matching

For annotations that still don't match (Problem 2 - renamed books), the system uses fuzzy matching:

1. Reads annotation text content
2. Searches for book title/author keywords
3. Matches based on similarity score (>60% threshold)
4. Assigns best matching book

## Diagnostic Tools

### 1. Match Annotations to Books
Shows which annotations matched and which didn't:
```bash
python scripts/match_annotations_to_books.py
```

Output:
- ✅ Matched annotations with book details
- ❌ Unmatched annotations with text samples
- Match rate percentage

### 2. Find Original Path (Enhanced)
Tests all path variants to find the original library location:
```bash
python scripts/find_original_path_enhanced.py
```

Output:
- Tests 1000+ hash combinations
- Reports which base path produced the most matches
- Shows matched books with their original paths

### 3. Check MCP Server Effectiveness
After reindexing, check the logs:
```bash
# Look for these log messages:
# "Created hash mapping: X hash variants from Y books"
# "Direct hash matches: X/Y"
# "Books without metadata: X"
```

## How to Test

### Step 1: Restart MCP Server
The enhanced matching is now in the code. Restart Claude Desktop to reload:
1. Quit Claude Desktop
2. Start Claude Desktop
3. Wait for Archilles MCP server to load

### Step 2: Reindex Annotations
In Claude Desktop chat:
```
Please reindex all annotations with force_reindex=True
```

This will:
1. Test 300+ path variants per book
2. Report match effectiveness in logs
3. Use fuzzy matching for unmatched annotations

### Step 3: Check Results
Look for these in the indexing output:
```
Testing 100+ path base variants...
Created hash mapping: 50000 hash variants from 200 books
Direct hash matches: 150/185 (81% matched)
Books without metadata: 35
```

### Step 4: Search Annotations
Try a test search:
```
Search annotations for: "Häresiologie"
```

Check if the results show proper book metadata:
- ✅ Book title and author visible
- ❌ "Unknown" metadata = matching failed

## Expected Results

### Best Case (All Problems Solved)
```
Direct hash matches: 185/185 (100%)
Books without metadata: 0
```
All annotations have proper book metadata.

### Good Case (Problem 1 Solved)
```
Direct hash matches: 150/185 (81%)
Books without metadata: 35
Fuzzy matched: 30/35
```
Most annotations matched via hash, some via fuzzy matching.

### Problematic Case (Need Manual Review)
```
Direct hash matches: 50/185 (27%)
Books without metadata: 135
Fuzzy matched: 80/135
```
Many books were renamed or library structure is very different.
Consider manual mapping or reviewing unmatched annotations.

## Advanced: Manual Mapping

If automatic matching fails, you can create a manual mapping file:

```json
// .archilles/annotation_hash_mapping.json
{
  "abc123...def": {
    "book_id": 7150,
    "title": "Die Erfindung Gottes",
    "author": "Thomas Römer"
  }
}
```

## Technical Details

### Hash Computation
```python
def compute_book_hash(book_path: str) -> str:
    return hashlib.sha256(book_path.encode('utf-8')).hexdigest()
```

### Path Variant Generation
See `src/calibre_mcp/annotations_indexer.py:_create_hash_to_book_mapping()`

### Fuzzy Matching Algorithm
See `src/calibre_mcp/annotations_indexer.py:_fuzzy_match_book()`

Scoring:
- 80% weight: Book title appears in annotation text
- 50% weight: Author name appears in annotation text
- 10% weight: Filename keywords match
- Minimum 60% threshold for match

## Known Limitations

1. **Renamed Books**: If books were extensively renamed in Calibre after annotations were created, automatic matching may fail

2. **Non-Standard Library Structures**: If your library was in an unusual location (network drive, special characters, etc.), you may need to add custom path variants

3. **Fuzzy Matching Accuracy**: Annotations that don't contain book title/author text may be mismatched

4. **Performance**: Testing 300+ variants per book is computationally expensive during first indexing (but results are cached)

## Future Improvements

1. **Manual Review UI**: Tool to manually map unmatched annotations to books
2. **Book ID Extraction**: Attempt to extract book ID from annotation file content (if Calibre adds this in future versions)
3. **Path Learning**: Learn the original path structure from successful matches
4. **Annotation Export**: Export annotations with metadata for backup/portability
