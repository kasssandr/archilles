# Installation Guide

A step-by-step guide to setting up Archilles on your machine.

---

## Table of Contents

1. [System Requirements](#system-requirements)
2. [Installation (Windows)](#installation-windows)
3. [Installation (macOS / Linux)](#installation-macos--linux)
4. [First-Run: Model Download](#first-run-model-download)
5. [Verify Your Installation](#verify-your-installation)
6. [Next Steps](#next-steps)

---

## System Requirements

### Required

| Component | Minimum | Notes |
|-----------|---------|-------|
| **Python** | 3.11+ | 3.12 works; 3.10 and below will not |
| **Calibre** | Any recent version | Must have an existing library with books |
| **RAM** | 8 GB | 16 GB recommended for larger libraries |
| **Disk space** | ~5 GB free | BGE-M3 model (~2.2 GB) + index storage |

### Optional but Recommended

| Component | Why it matters |
|-----------|----------------|
| **NVIDIA GPU (4 GB+ VRAM)** | Indexing speed: ~2 min/book with GPU vs. ~15 min/book CPU-only |
| **CUDA Toolkit** | Required for NVIDIA GPU acceleration |
| **Apple Silicon (M1/M2/M3/M4)** | MPS acceleration enabled automatically — no extra setup |
| **Claude Desktop** | The primary way to use Archilles (MCP integration) |

> **No GPU?** Archilles works fine on CPU — it just takes longer to build the initial index. Once indexed, search is fast regardless.

---

## Installation (Windows)

### Step 1: Install Python

Download Python 3.11 or 3.12 from [python.org](https://www.python.org/downloads/).

**Important during installation:** Check **"Add Python to PATH"**.

Verify:
```powershell
python --version
# Should show: Python 3.11.x or 3.12.x
```

### Step 2: Clone the Repository

```powershell
git clone https://github.com/kasssandr/archilles.git
cd archilles
```

> No git? Download [Git for Windows](https://git-scm.com/download/win) first, or download the repository as a ZIP from GitHub.

### Step 3: Create a Virtual Environment (Recommended)

A virtual environment keeps Archilles' dependencies isolated from your system Python.

```powershell
python -m venv venv
venv\Scripts\activate
```

Your prompt will change to show `(venv)` when active. Run this activation command every time you open a new terminal for Archilles work.

### Step 4: Install Dependencies

```powershell
pip install -r requirements.txt
```

This installs all required packages. Expect it to take a few minutes on first run.

> **GPU users:** If you want CUDA-accelerated indexing, install the correct PyTorch version for your CUDA version *before* running the above. See [pytorch.org/get-started](https://pytorch.org/get-started/locally/) for the right command.

### Step 5: Set Your Calibre Library Path

Archilles needs to know where your Calibre library is. Your library folder contains a file called `metadata.db`.

**Option A — Environment variable (temporary, for this session):**
```powershell
$env:CALIBRE_LIBRARY_PATH = "D:\My Calibre Library"
```

**Option B — System environment variable (permanent):**
1. Open *Settings → System → About → Advanced system settings → Environment Variables*
2. Under *User variables*, click *New*
3. Name: `CALIBRE_LIBRARY_PATH`
4. Value: your library path (e.g. `D:\My Calibre Library`)

> **Default:** If you don't set this, Archilles looks for `C:\Calibre Library`. You must set it if your library is elsewhere.

### Step 6: Index Your First Book

```powershell
python scripts/rag_demo.py index "D:\My Calibre Library\Author Name\Book Title (1)\book.pdf"
```

**What happens:**
1. On first run, Archilles downloads the BGE-M3 embedding model (~2.2 GB). This happens once. See [First-Run: Model Download](#first-run-model-download).
2. The book is extracted, chunked, and embedded. A 300-page PDF takes about 2–15 minutes depending on your hardware.
3. The index is saved to `.archilles\rag_db\` inside your Calibre library folder.

### Step 7: Test Your Installation

```powershell
python scripts/rag_demo.py stats
python scripts/rag_demo.py query "test search"
```

If stats shows at least 1 book and 1 chunk, your installation is working.

---

## Installation (macOS / Linux)

> **Note:** macOS and Linux are not officially tested. The instructions below should work, but you may encounter platform-specific issues. Please open a GitHub issue if you do.

```bash
# Clone
git clone https://github.com/kasssandr/archilles.git
cd archilles

# Virtual environment
python3 -m venv venv
source venv/bin/activate

# Dependencies
pip install -r requirements.txt

# Set library path
export CALIBRE_LIBRARY_PATH="/Users/yourname/Calibre Library"
# Add this line to ~/.zshrc or ~/.bashrc to make it permanent

# Index a book
python scripts/rag_demo.py index "/path/to/Calibre Library/Author/Book/book.epub"

# Verify
python scripts/rag_demo.py stats
```

**macOS note (Apple Silicon):** Archilles automatically detects and uses **MPS acceleration** (Metal Performance Shaders) on M1/M2/M3/M4 chips — no configuration needed. Indexing speed will be significantly faster than CPU-only.

**macOS note (PyMuPDF):** If you see errors related to `fitz` or `PyMuPDF`, try:
```bash
pip install --upgrade pymupdf
```

**Linux note:** For OCR support (scanned PDFs), install Tesseract:
```bash
sudo apt install tesseract-ocr tesseract-ocr-deu  # Debian/Ubuntu; adjust for your distro
```

---

## First-Run: Model Download

On the very first indexing operation, Archilles automatically downloads the **BGE-M3** embedding model from Hugging Face:

| What | Size | Where |
|------|------|-------|
| BGE-M3 (`BAAI/bge-m3`) | ~2.2 GB | `~/.cache/huggingface/` |
| bge-reranker-v2-m3 (optional) | ~560 MB | `~/.cache/huggingface/` |

The reranker only downloads if you enable `"enable_reranking": true` in `.archilles/config.json`.

**This download only happens once.** Subsequent indexing and search use the cached model.

> **Offline use:** If you need to run Archilles without internet access after initial setup, this works fine — the models are cached locally.

---

## Verify Your Installation

Run this sequence to confirm everything is working:

```powershell
# 1. Check index status
python scripts/rag_demo.py stats

# 2. Run a basic search
python scripts/rag_demo.py query "test"

# 3. Start MCP server (should start without errors, Ctrl+C to stop)
python mcp_server.py
```

Expected output for `stats` (after indexing at least one book):
```
Books indexed: 1
Total chunks: ~500–2000 (depending on book length)
Languages detected: ...
```

---

## Next Steps

- **Index more books:** [Batch indexing by tag or author →](USAGE.md#indexing)
- **Connect to Claude Desktop:** [MCP Integration Guide →](MCP_GUIDE.md)
- **Search strategies:** [Usage Guide →](USAGE.md)
- **Something not working?** [Troubleshooting →](TROUBLESHOOTING.md)

---

## Optional Configuration

You can create a configuration file at `.archilles/config.json` inside your Calibre library folder:

```json
{
  "enable_reranking": false,
  "reranker_device": "cpu",
  "rag_db_path": ".archilles/rag_db"
}
```

| Setting | Default | Description |
|---------|---------|-------------|
| `enable_reranking` | `false` | Enable cross-encoder reranking for better result quality. Downloads ~560 MB model on first use. |
| `reranker_device` | `"cpu"` | `"cpu"` or `"cuda"`. CPU is usually better since the GPU is busy with embeddings. |
| `rag_db_path` | `.archilles/rag_db` | Custom path for the vector database, if you want to store it elsewhere. |
