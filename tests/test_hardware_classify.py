"""Tests for classify_hardware() — mapping a detected HardwareProfile to one of
the five internal hardware classes (Hardware-Tiers-V2 §4).

Pure logic over synthetic specs (§9): no real GPU required.
"""
from src.archilles.hardware import HardwareProfile, classify_hardware


def _profile(*, cuda=False, mps=False, vram_gb=None):
    """Build a synthetic HardwareProfile; only the accelerator fields matter
    for classification."""
    return HardwareProfile(
        cpu_cores=8,
        ram_gb=32.0,
        gpu_available=cuda or mps,
        gpu_name="synthetic",
        vram_gb=vram_gb,
        cuda_available=cuda,
        mps_available=mps,
    )


class TestClassifyHardware:
    def test_cpu_only(self):
        assert classify_hardware(_profile()) == "cpu-only"

    def test_apple_mps(self):
        assert classify_hardware(_profile(mps=True)) == "apple-mps"

    def test_gpu_small_below_8gb(self):
        assert classify_hardware(_profile(cuda=True, vram_gb=4)) == "gpu-small"

    def test_gpu_small_unknown_vram(self):
        """CUDA present but VRAM unknown is treated conservatively as small."""
        assert classify_hardware(_profile(cuda=True, vram_gb=None)) == "gpu-small"

    def test_gpu_mid_at_8gb_boundary(self):
        assert classify_hardware(_profile(cuda=True, vram_gb=8)) == "gpu-mid"

    def test_gpu_mid_below_16gb(self):
        assert classify_hardware(_profile(cuda=True, vram_gb=12)) == "gpu-mid"

    def test_gpu_large_at_16gb_boundary(self):
        assert classify_hardware(_profile(cuda=True, vram_gb=16)) == "gpu-large"

    def test_gpu_large_above_16gb(self):
        assert classify_hardware(_profile(cuda=True, vram_gb=24)) == "gpu-large"

    def test_just_below_8gb_is_small(self):
        assert classify_hardware(_profile(cuda=True, vram_gb=7.9)) == "gpu-small"

    def test_cuda_wins_over_mps_when_both_present(self):
        """A CUDA GPU is the primary accelerator even if MPS also reports true."""
        assert classify_hardware(
            _profile(cuda=True, mps=True, vram_gb=24)
        ) == "gpu-large"
