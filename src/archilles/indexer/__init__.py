"""
ARCHILLES Indexer Module

Provides robust, checkpoint-based indexing with:
- Book-level progress tracking
- Automatic resume after interruption
"""

from .checkpoint import IndexingCheckpoint

__all__ = ['IndexingCheckpoint']
