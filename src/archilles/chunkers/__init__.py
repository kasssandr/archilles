"""
ARCHILLES Chunkers Module

Provides pluggable text chunking with:
- Abstract base class for chunker implementations
- Semantic chunker (respects sentence/paragraph boundaries)
- Fixed-size chunker (token/character based)
"""

from .base import TextChunker, ChunkerConfig, TextChunk

__all__ = [
    'TextChunker',
    'ChunkerConfig',
    'TextChunk',
]
