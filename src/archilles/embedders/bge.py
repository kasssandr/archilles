"""
ARCHILLES BGE Embedder Family

Implementation of BGE (BAAI General Embedding) models.

Supported models:
- bge-small-en-v1.5: 384 dim, fast, CPU-friendly
- bge-base-en-v1.5: 768 dim, balanced quality/speed
- bge-m3: 1024 dim, multilingual, high quality

These are the primary embedders used by ARCHILLES profiles:
- minimal profile -> bge-small
- balanced profile -> bge-base
- maximal profile -> bge-m3
"""

import time
from typing import List, Optional, Literal
import logging
import numpy as np

from .base import TextEmbedder, EmbedderCapabilities, EmbeddingResult, DeviceType

logger = logging.getLogger(__name__)

# Check for sentence-transformers
try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False

# Check for torch
try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False


# BGE model configurations
BGE_MODELS = {
    "bge-small": {
        "hf_name": "BAAI/bge-small-en-v1.5",
        "dimension": 384,
        "max_tokens": 512,
        "model_size_mb": 133,
        "vram_mb": 300,
        "quality_tier": 3,
        "speed_tier": 9,
    },
    "bge-base": {
        "hf_name": "BAAI/bge-base-en-v1.5",
        "dimension": 768,
        "max_tokens": 512,
        "model_size_mb": 438,
        "vram_mb": 600,
        "quality_tier": 6,
        "speed_tier": 6,
    },
    "bge-m3": {
        "hf_name": "BAAI/bge-m3",
        "dimension": 1024,
        "max_tokens": 8192,
        "model_size_mb": 2200,
        "vram_mb": 3000,
        "quality_tier": 9,
        "speed_tier": 3,
    },
}

BGEModelName = Literal["bge-small", "bge-base", "bge-m3"]


def _resolve_device(device: DeviceType) -> str:
    """Resolve 'auto' to the best available device, or pass through explicit values."""
    if device != "auto":
        return device
    if TORCH_AVAILABLE and torch.cuda.is_available():
        return "cuda"
    if TORCH_AVAILABLE and hasattr(torch.backends, 'mps') and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


class BGEEmbedder(TextEmbedder):
    """
    BGE (BAAI General Embedding) text embedder.

    Uses sentence-transformers for efficient embedding generation.
    Supports CPU and CUDA devices.

    Args:
        model_name: Which BGE model to use ("bge-small", "bge-base", "bge-m3")
        device: Device to use ("cpu", "cuda", "auto")
        batch_size: Batch size for embedding (default from capabilities)
        normalize: Whether to L2-normalize embeddings (default: True)
        show_progress: Show progress bar during embedding (default: False)
    """

    def __init__(
        self,
        model_name: BGEModelName = "bge-small",
        device: DeviceType = "auto",
        batch_size: Optional[int] = None,
        normalize: bool = True,
        show_progress: bool = False
    ):
        if not SENTENCE_TRANSFORMERS_AVAILABLE:
            raise ImportError(
                "sentence-transformers is not installed. "
                "Install with: pip install sentence-transformers"
            )

        if model_name not in BGE_MODELS:
            raise ValueError(
                f"Unknown model: {model_name}. "
                f"Available: {list(BGE_MODELS.keys())}"
            )

        self._model_name = model_name
        self._config = BGE_MODELS[model_name]
        self._normalize = normalize
        self._show_progress = show_progress
        self._model: Optional[SentenceTransformer] = None

        self._device = _resolve_device(device)

        if batch_size is not None:
            self._batch_size = batch_size
        elif self._device == "cpu":
            self._batch_size = 8
        else:
            self._batch_size = 32

    @property
    def name(self) -> str:
        return self._model_name

    @property
    def device(self) -> str:
        return self._device

    @property
    def capabilities(self) -> EmbedderCapabilities:
        return EmbedderCapabilities(
            model_name=self._config["hf_name"],
            embedding_dimension=self._config["dimension"],
            max_tokens=self._config["max_tokens"],
            max_batch_size=self._batch_size,
            supports_cuda=True,
            supports_mps=TORCH_AVAILABLE and hasattr(torch.backends, 'mps'),
            supports_batching=True,
            normalized_embeddings=self._normalize,
            quality_tier=self._config["quality_tier"],
            speed_tier=self._config["speed_tier"],
            model_size_mb=self._config["model_size_mb"],
            vram_required_mb=self._config["vram_mb"],
        )

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    def load_model(self) -> None:
        """Load the model into memory."""
        if self._model is not None:
            return

        logger.info(f"Loading {self._model_name} on {self._device}...")
        start = time.time()

        self._model = SentenceTransformer(
            self._config["hf_name"],
            device=self._device
        )

        duration = time.time() - start
        logger.info(f"Model loaded in {duration:.1f}s")

    def unload_model(self) -> None:
        """Unload the model from memory."""
        if self._model is None:
            return

        del self._model
        self._model = None

        # Clear GPU cache if using CUDA
        if TORCH_AVAILABLE and self._device == "cuda":
            torch.cuda.empty_cache()

        logger.info(f"Unloaded {self._model_name}")

    def embed_batch(self, texts: List[str]) -> EmbeddingResult:
        """Embed a batch of texts, returning an EmbeddingResult with the embeddings array."""
        if not texts:
            return EmbeddingResult(
                embeddings=np.array([], dtype=np.float32).reshape(0, self._config["dimension"]),
                model_name=self._config["hf_name"],
                embedding_dimension=self._config["dimension"],
                texts_count=0,
                duration_seconds=0.0,
                device=self._device
            )

        if self._model is None:
            self.load_model()

        start = time.time()
        embeddings = self._model.encode(
            texts,
            batch_size=self._batch_size,
            show_progress_bar=self._show_progress,
            normalize_embeddings=self._normalize,
            convert_to_numpy=True
        )

        duration = time.time() - start

        if not isinstance(embeddings, np.ndarray):
            embeddings = np.array(embeddings, dtype=np.float32)
        else:
            embeddings = embeddings.astype(np.float32)

        return EmbeddingResult(
            embeddings=embeddings,
            model_name=self._config["hf_name"],
            embedding_dimension=self._config["dimension"],
            texts_count=len(texts),
            duration_seconds=duration,
            device=self._device,
            metadata={
                "batch_size": self._batch_size,
                "normalized": self._normalize,
            }
        )


