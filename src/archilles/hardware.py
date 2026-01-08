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

        Decision logic:
        - No CUDA or < 6 GB VRAM -> "minimal" (CPU-only, resource-efficient)
        - 6-12 GB VRAM -> "balanced" (GPU-accelerated, good quality)
        - > 12 GB VRAM -> "maximal" (full GPU, maximum quality)

        Returns:
            Recommended profile name
        """
        if not self.cuda_available:
            logger.info("No CUDA available - recommending 'minimal' profile")
            return "minimal"

        if self.vram_gb is None or self.vram_gb < 6:
            logger.info(
                f"Limited VRAM ({self.vram_gb or 0:.1f} GB) - recommending 'minimal' profile"
            )
            return "minimal"

        if self.vram_gb >= 12:
            logger.info(
                f"High VRAM ({self.vram_gb:.1f} GB) - recommending 'maximal' profile"
            )
            return "maximal"

        logger.info(
            f"Moderate VRAM ({self.vram_gb:.1f} GB) - recommending 'balanced' profile"
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
    # Get CPU cores
    cpu_cores = _get_cpu_cores()

    # Get RAM
    ram_gb = _get_ram_gb()

    # Get GPU info
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

    # Build the display
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
    print()
    print("=" * 64)
    print()

    return profile


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

    # Map recommendations to display
    profile_descriptions = {
        "minimal": "Fast & resource-efficient (CPU-optimized)",
        "balanced": "Good balance of speed and quality",
        "maximal": "Maximum quality (requires strong GPU)",
    }

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
    else:
        print("    GPU: not detected")

    print()
    print(f"  Recommended: {recommended.upper()}")
    print()
    print("-" * 64)
    print()
    print("  Select a profile:")
    print()

    options = ["minimal", "balanced", "maximal"]
    for i, opt in enumerate(options, 1):
        rec_marker = " <- recommended" if opt == recommended else ""
        print(f"    [{i}] {opt.upper()}: {profile_descriptions[opt]}{rec_marker}")

    print()
    print("=" * 64)
    print()

    while True:
        try:
            choice = input(f"Choose profile [1-3, default={options.index(recommended)+1}]: ").strip()

            if choice == "":
                return recommended

            if choice in ["1", "2", "3"]:
                return options[int(choice) - 1]

            if choice.lower() in options:
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
