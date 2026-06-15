"""
ARCHILLES Embedders Module

Provides pluggable text embedding with:
- Abstract base class for embedder implementations
- Built-in BGE embedder family
"""

from .base import TextEmbedder, EmbedderCapabilities, EmbeddingResult
from .remote import RemoteBGEEmbedder

__all__ = [
    'TextEmbedder',
    'EmbedderCapabilities',
    'EmbeddingResult',
    'RemoteBGEEmbedder',
]