def create_bge_embedder(
    model_name: BGEModelName = "bge-small",
    device: DeviceType = "auto",
    **kwargs
) -> Optional[BGEEmbedder]:
    """
    Factory function to create BGE embedder if dependencies are available.

    Args:
        model_name: Which BGE model to use
        device: Device to use
        **kwargs: Additional arguments for BGEEmbedder

    Returns:
        BGEEmbedder instance or None if dependencies not installed
    """
    if not SENTENCE_TRANSFORMERS_AVAILABLE:
        logger.warning("sentence-transformers not available")
        return None

    return BGEEmbedder(model_name=model_name, device=device, **kwargs)


_PROFILE_MAP = {
    "minimal": ("bge-small", "cpu", 8),
    "balanced": ("bge-base", "cuda", 32),
    "maximal": ("bge-m3", "cuda", 64),
}


def create_embedder_for_profile(profile_name: str) -> Optional[BGEEmbedder]:
    """
    Create the appropriate BGE embedder for a hardware profile.

    Args:
        profile_name: "minimal", "balanced", or "maximal"

    Returns:
        Configured BGEEmbedder instance
    """
    if profile_name not in _PROFILE_MAP:
        raise ValueError(f"Unknown profile: {profile_name}")

    model_name, device, batch_size = _PROFILE_MAP[profile_name]
    return create_bge_embedder(
        model_name=model_name,
        device=device,
        batch_size=batch_size,
    )


# Auto-register all BGE embedders
def _auto_register():
    """Auto-register BGE embedders with global registry."""
    if not SENTENCE_TRANSFORMERS_AVAILABLE:
        return

    from .registry import register_embedder

    for model_name in BGE_MODELS:
        try:
            embedder = BGEEmbedder(model_name=model_name, device="cpu")
            register_embedder(embedder)
            logger.debug(f"Auto-registered BGE embedder: {model_name}")
        except Exception as e:
            logger.warning(f"Failed to register {model_name}: {e}")


# Quick test
if __name__ == "__main__":
    import sys

    if not SENTENCE_TRANSFORMERS_AVAILABLE:
        print("sentence-transformers not installed!")
        sys.exit(1)

    # Test basic embedder
    print("Creating BGE-small embedder...")
    embedder = BGEEmbedder("bge-small", device="cpu")
    print(f"Embedder: {embedder}")
    print(f"Capabilities: {embedder.capabilities}")

    # Test embedding
    print("\nLoading model and embedding test texts...")
    texts = [
        "The quick brown fox jumps over the lazy dog.",
        "Machine learning is a subset of artificial intelligence.",
        "Python is a popular programming language.",
    ]

    with embedder:
        result = embedder.embed_batch(texts)
        print(f"\nResult: {result}")
        print(f"Embeddings shape: {result.embeddings.shape}")
        print(f"Texts/second: {result.texts_per_second:.1f}")

        # Test single embedding
        single = embedder.embed("Hello world!")
        print(f"Single embedding shape: {single.shape}")

    print("\nModel unloaded.")
