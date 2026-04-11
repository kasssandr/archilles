"""
ARCHILLES Chunker Registry

Central registry for discovering and selecting text chunkers.
"""

from typing import Optional
import logging

from src.archilles.registry import BaseRegistry
from .base import TextChunker, ChunkerConfig

logger = logging.getLogger(__name__)


class ChunkerRegistry(BaseRegistry[TextChunker]):
    """
    Registry for text chunkers.

    Maintains a collection of available chunkers and provides
    methods to select the appropriate chunker for a task.
    """

    _label = "chunker"

    def get_default(self) -> Optional[TextChunker]:
        """
        Get the default chunker (semantic if available, else first registered).

        Returns:
            Default chunker or None if registry is empty
        """
        return self.get("semantic") or next(iter(self), None)

    def list_chunkers(self) -> list[str]:
        """Get list of registered chunker names."""
        return self.list_names()

    def print_info(self) -> None:
        """Print information about registered chunkers."""
        print()
        print("=" * 64)
        print("  REGISTERED CHUNKERS")
        print("=" * 64)

        if not self:
            print("  No chunkers registered.")
        else:
            for name in sorted(self.list_names()):
                chunker = self.get(name)
                cfg = chunker.config
                print(f"\n  [{name}]")
                print(f"    Description: {chunker.description}")
                print(f"    Chunk size: {cfg.chunk_size} {cfg.size_unit}")
                print(f"    Overlap: {cfg.chunk_overlap}")
                if cfg.respect_sentences:
                    print(f"    Respects: sentences, paragraphs")

        print()
        print("=" * 64)
        print()


# Global registry instance
_global_registry = ChunkerRegistry()


def get_registry() -> ChunkerRegistry:
    """Get the global chunker registry."""
    return _global_registry


def register_chunker(chunker: TextChunker) -> None:
    """
    Register a chunker in the global registry.

    Args:
        chunker: Chunker instance to register
    """
    _global_registry.register(chunker)


def get_chunker(name: str) -> Optional[TextChunker]:
    """
    Get a chunker by name from the global registry.

    Args:
        name: Chunker name

    Returns:
        Chunker instance or None if not found
    """
    return _global_registry.get(name)


def list_chunkers() -> list[str]:
    """Get list of registered chunker names."""
    return _global_registry.list_chunkers()


# Quick test
if __name__ == "__main__":
    from .semantic import SemanticChunker
    from .fixed import FixedSizeChunker

    # Test registry
    registry = ChunkerRegistry()
    registry.register(SemanticChunker())
    registry.register(FixedSizeChunker())
    registry.print_info()

    # Test lookup
    chunker = registry.get("semantic")
    print(f"Found chunker: {chunker}")

    # Test default
    default = registry.get_default()
    print(f"Default chunker: {default}")
