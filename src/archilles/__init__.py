"""
ARCHILLES - Adaptive RAG for Calibre Historical & Literary Library Exploration System

This module provides hardware-adaptive indexing profiles and utilities
for the ARCHILLES RAG system.

Submodules:
- hardware: Hardware detection and profile recommendation
- profiles: Indexing profiles for different hardware capabilities
- indexer: Checkpoint-based indexing with resume support
- parsers: Pluggable document parsing (PDF, EPUB, etc.)
- embedders: Pluggable text embedding (BGE family, etc.)
"""

from .hardware import HardwareProfile, detect_hardware
from .profiles import IndexingProfile, PROFILES, get_profile

# Lazy imports for optional submodules
def get_parser(name_or_path):
    """Get a parser by name or for a file path."""
    from .parsers import get_parser as _get_parser
    return _get_parser(name_or_path)

def get_embedder(name):
    """Get an embedder by name."""
    from .embedders import get_embedder as _get_embedder
    return _get_embedder(name)

__all__ = [
    # Hardware
    'HardwareProfile',
    'detect_hardware',
    # Profiles
    'IndexingProfile',
    'PROFILES',
    'get_profile',
    # Convenience functions
    'get_parser',
    'get_embedder',
]

__version__ = "0.3.0"
