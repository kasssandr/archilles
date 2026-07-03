"""Tests for the Hardware-Tiers-V2 mode wiring in batch_index (Etappe 3).

``resolve_indexing_plan`` is the pure decision seam between the CLI/config and
the ExecutionPlan: it picks the mode source (CLI over config), honours the legacy
``--profile`` override, derives the effective ``hierarchical`` (the ``--hierarchical``
flag is an advanced force-on), and turns ``full-external`` into prepare-only on the
index path (``index_book`` always embeds locally, so external embedding must go
through the two-phase prepare/embed flow — §8 sweet spot).

detect_hardware()/get_mode() do the I/O; this function is pure (hardware + recipe
injected), so the whole resolution is unit-testable without real hardware (§9).
"""
import dataclasses

import pytest

from src.archilles.hardware import HardwareProfile
from src.archilles.recipe import default_recipe
from scripts.batch_index import build_parser, resolve_indexing_plan

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


def _resolve(**kw):
    base = dict(
        mode_cli=None,
        mode_config="auto",
        profile_override=None,
        hierarchical_flag=False,
        prepare_only_flag=False,
        hw=_caps(),
        recipe=R,
    )
    base.update(kw)
    return resolve_indexing_plan(**base)


class TestModeSource:
    def test_cli_mode_overrides_config(self):
        res = _resolve(mode_cli="light", mode_config="full-local",
                       hw=_caps(cuda=True, vram_gb=24))
        assert res.resolved_mode == "light"
        assert res.execution_plan.mode == "light"

    def test_config_mode_used_when_no_cli(self):
        res = _resolve(mode_cli=None, mode_config="full-local",
                       hw=_caps(cuda=True, vram_gb=24))
        assert res.resolved_mode == "full-local"


class TestAutoResolution:
    def test_auto_weak_hardware_is_light_flat(self):
        res = _resolve(hw=_caps())  # cpu-only
        assert res.profile_name is None
        assert res.execution_plan.mode == "light"
        assert res.hierarchical is False
        assert res.prepare_only is False

    def test_auto_capable_hardware_is_full_local_hierarchical(self):
        res = _resolve(hw=_caps(cuda=True, vram_gb=24))
        assert res.execution_plan.mode == "full-local"
        assert res.hierarchical is True
        assert res.prepare_only is False


class TestHierarchicalFlagForcesOn:
    def test_flag_forces_hierarchical_even_under_light(self):
        """--hierarchical is an advanced override: it forces hierarchical on
        even when the resolved mode (light) would otherwise be flat."""
        res = _resolve(mode_cli="light", hierarchical_flag=True,
                       hw=_caps(cuda=True, vram_gb=24))
        assert res.execution_plan.hierarchical is False  # plan stays flat
        assert res.hierarchical is True                   # effective is forced on


class TestFullExternalForcesPrepareOnly:
    def test_full_external_forces_prepare_only(self):
        res = _resolve(mode_cli="full-external", hw=_caps(cuda=True, vram_gb=4))
        assert res.execution_plan.embed_local is False
        assert res.prepare_only is True
        assert res.hierarchical is True

    def test_explicit_prepare_only_flag_passes_through(self):
        res = _resolve(prepare_only_flag=True, hw=_caps(cuda=True, vram_gb=24))
        assert res.prepare_only is True


class TestProfileOverride:
    def test_profile_override_bypasses_plan(self):
        res = _resolve(profile_override="balanced", mode_config="full-local")
        assert res.profile_name == "balanced"
        assert res.execution_plan is None
        assert res.resolved_mode is None

    def test_profile_override_keeps_hierarchical_flag(self):
        res = _resolve(profile_override="maximal", hierarchical_flag=True)
        assert res.hierarchical is True
        res2 = _resolve(profile_override="maximal", hierarchical_flag=False)
        assert res2.hierarchical is False


class TestResolutionIsImmutable:
    def test_resolution_is_frozen(self):
        res = _resolve()
        with pytest.raises(dataclasses.FrozenInstanceError):
            res.prepare_only = True  # type: ignore[misc]


class TestModeCliArgument:
    def test_mode_arg_defaults_to_none(self):
        args = build_parser().parse_args(["--all"])
        assert args.mode is None

    def test_mode_arg_accepts_valid_modes(self):
        for mode in ("auto", "light", "full-local", "full-external"):
            args = build_parser().parse_args(["--all", "--mode", mode])
            assert args.mode == mode

    def test_mode_arg_rejects_invalid(self):
        with pytest.raises(SystemExit):
            build_parser().parse_args(["--all", "--mode", "bogus"])
