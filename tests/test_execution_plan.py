"""Tests for plan() — deriving an ExecutionPlan from hardware capabilities, an
IndexRecipe and a mode (Hardware-Tiers-V2 §3, §4, §9).

plan() is a pure function: the whole multi-tier decision logic is unit-testable
with synthetic specs, even though only gpu-small is physically available.

Layering reminder: the recipe (identity + chunk schema) never varies; the plan
(batch/device, local-vs-external, reranking) varies by machine and mode.
"""
import pytest

from src.archilles.hardware import HardwareProfile
from src.archilles.recipe import IndexRecipe, default_recipe
from src.archilles.execution import plan

R = default_recipe()


def _caps(*, cuda=False, mps=False, vram_gb=None):
    return HardwareProfile(
        cpu_cores=8,
        ram_gb=32.0,
        gpu_available=cuda or mps,
        gpu_name="synthetic",
        vram_gb=vram_gb,
        cuda_available=cuda,
        mps_available=mps,
    )


class TestPlanAutoOnCapableHardware:
    def test_gpu_large_auto_is_full_local_batch_64_rerank_cuda(self):
        p = plan(_caps(cuda=True, vram_gb=24), R)
        assert p.hardware_class == "gpu-large"
        assert p.mode == "full-local"
        assert p.batch_size == 64
        assert p.embedding_device == "cuda"
        assert p.rerank_device == "cuda"
        assert p.embed_local is True
        assert p.hierarchical is True

    def test_gpu_mid_auto_is_full_local_batch_32_rerank_cuda(self):
        p = plan(_caps(cuda=True, vram_gb=12), R)
        assert p.hardware_class == "gpu-mid"
        assert p.mode == "full-local"
        assert p.batch_size == 32
        assert p.rerank_device == "cuda"
        assert p.embed_local is True
        assert p.hierarchical is True

    def test_apple_mps_auto_is_full_local_device_mps_rerank_cpu(self):
        p = plan(_caps(mps=True), R)
        assert p.hardware_class == "apple-mps"
        assert p.mode == "full-local"
        assert p.embedding_device == "mps"
        assert p.rerank_device == "cpu"
        assert p.batch_size == 16
        assert p.embed_local is True
        assert p.hierarchical is True


class TestPlanAutoOnWeakHardwareIsLight:
    def test_gpu_small_auto_is_light_flat_local(self):
        p = plan(_caps(cuda=True, vram_gb=4), R)
        assert p.hardware_class == "gpu-small"
        assert p.mode == "light"
        assert p.hierarchical is False
        assert p.embed_local is True
        assert p.embedding_device == "cuda"
        assert p.batch_size == 8
        assert p.rerank_device == "cpu"

    def test_cpu_only_auto_is_light_flat_local(self):
        p = plan(_caps(), R)
        assert p.hardware_class == "cpu-only"
        assert p.mode == "light"
        assert p.hierarchical is False
        assert p.embed_local is True
        assert p.embedding_device == "cpu"
        assert p.batch_size == 8
        assert p.rerank_device == "cpu"


class TestExplicitModesOverrideAuto:
    def test_gpu_small_full_external_embeds_externally(self):
        """The §9 'embed_local=False for vram=4' case: opt-in full quality."""
        p = plan(_caps(cuda=True, vram_gb=4), R, mode="full-external")
        assert p.mode == "full-external"
        assert p.embed_local is False
        assert p.hierarchical is True
        assert p.rerank_device == "cpu"
        assert p.batch_size == 8

    def test_gpu_large_light_forces_flat(self):
        p = plan(_caps(cuda=True, vram_gb=24), R, mode="light")
        assert p.mode == "light"
        assert p.hierarchical is False
        assert p.embed_local is True
        assert p.batch_size == 64

    def test_gpu_small_full_local_is_allowed_but_slow(self):
        p = plan(_caps(cuda=True, vram_gb=4), R, mode="full-local")
        assert p.mode == "full-local"
        assert p.hierarchical is True
        assert p.embed_local is True
        assert p.batch_size == 8


class TestRecipeAndReranking:
    def test_full_local_honours_a_flat_recipe(self):
        flat = IndexRecipe(hierarchical=False)
        p = plan(_caps(cuda=True, vram_gb=24), flat, mode="full-local")
        assert p.hierarchical is False

    def test_reranking_is_enabled_everywhere(self):
        for caps in (_caps(), _caps(mps=True), _caps(cuda=True, vram_gb=24)):
            assert plan(caps, R).rerank_enabled is True

    def test_invalid_mode_raises(self):
        with pytest.raises(ValueError):
            plan(_caps(), R, mode="bogus")

    def test_plan_is_immutable(self):
        import dataclasses

        p = plan(_caps(), R)
        with pytest.raises(dataclasses.FrozenInstanceError):
            p.batch_size = 1  # type: ignore[misc]
