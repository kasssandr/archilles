"""
ARCHILLES Embedder Base Classes

Abstract base class and data structures for text embedding.

Design Philosophy:
- Embedders handle batching internally for efficiency
- Device selection (CPU/GPU) is part of configuration
- EmbeddingResult includes both vectors and metadata
- Support for different embedding dimensions and normalization
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Literal
import numpy as np


DeviceType = Literal["cpu", "cuda", "mps", "auto"]


@dataclass
class EmbedderCapabilities:
    """
    Declares what an embedder can handle.

    Used by the registry to select appropriate embedders
    and by callers to understand embedder characteristics.
    """

    # Model information
    model_name: str
    embedding_dimension: int

    # Input constraints
    max_tokens: int = 512  # Maximum input tokens
    max_batch_size: int = 32  # Recommended max batch size

    # Feature flags
    supports_cuda: bool = True
    supports_mps: bool = False  # Apple Silicon
    supports_batching: bool = True
    normalized_embeddings: bool = True  # L2 normalized

    # Performance characteristics (relative scale 1-10)
    speed_tier: int = 5  # Higher = faster
    quality_tier: int = 5  # Higher = better quality

    # Memory requirements
    model_size_mb: float = 0.0  # Approximate model size
    vram_required_mb: float = 0.0  # VRAM needed for GPU inference


@dataclass
class EmbeddingResult:
    """
    Result of embedding one or more texts.

    Contains the embedding vectors and metadata about the operation.
    """

    # The embeddings - shape: (n_texts, embedding_dim)
    embeddings: np.ndarray

    # Metadata
    model_name: str
    embedding_dimension: int
    texts_count: int

    # Timing
    duration_seconds: float = 0.0
    tokens_processed: int = 0

    # Device used
    device: str = "cpu"

    # Additional info
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def texts_per_second(self) -> float:
        """Calculate text throughput."""
        if self.duration_seconds > 0:
            return self.texts_count / self.duration_seconds
        return 0.0

    @property
    def tokens_per_second(self) -> float:
        """Calculate token throughput."""
        if self.duration_seconds > 0:
            return self.tokens_processed / self.duration_seconds
        return 0.0

    def get_embedding(self, index: int) -> np.ndarray:
        """Get embedding for a specific text by index."""
        return self.embeddings[index]

    def to_list(self) -> List[List[float]]:
        """Convert embeddings to nested lists for JSON serialization."""
        return self.embeddings.tolist()

    def __repr__(self) -> str:
        return (
            f"EmbeddingResult(texts={self.texts_count}, dim={self.embedding_dimension}, "
            f"device='{self.device}', duration={self.duration_seconds:.2f}s)"
        )


class TextEmbedder(ABC):
    """
    Abstract base class for text embedders.

    Implementations should:
    1. Declare capabilities in the capabilities property
    2. Implement embed() for single texts and embed_batch() for batches
    3. Handle device selection (CPU/GPU) appropriately
    4. Be thread-safe for parallel embedding

    Example implementation:
        class MyEmbedder(TextEmbedder):
            @property
            def name(self) -> str:
                return "my-embedder"

            @property
            def capabilities(self) -> EmbedderCapabilities:
                return EmbedderCapabilities(
                    model_name="my-model",
                    embedding_dimension=768,
                )

            def embed_batch(self, texts: List[str]) -> EmbeddingResult:
                # Implementation here
                pass
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier, lowercase with hyphens (e.g., "bge-small", "openai-ada")."""
        pass

    @property
    @abstractmethod
    def capabilities(self) -> EmbedderCapabilities:
        """Declare embedder characteristics."""
        pass

    @property
    def device(self) -> str:
        """Current device being used (cpu, cuda, or mps)."""
        return "cpu"

    @abstractmethod
    def embed_batch(self, texts: List[str]) -> EmbeddingResult:
        """Embed a batch of texts.

        Raises:
            RuntimeError: If embedding fails
        """
        pass

    def embed(self, text: str) -> np.ndarray:
        """Embed a single text. Returns a 1D numpy array."""
        result = self.embed_batch([text])
        return result.get_embedding(0)

    def embed_with_metadata(self, text: str) -> EmbeddingResult:
        """Embed a single text, returning full EmbeddingResult metadata."""
        return self.embed_batch([text])

    @abstractmethod
    def load_model(self) -> None:
        """Load the model into memory. Called before first embedding."""
        pass

    @abstractmethod
    def unload_model(self) -> None:
        """Unload the model from memory, freeing GPU resources."""
        pass

    @property
    def is_loaded(self) -> bool:
        """Check if model is loaded."""
        return False

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name='{self.name}', device='{self.device}')"

    def __enter__(self):
        """Context manager entry - load model."""
        self.load_model()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - unload model."""
        self.unload_model()
        return False


# Quick test
if __name__ == "__main__":
    # Test data structures
    caps = EmbedderCapabilities(
        model_name="test-model",
        embedding_dimension=384,
        max_tokens=512,
        supports_cuda=True
    )
    print(f"Capabilities: {caps}")

    # Create mock embedding result
    embeddings = np.random.randn(3, 384).astype(np.float32)
    result = EmbeddingResult(
        embeddings=embeddings,
        model_name="test-model",
        embedding_dimension=384,
        texts_count=3,
        duration_seconds=0.1,
        device="cpu"
    )
    print(f"Result: {result}")
    print(f"Texts/second: {result.texts_per_second:.1f}")
    print(f"First embedding shape: {result.get_embedding(0).shape}")
