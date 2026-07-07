"""
ARCHILLES Hardware Detection

Automatically detects system hardware capabilities to recommend
appropriate indexing profiles.

Supported accelerators:
- NVIDIA CUDA (Windows/Linux): full support, all profiles available
- Apple MPS / Metal (macOS Apple Silicon): supported, "minimal" profile recommended
- CPU fallback: always available, "minimal" profile
"""

from dataclasses import dataclass
from functools import lru_cache
from typing import Optional, Literal
import logging

logger = logging.getLogger(__name__)

# Internal hardware classes (Hardware-Tiers-V2 §4). These are detected
# automatically and drive plan(); they are NOT part of the user-facing
# vocabulary (which is auto/light/full-local/full-external).
HardwareClass = Literal["cpu-only", "apple-mps", "gpu-small", "gpu-mid", "gpu-large"]

# VRAM thresholds (GB): BGE-M3 (~2.5 GB) + bge-reranker-v2-m3 (~2.5 GB) +
# activations peak at ~6–7 GB when run together, so 8 GB is the comfortable
# floor for local GPU embedding + GPU reranking; ≥16 GB leaves room for large
# batches.
_VRAM_GPU_MID_MIN = 8
_VRAM_GPU_LARGE_MIN = 16


@dataclass
class HardwareProfile:
    """Detected hardware capabilities."""

    cpu_cores: int
    ram_gb: float
    gpu_available: bool
    gpu_name: Optional[str]
    vram_gb: Optional[float]
    cuda_available: bool
    mps_available: bool = False  # Apple Silicon Metal Performance Shaders

    def summary(self) -> str:
        """Generate a human-readable hardware summary."""
        lines = [
            f"CPU: {self.cpu_cores} cores",
            f"RAM: {self.ram_gb:.1f} GB",
        ]

        if self.mps_available:
            lines.append("GPU: Apple MPS (Metal Performance Shaders)")
        elif self.gpu_available and self.gpu_name:
            vram_str = f"{self.vram_gb:.1f} GB" if self.vram_gb else "unknown"
            lines.append(f"GPU: {self.gpu_name} ({vram_str} VRAM)")
            lines.append(f"CUDA: {'available' if self.cuda_available else 'not available'}")
        else:
            lines.append("GPU: not detected (CPU-only mode)")

        return "\n".join(lines)


@lru_cache(maxsize=1)
def detect_hardware() -> HardwareProfile:
    """
    Detect available hardware capabilities.

    Returns:
        HardwareProfile with detected capabilities
    """
    cpu_cores = _get_cpu_cores()
    ram_gb = _get_ram_gb()
    gpu_available, gpu_name, vram_gb, cuda_available = _get_gpu_info()
    mps_available = _is_mps_available()

    # If MPS is available but CUDA isn't, fill in GPU info from MPS
    if mps_available and not gpu_available:
        gpu_available = True
        gpu_name = "Apple MPS"

    profile = HardwareProfile(
        cpu_cores=cpu_cores,
        ram_gb=ram_gb,
        gpu_available=gpu_available,
        gpu_name=gpu_name,
        vram_gb=vram_gb,
        cuda_available=cuda_available,
        mps_available=mps_available,
    )

    logger.info(f"Detected hardware:\n{profile.summary()}")
    return profile


def classify_hardware(profile: HardwareProfile) -> HardwareClass:
    """Map a detected HardwareProfile to one of the five internal classes (§4).

    CUDA is the primary accelerator: a CUDA GPU classifies by VRAM regardless of
    MPS. Without CUDA, MPS yields ``apple-mps``; otherwise ``cpu-only``. Unknown
    VRAM on a CUDA GPU is treated conservatively as ``gpu-small``.

    This is a pure function — testable with synthetic specs, no real GPU needed.
    """
    if profile.cuda_available:
        vram = profile.vram_gb
        if vram is None or vram < _VRAM_GPU_MID_MIN:
            return "gpu-small"
        if vram < _VRAM_GPU_LARGE_MIN:
            return "gpu-mid"
        return "gpu-large"
    if profile.mps_available:
        return "apple-mps"
    return "cpu-only"


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


def _is_mps_available() -> bool:
    """Check if Apple MPS (Metal Performance Shaders) is available."""
    try:
        import torch
        return torch.backends.mps.is_available()
    except (ImportError, AttributeError):
        return False


def get_best_device() -> str:
    """
    Return the best available compute device string for sentence-transformers.

    Priority: CUDA (NVIDIA) > MPS (Apple Silicon) > CPU

    Returns:
        "cuda", "mps", or "cpu"
    """
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda"
        if torch.backends.mps.is_available():
            return "mps"
    except (ImportError, AttributeError):
        pass
    return "cpu"


# Quick test
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    hw = detect_hardware()
    print(f"\nHardware Summary:\n{hw.summary()}")
    print(f"\nHardware Class: {classify_hardware(hw)}")
