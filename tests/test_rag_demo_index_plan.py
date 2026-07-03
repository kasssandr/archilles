"""Tests for `rag_demo.py index` resolving mode/plan (review 2026-07-03,
finding 1.3).

`index` used to build ArchillesRAG without an execution_plan, and
`hierarchical` came only from the `--hierarchical` flag. A user on a
full-local machine single-indexing a book got a flat book in an otherwise
hierarchical DB, since batch_index and the watchdog would have chosen
hierarchical via the same config. `_resolve_index_plan` wires the same
mode/plan resolution `batch_index.main()` uses (mode from config only — no
CLI --mode flag exists for `index`, that's `embed`'s embedder mode).
"""

from scripts.rag_demo import _resolve_index_plan
from src.archilles.hardware import HardwareProfile


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


class TestResolveIndexPlan:
    def test_full_local_mode_yields_hierarchical_plan(self, monkeypatch):
        monkeypatch.setattr("scripts.rag_demo.get_mode", lambda library_path: "full-local")
        monkeypatch.setattr(
            "src.archilles.hardware.detect_hardware", lambda: _caps(cuda=True, vram_gb=24)
        )

        execution_plan, hierarchical = _resolve_index_plan(None, False, None)

        assert execution_plan is not None
        assert execution_plan.mode == "full-local"
        assert hierarchical is True

    def test_light_mode_forces_flat_without_hierarchical_flag(self, monkeypatch):
        monkeypatch.setattr("scripts.rag_demo.get_mode", lambda library_path: "light")
        monkeypatch.setattr(
            "src.archilles.hardware.detect_hardware", lambda: _caps(cuda=True, vram_gb=24)
        )

        execution_plan, hierarchical = _resolve_index_plan(None, False, None)

        assert execution_plan is not None
        assert execution_plan.mode == "light"
        assert hierarchical is False

    def test_hierarchical_flag_force_enables_under_light_mode(self, monkeypatch):
        # --hierarchical is a force-on: it can turn a flat mode hierarchical,
        # never the reverse.
        monkeypatch.setattr("scripts.rag_demo.get_mode", lambda library_path: "light")
        monkeypatch.setattr(
            "src.archilles.hardware.detect_hardware", lambda: _caps(cuda=True, vram_gb=24)
        )

        execution_plan, hierarchical = _resolve_index_plan(None, True, None)

        assert hierarchical is True

    def test_profile_override_bypasses_plan_entirely(self, monkeypatch):
        # Legacy --profile path: no execution_plan, hierarchical follows the
        # flag only — mirrors resolve_indexing_plan's profile_override branch.
        monkeypatch.setattr("scripts.rag_demo.get_mode", lambda library_path: "full-local")
        monkeypatch.setattr(
            "src.archilles.hardware.detect_hardware", lambda: _caps(cuda=True, vram_gb=24)
        )

        execution_plan, hierarchical = _resolve_index_plan("minimal", False, None)

        assert execution_plan is None
        assert hierarchical is False
