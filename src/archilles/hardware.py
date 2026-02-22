"""
ARCHILLES Hardware Detection

Automatically detects system hardware capabilities to recommend
appropriate indexing profiles.

Reference hardware (ThinkPad P15 Gen 1):
- CPU: Intel Core i7-10750H (6 cores)
- RAM: 64 GB
- GPU: NVIDIA Quadro T1000 (4 GB VRAM)
- Recommended profile: "minimal" (due to limited VRAM)
"""

from dataclasses import dataclass
from typing import Optional, Literal
import logging

logger = logging.getLogger(__name__)

ProfileName = Literal["minimal", "balanced", "maximal"]


@dataclass
class HardwareProfile:
    """Detected hardware capabilities."""

    cpu_cores: int
    ram_gb: float
    gpu_available: bool
    gpu_name: Optional[str]
    vram_gb: Optional[float]
    cuda_available: bool

    def recommend_profile(self) -> ProfileName:
        """
        Recommend an indexing profile based on detected hardware.

        All profiles use BGE-M3 (same quality!) - only batch_size differs:
        - < 8 GB VRAM -> "minimal" (batch_size=8, ~2 min/book)
        - 8-16 GB VRAM -> "balanced" (batch_size=32, ~30s/book)
        - > 16 GB VRAM -> "maximal" (batch_size=64, ~15s/book)

        Returns:
            Recommended profile name
        """
        if not self.cuda_available:
            logger.info("No CUDA available - recommending 'minimal' profile (will use CPU)")
            return "minimal"

        if self.vram_gb is None or self.vram_gb < 8:
            logger.info(
                f"VRAM ({self.vram_gb or 0:.1f} GB) - recommending 'minimal' profile (batch_size=8)"
            )
            return "minimal"

        if self.vram_gb >= 16:
            logger.info(
                f"High VRAM ({self.vram_gb:.1f} GB) - recommending 'maximal' profile (batch_size=64)"
            )
            return "maximal"

        logger.info(
            f"Moderate VRAM ({self.vram_gb:.1f} GB) - recommending 'balanced' profile (batch_size=32)"
        )
        return "balanced"

    def summary(self) -> str:
        """Generate a human-readable hardware summary."""
        lines = [
            f"CPU: {self.cpu_cores} cores",
            f"RAM: {self.ram_gb:.1f} GB",
        ]

        if self.gpu_available and self.gpu_name:
            vram_str = f"{self.vram_gb:.1f} GB" if self.vram_gb else "unknown"
            lines.append(f"GPU: {self.gpu_name} ({vram_str} VRAM)")
            lines.append(f"CUDA: {'available' if self.cuda_available else 'not available'}")
        else:
            lines.append("GPU: not detected")

        return "\n".join(lines)


def detect_hardware() -> HardwareProfile:
    """
    Detect available hardware capabilities.

    Returns:
        HardwareProfile with detected capabilities
    """
    cpu_cores = _get_cpu_cores()
    ram_gb = _get_ram_gb()
    gpu_available, gpu_name, vram_gb, cuda_available = _get_gpu_info()

    profile = HardwareProfile(
        cpu_cores=cpu_cores,
        ram_gb=ram_gb,
        gpu_available=gpu_available,
        gpu_name=gpu_name,
        vram_gb=vram_gb,
        cuda_available=cuda_available,
    )

    logger.info(f"Detected hardware:\n{profile.summary()}")
    return profile


