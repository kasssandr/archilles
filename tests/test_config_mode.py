"""Tests for get_mode — the single user-facing Hardware-Tiers-V2 variable.

``mode`` lives in ``.archilles/config.json`` (auto/light/full-local/full-external)
and is consumed by ``plan()`` to derive the ExecutionPlan. The reader is lenient:
a missing/invalid value falls back to ``"auto"`` so a config typo never crashes
indexing (``plan()`` itself raises on a bad mode, so the reader must guard).

Etappe 3 of the Hardware-Tiers-V2 concept
(docs/internal/CONCEPT_2026-06-23_HARDWARE_TIERS_V2.md §7, §10.3).
"""

import json
from pathlib import Path

from src.archilles.config import DEFAULT_MODE, get_mode


def test_default_mode_is_auto():
    assert DEFAULT_MODE == "auto"


def test_none_library_returns_default():
    assert get_mode(None) == "auto"


def test_no_argument_returns_default():
    assert get_mode() == "auto"


def test_library_without_config_returns_default(tmp_path: Path):
    assert get_mode(tmp_path) == "auto"


def test_each_valid_mode_is_read(tmp_path: Path):
    archilles_dir = tmp_path / ".archilles"
    archilles_dir.mkdir()
    cfg = archilles_dir / "config.json"
    for mode in ("auto", "light", "full-local", "full-external"):
        cfg.write_text(json.dumps({"mode": mode}), encoding="utf-8")
        assert get_mode(tmp_path) == mode


def test_invalid_mode_falls_back_to_auto(tmp_path: Path):
    """A typo'd mode must not propagate to plan() (which would raise)."""
    archilles_dir = tmp_path / ".archilles"
    archilles_dir.mkdir()
    (archilles_dir / "config.json").write_text(
        json.dumps({"mode": "ful-locale"}), encoding="utf-8"
    )
    assert get_mode(tmp_path) == "auto"


def test_non_string_mode_falls_back_to_auto(tmp_path: Path):
    archilles_dir = tmp_path / ".archilles"
    archilles_dir.mkdir()
    (archilles_dir / "config.json").write_text(
        json.dumps({"mode": 123}), encoding="utf-8"
    )
    assert get_mode(tmp_path) == "auto"


def test_malformed_json_falls_back_to_auto(tmp_path: Path):
    archilles_dir = tmp_path / ".archilles"
    archilles_dir.mkdir()
    (archilles_dir / "config.json").write_text("{ not json", encoding="utf-8")
    assert get_mode(tmp_path) == "auto"
