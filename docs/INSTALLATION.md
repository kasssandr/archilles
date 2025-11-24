# Installation Guide

> **Status**: Documentation in progress

## Prerequisites

- Python 3.8 or higher
- [Calibre](https://calibre-ebook.com/) installed with your library
- (Optional) [Claude Desktop](https://claude.ai/download) for MCP integration

## Installation Methods

### Option 1: Standard Installation

```bash
# Clone the repository
git clone https://github.com/archilles/archilles.git
cd archilles

# Create virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Option 2: Development Installation

```bash
# Clone and install in editable mode
git clone https://github.com/archilles/archilles.git
cd archilles
pip install -e .
```

## Configuration

### 1. Locate Your Calibre Library

Your Calibre library contains a `metadata.db` file. Common locations:

- **Linux**: `~/Calibre Library/`
- **macOS**: `~/Library/Calibre Library/`
- **Windows**: `C:\Users\[Username]\Calibre Library\`

### 2. Index Your First Book

```bash
python scripts/rag_demo.py index "/path/to/your/Calibre Library/Author/Book/book.epub"
```

### 3. Test Your Installation

```bash
python scripts/rag_demo.py query "test search query"
```

## MCP Integration (Optional)

> **Coming soon**: Detailed MCP setup instructions

For Claude Desktop integration, see [MCP_GUIDE.md](MCP_GUIDE.md).

## Troubleshooting

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for common installation issues.

## Next Steps

- Read the [User Guide](USER_GUIDE.md) to learn search strategies
- Explore [Architecture](ARCHITECTURE.md) to understand how it works
- Check the [FAQ](FAQ.md) for common questions
