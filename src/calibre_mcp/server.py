#!/usr/bin/env python3
"""
Calibre MCP Server

A Model Context Protocol server for Calibre library integration.
Provides tools for searching, analyzing, and accessing Calibre library data.
"""

import json
import logging
import sys
from pathlib import Path
from typing import Any, Optional

# Import CalibreAnalyzer from local module
from .calibre_analyzer import CalibreAnalyzer

# Import service layer for RAG search
try:
    from src.service import ArchillesService
    SERVICE_AVAILABLE = True
except ImportError:
    SERVICE_AVAILABLE = False
    logging.warning("ArchillesService not available. XML prompt generation disabled.")

from .annotations import (
    compute_book_hash,
    get_book_annotations,
    get_highlights,
    get_notes,
    get_bookmarks,
    list_all_annotated_books,
    search_annotations,
    get_annotations_dir,
    get_combined_annotations,
    get_pdf_annotations
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CalibreMCPServer:
    """
    MCP Server for Calibre library integration.

    This server provides tools for:
    - Retrieving book annotations (highlights, notes, bookmarks)
    - Searching through annotations
    - Analyzing library metadata
    """

    def __init__(
        self,
        library_path: Optional[str] = None,
        annotations_dir: Optional[str] = None,
        enable_semantic_search: bool = False,
        chroma_persist_dir: Optional[str] = None,
        rag_db_path: Optional[str] = None,
        enable_reranking: bool = False,
        reranker_device: Optional[str] = 'cpu',
        citation_config: Optional[Any] = None,
    ):
        """
        Initialize the Calibre MCP Server.

        Args:
            library_path: Path to the Calibre library
            annotations_dir: Custom path to annotations directory
            enable_semantic_search: Enable semantic search with ChromaDB
            chroma_persist_dir: Directory to persist ChromaDB data
            rag_db_path: Path to RAG database (default: ./archilles_rag_db)
            enable_reranking: Enable cross-encoder reranking for search results
            reranker_device: Device for reranker model ('cpu' to avoid GPU OOM)
            citation_config: CitationConfig instance for bibliography formatting
        """
        self.library_path = Path(library_path) if library_path else None
        self.annotations_dir = annotations_dir
        self.enable_semantic_search = enable_semantic_search

        # Initialize database path for metadata operations
        self.db_path = None
        if library_path:
            db_candidate = Path(library_path) / "metadata.db"
            if db_candidate.exists():
                self.db_path = str(db_candidate)
            else:
                # Check if library_path is the metadata.db itself
                if Path(library_path).name == "metadata.db" and Path(library_path).exists():
                    self.db_path = library_path

        # Initialize semantic search if enabled
        self.indexer = None
        if enable_semantic_search:
            try:
                from .annotations_indexer import AnnotationsIndexer
                self.indexer = AnnotationsIndexer(
                    chroma_persist_dir=chroma_persist_dir,
                    annotations_dir=annotations_dir,
                    library_path=library_path
                )
                logger.info("Semantic search enabled")
            except ImportError:
                logger.warning(
                    "ChromaDB not available. Semantic search disabled. "
                    "Install with: pip install chromadb"
                )
                self.enable_semantic_search = False

        # Citation style configuration
        self.citation_config = citation_config

        # Initialize service layer for RAG search (lazy loading)
        # Initialization is deferred until first use to avoid blocking server startup
        self.service = ArchillesService(
            db_path=rag_db_path or "./archilles_rag_db",
            enable_reranking=enable_reranking,
            reranker_device=reranker_device,
            citation_config=citation_config,
        ) if SERVICE_AVAILABLE else None

    def _ensure_rag_initialized(self) -> bool:
        """
        Ensure RAG system is initialized (lazy loading via service layer).

        Returns:
            True if RAG is available, False otherwise
        """
        if self.service is None:
            logger.warning("ArchillesService not available")
            return False
        return self.service._ensure_initialized()

    def get_book_annotations_tool(
        self,
        book_path: str,
        annotation_type: Optional[str] = None,
        exclude_toc_markers: bool = True,
        include_pdf: bool = True,
        min_length: int = 20,
        exclude_first_percent: float = 5.0
    ) -> dict[str, Any]:
        """
        MCP Tool: Get annotations for a specific book with intelligent filtering.

        Args:
            book_path: Full path to the book file
            annotation_type: Optional filter - 'highlight', 'note', or 'bookmark'
            exclude_toc_markers: Whether to exclude TOC markers and technical highlights
            include_pdf: Whether to extract PDF-internal annotations (for PDF files)
            min_length: Minimum character length for annotations
            exclude_first_percent: Exclude annotations in first X% of book

        Returns:
            Dictionary with annotations and metadata
        """
        # Calculate the correct hash
        book_hash = compute_book_hash(book_path)

        # Prepare annotation type filter
        annotation_types = None
        if annotation_type:
            annotation_types = [annotation_type]

        # Use the enhanced combined annotations function
        result = get_combined_annotations(
            book_path=book_path,
            annotations_dir=self.annotations_dir,
            include_pdf=include_pdf,
            exclude_toc_markers=exclude_toc_markers,
            min_length=min_length,
            exclude_first_percent=exclude_first_percent,
            annotation_types=annotation_types
        )

        # Add hash to result
        result['book_hash'] = book_hash

        return result

    def search_annotations_tool(
        self,
        query: str,
        case_sensitive: bool = False,
        use_semantic: bool = False,
        max_results: int = 10,
        max_per_book: int = 2
    ) -> dict[str, Any]:
        """
        MCP Tool: Search through all annotations.

        Supports both text-based and semantic search.

        Args:
            query: Search query string
            case_sensitive: Whether to use case-sensitive search (text search only)
            use_semantic: Use semantic search instead of text search
            max_results: Maximum number of results (semantic search only)
            max_per_book: Maximum results per book to prevent one book dominating results (semantic only)

        Returns:
            Dictionary with search results
        """
        # Use semantic search if enabled and requested
        if use_semantic and self.enable_semantic_search and self.indexer:
            max_per_book_param = max_per_book if max_per_book > 0 else None
            results = self.indexer.search_annotations(
                query=query,
                n_results=max_results,
                max_per_book=max_per_book_param
            )

            return {
                'query': query,
                'search_type': 'semantic',
                'result_count': len(results),
                'max_per_book': max_per_book,
                'results': results
            }

        # Fall back to text-based search
        results = search_annotations(query, self.annotations_dir, case_sensitive)

        return {
            'query': query,
            'search_type': 'text',
            'case_sensitive': case_sensitive,
            'result_count': len(results),
            'results': results
        }

    def list_annotated_books_tool(self) -> dict[str, Any]:
        """
        MCP Tool: List all books that have annotations.

        Returns:
            Dictionary with list of annotated books
        """
        books = list_all_annotated_books(self.annotations_dir)

        return {
            'total_books': len(books),
            'books': books
        }

    def compute_hash_tool(self, book_path: str) -> dict[str, Any]:
        """
        MCP Tool: Compute the annotation hash for a book path.

        This is useful for debugging annotation lookup issues.

        Args:
            book_path: Full path to the book file

        Returns:
            Dictionary with hash information
        """
        book_hash = compute_book_hash(book_path)
        annots_dir = self.annotations_dir or get_annotations_dir()
        expected_file = Path(annots_dir) / f"{book_hash}.json"

        return {
            'book_path': book_path,
            'hash': book_hash,
            'expected_annotation_file': str(expected_file),
            'file_exists': expected_file.exists()
        }

    def index_annotations_tool(
        self,
        force_reindex: bool = False,
        exclude_toc_markers: bool = True
    ) -> dict[str, Any]:
        """
        MCP Tool: Index all annotations for semantic search.

        Args:
            force_reindex: Force reindexing of all annotations
            exclude_toc_markers: Whether to exclude TOC markers

        Returns:
            Dictionary with indexing statistics
        """
        if not self.enable_semantic_search or not self.indexer:
            return {
                'error': 'Semantic search is not enabled',
                'help': 'Initialize server with enable_semantic_search=True'
            }

        stats = self.indexer.index_all_annotations(
            exclude_toc_markers=exclude_toc_markers,
            force_reindex=force_reindex
        )

        return {
            'status': 'completed',
            'statistics': stats
        }

    def get_index_stats_tool(self) -> dict[str, Any]:
        """
        MCP Tool: Get statistics about the annotation index.

        Returns:
            Dictionary with index statistics
        """
        if not self.enable_semantic_search or not self.indexer:
            return {
                'error': 'Semantic search is not enabled'
            }

        stats = self.indexer.get_collection_stats()

        return {
            'status': 'ok',
            'statistics': stats
        }

    def detect_duplicates_tool(
        self,
        method: str = 'title_author',
        include_doublette_tag: bool = True
    ) -> dict[str, Any]:
        """
        MCP Tool: Detect duplicate books in the library.

        Supports multiple detection methods:
        - 'title_author': Match by normalized title and author (most thorough)
        - 'isbn': Match by ISBN (most accurate)
        - 'exact_title': Match by exact title only

        Args:
            method: Detection method - 'title_author', 'isbn', or 'exact_title'
            include_doublette_tag: Also show books tagged with "Doublette"

        Returns:
            Dictionary with duplicate groups and statistics
        """
        if not self.db_path:
            return {
                'error': 'Library database not available',
                'help': 'Initialize server with library_path pointing to Calibre library or metadata.db'
            }

        try:
            with CalibreAnalyzer(self.db_path) as analyzer:
                result = analyzer.detect_duplicates(
                    method=method,
                    include_doublette_tag=include_doublette_tag
                )
                return result
        except Exception as e:
            return {
                'error': f'Failed to detect duplicates: {str(e)}'
            }

    def get_book_details_tool(self, book_id: int) -> dict[str, Any]:
        """
        MCP Tool: Get detailed information about a specific book.

        Args:
            book_id: Calibre book ID

        Returns:
            Dictionary with book details
        """
        if not self.db_path:
            return {
                'error': 'Library database not available',
                'help': 'Initialize server with library_path pointing to Calibre library or metadata.db'
            }

        try:
            with CalibreAnalyzer(self.db_path) as analyzer:
                book = analyzer.get_book_details(book_id)
                if not book:
                    return {
                        'error': f'Book with ID {book_id} not found'
                    }
                return book
        except Exception as e:
            return {
                'error': f'Failed to get book details: {str(e)}'
            }

    def get_doublette_tag_instruction_tool(self, book_id: int) -> dict[str, Any]:
        """
        MCP Tool: Get instructions for adding the "Doublette" tag to a book.

        Note: This server cannot modify the database directly.
        Use Calibre's calibredb command to actually add tags.

        Args:
            book_id: Calibre book ID

        Returns:
            Dictionary with tagging instructions
        """
        if not self.db_path:
            return {
                'error': 'Library database not available'
            }

        try:
            with CalibreAnalyzer(self.db_path) as analyzer:
                return analyzer.add_doublette_tag(book_id)
        except Exception as e:
            return {
                'error': f'Failed to get tag instruction: {str(e)}'
            }

    def export_bibliography_tool(
        self,
        format: str = 'bibtex',
        author: Optional[str] = None,
        tag: Optional[str] = None,
        year_from: Optional[int] = None,
        year_to: Optional[int] = None,
        max_books: Optional[int] = None
    ) -> dict[str, Any]:
        """
        MCP Tool: Export bibliography in various formats.

        Supports BibTeX, RIS, EndNote, JSON, and CSV formats.
        Books can be filtered by author, tag, and publication year.

        Args:
            format: Export format - 'bibtex', 'ris', 'endnote', 'json', 'csv'
            author: Filter by author name (case-insensitive partial match)
            tag: Filter by tag name (case-insensitive partial match)
            year_from: Filter books published from this year
            year_to: Filter books published up to this year
            max_books: Maximum number of books to export

        Returns:
            Dictionary with exported bibliography data
        """
        if not self.db_path:
            return {
                'error': 'Library database not available',
                'help': 'Initialize server with library_path pointing to Calibre library or metadata.db'
            }

        try:
            with CalibreAnalyzer(self.db_path) as analyzer:
                result = analyzer.export_bibliography(
                    format=format,
                    author=author,
                    tag=tag,
                    year_from=year_from,
                    year_to=year_to,
                    max_books=max_books
                )
                return result
        except Exception as e:
            return {
                'error': f'Failed to export bibliography: {str(e)}'
            }

    def list_books_by_author_tool(
        self,
        author: str,
        tags: Optional[list[str]] = None,
        year_from: Optional[int] = None,
        year_to: Optional[int] = None,
        sort_by: str = 'title'
    ) -> dict[str, Any]:
        """
        MCP Tool: List all books by an author from the Calibre metadata database.

        Direct metadata query (not vector search). Reliable for finding all works
        by an author, including short texts (articles, book chapters) where
        vector search may miss results.

        Args:
            author: Author name (case-insensitive partial match, required)
            tags: Optional list of tag names to filter by (AND logic)
            year_from: Optional minimum publication year
            year_to: Optional maximum publication year
            sort_by: Sort order - 'title' (default) or 'year'

        Returns:
            Dictionary with matched books and metadata
        """
        if not self.db_path:
            return {
                'error': 'Library database not available',
                'help': 'Initialize server with library_path pointing to Calibre library or metadata.db'
            }

        try:
            with CalibreAnalyzer(self.db_path) as analyzer:
                result = analyzer.list_books_by_author(
                    author=author,
                    tags=tags,
                    year_from=year_from,
                    year_to=year_to,
                    sort_by=sort_by
                )
                return result
        except Exception as e:
            return {
                'error': f'Failed to list books by author: {str(e)}'
            }

    def list_tags_tool(
        self,
        min_books: int = 1,
        max_tags: int = 100
    ) -> dict[str, Any]:
        """
        MCP Tool: List all tags in the Calibre library with book counts.

        Args:
            min_books: Only show tags with at least this many books (default: 1)
            max_tags: Maximum number of tags to return (default: 100)

        Returns:
            Dictionary with tag list and statistics
        """
        if not self.db_path:
            return {
                'error': 'Library database not available',
                'help': 'Initialize server with library_path pointing to Calibre library or metadata.db'
            }

        try:
            with CalibreAnalyzer(self.db_path) as analyzer:
                tags_stats = analyzer.get_tags_stats()

                # Filter by min_books
                filtered_tags = [
                    tag for tag in tags_stats
                    if tag['book_count'] >= min_books
                ]

                # Limit results
                limited_tags = filtered_tags[:max_tags]

                return {
                    'total_tags': len(tags_stats),
                    'filtered_tags': len(filtered_tags),
                    'returned_tags': len(limited_tags),
                    'tags': limited_tags,
                    'usage': 'Use these tag names in the "tags" parameter of search_books_with_citations'
                }
        except Exception as e:
            return {
                'error': f'Failed to list tags: {str(e)}'
            }

    def search_books_with_citations_tool(
        self,
        query: str,
        top_k: int = 5,
        mode: str = 'hybrid',
        language: Optional[str] = None,
        tags: Optional[list[str]] = None,
        expand_context: bool = False
    ) -> dict[str, Any]:
        """
        MCP Tool: Search books and generate XML-structured prompts with citation support.

        This tool combines RAG search with XML prompt generation, providing:
        - Structured <documents> with metadata
        - System prompt with citation instructions
        - Ready-to-use prompts for Claude

        Args:
            query: Search query
            top_k: Number of results to return (default: 5)
            mode: Search mode - 'hybrid', 'semantic', or 'keyword' (default: 'hybrid')
            language: Filter by language (e.g., 'de', 'en', 'la')
            tags: Filter by Calibre tags (e.g., ['Geschichte', 'Philosophie'])
            expand_context: Enable context expansion (Small-to-Big) if char_offsets available

        Returns:
            Dictionary with XML prompts and search results
        """
        # Lazy initialization of RAG system
        if not self._ensure_rag_initialized():
            return {
                'error': 'RAG system not available',
                'help': 'RAG system requires ArchillesService to be installed and initialized',
                'initialization_log': 'Check ~/.archilles/mcp_server.log for details'
            }

        try:
            # Delegate to service layer (handles stdout redirection internally)
            result = self.service.search_with_citations(
                query=query,
                top_k=top_k,
                mode=mode,
                language=language,
                tags=tags,
                expand_context=expand_context,
            )

            if "error" in result:
                return result

            results = result.get("results", [])
            if not results:
                return {
                    'results': [],
                    'message': 'No results found',
                    'query': query
                }

            # Return structured response
            return {
                'query': query,
                'num_results': result['num_results'],
                'search_mode': mode,
                'language_filter': language,
                'system_prompt': result['system_prompt'],
                'user_prompt': result['user_prompt'],
                'usage_instructions': (
                    "Copy 'system_prompt' to Claude's System Prompt field, "
                    "then copy 'user_prompt' to the message. "
                    "Claude will cite sources as [doc_1], [doc_2], etc."
                ),
                'raw_results': [
                    {
                        'rank': r['rank'],
                        'text_preview': r['text'][:200] + '...' if len(r['text']) > 200 else r['text'],
                        'similarity': r.get('similarity', 0),
                        'metadata': {
                            'author': r['metadata'].get('author'),
                            'title': r['metadata'].get('book_title'),
                            'year': r['metadata'].get('year'),
                            'page': r['metadata'].get('page'),
                        }
                    }
                    for r in results
                ]
            }

        except Exception as e:
            logger.error(f"Search with citations failed: {e}", exc_info=True)
            return {
                'error': f'Search failed: {str(e)}',
                'query': query
            }


def create_mcp_tools(server: CalibreMCPServer) -> list[dict]:
    """
    Create MCP tool definitions for the server.

    Args:
        server: The CalibreMCPServer instance

    Returns:
        List of MCP tool definitions
    """
    return [
        {
            'name': 'get_book_annotations',
            'description': 'Get annotations (highlights, notes, bookmarks) for a specific book with intelligent filtering to exclude TOC markers and technical highlights',
            'inputSchema': {
                'type': 'object',
                'properties': {
                    'book_path': {
                        'type': 'string',
                        'description': 'Full path to the book file'
                    },
                    'annotation_type': {
                        'type': 'string',
                        'enum': ['highlight', 'note', 'bookmark'],
                        'description': 'Optional filter for annotation type'
                    },
                    'exclude_toc_markers': {
                        'type': 'boolean',
                        'description': 'Whether to exclude TOC markers and technical highlights (default: true)',
                        'default': True
                    },
                    'include_pdf': {
                        'type': 'boolean',
                        'description': 'Whether to extract PDF-internal annotations for PDF files (default: true)',
                        'default': True
                    },
                    'min_length': {
                        'type': 'integer',
                        'description': 'Minimum character length for annotations (default: 20)',
                        'default': 20
                    },
                    'exclude_first_percent': {
                        'type': 'number',
                        'description': 'Exclude annotations in first X% of book (default: 5.0)',
                        'default': 5.0
                    }
                },
                'required': ['book_path']
            }
        },
        {
            'name': 'search_annotations',
            'description': 'Search through all annotations using text-based or semantic search with intelligent deduplication',
            'inputSchema': {
                'type': 'object',
                'properties': {
                    'query': {
                        'type': 'string',
                        'description': 'Search query string'
                    },
                    'case_sensitive': {
                        'type': 'boolean',
                        'description': 'Whether to use case-sensitive search (text search only)',
                        'default': False
                    },
                    'use_semantic': {
                        'type': 'boolean',
                        'description': 'Use semantic search instead of text search (requires ChromaDB)',
                        'default': False
                    },
                    'max_results': {
                        'type': 'integer',
                        'description': 'Maximum number of results (semantic search only)',
                        'default': 10
                    },
                    'max_per_book': {
                        'type': 'integer',
                        'description': 'Maximum results per book to prevent one book dominating results (semantic search only, use 0 for unlimited)',
                        'default': 2
                    }
                },
                'required': ['query']
            }
        },
        {
            'name': 'list_annotated_books',
            'description': 'List all books that have annotations',
            'inputSchema': {
                'type': 'object',
                'properties': {}
            }
        },
        {
            'name': 'compute_annotation_hash',
            'description': 'Compute the annotation hash for a book path (for debugging)',
            'inputSchema': {
                'type': 'object',
                'properties': {
                    'book_path': {
                        'type': 'string',
                        'description': 'Full path to the book file'
                    }
                },
                'required': ['book_path']
            }
        },
        {
            'name': 'index_annotations',
            'description': 'Index all annotations for semantic search (requires semantic search to be enabled)',
            'inputSchema': {
                'type': 'object',
                'properties': {
                    'force_reindex': {
                        'type': 'boolean',
                        'description': 'Force reindexing of all annotations',
                        'default': False
                    },
                    'exclude_toc_markers': {
                        'type': 'boolean',
                        'description': 'Whether to exclude TOC markers',
                        'default': True
                    }
                }
            }
        },
        {
            'name': 'get_index_stats',
            'description': 'Get statistics about the annotation index',
            'inputSchema': {
                'type': 'object',
                'properties': {}
            }
        },
        {
            'name': 'detect_duplicates',
            'description': 'Detect duplicate books in the library using various methods (title+author, ISBN, or exact title). Also shows books tagged with "Doublette".',
            'inputSchema': {
                'type': 'object',
                'properties': {
                    'method': {
                        'type': 'string',
                        'enum': ['title_author', 'isbn', 'exact_title'],
                        'description': 'Detection method: title_author (normalized title+author), isbn (by ISBN), or exact_title (exact title match)',
                        'default': 'title_author'
                    },
                    'include_doublette_tag': {
                        'type': 'boolean',
                        'description': 'Also show books tagged with "Doublette"',
                        'default': True
                    }
                }
            }
        },
        {
            'name': 'get_book_details',
            'description': 'Get detailed information about a specific book by Calibre book ID',
            'inputSchema': {
                'type': 'object',
                'properties': {
                    'book_id': {
                        'type': 'integer',
                        'description': 'Calibre book ID'
                    }
                },
                'required': ['book_id']
            }
        },
        {
            'name': 'get_doublette_tag_instruction',
            'description': 'Get instructions for adding the "Doublette" tag to a book (for manual tagging)',
            'inputSchema': {
                'type': 'object',
                'properties': {
                    'book_id': {
                        'type': 'integer',
                        'description': 'Calibre book ID to tag'
                    }
                },
                'required': ['book_id']
            }
        },
        {
            'name': 'export_bibliography',
            'description': 'Export bibliography in various formats (BibTeX, RIS, EndNote, JSON, CSV). Books can be filtered by author, tag, and publication year.',
            'inputSchema': {
                'type': 'object',
                'properties': {
                    'format': {
                        'type': 'string',
                        'enum': ['bibtex', 'ris', 'endnote', 'json', 'csv'],
                        'description': 'Export format: bibtex (LaTeX), ris (Reference Manager), endnote, json, or csv',
                        'default': 'bibtex'
                    },
                    'author': {
                        'type': 'string',
                        'description': 'Filter by author name (case-insensitive partial match)'
                    },
                    'tag': {
                        'type': 'string',
                        'description': 'Filter by tag name (case-insensitive partial match)'
                    },
                    'year_from': {
                        'type': 'integer',
                        'description': 'Filter books published from this year (e.g., 2000)'
                    },
                    'year_to': {
                        'type': 'integer',
                        'description': 'Filter books published up to this year (e.g., 2023)'
                    },
                    'max_books': {
                        'type': 'integer',
                        'description': 'Maximum number of books to export'
                    }
                }
            }
        },
        {
            'name': 'list_books_by_author',
            'description': 'List all books by an author from the Calibre metadata database. Direct metadata query (not vector search), reliable for short texts like articles or book chapters. Supports tag and year filtering.',
            'inputSchema': {
                'type': 'object',
                'properties': {
                    'author': {
                        'type': 'string',
                        'description': 'Author name to search for (case-insensitive partial match, e.g., "Mason" matches "Steve Mason")'
                    },
                    'tags': {
                        'type': 'array',
                        'items': {'type': 'string'},
                        'description': 'Optional list of tag names to filter by (AND logic, case-insensitive partial match, e.g., ["Artikel"])'
                    },
                    'year_from': {
                        'type': 'integer',
                        'description': 'Filter books published from this year (e.g., 2000)'
                    },
                    'year_to': {
                        'type': 'integer',
                        'description': 'Filter books published up to this year (e.g., 2023)'
                    },
                    'sort_by': {
                        'type': 'string',
                        'enum': ['title', 'year'],
                        'description': 'Sort order: by title (default, alphabetical) or by year (descending)',
                        'default': 'title'
                    }
                },
                'required': ['author']
            }
        },
        {
            'name': 'list_tags',
            'description': 'List all tags in the Calibre library with book counts. Useful for discovering available tags before filtering search results.',
            'inputSchema': {
                'type': 'object',
                'properties': {
                    'min_books': {
                        'type': 'integer',
                        'description': 'Only show tags with at least this many books (default: 1)',
                        'default': 1
                    },
                    'max_tags': {
                        'type': 'integer',
                        'description': 'Maximum number of tags to return (default: 100)',
                        'default': 100
                    }
                }
            }
        },
        {
            'name': 'search_books_with_citations',
            'description': 'Search books with RAG and generate XML-structured prompts with citation support. Returns system prompt + user prompt ready for Claude Desktop. Claude will cite sources as [doc_1], [doc_2], etc.',
            'inputSchema': {
                'type': 'object',
                'properties': {
                    'query': {
                        'type': 'string',
                        'description': 'Search query (e.g., "Was ist Herrschaftslegitimation?")'
                    },
                    'top_k': {
                        'type': 'integer',
                        'description': 'Number of results to return (default: 5)',
                        'default': 5
                    },
                    'mode': {
                        'type': 'string',
                        'enum': ['hybrid', 'semantic', 'keyword'],
                        'description': 'Search mode: hybrid (recommended), semantic (meaning-based), or keyword (exact matching)',
                        'default': 'hybrid'
                    },
                    'language': {
                        'type': 'string',
                        'description': 'Filter by language code (e.g., "de" for German, "en" for English, "la" for Latin)'
                    },
                    'tags': {
                        'type': 'array',
                        'items': {'type': 'string'},
                        'description': 'Filter by Calibre tags (e.g., ["Geschichte", "Philosophie"]). Results must match ALL tags (AND logic).'
                    },
                    'expand_context': {
                        'type': 'boolean',
                        'description': 'Enable context expansion (Small-to-Big retrieval) if char_offsets available',
                        'default': False
                    }
                },
                'required': ['query']
            }
        }
    ]


if __name__ == '__main__':
    # Example usage
    server = CalibreMCPServer()

    # Test with example book path
    test_path = r"D:\Calibre-Bibliothek\Henri Pirenne\Mohammed and Charlemagne (6700)\Mohammed and Charlemagne - Henri Pirenne.epub"

    result = server.compute_hash_tool(test_path)
    print(json.dumps(result, indent=2))
