"""
ARCHILLES Indexing Profiles

Hardware-adaptive configuration profiles for different system capabilities.

ALL profiles use BGE-M3 (best multilingual model) - only batch_size differs!

Profile Overview:
-----------------
| Profile   | Hardware           | Batch | Speed       |
|-----------|--------------------|-------|-------------|
| minimal   | <8 GB VRAM / MPS   | 8     | ~2 min/book |
| balanced  | 8-16 GB VRAM       | 32    | ~30s/book   |
| maximal   | 16+ GB VRAM        | 64    | ~15s/book   |

Quality is IDENTICAL across all profiles - only indexing speed differs.

The embedding device (cuda/mps/cpu) is detected automatically at startup.
"""

from dataclasses import dataclass, asdict
from typing import Literal, Dict, Any

ProfileName = Literal["minimal", "balanced", "maximal"]


@dataclass
class IndexingProfile:
    """Configuration for an indexing profile."""

    name: ProfileName
    embedding_model: str
    embedding_device: str  # "cpu", "cuda", "mps"
    batch_size: int
    chunk_size: int  # in tokens
    chunk_overlap: int
    description: str

    # Note: model/dimension and the chunk schema (child/parent sizes,
    # hierarchical) are owned by IndexRecipe (src/archilles/recipe.py), the
    # single source of truth for the main path. chunk_size/chunk_overlap stay
    # here only for the deferred modular pipeline (pipeline.py), which still
    # reads them; they are removed together with that path in a later stage.

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return asdict(self)


# Lazy-initialised: calling get_best_device() at import time pulls in torch,
# which is expensive (~2s) and unnecessary for non-embedding code paths.
_PROFILES: Dict[ProfileName, IndexingProfile] | None = None


def _build_profiles() -> Dict[ProfileName, IndexingProfile]:
    from .hardware import get_best_device

    common = dict(
        embedding_model="BAAI/bge-m3",
        embedding_device=get_best_device(),
        chunk_size=512,
        chunk_overlap=128,
    )
    return {
        "minimal": IndexingProfile(
            name="minimal",
            batch_size=8,
            description="For 4-6 GB GPUs, Apple Silicon (MPS), or CPU-only. Full quality, ~2–15 min/book.",
            **common,
        ),
        "balanced": IndexingProfile(
            name="balanced",
            batch_size=32,
            description="For 8-12GB GPUs (RTX 3060, RTX 2070). Full quality, ~30s/book.",
            **common,
        ),
        "maximal": IndexingProfile(
            name="maximal",
            batch_size=64,
            description="For 16GB+ GPUs (RTX 3090, RTX 4080). Full quality, ~15s/book.",
            **common,
        ),
    }


def _get_profiles() -> Dict[ProfileName, IndexingProfile]:
    global _PROFILES
    if _PROFILES is None:
        _PROFILES = _build_profiles()
    return _PROFILES


def get_profile(name: ProfileName) -> IndexingProfile:
    """
    Get a profile by name.

    Args:
        name: Profile name ("minimal", "balanced", or "maximal")

    Returns:
        IndexingProfile configuration

    Raises:
        KeyError: If profile name is not recognized
    """
    profiles = _get_profiles()
    if name not in profiles:
        raise KeyError(
            f"Unknown profile: {name}. Valid profiles: {list(profiles.keys())}"
        )
    return profiles[name]


def list_profiles() -> None:
    """Print all available profiles with descriptions."""
    print()
    print("=" * 70)
    print("  ARCHILLES Indexing Profiles")
    print("=" * 70)
    print()

    for name, profile in _get_profiles().items():
        print(f"  [{name.upper()}]")
        print(f"    {profile.description}")
        print(f"    Model: {profile.embedding_model}")
        print(f"    Device: {profile.embedding_device}")
        print(f"    Chunk size: {profile.chunk_size} tokens (overlap: {profile.chunk_overlap})")
        print(f"    Batch size: {profile.batch_size}")
        print()

    print("=" * 70)
    print()


# Quick test
if __name__ == "__main__":
    list_profiles()
