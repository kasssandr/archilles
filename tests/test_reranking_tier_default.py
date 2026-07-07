"""Hardware-tier default for cross-encoder reranking.

The CPU reranker is the main driver of multi-minute MCP searches, while on
a mid/large GPU it is fast and improves quality. When the user does not set
``enable_reranking`` anywhere, the default is now derived from the detected
hardware class instead of a flat ``False``/``True``. An explicit config
value (master, per-source, or library-local) always wins.
"""

import json

import pytest

import src.archilles.hardware as hardware
from src.archilles.config import (
    MasterConfig,
    SourceConfig,
    load_master_config,
    resolve_enable_reranking,
    resolve_source_config,
)
from src.archilles.hardware import HardwareProfile, default_enable_reranking


def _profile(cuda: bool, vram: float | None) -> HardwareProfile:
    return HardwareProfile(
        cpu_cores=8,
        ram_gb=32.0,
        gpu_available=cuda,
        gpu_name="Test GPU" if cuda else None,
        vram_gb=vram,
        cuda_available=cuda,
    )


class TestDefaultEnableReranking:
    @pytest.mark.parametrize(
        "hardware_class,expected",
        [
            ("cpu-only", False),
            ("apple-mps", False),
            ("gpu-small", False),
            ("gpu-mid", True),
            ("gpu-large", True),
        ],
    )
    def test_per_class(self, hardware_class, expected):
        assert default_enable_reranking(hardware_class) is expected


class TestResolveEnableReranking:
    def test_explicit_value_wins_without_hardware_detection(self, monkeypatch):
        def _boom():
            raise AssertionError("hardware detection must not run")

        monkeypatch.setattr(hardware, "detect_hardware", _boom)

        assert resolve_enable_reranking(True) is True
        assert resolve_enable_reranking(False) is False

    def test_none_derives_from_hardware_class(self, monkeypatch):
        monkeypatch.setattr(
            hardware, "detect_hardware", lambda: _profile(cuda=True, vram=16.0)
        )
        assert resolve_enable_reranking(None) is True

        monkeypatch.setattr(
            hardware, "detect_hardware", lambda: _profile(cuda=False, vram=None)
        )
        assert resolve_enable_reranking(None) is False


class TestResolveSourceConfigTierDefault:
    def _master(self, tmp_path, **master_kwargs):
        return MasterConfig(
            sources=[SourceConfig(name="lib", library_path=tmp_path)],
            **master_kwargs,
        )

    def test_unset_everywhere_uses_tier_default(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            hardware, "detect_hardware", lambda: _profile(cuda=True, vram=16.0)
        )
        cfg = resolve_source_config(self._master(tmp_path), "lib")
        assert cfg["enable_reranking"] is True

        monkeypatch.setattr(
            hardware, "detect_hardware", lambda: _profile(cuda=False, vram=None)
        )
        cfg = resolve_source_config(self._master(tmp_path), "lib")
        assert cfg["enable_reranking"] is False

    def test_explicit_master_false_beats_gpu_tier(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            hardware, "detect_hardware", lambda: _profile(cuda=True, vram=16.0)
        )
        cfg = resolve_source_config(
            self._master(tmp_path, enable_reranking=False), "lib"
        )
        assert cfg["enable_reranking"] is False

    def test_library_local_override_beats_tier(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            hardware, "detect_hardware", lambda: _profile(cuda=True, vram=16.0)
        )
        archilles_dir = tmp_path / ".archilles"
        archilles_dir.mkdir()
        (archilles_dir / "config.json").write_text(
            json.dumps({"enable_reranking": False}), encoding="utf-8"
        )

        cfg = resolve_source_config(self._master(tmp_path), "lib")
        assert cfg["enable_reranking"] is False


class TestMasterConfigParsing:
    def test_absent_enable_reranking_stays_none(self, tmp_path):
        path = tmp_path / "config.json"
        path.write_text(
            json.dumps(
                {"sources": [{"name": "lib", "library_path": str(tmp_path)}]}
            ),
            encoding="utf-8",
        )
        master = load_master_config(path)
        assert master.enable_reranking is None

    def test_explicit_enable_reranking_parses_to_bool(self, tmp_path):
        path = tmp_path / "config.json"
        path.write_text(
            json.dumps(
                {
                    "sources": [{"name": "lib", "library_path": str(tmp_path)}],
                    "enable_reranking": True,
                }
            ),
            encoding="utf-8",
        )
        master = load_master_config(path)
        assert master.enable_reranking is True
