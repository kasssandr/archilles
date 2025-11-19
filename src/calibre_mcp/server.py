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
    get_annotations_dir
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
        annotations_dir: Optional[str] = None
    ):
        """
        Initialize the Calibre MCP Server.

        Args:
            library_path: Path to the Calibre library
            annotations_dir: Custom path to annotations directory
        """
        self.library_path = Path(library_path) if library_path else None
        self.annotations_dir = annotations_dir

    def get_book_annotations_tool(
        self,
        book_path: str,
        annotation_type: Optional[str] = None
    ) -> dict[str, Any]:
        """
        MCP Tool: Get annotations for a specific book.

        Args:
            book_path: Full path to the book file
            annotation_type: Optional filter - 'highlight', 'note', or 'bookmark'

        Returns:
            Dictionary with annotations and metadata
        """
        # Calculate the correct hash
        book_hash = compute_book_hash(book_path)

        if annotation_type == 'highlight':
            annotations = get_highlights(book_path, self.annotations_dir)
        elif annotation_type == 'note':
            annotations = get_notes(book_path, self.annotations_dir)
        elif annotation_type == 'bookmark':
            annotations = get_bookmarks(book_path, self.annotations_dir)
        else:
            annotations = get_book_annotations(book_path, self.annotations_dir)

        return {
            'book_path': book_path,
            'book_hash': book_hash,
            'annotation_count': len(annotations) if annotations else 0,
            'annotations': annotations or [],
            'annotation_type_filter': annotation_type
        }

    def search_annotations_tool(
        self,
        query: str,
        case_sensitive: bool = False
    ) -> dict[str, Any]:
        """
        MCP Tool: Search through all annotations.

        Args:
            query: Search query string
            case_sensitive: Whether to use case-sensitive search

        Returns:
            Dictionary with search results
        """
        results = search_annotations(query, self.annotations_dir, case_sensitive)

        return {
            'query': query,
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
            'description': 'Get annotations (highlights, notes, bookmarks) for a specific book',
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
                    }
                },
                'required': ['book_path']
            }
        },
        {
            'name': 'search_annotations',
            'description': 'Search through all annotations for matching text',
            'inputSchema': {
                'type': 'object',
                'properties': {
                    'query': {
                        'type': 'string',
                        'description': 'Search query string'
                    },
                    'case_sensitive': {
                        'type': 'boolean',
                        'description': 'Whether to use case-sensitive search',
                        'default': False
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
        }
    ]


if __name__ == '__main__':
    # Example usage
    server = CalibreMCPServer()

    # Test with example book path
    test_path = r"D:\Calibre-Bibliothek\Henri Pirenne\Mohammed and Charlemagne (6700)\Mohammed and Charlemagne - Henri Pirenne.epub"

    result = server.compute_hash_tool(test_path)
    print(json.dumps(result, indent=2))
