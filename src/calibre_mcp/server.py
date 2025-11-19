#!/usr/bin/env python3
"""
Calibre MCP Server

A Model Context Protocol server for Calibre library integration.
Provides tools for searching, analyzing, and accessing Calibre library data.
"""

import json
import logging
from pathlib import Path
from typing import Any, Optional

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
        chroma_persist_dir: Optional[str] = None
    ):
        """
        Initialize the Calibre MCP Server.

        Args:
            library_path: Path to the Calibre library
            annotations_dir: Custom path to annotations directory
            enable_semantic_search: Enable semantic search with ChromaDB
            chroma_persist_dir: Directory to persist ChromaDB data
        """
        self.library_path = Path(library_path) if library_path else None
        self.annotations_dir = annotations_dir
        self.enable_semantic_search = enable_semantic_search

        # Initialize semantic search if enabled
        self.indexer = None
        if enable_semantic_search:
            try:
                from .annotations_indexer import AnnotationsIndexer
                self.indexer = AnnotationsIndexer(
                    chroma_persist_dir=chroma_persist_dir,
                    annotations_dir=annotations_dir
                )
                logger.info("Semantic search enabled")
            except ImportError:
                logger.warning(
                    "ChromaDB not available. Semantic search disabled. "
                    "Install with: pip install chromadb"
                )
                self.enable_semantic_search = False

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
        max_results: int = 10
    ) -> dict[str, Any]:
        """
        MCP Tool: Search through all annotations.

        Supports both text-based and semantic search.

        Args:
            query: Search query string
            case_sensitive: Whether to use case-sensitive search (text search only)
            use_semantic: Use semantic search instead of text search
            max_results: Maximum number of results (semantic search only)

        Returns:
            Dictionary with search results
        """
        # Use semantic search if enabled and requested
        if use_semantic and self.enable_semantic_search and self.indexer:
            results = self.indexer.search_annotations(
                query=query,
                n_results=max_results
            )

            return {
                'query': query,
                'search_type': 'semantic',
                'result_count': len(results),
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
            'description': 'Search through all annotations using text-based or semantic search',
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
        }
    ]


if __name__ == '__main__':
    # Example usage
    server = CalibreMCPServer()

    # Test with example book path
    test_path = r"D:\Calibre-Bibliothek\Henri Pirenne\Mohammed and Charlemagne (6700)\Mohammed and Charlemagne - Henri Pirenne.epub"

    result = server.compute_hash_tool(test_path)
    print(json.dumps(result, indent=2))
