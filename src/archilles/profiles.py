"""
ARCHILLES Indexing Profiles

Hardware-adaptive configuration profiles for different system capabilities.

ALL profiles use BGE-M3 (best multilingual model) - only batch_size differs!

Profile Overview:
-----------------
| Profile   | VRAM       | Model  | Batch | Speed      | Use Case               |
|-----------|------------|--------|-------|------------|------------------------|
| minimal   | 4-6 GB     | bge-m3 | 8     | ~2 min/book| Quadro T1000, GTX 1650 |
| balanced  | 8-12 GB    | bge-m3 | 32    | ~30s/book  | RTX 3060, RTX 2070     |
| maximal   | 16+ GB     | bge-m3 | 64    | ~15s/book  | RTX 3090, RTX 4080     |

Quality is IDENTICAL across all profiles - only indexing speed differs.

Reference: Tom's ThinkPad P15 (Quadro T1000, 4GB VRAM) -> "minimal" profile
"""

from dataclasses import dataclass, field, asdict
from typing import Literal, Dict, Any
from datetime import datetime
import json

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
    max_parallel_docs: int
    description: str

    # These defaults are overridden by every profile definition below,
    # but kept as sensible fallbacks for ad-hoc construction.
    embedding_dimension: int = 384
    max_tokens_per_chunk: int = 512

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return asdict(self)

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "IndexingProfile":
        """Create from dictionary."""
        return cls(**data)


# Shared settings for all profiles (all use BGE-M3 for consistent quality)
_COMMON = dict(
    embedding_model="BAAI/bge-m3",
    embedding_device="cuda",
    chunk_size=512,
    chunk_overlap=128,
    embedding_dimension=1024,
    max_tokens_per_chunk=8192,
)

PROFILES: Dict[ProfileName, IndexingProfile] = {
    "minimal": IndexingProfile(
        name="minimal",
        batch_size=8,
        max_parallel_docs=2,
        description="For 4-6GB GPUs (Quadro T1000, GTX 1650). Full quality, ~2 min/book.",
        **_COMMON,
    ),
    "balanced": IndexingProfile(
        name="balanced",
        batch_size=32,
        max_parallel_docs=4,
        description="For 8-12GB GPUs (RTX 3060, RTX 2070). Full quality, ~30s/book.",
        **_COMMON,
    ),
    "maximal": IndexingProfile(
        name="maximal",
        batch_size=64,
        max_parallel_docs=8,
        description="For 16GB+ GPUs (RTX 3090, RTX 4080). Full quality, ~15s/book.",
        **_COMMON,
    ),
}


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
    if name not in PROFILES:
        raise KeyError(
            f"Unknown profile: {name}. Valid profiles: {list(PROFILES.keys())}"
        )
    return PROFILES[name]


def list_profiles() -> None:
    """Print all available profiles with descriptions."""
    print()
    print("=" * 70)
    print("  ARCHILLES Indexing Profiles")
    print("=" * 70)
    print()

    for name, profile in PROFILES.items():
        print(f"  [{name.upper()}]")
        print(f"    {profile.description}")
        print(f"    Model: {profile.embedding_model}")
        print(f"    Device: {profile.embedding_device}")
        print(f"    Chunk size: {profile.chunk_size} tokens (overlap: {profile.chunk_overlap})")
        print(f"    Batch size: {profile.batch_size}")
        print()

    print("=" * 70)
    print()


@dataclass
class IndexMetadata:
    """
    Metadata stored with each index for reproducibility.

    This information is critical for:
    - Reproducing search results on different systems
    - Deciding whether to re-index with a different profile
    - Debugging performance issues
    """

    archilles_version: str
    profile_name: ProfileName
    embedding_model: str
    chunk_size: int
    chunk_overlap: int
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    # Hardware snapshot at index creation time
    hardware_gpu: str = "unknown"
    hardware_vram_gb: float = 0.0
    hardware_ram_gb: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database metadata."""
        return asdict(self)

    @classmethod
    def from_profile(
        cls,
        profile: IndexingProfile,
        version: str = "0.2.0",
        gpu: str = "unknown",
        vram_gb: float = 0.0,
        ram_gb: float = 0.0,
    ) -> "IndexMetadata":
        """Create metadata from a profile and hardware info."""
        return cls(
            archilles_version=version,
            profile_name=profile.name,
            embedding_model=profile.embedding_model,
            chunk_size=profile.chunk_size,
            chunk_overlap=profile.chunk_overlap,
            hardware_gpu=gpu,
            hardware_vram_gb=vram_gb,
            hardware_ram_gb=ram_gb,
        )


def create_index_metadata(
    profile: IndexingProfile,
    version: str = "0.2.0",
) -> IndexMetadata:
    """
    Create index metadata from profile and current hardware.

    Args:
        profile: The indexing profile being used
        version: ARCHILLES version string

    Returns:
        IndexMetadata for storing with the collection
    """
    # Try to detect current hardware
    try:
        from .hardware import detect_hardware
        hw = detect_hardware()
        return IndexMetadata.from_profile(
            profile=profile,
            version=version,
            gpu=hw.gpu_name or "none",
            vram_gb=hw.vram_gb or 0.0,
            ram_gb=hw.ram_gb,
        )
    except Exception:
        # Fallback if hardware detection fails
        return IndexMetadata.from_profile(profile=profile, version=version)


# Quick test
if __name__ == "__main__":
    list_profiles()

    print("\nMinimal profile details:")
    p = get_profile("minimal")
    print(p.to_json())

    print("\nExample index metadata:")
    meta = IndexMetadata.from_profile(p, gpu="NVIDIA Quadro T1000", vram_gb=4.0, ram_gb=64.0)
    print(json.dumps(meta.to_dict(), indent=2))
