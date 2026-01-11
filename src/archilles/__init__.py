"""
ARCHILLES - Adaptive RAG for Calibre Historical & Literary Library Exploration System

This module provides hardware-adaptive indexing profiles and utilities
for the ARCHILLES RAG system.

Submodules:
- hardware: Hardware detection and profile recommendation
- profiles: Indexing profiles for different hardware capabilities
- indexer: Checkpoint-based indexing with resume support
- parsers: Pluggable document parsing (PDF, EPUB, etc.)
- chunkers: Pluggable text chunking (semantic, fixed-size, token-based)
- embedders: Pluggable text embedding (BGE family, etc.)
- pipeline: Unified parser → chunker → embedder pipeline
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

def get_chunker(name):
    """Get a chunker by name."""
    from .chunkers import get_chunker as _get_chunker
    return _get_chunker(name)

def create_pipeline(profile_name='minimal'):
    """Create a modular indexing pipeline for a hardware profile."""
    from .pipeline import ModularPipeline
    return ModularPipeline.from_profile(profile_name)

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
    'get_chunker',
    'create_pipeline',
]

__version__ = "0.4.0"
