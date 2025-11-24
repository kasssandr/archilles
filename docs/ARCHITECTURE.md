# Architecture Documentation

> **Status**: Documentation in progress

## System Overview

Archilles is a local-first RAG (Retrieval-Augmented Generation) system designed specifically for Calibre libraries.

```
┌─────────────────────────────────────────────────────────┐
│                    ARCHILLES SYSTEM                      │
├─────────────────────────────────────────────────────────┤
│                                                          │
│  ┌──────────┐      ┌──────────┐      ┌──────────┐     │
│  │ Calibre  │──────│ Extractor│──────│ ChromaDB │     │
│  │   DB     │      │  Chain   │      │  Vector  │     │
│  └──────────┘      └──────────┘      │   Store  │     │
│                                       └──────────┘     │
│                                             │           │
│                    ┌────────────────────────┤           │
│                    │                        │           │
│              ┌──────────┐            ┌──────────┐      │
│              │   BM25   │            │   BGE-M3 │      │
│              │ Keyword  │            │ Semantic │      │
│              │  Index   │            │ Embeddings│     │
│              └──────────┘            └──────────┘      │
│                    │                        │           │
│                    └────────┬───────────────┘           │
│                             │                           │
│                      ┌──────────────┐                   │
│                      │ Hybrid Search│                   │
│                      │     (RRF)    │                   │
│                      └──────────────┘                   │
│                             │                           │
│                      ┌──────────────┐                   │
│                      │ MCP Server   │                   │
│                      └──────────────┘                   │
└─────────────────────────────────────────────────────────┘
```

## Core Components

### 1. Metadata Extraction (`src/calibre_db.py`)

**Purpose**: Read-only access to Calibre's metadata.db

**Extracts**:
- Book metadata (title, author, publisher, ISBN)
- Tags and collections
- Comments (with HTML cleaning)
- Custom fields (automatic discovery)

**Key Feature**: Generic custom field support – works with ANY user-defined fields without configuration.

### 2. Text Extraction (`src/extractors/`)

**Supported Formats**: 30+ formats including:
- PDF (via PyMuPDF)
- EPUB (via ebooklib)
- MOBI, DJVU, DOCX, etc. (via Calibre converter fallback)

**Features**:
- Language detection (75+ languages via Lingua)
- Page number extraction
- Chapter detection
- Chunking with overlap (configurable)

### 3. Vector Database (ChromaDB)

**Storage**: Local persistent storage

**Contains**:
- Document chunks (text)
- BGE-M3 embeddings (1024 dimensions)
- Metadata (book info, page numbers, tags, custom fields)

### 4. Search Layer

#### Semantic Search (BGE-M3)
- Multilingual embeddings
- Concept-based matching
- Cosine similarity

#### Keyword Search (BM25)
- Exact term matching
- Enriched with metadata (tags, titles, authors, custom fields)
- Academic-friendly tokenization

#### Hybrid Search (RRF)
- Reciprocal Rank Fusion
- Combines semantic + keyword scores
- Smart boosting:
  - Calibre comments: 1.2x
  - Tag matches: 1.15x

### 5. MCP Server

> **Coming soon**: Detailed MCP architecture documentation

## Data Flow

### Indexing

```
Book File
  ↓
Format Detection
  ↓
Text Extraction (chunks)
  ↓
Language Detection
  ↓
Calibre Metadata Lookup
  ↓
BGE-M3 Embedding Generation
  ↓
ChromaDB Storage
  ↓
BM25 Index Update
```

### Searching

```
User Query
  ↓
┌─────────┴──────────┐
│                    │
Semantic Search   Keyword Search
(ChromaDB)        (BM25)
│                    │
└─────────┬──────────┘
          ↓
  Reciprocal Rank Fusion
          ↓
     Boosting Applied
          ↓
  Filtered & Ranked Results
```

## Technology Stack

- **Python 3.8+**
- **ChromaDB**: Vector database
- **sentence-transformers**: BGE-M3 embeddings
- **rank-bm25**: Keyword search
- **PyMuPDF**: PDF extraction
- **ebooklib**: EPUB handling
- **lingua-language-detector**: Language detection
- **SQLite**: Calibre database interface

## Performance Considerations

> **Coming soon**: Benchmarks and optimization guidelines

## Security & Privacy

- **No network calls** (except initial model download)
- **No telemetry**
- **Local-only processing**
- **Read-only Calibre access**

## Future Architecture

Planned enhancements:
- Graph RAG layer (entity relationships)
- Incremental indexing
- Multi-library support
- Plugin system for custom extractors

---

For implementation details, see the source code in `/src`.
