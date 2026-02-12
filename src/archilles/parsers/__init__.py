"""
ARCHILLES Parsers Module

Provides pluggable document parsing with:
- Abstract base class for parser implementations
- Built-in PyMuPDF parser for PDFs
- Built-in EPUB parser for EPUB files
- Registry for parser discovery and management
"""

from .base import DocumentParser, ParsedDocument, ParsedChunk, ParserCapabilities
from .registry import ParserRegistry, get_parser, register_parser

# Optional parser imports (may not be available if dependencies not installed)
try:
    from .pymupdf_parser import PyMuPDFParser
except ImportError:
    PyMuPDFParser = None

try:
    from .epub_parser import EPUBParser
except ImportError:
    EPUBParser = None

__all__ = [
    'DocumentParser',
    'ParsedDocument',
    'ParsedChunk',
    'ParserCapabilities',
    'ParserRegistry',
    'get_parser',
    'register_parser',
    'PyMuPDFParser',
    'EPUBParser',
]
