"""
ARCHILLES Embedders Module

Provides pluggable text embedding with:
- Abstract base class for embedder implementations
- Built-in BGE embedder family
- Registry for embedder discovery and management
"""

from .base import TextEmbedder, EmbedderCapabilities, EmbeddingResult
from .registry import EmbedderRegistry, get_embedder, register_embedder

__all__ = [
    'TextEmbedder',
    'EmbedderCapabilities',
    'EmbeddingResult',
    'EmbedderRegistry',
    'get_embedder',
    'register_embedder',
]