def _get_cpu_cores() -> int:
    """Get number of physical CPU cores."""
    try:
        import psutil
        cores = psutil.cpu_count(logical=False)
        return cores if cores else 1
    except ImportError:
        logger.warning("psutil not available, using os.cpu_count()")
        import os
        cores = os.cpu_count()
        # Estimate physical cores as half of logical cores
        return max(1, (cores or 2) // 2)


def _get_ram_gb() -> float:
    """Get total system RAM in GB."""
    try:
        import psutil
        return psutil.virtual_memory().total / (1024 ** 3)
    except ImportError:
        logger.warning("psutil not available, cannot detect RAM")
        return 8.0  # Conservative default


def _get_gpu_info() -> tuple[bool, Optional[str], Optional[float], bool]:
    """
    Get GPU information.

    Returns:
        Tuple of (gpu_available, gpu_name, vram_gb, cuda_available)
    """
    try:
        import torch

        if not torch.cuda.is_available():
            return False, None, None, False

        gpu_name = torch.cuda.get_device_name(0)
        vram_bytes = torch.cuda.get_device_properties(0).total_memory
        vram_gb = vram_bytes / (1024 ** 3)

        return True, gpu_name, vram_gb, True

    except ImportError:
        logger.warning("PyTorch not available, cannot detect GPU")
        return False, None, None, False
    except Exception as e:
        logger.warning(f"Error detecting GPU: {e}")
        return False, None, None, False


def _print_hardware_header(profile: HardwareProfile, recommended: ProfileName) -> None:
    """Print the common hardware-detection banner used by display functions."""
    print()
    print("=" * 64)
    print("  ARCHILLES - Hardware Detection")
    print("=" * 64)
    print()
    print("  Detected Hardware:")
    print(f"    CPU: {profile.cpu_cores} cores")
    print(f"    RAM: {profile.ram_gb:.1f} GB")

    if profile.gpu_available and profile.gpu_name:
        vram_str = f"{profile.vram_gb:.1f} GB" if profile.vram_gb else "unknown"
        print(f"    GPU: {profile.gpu_name} ({vram_str})")
        print(f"    CUDA: {'available' if profile.cuda_available else 'not available'}")
    else:
        print("    GPU: not detected")

    print()
    print(f"  Recommended Profile: {recommended.upper()}")


def print_hardware_detection(profile: Optional[HardwareProfile] = None) -> HardwareProfile:
    """
    Print hardware detection results in a formatted box.

    Args:
        profile: Optional pre-detected profile, will detect if not provided

    Returns:
        The hardware profile (detected or provided)
    """
    if profile is None:
        profile = detect_hardware()

    recommended = profile.recommend_profile()
    _print_hardware_header(profile, recommended)

    print()
    print("=" * 64)
    print()

    return profile


_PROFILE_DESCRIPTIONS = {
    "minimal": "Fast & resource-efficient (CPU-optimized)",
    "balanced": "Good balance of speed and quality",
    "maximal": "Maximum quality (requires strong GPU)",
}

_PROFILE_OPTIONS = ["minimal", "balanced", "maximal"]


def select_profile_interactive(profile: Optional[HardwareProfile] = None) -> str:
    """
    Interactive profile selection with hardware-based recommendation.

    Args:
        profile: Optional pre-detected profile, will detect if not provided

    Returns:
        Selected profile name ("minimal", "balanced", or "maximal")
    """
    if profile is None:
        profile = detect_hardware()

    recommended = profile.recommend_profile()
    _print_hardware_header(profile, recommended)

    print()
    print("-" * 64)
    print()
    print("  Select a profile:")
    print()

    for i, opt in enumerate(_PROFILE_OPTIONS, 1):
        rec_marker = " <- recommended" if opt == recommended else ""
        print(f"    [{i}] {opt.upper()}: {_PROFILE_DESCRIPTIONS[opt]}{rec_marker}")

    print()
    print("=" * 64)
    print()

    default_index = _PROFILE_OPTIONS.index(recommended) + 1

    while True:
        try:
            choice = input(f"Choose profile [1-3, default={default_index}]: ").strip()

            if choice == "":
                return recommended

            if choice in ("1", "2", "3"):
                return _PROFILE_OPTIONS[int(choice) - 1]

            if choice.lower() in _PROFILE_OPTIONS:
                return choice.lower()

            print("  Invalid choice. Enter 1, 2, or 3.")

        except (EOFError, KeyboardInterrupt):
            print(f"\n  Using recommended profile: {recommended}")
            return recommended


# Quick test
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    hw = detect_hardware()
    print(f"\nHardware Summary:\n{hw.summary()}")
    print(f"\nRecommended Profile: {hw.recommend_profile()}")
