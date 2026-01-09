"""
ARCHILLES Parsers Module

Provides pluggable document parsing with:
- Abstract base class for parser implementations
- Built-in PyMuPDF parser for PDFs
- Registry for parser discovery and management
"""

from .base import DocumentParser, ParsedDocument, ParsedChunk, ParserCapabilities
from .registry import ParserRegistry, get_parser, register_parser

__all__ = [
    'DocumentParser',
    'ParsedDocument',
    'ParsedChunk',
    'ParserCapabilities',
    'ParserRegistry',
    'get_parser',
    'register_parser',
]
