# Archilles Setup Guide for Windows Users

## Your Current Situation
You're using Claude Code which runs in a Linux Docker container on Windows 11. Your Calibre library and RAG database are on your Windows D: drive but the container cannot access them directly.

## Solution Options

### Option A: Work Directly on Windows (RECOMMENDED for Development)

**Best for:** Testing, indexing books, running queries on your actual library

1. **Open PowerShell on Windows** (not in Claude Code)

2. **Navigate to your archilles directory:**
   ```powershell
   cd C:\Users\tomra\archilles
   ```

3. **Set environment variables:**
   ```powershell
   $env:CALIBRE_LIBRARY_PATH = "D:\Calibre-Bibliothek"
   $env:RAG_DB_PATH = "D:\Calibre-Bibliothek\.archilles\rag_db"
   ```

4. **Install dependencies** (if not already done):
   ```powershell
   pip install -r requirements.txt
   ```

5. **Run commands directly:**
   ```powershell
   # Query your existing RAG database
   python scripts/rag_demo.py query "David Melchizedek"

   # Check what's indexed
   python scripts/list_indexed_books.py

   # Index a new book
   python scripts/rag_demo.py index "D:\Calibre-Bibliothek\Author\Book\book.pdf"
   ```

**Advantages:**
- ✅ Direct access to all your books
- ✅ Works with your existing RAG database immediately
- ✅ No file copying needed
- ✅ Faster for actual usage

**Disadvantages:**
- ❌ Claude Code can't directly help you (you'd run commands manually)
- ❌ Need Python installed on Windows

---

### Option B: Copy Database to Linux Container

**Best for:** Let Claude Code help you develop features, but can't access actual books

1. **On Windows, zip your RAG database:**
   ```powershell
   Compress-Archive -Path "D:\Calibre-Bibliothek\.archilles\rag_db\*" -DestinationPath "D:\rag_db.zip"
   ```

2. **Copy the zip file into the Claude Code workspace**
   - The workspace is synced between Windows and the Linux container
   - Copy `rag_db.zip` to: `C:\Users\tomra\archilles\rag_db.zip`

3. **In Claude Code (Linux), extract it:**
   ```bash
   cd /home/user/archilles
   unzip rag_db.zip -d ./rag_db/
   ```

4. **Set environment variables in Linux:**
   ```bash
   export RAG_DB_PATH="/home/user/archilles/rag_db"
   ```

**Advantages:**
- ✅ Claude Code can help you query and develop
- ✅ Good for testing code changes

**Disadvantages:**
- ❌ No access to actual books (can't index new ones)
- ❌ Database gets out of sync if you index on Windows
- ❌ Need to re-copy when Windows DB changes

---

### Option C: Hybrid Approach (BEST OF BOTH WORLDS)

**Use Windows for:** Indexing books, running queries on your library
**Use Claude Code for:** Code development, testing, documentation

This is probably what makes most sense given:
- You have "0.001 idea about coding" (your words!)
- You want Claude Code to help you develop
- But you also need to actually use the system with your library

---

## My Recommendation

**Start with Option A (Windows PowerShell)** to:
1. Verify your RAG database works
2. Run queries on your existing indexed books
3. Understand what you have

**Then use Claude Code (this environment)** to:
1. Develop new features
2. Fix bugs
3. Improve the codebase

**Then test changes on Windows** before committing.

---

## Next Steps

**Tell me which option you prefer**, and I'll help you:
1. Set up the environment
2. Verify it works
3. Show you what's in your RAG database
4. Plan next development steps

Remember: **You're not stuck!** We just need to choose the right tool for each job.
