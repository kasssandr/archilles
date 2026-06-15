"""Tests for config-driven embedder selection (embed-prepared)."""

import json

import pytest

from src.archilles.config import get_embedder_config, resolve_embedder_settings


def _write_config(tmp_path, payload: dict):
    cfg_dir = tmp_path / ".archilles"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "config.json").write_text(json.dumps(payload), encoding="utf-8")
    return tmp_path


# ── get_embedder_config ──────────────────────────────────────────────

def test_get_embedder_config_full_block(tmp_path):
    lib = _write_config(tmp_path, {"embedder": {"mode": "remote", "host": "http://gpu:8900"}})
    assert get_embedder_config(lib) == {"mode": "remote", "host": "http://gpu:8900"}


def test_get_embedder_config_no_block(tmp_path):
    lib = _write_config(tmp_path, {"rag_db_path": "x"})
    assert get_embedder_config(lib) == {}


def test_get_embedder_config_no_file(tmp_path):
    assert get_embedder_config(tmp_path) == {}


def test_get_embedder_config_none_library():
    assert get_embedder_config(None) == {}


def test_get_embedder_config_malformed_json(tmp_path):
    cfg_dir = tmp_path / ".archilles"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "config.json").write_text("{ not json", encoding="utf-8")
    assert get_embedder_config(tmp_path) == {}


def test_get_embedder_config_block_not_object(tmp_path):
    lib = _write_config(tmp_path, {"embedder": "remote"})
    assert get_embedder_config(lib) == {}


# ── resolve_embedder_settings ────────────────────────────────────────

def test_resolve_all_defaults():
    out = resolve_embedder_settings({}, {})
    assert out == {
        "mode": "local", "host": None, "port": 8000,
        "token": None, "batch_size": 100, "use_gzip": True,
    }


def test_resolve_config_only():
    cfg = {"mode": "remote", "host": "http://gpu:8900", "port": 8900}
    out = resolve_embedder_settings({}, cfg)
    assert out["mode"] == "remote"
    assert out["host"] == "http://gpu:8900"
    assert out["port"] == 8900
    assert out["batch_size"] == 100  # default fills the gap


def test_resolve_cli_overrides_config():
    cli = {"mode": "local", "host": None, "port": None,
           "token": None, "batch_size": None, "use_gzip": None}
    cfg = {"mode": "remote", "host": "http://gpu:8900"}
    out = resolve_embedder_settings(cli, cfg)
    assert out["mode"] == "local"            # CLI wins
    assert out["host"] == "http://gpu:8900"  # config fills where CLI is None


def test_resolve_gzip_no_gzip_cli_wins():
    out = resolve_embedder_settings({"use_gzip": False}, {"use_gzip": True})
    assert out["use_gzip"] is False


def test_resolve_gzip_from_config():
    out = resolve_embedder_settings({"use_gzip": None}, {"use_gzip": False})
    assert out["use_gzip"] is False


def test_resolve_invalid_mode_raises():
    with pytest.raises(ValueError):
        resolve_embedder_settings({}, {"mode": "remot"})
