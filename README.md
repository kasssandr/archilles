# ARCHILLES

**Intelligent search for your Calibre library**

A privacy-first RAG system that brings semantic search to your personal research library. Built for scholars, researchers, and anyone with a serious book collection.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![MCP Compatible](https://img.shields.io/badge/MCP-Compatible-green.svg)](https://modelcontextprotocol.io/)

---

**[Quick Start](#quick-start)** • **[Features](#key-features)** • **[Documentation](#documentation)** • **[Roadmap](#product-roadmap)** • **[archilles.org](https://archilles.org)**

---

## What is Archilles?

If you're a researcher, you know this problem: You've spent years building a carefully curated library in Calibre—hundreds or thousands of books, annotated and tagged. But when you need to find that specific argument about medieval trade routes, or compare how three different authors approach consciousness, you're stuck with keyword search. You know the passage exists. You just can't find it.

**Archilles solves this.**

It's a semantic search system built specifically for Calibre libraries. Instead of matching keywords, it understands *meaning*. Ask it "discussions of political legitimacy in early modern Europe" and it finds relevant passages—even if they never use those exact words.

Everything runs locally on your machine. Your library, your annotations, your research—they stay private. No cloud services, no data uploads, no subscriptions.

### Built on solid foundations

- **Retrieval-Augmented Generation (RAG)**: Combines semantic embeddings with keyword search for best-of-both-worlds accuracy
- **Model Context Protocol (MCP)**: Native integration with Claude and other AI assistants
- **Calibre Integration**: Works seamlessly with your existing library structure
- **Local-First**: ChromaDB for vector storage, all processing happens on your hardware

---

## Key Features

### 🧠 **Semantic Search**
Find books by meaning, not just keywords. Ask natural questions and get relevant passages from across your entire library.

### 🔒 **Privacy-First**
All data stays on your machine. No cloud uploads, no telemetry, no tracking. Your research library remains private.

### 🔗 **MCP-Native**
Seamless integration with Claude Desktop and other MCP-compatible tools. Your AI assistant can search your library directly.

### 📚 **Calibre-Integrated**
Reads directly from your Calibre library structure. Extracts metadata, tags, comments, annotations, and custom fields automatically.

### 💬 **Comments & Annotations**
Searches beyond book text. Your Calibre comments, highlights, and notes are all indexed and searchable.

### 🏷️ **Tag-Aware**
Filter by Calibre tags, combine searches across custom fields, leverage all the organization you've already done.

### 🌍 **Multilingual**
Built-in language detection for 75+ languages. Search in German, English, Latin, Greek, French—or all at once.

### ⚡ **Hybrid Search**
Combines semantic understanding (BGE-M3 embeddings) with keyword precision (BM25). Get the best of both approaches.

---

## Why Archilles?

| **Archilles** | **Cloud RAG Services** | **Calibre Search** | **Other MCP Servers** |
|---------------|------------------------|--------------------|-----------------------|
| Privacy-first, local processing | Your data uploaded to cloud | Basic keyword matching | Often single-purpose |
| Semantic + keyword hybrid | Usually semantic only | No semantic understanding | Varying capabilities |
| Calibre-native integration | Generic document handling | Built-in but limited | May not support Calibre |
| One-time setup, no subscriptions | Monthly fees, usage limits | Free (included) | Varies widely |
| Full control over your data | Terms of service apply | Your data, basic search | Depends on service |

Archilles gives you the semantic search capabilities of modern RAG systems while keeping everything under your control. If you've invested years in building and organizing your Calibre library, Archilles makes that investment exponentially more valuable.

---

## Quick Start

### Prerequisites
- Python 3.8 or higher
- [Calibre](https://calibre-ebook.com/) with your book library
- (Optional) [Claude Desktop](https://claude.ai/download) for MCP integration

### Installation

```bash
# Clone the repository
git clone https://github.com/archilles/archilles.git
cd archilles

# Install dependencies
pip install -r requirements.txt

# Set your Calibre library path (optional - defaults to D:/Calibre-Bibliothek)
# Windows PowerShell:
$env:CALIBRE_LIBRARY_PATH = "D:\Your-Calibre-Library"
# Linux/Mac:
export CALIBRE_LIBRARY_PATH="/path/to/your/Calibre Library"
```

### Index Your First Book

```bash
# Index a single book
python scripts/rag_demo.py index "/path/to/Calibre Library/Author/Book/book.pdf"

# Check your index
python scripts/rag_demo.py stats
```

### Batch Index by Tag

```bash
# Preview what would be indexed (dry run)
python scripts/batch_index.py --tag "Your-Tag" --dry-run

# Index all books with a specific Calibre tag
python scripts/batch_index.py --tag "Leit-Literatur"

# Index with progress logging
python scripts/batch_index.py --tag "History" --log indexing.json

# Resume interrupted indexing (skip already indexed books)
python scripts/batch_index.py --tag "History" --skip-existing
```

### Search Your Library

```bash
# Hybrid search (recommended - combines semantic + keyword)
python scripts/rag_demo.py query "trade networks in medieval Europe"

# Filter by language
python scripts/rag_demo.py query "Rex" --language la

# Filter by tags
python scripts/rag_demo.py query "political theory" --tag-filter Philosophy History

# Export results to Markdown (for Joplin/Obsidian)
python scripts/rag_demo.py query "consciousness" --export results.md
```

### Claude Desktop Integration

Add to your Claude Desktop config (`%APPDATA%\Claude\claude_desktop_config.json` on Windows):

```json
{
  "mcpServers": {
    "archilles": {
      "command": "python",
      "args": ["C:/Users/YOU/archilles/mcp_server.py"],
      "env": {
        "CALIBRE_LIBRARY_PATH": "D:/Your-Calibre-Library"
      }
    }
  }
}
```

Then in Claude Desktop, you can use natural language:
- *"Search my books for discussions of political legitimacy"*
- *"Find annotations about consciousness"*
- *"What did I highlight about medieval trade?"*

**📖 [Full Installation Guide →](docs/INSTALLATION.md)**

---

## How It Works

Archilles builds a semantic index of your Calibre library that enables intelligent search:

```
┌─────────────┐
│   Calibre   │ ← Your existing library (books, metadata, tags, comments)
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  Archilles  │ ← Extracts text, generates embeddings, builds search index
│   Indexer   │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  ChromaDB   │ ← Local vector database (embeddings + BM25 keyword index)
└──────┬──────┘
       │
       ▼
┌─────────────┐
│     MCP     │ ← Model Context Protocol server
│   Server    │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   Claude    │ ← Your AI assistant can now search your library
└─────────────┘
```

### What Gets Indexed

- **Book text**: Full-text extraction from 30+ formats (PDF, EPUB, MOBI, DJVU, etc.)
- **Calibre metadata**: Title, author, publisher, ISBN, language
- **Tags**: Your Calibre tags become searchable
- **Comments**: Calibre's comments field (HTML cleaned automatically)
- **Custom fields**: Any custom Calibre fields you've defined (reading status, projects, ratings, etc.)
- **Annotations**: Your Calibre highlights and notes (searchable via `search_annotations`)

### Search Technology

- **BGE-M3 embeddings**: State-of-the-art multilingual semantic understanding (1024 dimensions)
- **BM25 keyword search**: Precision matching for exact terms (especially useful for names, Latin phrases, technical terms)
- **Reciprocal Rank Fusion (RRF)**: Intelligently combines semantic and keyword results
- **Smart boosting**: Calibre comments and tag matches get priority in results

**🏗️ [Architecture Details →](docs/ARCHITECTURE.md)**

---

## Use Cases

### 📜 Historian
*"Find all discussions of trade routes between Mediterranean and Northern Europe before 1500"*

Archilles searches across your entire collection—Latin primary sources, German monographs, English translations—and surfaces relevant passages based on concepts, not just keywords.

### 📖 Literary Scholar
*"Trace the motif of unreliable narrators across these 50 twentieth-century novels"*

Semantic search finds passages that *demonstrate* unreliable narration, even when the texts never use that term. Your annotations and comments help prioritize the most relevant examples.

### 🤔 Philosopher
*"Compare views on the hard problem of consciousness across Chalmers, Dennett, and Nagel"*

Hybrid search combines precise name matching with semantic understanding of philosophical concepts. Your Calibre tags help filter to relevant texts.

### 🎵 Musicologist
*"Find theoretical discussions of modal harmony in Renaissance treatises"*

Multilingual search works across Latin treatises, Italian commentary, and modern scholarship. Technical terms get exact matching while broader concepts use semantic search.

### ⚖️ Legal Researcher
*"Locate all references to customary law in medieval court records"*

Search through your collection of primary sources and secondary literature simultaneously. Custom Calibre fields (like "source_type" or "jurisdiction") help organize results.

---

## Product Roadmap

### Current Release: v0.9 Gamma (December 2024)

✅ **Core functionality complete:**
- Full-text indexing (30+ formats)
- Semantic + keyword hybrid search
- Calibre metadata integration (tags, comments, custom fields)
- MCP server for Claude integration
- Multi-language support (75+ languages)

### Coming in v1.0 (Q1 2025)

🚧 **Planned improvements:**
- PDF & EPUB annotations extraction (highlights, notes, bookmarks)
- Incremental indexing (update only changed books)
- Improved embedding models (domain-specific options)
- Web UI for non-technical users
- Collection-level search (search across multiple books simultaneously)

### Future Development

🔮 **On the horizon:**
- Graph RAG (entity relationships, timeline views)
- Special Editions (discipline-specific extensions)
- Multi-library support
- Advanced citation export (BibTeX, Zotero)

**📅 [Detailed Roadmap →](docs/ROADMAP.md)**

---

## Special Editions *(Future)*

Archilles is being developed as a modular platform. The core (what you're using now) will always be free and open source.

**Special Editions** will extend Archilles with discipline-specific features for researchers who need them:

- **📜 Historical Edition**: Timeline visualization, prosopography, chronology-aware search
- **📖 Literary Edition**: Motif tracking, intertextual connections, narrative structure analysis
- **⚖️ Legal Edition**: Citation networks, precedent tracking, jurisdiction-aware search
- **🎵 Musical Edition**: Score analysis integration, theoretical terminology, composer networks

These editions are commercial add-ons to support ongoing development. The core will remain MIT licensed and fully functional.

**🎯 [Edition Details →](docs/EDITIONS.md)**

---

## Community & Contributing

### Get Help

- **Issues**: [GitHub Issues](https://github.com/archilles/archilles/issues) for bugs and feature requests
- **Discussions**: [GitHub Discussions](https://github.com/archilles/archilles/discussions) for questions and ideas
- **Documentation**: [Full documentation](docs/) for guides and troubleshooting

### Contribute

Archilles is open source (MIT License). Contributions are welcome!

- Found a bug? [Open an issue](https://github.com/archilles/archilles/issues)
- Want to add a feature? Check [CONTRIBUTING.md](CONTRIBUTING.md)
- Improved documentation? Pull requests appreciated

### Beta Testing

We're actively seeking beta testers from diverse research disciplines. If you have a substantial Calibre library (500+ books) and want to help shape Archilles, join our beta program.

**Code of Conduct**: We're committed to building a welcoming community. See [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

---

## Documentation

📖 **[Installation Guide](docs/INSTALLATION.md)** – Detailed setup instructions
📘 **[User Guide](docs/USER_GUIDE.md)** – How to use Archilles effectively
🏗️ **[Architecture](docs/ARCHITECTURE.md)** – Technical deep dive
🔌 **[MCP Integration](docs/MCP_GUIDE.md)** – Connect Archilles to Claude
❓ **[FAQ](docs/FAQ.md)** – Frequently asked questions
🔧 **[Troubleshooting](docs/TROUBLESHOOTING.md)** – Common issues and solutions

---

## Legal & Privacy

### License
Archilles is released under the [MIT License](LICENSE). Free to use, modify, and distribute.

### Privacy Statement
Archilles is **local-first software**. We collect no telemetry, no analytics, no usage data. Your library stays on your machine.

### User Responsibility
You are responsible for ensuring your use of Archilles complies with copyright law in your jurisdiction. Archilles is a tool for searching *your own* legally acquired library.

**📜 [Full Legal Details →](docs/LEGAL.md)**

---

## Acknowledgments

Archilles is built on the shoulders of giants:

- **[Calibre](https://calibre-ebook.com/)** by Kovid Goyal – The gold standard for e-book library management
- **[ChromaDB](https://www.trychroma.com/)** – Elegant vector database for RAG applications
- **[Model Context Protocol](https://modelcontextprotocol.io/)** by Anthropic – Standardized AI assistant integration
- **[BGE-M3](https://huggingface.co/BAAI/bge-m3)** – State-of-the-art multilingual embeddings
- **[Anthropic Claude](https://www.anthropic.com/claude)** – AI assistant that respects user privacy

Inspired by NotebookLM, Zotero, and decades of digital humanities research.

Thanks to our beta testing community (you know who you are!).

---

## Contact & Links

🌐 **Website**: [archilles.org](https://archilles.org) • [archilles.de](https://archilles.de)
💻 **GitHub**: [github.com/archilles/archilles](https://github.com/archilles/archilles)
💬 **Discussions**: [GitHub Discussions](https://github.com/archilles/archilles/discussions)
📧 **Contact**: [hello@archilles.org](mailto:hello@archilles.org)

---

**Built for researchers, by a researcher.**

*Archilles: Because your library deserves better than keyword search.*
