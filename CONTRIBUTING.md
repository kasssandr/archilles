# Contributing to Archilles

Thank you for your interest in contributing to Archilles!

## How to Contribute

### Reporting Bugs

**Before submitting a bug report:**
- Check [FAQ.md](docs/FAQ.md) and [TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)
- Search [existing issues](https://github.com/kasssandr/archilles/issues) to avoid duplicates

**When reporting a bug, include:**
- Steps to reproduce
- Expected vs. actual behavior
- OS, Python version, and hardware (CPU/GPU)
- Full error traceback if applicable

### Suggesting Features

Feature requests are welcome. Open an issue with:
- A clear use case description
- Why the feature would be valuable to other researchers
- Any alternative approaches you've considered

### Pull Requests

1. Fork the repository and create a feature branch:
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. Make your changes, following the code style guidelines below.

3. Open a pull request with a clear description of what changes and why.

**For significant changes**, please open an issue first to discuss the approach before investing time in implementation.

---

## Development Setup

```bash
# Clone
git clone https://github.com/kasssandr/archilles.git
cd archilles

# Create virtual environment
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install dev tools
pip install black flake8
```

---

## Code Style

- **Formatting**: `black src/ scripts/`
- **Linting**: `flake8 src/ scripts/`
- **Type hints**: Encouraged for new code
- **Docstrings**: Required for public functions and classes

There is currently no automated test suite. If you are adding a significant feature, a manual test description in your PR is appreciated.

---

## Areas for Contribution

**High priority:**
- Bug reports and fixes — especially on macOS and Linux (untested platforms)
- Documentation improvements and corrections
- Test coverage — writing `pytest` tests for core components would be a valuable contribution

**Medium priority:**
- Additional e-book format support
- Chunking strategy improvements
- CLI usability improvements

**Future features** (see [ROADMAP.md](docs/ROADMAP.md)):
- Domain-specific embedding models
- VLM-based OCR
- Graph RAG

---

## Project Structure

```
archilles/
├── docs/                   # Documentation
├── scripts/
│   ├── rag_demo.py         # Main CLI (index, query, stats)
│   └── batch_index.py      # Batch indexing by Calibre tag
├── src/
│   ├── archilles/          # Core pipeline (embedder, retriever, profiles)
│   ├── calibre_db.py       # Read-only Calibre integration
│   ├── calibre_mcp/        # MCP server and tools
│   ├── extractors/         # Format-specific text extractors
│   ├── service/            # ArchillesService facade
│   └── storage/            # LanceDB backend
├── mcp_server.py           # Entry point for Claude Desktop
└── requirements.txt
```

---

## Questions?

- **Bugs / features**: [GitHub Issues](https://github.com/kasssandr/archilles/issues)
- **Questions / discussion**: [GitHub Discussions](https://github.com/kasssandr/archilles/discussions)
- **Security issues**: [hello@archilles.org](mailto:hello@archilles.org)

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).
