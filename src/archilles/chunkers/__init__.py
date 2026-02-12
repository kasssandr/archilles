"""
ARCHILLES Chunkers Module

Provides pluggable text chunking with:
- Abstract base class for chunker implementations
- Semantic chunker (respects sentence/paragraph boundaries)
- Fixed-size chunker (token/character based)
- Registry for chunker discovery and management
"""

from .base import TextChunker, ChunkerConfig, TextChunk
from .registry import ChunkerRegistry, get_chunker, register_chunker

__all__ = [
    'TextChunker',
    'ChunkerConfig',
    'TextChunk',
    'ChunkerRegistry',
    'get_chunker',
    'register_chunker',
]
