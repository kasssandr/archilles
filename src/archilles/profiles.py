"""
ARCHILLES Indexing Profiles

Hardware-adaptive configuration profiles for different system capabilities.

Profile Overview:
-----------------
| Profile   | VRAM Trigger | Embedding Model      | Batch | Chunk | Philosophy          |
|-----------|--------------|----------------------|-------|-------|---------------------|
| minimal   | <6 GB / no CUDA | bge-small-en-v1.5 | 8     | 1000  | Works everywhere    |
| balanced  | 6-12 GB      | bge-base-en-v1.5     | 32    | 768   | Sweet spot          |
| maximal   | >12 GB       | bge-m3               | 64    | 512   | Maximum quality     |

Reference: Tom's ThinkPad P15 (Quadro T1000, 4GB VRAM) -> "minimal" profile
"""

from dataclasses import dataclass, field, asdict
from typing import Literal, Dict, Any, Optional
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

    # Additional settings with defaults
    embedding_dimension: int = 384  # Varies by model
    max_tokens_per_chunk: int = 512  # Model's max input

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


# Pre-defined profiles
PROFILES: Dict[ProfileName, IndexingProfile] = {
    "minimal": IndexingProfile(
        name="minimal",
        embedding_model="BAAI/bge-small-en-v1.5",
        embedding_device="cpu",
        batch_size=8,
        chunk_size=1000,
        chunk_overlap=200,
        max_parallel_docs=2,
        description="For laptops and older hardware. Fast, resource-efficient.",
        embedding_dimension=384,
        max_tokens_per_chunk=512,
    ),
    "balanced": IndexingProfile(
        name="balanced",
        embedding_model="BAAI/bge-base-en-v1.5",
        embedding_device="cuda",
        batch_size=32,
        chunk_size=768,
        chunk_overlap=150,
        max_parallel_docs=4,
        description="Recommended for most systems. Good balance of speed and quality.",
        embedding_dimension=768,
        max_tokens_per_chunk=512,
    ),
    "maximal": IndexingProfile(
        name="maximal",
        embedding_model="BAAI/bge-m3",
        embedding_device="cuda",
        batch_size=64,
        chunk_size=512,
        chunk_overlap=128,
        max_parallel_docs=8,
        description="For high-end GPUs. Maximum semantic depth and quality.",
        embedding_dimension=1024,
        max_tokens_per_chunk=8192,  # bge-m3 supports longer sequences
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
        """Convert to dictionary for ChromaDB metadata."""
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


def save_index_metadata(db_path: str, metadata: IndexMetadata) -> None:
    """
    Save index metadata to a JSON file alongside the database.

    Args:
        db_path: Path to the ChromaDB directory
        metadata: IndexMetadata to save
    """
    from pathlib import Path
    metadata_path = Path(db_path) / "index_metadata.json"
    with open(metadata_path, 'w') as f:
        json.dump(metadata.to_dict(), f, indent=2)


def load_index_metadata(db_path: str) -> Optional[IndexMetadata]:
    """
    Load index metadata from JSON file.

    Args:
        db_path: Path to the ChromaDB directory

    Returns:
        IndexMetadata if file exists, None otherwise
    """
    from pathlib import Path
    metadata_path = Path(db_path) / "index_metadata.json"

    if not metadata_path.exists():
        return None

    try:
        with open(metadata_path, 'r') as f:
            data = json.load(f)

        return IndexMetadata(
            archilles_version=data.get('archilles_version', 'unknown'),
            profile_name=data.get('profile_name', 'unknown'),
            embedding_model=data.get('embedding_model', 'unknown'),
            chunk_size=data.get('chunk_size', 0),
            chunk_overlap=data.get('chunk_overlap', 0),
            created_at=data.get('created_at', ''),
            hardware_gpu=data.get('hardware_gpu', 'unknown'),
            hardware_vram_gb=data.get('hardware_vram_gb', 0.0),
            hardware_ram_gb=data.get('hardware_ram_gb', 0.0)
        )
    except (json.JSONDecodeError, KeyError) as e:
        import logging
        logging.warning(f"Could not load index metadata: {e}")
        return None


def check_index_compatibility(db_path: str, current_profile: IndexingProfile) -> Dict[str, Any]:
    """
    Check if existing index is compatible with current profile.

    Returns compatibility info and warnings.

    Args:
        db_path: Path to the ChromaDB directory
        current_profile: Profile we want to use now

    Returns:
        Dict with 'compatible' (bool), 'warnings' (list), and 'existing_metadata' (if any)
    """
    from pathlib import Path

    result = {
        'compatible': True,
        'warnings': [],
        'existing_metadata': None
    }

    existing = load_index_metadata(db_path)
    if not existing:
        # No existing metadata - this is a new index
        return result

    result['existing_metadata'] = existing

    # Check embedding model compatibility (CRITICAL - must match!)
    if existing.embedding_model != current_profile.embedding_model:
        result['compatible'] = False
        result['warnings'].append(
            f"INCOMPATIBLE: Index uses '{existing.embedding_model}' but "
            f"current profile uses '{current_profile.embedding_model}'. "
            f"Cannot mix embeddings from different models!"
        )

    # Check chunk size (warning only - can add to existing index)
    if existing.chunk_size != current_profile.chunk_size:
        result['warnings'].append(
            f"NOTICE: Index chunk size ({existing.chunk_size}) differs from "
            f"current profile ({current_profile.chunk_size}). New chunks will use new size."
        )

    # Check profile name
    if existing.profile_name != current_profile.name:
        result['warnings'].append(
            f"NOTICE: Index was created with '{existing.profile_name}' profile, "
            f"but current profile is '{current_profile.name}'."
        )

    return result


def print_index_info(db_path: str) -> None:
    """Print information about existing index."""
    from pathlib import Path

    existing = load_index_metadata(db_path)

    print()
    print("=" * 64)
    print("  INDEX METADATA")
    print("=" * 64)

    if not existing:
        print("  No metadata found (legacy index or new database)")
    else:
        print(f"  ARCHILLES Version: {existing.archilles_version}")
        print(f"  Profile:           {existing.profile_name}")
        print(f"  Embedding Model:   {existing.embedding_model}")
        print(f"  Chunk Size:        {existing.chunk_size} tokens")
        print(f"  Chunk Overlap:     {existing.chunk_overlap} tokens")
        print(f"  Created:           {existing.created_at[:19] if existing.created_at else 'unknown'}")
        print()
        print(f"  Hardware Snapshot:")
        print(f"    GPU:  {existing.hardware_gpu}")
        print(f"    VRAM: {existing.hardware_vram_gb:.1f} GB")
        print(f"    RAM:  {existing.hardware_ram_gb:.1f} GB")

    print("=" * 64)
    print()


# Quick test
if __name__ == "__main__":
    list_profiles()

    print("\nMinimal profile details:")
    p = get_profile("minimal")
    print(p.to_json())

    print("\nExample index metadata:")
    meta = IndexMetadata.from_profile(p, gpu="NVIDIA Quadro T1000", vram_gb=4.0, ram_gb=64.0)
    print(json.dumps(meta.to_dict(), indent=2))
