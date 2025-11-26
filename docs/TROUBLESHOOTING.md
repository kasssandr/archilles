# Troubleshooting Guide

> **Status**: Documentation in progress

## Installation Issues

### PyTorch installation fails

**Problem**: `pip install` fails with PyTorch errors

**Solution**:
```bash
# Install PyTorch separately first
pip install torch torchvision torchaudio

# Then install other requirements
pip install -r requirements.txt
```

### Model download fails

**Problem**: BGE-M3 model download times out or fails

**Solution**:
- Check internet connection
- Retry (model is cached after first successful download)
- Manual download: See [Hugging Face BGE-M3](https://huggingface.co/BAAI/bge-m3)

### Calibre not found

**Problem**: `calibre-debug` command not found

**Solution**:
- Ensure Calibre is installed: https://calibre-ebook.com/download
- Add Calibre to PATH (Windows)
- On macOS: `/Applications/calibre.app/Contents/MacOS/calibre-debug`

## Indexing Issues

### Book not found in Calibre

**Problem**: "Book not found in Calibre library"

**Solution**:
- Verify book is in Calibre (open Calibre GUI)
- Check file path is correct
- Ensure `metadata.db` is accessible

### Indexing is very slow

**Problem**: Indexing takes too long

**Possible causes & solutions**:
- **Large PDF**: PDFs can be slow. Try converting to EPUB in Calibre first
- **CPU only**: GPU acceleration helps. Install PyTorch with CUDA
- **Many images**: Image-heavy books take longer (text extraction overhead)

### Out of memory during indexing

**Problem**: Process crashes with memory error

**Solution**:
- Reduce chunk size: Edit `scripts/rag_demo.py` → `chunk_size=512` → `chunk_size=256`
- Index books one at a time
- Close other applications
- Upgrade RAM (16 GB recommended)

## Search Issues

### No results found

**Checklist**:
1. Is the book indexed? Check with `python scripts/rag_demo.py stats`
2. Try different search mode (`--mode hybrid` / `semantic` / `keyword`)
3. Check language filter (remove or adjust `--language`)
4. Simplify query (shorter, broader terms)

### Wrong results returned

**Debugging**:
- Semantic mode too broad? Try `--mode keyword`
- Keyword mode too narrow? Try `--mode semantic`
- Use `--exact` for precise phrase matching
- Add tag filter to narrow scope

### Search is slow

**Solutions**:
- First search loads model (slow), subsequent searches are fast
- GPU acceleration: Install PyTorch with CUDA
- Reduce `--top-k` (default: 5)

## MCP Integration Issues

> **Coming soon**: MCP-specific troubleshooting

## Database Issues

### ChromaDB errors

**Problem**: "ChromaDB connection failed" or similar

**Solution**:
```bash
# Remove corrupted database
rm -rf archilles_rag_db/

# Re-index books
python scripts/rag_demo.py index "path/to/book.epub"
```

### Disk space issues

**Problem**: "No space left on device"

**Solution**:
- ChromaDB grows with library size
- Estimate: ~100-200 MB per 1000 books
- Free up space or change `--db-path` to different drive

## Platform-Specific Issues

### Windows: Path errors

**Problem**: "Path not found" with Windows paths

**Solution**:
- Use forward slashes: `C:/Users/Name/Calibre Library`
- Or escape backslashes: `C:\\Users\\Name\\Calibre Library`
- Use quotes for paths with spaces

### macOS: Permission denied

**Problem**: Cannot access Calibre library

**Solution**:
- Grant Terminal full disk access (System Preferences → Security & Privacy)
- Check file permissions: `ls -la "/path/to/Calibre Library"`

### Linux: Missing dependencies

**Problem**: Various import errors

**Solution**:
```bash
# Install system dependencies (Debian/Ubuntu)
sudo apt-get install python3-dev build-essential

# For PDF support
sudo apt-get install libmupdf-dev
```

## Performance Tuning

### For large libraries (1000+ books)

- Index incrementally (high-priority books first)
- Use tag filters to search subsets
- Consider multiple smaller indexes by topic/period

### For slow machines

- Reduce `chunk_size` in `scripts/rag_demo.py`
- Use keyword mode (BM25 is faster than embeddings)
- Close other applications during indexing

## Getting Help

### Collect debug information

```bash
# Python version
python --version

# Installed packages
pip list | grep -E "chromadb|sentence-transformers|torch"

# Archilles version
git log -1 --oneline

# Test indexing
python scripts/rag_demo.py index "path/to/small/book.epub" 2>&1 | tee debug.log
```

### Where to ask

- **Bugs**: [GitHub Issues](https://github.com/archilles/archilles/issues)
- **Questions**: [GitHub Discussions](https://github.com/archilles/archilles/discussions)
- **Security**: [hello@archilles.org](mailto:hello@archilles.org)

---

**Can't find a solution?** Open an issue with:
1. Error message (full traceback)
2. Python version
3. Operating system
4. Steps to reproduce
