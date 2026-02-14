# Product Roadmap

> Last updated: December 2024

## Current Release: v0.9 Gamma

**Status**: Feature-complete for core functionality

✅ **Completed**:
- Full-text indexing (30+ formats via Calibre converter)
- Semantic search (BGE-M3 embeddings)
- Keyword search (BM25)
- Hybrid search with Reciprocal Rank Fusion
- Calibre metadata integration
  - Tags
  - Comments (with HTML cleaning)
  - Custom fields (automatic discovery)
- Multi-language support (75+ languages)
- Language filtering
- Tag filtering
- MCP server foundation
- Command-line interface
- Export to Markdown

## Next: v1.0 (Target: Q1 2026)

**Focus**: Refinement & user experience

### Planned Features

🚧 **Annotations Support**
- Extract PDF highlights and notes
- Index EPUB bookmarks and annotations
- Searchable user annotations

🚧 **Incremental Indexing**
- Update only changed books
- Background indexing
- Index queue management

🚧 **Improved Embeddings**
- Model selection (BGE-M3, alternatives)
- Domain-specific embedding options
- Fine-tuning support

🚧 **Web UI**
- Browser-based interface for non-technical users
- Visual search results
- Library browser

🚧 **Collection Search**
- Search across multiple books simultaneously
- Book-level vs chunk-level results
- Cross-book citations

🚧 **Enhanced MCP Integration**
- More MCP tools (list_books, get_metadata, etc.)
- Better Claude Desktop integration
- Configuration wizard

### Quality Improvements

- Comprehensive documentation
- Unit test suite
- Performance benchmarks
- Windows installer
- macOS .app bundle

## Future: v1.1+ (Q2 2026 onwards)

### Graph RAG

**Goal**: Understand relationships between entities, ideas, and texts

**Features**:
- Entity extraction (people, places, concepts)
- Relationship mapping
- Timeline visualization
- Network graphs
- Prosopography support

**Research**: Evaluate knowledge graph backends (Neo4j, others)

### Special Editions

Discipline-specific extensions (commercial add-ons):

**📜 Historical Edition**
- Timeline views
- Prosopography (person networks)
- Chronology-aware search
- Primary source handling
- Medieval dating systems

**📖 Literary Edition**
- Motif tracking
- Intertextual connections
- Narrative structure analysis
- Character networks
- Stylometric tools

**⚖️ Legal Edition**
- Citation networks
- Precedent tracking
- Jurisdiction-aware search
- Case law handling
- Legal terminology

**🎵 Musical Edition**
- Score analysis integration
- Theoretical terminology
- Composer networks
- Period-aware search
- Manuscript handling

See [EDITIONS.md](EDITIONS.md) for detailed edition plans.

### Multi-Library Support

- Manage multiple Calibre libraries
- Cross-library search
- Library-specific configurations
- Library import/export

### Advanced Features

🔮 **On the horizon**:
- Wikidata integration (entity disambiguation)
- Zotero backend (parallel to Calibre)
- Citation export (BibTeX, Zotero)
- Annotation sync with external tools
- Plugin system for custom extractors
- Mobile companion app (search only)
- Collaborative features (shared annotations)

### Platform Expansion

- Desktop applications (Electron-based)
- Better Windows integration
- macOS native features
- Linux package repositories (apt, yum, AUR)

## Long-Term Vision

**Archilles as Research Infrastructure**:
- The semantic layer for personal research libraries
- Integration with citation managers (Zotero, Mendeley)
- Part of academic workflow (discover → annotate → cite → write)
- Community-driven entity databases
- Academic institution deployments

## Community Input

The roadmap is shaped by user needs. **Your feedback matters!**

- **Feature requests**: [GitHub Issues](https://github.com/archilles/archilles/issues)
- **Discussions**: [GitHub Discussions](https://github.com/archilles/archilles/discussions)
- **Beta testing**: Join our testing program

## Release Philosophy

- **Core remains free and open source** (MIT License)
- **Special Editions** fund ongoing development
- **No breaking changes** without migration path
- **Privacy-first** always

---

**Want to influence the roadmap?** Share your research needs in [Discussions](https://github.com/archilles/archilles/discussions).
