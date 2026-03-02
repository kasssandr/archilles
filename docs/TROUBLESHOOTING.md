# Troubleshooting Guide

Solutions to the most common problems with Archilles.

---

## Table of Contents

1. [Installation Problems](#installation-problems)
2. [Indexing Problems](#indexing-problems)
3. [MCP / Claude Desktop Problems](#mcp--claude-desktop-problems)
4. [Search Problems](#search-problems)
5. [Performance](#performance)
6. [Diagnosing Unknown Issues](#diagnosing-unknown-issues)

---

## Installation Problems

### `pip install -r requirements.txt` fails

**Error mentions `torch` or CUDA:**
PyTorch installation depends on your CUDA version. Install the correct version first, then run `pip install -r requirements.txt` again:
```bash
# Visit https://pytorch.org/get-started/locally/ for the exact command for your system
# Example for CUDA 12.1:
pip install torch --index-url https://download.pytorch.org/whl/cu121
```

**Error mentions a build failure (Windows):**
Make sure you have the Microsoft C++ Build Tools installed.
Download from: [visualstudio.microsoft.com/visual-cpp-build-tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/)

**Error mentions `lancedb`:**
LanceDB requires Python 3.11+. Check your version:
```bash
python --version
```
If it shows 3.10 or below, install Python 3.11 or 3.12 and recreate your virtual environment.

---

### Python version errors

Archilles requires **Python 3.11 or higher**. If you see syntax errors or missing features:

```bash
# Windows — use the py launcher to select the right version:
py -3.11 -m venv venv

# macOS/Linux:
python3.11 -m venv venv
```

---

### `ModuleNotFoundError` on first run

Your virtual environment is probably not activated:

```bash
# Windows:
venv\Scripts\activate

# macOS/Linux:
source venv/bin/activate
```

Your prompt should show `(venv)` when active. Then retry the command.

---

### BGE-M3 model download fails

On first indexing run, Archilles downloads ~2.2 GB from Hugging Face. If this fails:

- Check your internet connection
- Retry — the download resumes where it left off on the next attempt
- If behind a proxy, set `HF_DATASETS_OFFLINE=0` and configure your proxy settings

The model is cached in `~/.cache/huggingface/` after a successful download and never needs to be downloaded again.

---

## Indexing Problems

### "CALIBRE_LIBRARY_PATH not set" or library not found

Archilles cannot find your Calibre library.

1. **Confirm the path contains `metadata.db`:**
   ```powershell
   Test-Path "D:\My Calibre Library\metadata.db"
   # Should print: True
   ```

2. **Set the environment variable for your current session:**
   ```powershell
   $env:CALIBRE_LIBRARY_PATH = "D:\My Calibre Library"
   ```

3. **For permanent use**, add it as a Windows user environment variable:
   Settings → System → About → Advanced system settings → Environment Variables → New

4. **For MCP use**, add it to `claude_desktop_config.json` under `env` — see [MCP Guide](MCP_GUIDE.md).

---

### Indexing is very slow

Expected speeds:
- **With GPU (4 GB+ VRAM):** ~1–3 minutes per book
- **CPU only:** ~10–20 minutes per book

If slower than expected, check whether PyTorch sees your GPU:
```bash
python -c "import torch; print(torch.cuda.is_available())"
```
If `False`, reinstall PyTorch with CUDA support for your driver version.

On very first run, BGE-M3 (~2.2 GB) downloads before indexing begins — that wait is normal.

---

### Indexing aborts partway through

Resume from where it stopped:
```bash
python scripts/batch_index.py --tag "Your-Tag" --skip-existing
```

Also check: disk space (index can be several GB for large libraries) and available RAM.

---

### A book is skipped as "mostly scanned"

Archilles detects PDFs with mostly image pages and no embedded text. These cannot be semantically indexed without OCR.

To enable OCR (requires Tesseract installed):
```bash
python scripts/rag_demo.py index "path/to/scanned_book.pdf" --ocr
```

Install Tesseract on Windows: [github.com/UB-Mannheim/tesseract/wiki](https://github.com/UB-Mannheim/tesseract/wiki)

---

### "DATABASE ERROR" during batch indexing

Indicates a problem with the LanceDB database, usually from an abrupt shutdown during a write.

```bash
# Check if the database is accessible at all
python scripts/rag_demo.py stats

# If stats works, just resume:
python scripts/batch_index.py --tag "Your-Tag" --skip-existing

# If stats also fails, restore from a backup (if SafeIndexer was running):
# Backups are stored in: D:\Calibre Library\.archilles\rag_db_backup_*
```

---

## MCP / Claude Desktop Problems

### Tools don't appear in Claude Desktop

**1. Validate the JSON syntax of your config file:**
```powershell
# Windows PowerShell:
Get-Content "$env:APPDATA\Claude\claude_desktop_config.json" | python -m json.tool
```
A single misplaced comma or missing brace will prevent loading.

**2. Use the full path to your virtual environment's Python:**
```json
"command": "C:\\Users\\YourName\\archilles\\venv\\Scripts\\python.exe"
```
Using just `python` may pick up the wrong interpreter.

**3. Restart Claude Desktop completely.**
On Windows, open Task Manager and make sure no Claude process is still running in the background before reopening.

**4. Check the log file** for startup errors:
```
C:\Users\YourName\.archilles\mcp_server.log
```

---

### "Tool ran without output"

The MCP server returned an empty response. Common causes:

- **Missing library path:** Add `CALIBRE_LIBRARY_PATH` to the `env` section of your config.
- **Wrong path:** The `CALIBRE_LIBRARY_PATH` in the MCP config must point to the same library where `.archilles/rag_db/` lives.
- **Outdated version:** Pull the latest version from GitHub and restart.

---

### Library found but no results

The server starts but searches return nothing:

1. Confirm books are indexed: `python scripts/rag_demo.py stats`
2. Make sure the `CALIBRE_LIBRARY_PATH` in `claude_desktop_config.json` matches exactly where your index is stored. The index lives inside your Calibre library at `.archilles/rag_db/`.

---

### Slow first response after Claude Desktop start

On first use after launch, Archilles loads BGE-M3 into memory. This takes 10–60 seconds depending on your hardware. Subsequent queries in the same session are fast.

---

### MCP server crashes on startup

Run it manually to see the error directly:
```bash
python mcp_server.py
```

Common causes:

| Error | Solution |
|-------|----------|
| `ModuleNotFoundError` | Wrong Python path in config — use the venv Python |
| `CALIBRE_LIBRARY_PATH not set` | Add it to the `env` section in your config |
| `LanceDBError` on startup | Database issue — check `rag_demo.py stats` |

---

## Search Problems

### Search returns no results

1. Check if books are indexed: `python scripts/rag_demo.py stats`
2. Try a simpler, broader query first to confirm the index is working.
3. If you used `--language`, make sure the code is correct (e.g. `de`, `en`, `la` — not `german`).
4. Try keyword mode for very specific terms:
   ```bash
   python scripts/rag_demo.py query "your term" --mode keyword
   ```

---

### Search results are irrelevant

- **Use hybrid mode** (default) — almost always better than either mode alone.
- **Add more context:** instead of "trade", try "medieval trade routes between Italy and Flanders".
- **Filter by tag or language** to reduce noise.
- **For exact phrases and names**, use `--exact`:
  ```bash
  python scripts/rag_demo.py query "in necessariis unitas" --exact
  ```

---

### Citations show wrong page numbers

Page numbers are extracted from the PDF's internal page labels. Some PDFs have incorrect or missing labels — this is a limitation of the source file, not a bug.

EPUB results always show chapter names instead of page numbers. This is by design — EPUBs have no physical pages. See the note in [USAGE.md](USAGE.md) about using verbatim quotes to locate passages in EPUB files.

---

## Performance

### High RAM usage during indexing

Typical peak usage:
- Base Python + LanceDB: ~1–2 GB
- BGE-M3 loaded for embedding: +2–3 GB additional
- Indexing large PDFs: up to 6–8 GB peak

Use the `minimal` profile to reduce memory usage (smaller batch size):
```bash
python scripts/batch_index.py --tag "Your-Tag" --profile minimal
```

---

### GPU not being used

```bash
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'No GPU')"
```

If `False`: reinstall PyTorch with CUDA support matching your GPU driver. Visit [pytorch.org/get-started/locally](https://pytorch.org/get-started/locally/).

---

## Diagnosing Unknown Issues

### Check the log file

```bash
# Windows:
type C:\Users\YourName\.archilles\mcp_server.log

# macOS/Linux:
cat ~/.archilles/mcp_server.log
```

### Run the MCP server manually

Instead of letting Claude Desktop start it, run it yourself to see all output live:
```bash
python mcp_server.py
```
Startup errors print immediately. Press Ctrl+C to stop.

### Collect debug info for a bug report

```bash
# Python version
python --version

# Git commit (which version of Archilles you have)
git log -1 --oneline

# Installed packages (relevant ones)
pip list | grep -E "lancedb|sentence-transformers|torch|pymupdf"

# Index status
python scripts/rag_demo.py stats
```

---

## Still stuck?

Open an issue on [GitHub](https://github.com/kasssandr/archilles/issues) and include:
- Your operating system and Python version
- The error message or the relevant section of `~/.archilles/mcp_server.log`
- Output of `python scripts/rag_demo.py stats`
- The git commit hash (`git log -1 --oneline`)
- What you were trying to do when the error occurred
