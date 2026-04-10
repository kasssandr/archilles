"""
ARCHILLES Chunker Registry

Central registry for discovering and selecting text chunkers.
"""

from typing import Dict, List, Optional
import logging

from .base import TextChunker, ChunkerConfig

logger = logging.getLogger(__name__)


class ChunkerRegistry:
    """
    Registry for text chunkers.

    Maintains a collection of available chunkers and provides
    methods to select the appropriate chunker for a task.
    """

    def __init__(self):
        self._chunkers: Dict[str, TextChunker] = {}

    def register(self, chunker: TextChunker) -> None:
        """
        Register a chunker instance.

        Args:
            chunker: Chunker instance to register

        Raises:
            ValueError: If a chunker with this name is already registered
        """
        if chunker.name in self._chunkers:
            raise ValueError(f"Chunker '{chunker.name}' is already registered")

        self._chunkers[chunker.name] = chunker
        logger.debug(f"Registered chunker: {chunker.name}")

    def unregister(self, name: str) -> bool:
        """
        Remove a chunker from the registry.

        Args:
            name: Name of chunker to remove

        Returns:
            True if chunker was removed, False if not found
        """
        if name in self._chunkers:
            del self._chunkers[name]
            return True
        return False

    def get(self, name: str) -> Optional[TextChunker]:
        """
        Get a chunker by name.

        Args:
            name: Chunker name

        Returns:
            Chunker instance or None if not found
        """
        return self._chunkers.get(name)

    def get_default(self) -> Optional[TextChunker]:
        """
        Get the default chunker (semantic if available, else first registered).

        Returns:
            Default chunker or None if registry is empty
        """
        if "semantic" in self._chunkers:
            return self._chunkers["semantic"]
        if self._chunkers:
            return next(iter(self._chunkers.values()))
        return None

    def list_chunkers(self) -> List[str]:
        """Get list of registered chunker names."""
        return list(self._chunkers.keys())

    def print_info(self) -> None:
        """Print information about registered chunkers."""
        print()
        print("=" * 64)
        print("  REGISTERED CHUNKERS")
        print("=" * 64)

        if not self._chunkers:
            print("  No chunkers registered.")
        else:
            for name, chunker in sorted(self._chunkers.items()):
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


def list_chunkers() -> List[str]:
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
