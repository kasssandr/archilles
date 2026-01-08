"""
ARCHILLES Indexer Module

Provides robust, checkpoint-based indexing with:
- Chunk-level progress tracking
- Automatic resume after interruption
- Failed book retry functionality
"""

from .checkpoint import IndexingCheckpoint, ChunkProgress

__all__ = ['IndexingCheckpoint', 'ChunkProgress']
