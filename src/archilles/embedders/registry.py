"""
ARCHILLES Embedder Registry

Central registry for discovering and selecting text embedders.

Features:
- Register embedders by name
- Select by capabilities (dimension, device support)
- Quality/speed-based selection
"""

from typing import Optional
import logging

from src.archilles.registry import BaseRegistry
from .base import TextEmbedder, DeviceType

logger = logging.getLogger(__name__)


class EmbedderRegistry(BaseRegistry[TextEmbedder]):
    """
    Registry for text embedders.

    Maintains a collection of available embedders and provides
    methods to select the best embedder for given requirements.
    """

    _label = "embedder"

    def get_by_dimension(self, dimension: int) -> Optional[TextEmbedder]:
        """
        Get an embedder that produces embeddings of a specific dimension.

        Args:
            dimension: Required embedding dimension

        Returns:
            Matching embedder, or None if not found
        """
        for embedder in self:
            if embedder.capabilities.embedding_dimension == dimension:
                return embedder
        return None

    def get_for_device(self, device: DeviceType) -> list[TextEmbedder]:
        """
        Get embedders that support a specific device.

        Args:
            device: Device type ("cpu", "cuda", "mps", "auto")

        Returns:
            List of compatible embedders
        """
        if device in ("cpu", "auto"):
            return list(self)

        device_support = {"cuda": "supports_cuda", "mps": "supports_mps"}
        attr = device_support.get(device)
        if not attr:
            return []

        return [
            e for e in self
            if getattr(e.capabilities, attr, False)
        ]

    def get_best_for_quality(self) -> Optional[TextEmbedder]:
        """
        Get the highest quality embedder available.

        Returns:
            Embedder with highest quality_tier, or None if empty
        """
        if not self:
            return None
        return max(self, key=lambda e: e.capabilities.quality_tier)

    def get_best_for_speed(self) -> Optional[TextEmbedder]:
        """
        Get the fastest embedder available.

        Returns:
            Embedder with highest speed_tier, or None if empty
        """
        if not self:
            return None
        return max(self, key=lambda e: e.capabilities.speed_tier)

    def list_embedders(self) -> list[str]:
        """Get list of registered embedder names."""
        return self.list_names()

    def print_info(self) -> None:
        """Print information about registered embedders."""
        print()
        print("=" * 64)
        print("  REGISTERED EMBEDDERS")
        print("=" * 64)

        if not self:
            print("  No embedders registered.")
        else:
            for name in sorted(self.list_names()):
                embedder = self.get(name)
                caps = embedder.capabilities
                print(f"\n  [{name}]")
                print(f"    Model: {caps.model_name}")
                print(f"    Dimension: {caps.embedding_dimension}")
                print(f"    Max tokens: {caps.max_tokens}")
                devices = ["cpu"]
                if caps.supports_cuda:
                    devices.append("cuda")
                if caps.supports_mps:
                    devices.append("mps")
                print(f"    Devices: {', '.join(devices)}")
                print(f"    Quality/Speed: {caps.quality_tier}/{caps.speed_tier}")
                if caps.model_size_mb > 0:
                    print(f"    Model size: {caps.model_size_mb:.0f} MB")

        print()
        print("=" * 64)
        print()


# Global registry instance
_global_registry = EmbedderRegistry()


def get_registry() -> EmbedderRegistry:
    """Get the global embedder registry."""
    return _global_registry


def register_embedder(embedder: TextEmbedder) -> None:
    """
    Register an embedder in the global registry.

    Args:
        embedder: Embedder instance to register
    """
    _global_registry.register(embedder)


def get_embedder(name: str) -> Optional[TextEmbedder]:
    """
    Get an embedder by name from the global registry.

    Args:
        name: Embedder name

    Returns:
        Embedder instance or None if not found
    """
    return _global_registry.get(name)


def list_embedders() -> list[str]:
    """Get list of registered embedder names."""
    return _global_registry.list_embedders()


# Quick test
if __name__ == "__main__":
    from .base import EmbedderCapabilities, EmbeddingResult
    import numpy as np

    # Create a mock embedder for testing
    class MockEmbedder(TextEmbedder):
        @property
        def name(self) -> str:
            return "mock-embedder"

        @property
        def capabilities(self) -> EmbedderCapabilities:
            return EmbedderCapabilities(
                model_name="mock-model",
                embedding_dimension=384,
                quality_tier=5,
                speed_tier=8
            )

        def embed_batch(self, texts):
            embeddings = np.random.randn(len(texts), 384).astype(np.float32)
            return EmbeddingResult(
                embeddings=embeddings,
                model_name="mock-model",
                embedding_dimension=384,
                texts_count=len(texts),
                duration_seconds=0.01
            )

        def load_model(self):
            pass

        def unload_model(self):
            pass

    # Test registry
    registry = EmbedderRegistry()
    registry.register(MockEmbedder())
    registry.print_info()

    # Test lookup
    embedder = registry.get("mock-embedder")
    print(f"Found embedder: {embedder}")
