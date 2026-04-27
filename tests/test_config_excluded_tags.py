"""Tests for get_excluded_tags fallback semantics."""

import json
import os
from pathlib import Path

import pytest

from src.archilles.config import (
    DEFAULT_EXCLUDED_TAGS,
    get_excluded_tags,
)


def test_none_library_returns_defaults_without_sys_exit():
    """``get_excluded_tags(None)`` must not call ``get_library_path()`` (which
    would ``sys.exit(1)`` if no env var is set, killing the interpreter via
    ``BaseException`` and bypassing ``except Exception`` clauses in callers).

    Regression for ``find_scanned.py`` module-import crash.
    """
    result = get_excluded_tags(None)
    assert result == list(DEFAULT_EXCLUDED_TAGS)
    assert result == ['exclude']


def test_no_argument_returns_defaults():
    """Calling without any argument also returns defaults (does not consult env)."""
    # Even if env vars are set, the function should not try to read them when
    # the caller passes no library_path argument.
    result = get_excluded_tags()
    assert result == list(DEFAULT_EXCLUDED_TAGS)


def test_library_without_config_returns_defaults(tmp_path: Path):
    """A library directory with no .archilles/config.json yields defaults."""
    assert get_excluded_tags(tmp_path) == list(DEFAULT_EXCLUDED_TAGS)


def test_library_with_config_returns_custom_list(tmp_path: Path):
    """``excluded_tags`` in config.json overrides the defaults."""
    archilles_dir = tmp_path / ".archilles"
    archilles_dir.mkdir()
    (archilles_dir / "config.json").write_text(
        json.dumps({"excluded_tags": ["exclude", "draft", "Übersetzung"]}),
        encoding="utf-8",
    )
    assert get_excluded_tags(tmp_path) == ["exclude", "draft", "Übersetzung"]


def test_library_with_non_list_config_falls_back(tmp_path: Path):
    """A malformed config (not a list) falls back to defaults instead of crashing."""
    archilles_dir = tmp_path / ".archilles"
    archilles_dir.mkdir()
    (archilles_dir / "config.json").write_text(
        json.dumps({"excluded_tags": "not-a-list"}),
        encoding="utf-8",
    )
    assert get_excluded_tags(tmp_path) == list(DEFAULT_EXCLUDED_TAGS)


def test_returns_fresh_list_each_call(tmp_path: Path):
    """Mutating the returned list must not poison the global default."""
    a = get_excluded_tags(None)
    a.append("custom")
    b = get_excluded_tags(None)
    assert "custom" not in b
    assert b == list(DEFAULT_EXCLUDED_TAGS)


def test_find_scanned_imports_without_env(monkeypatch):
    """Module import must succeed when no library env var is set.

    Regression for bug_003: ``try/except Exception`` cannot catch
    ``SystemExit`` (a ``BaseException``), so the previous fallback was dead
    code and any import without env vars killed the interpreter.
    """
    for var in ("ARCHILLES_LIBRARY_PATH", "CALIBRE_LIBRARY_PATH", "CALIBRE_LIBRARY"):
        monkeypatch.delenv(var, raising=False)

    # Force a fresh import — clear any cached module first
    import sys
    sys.modules.pop("scripts.find_scanned", None)

    import scripts.find_scanned as fs
    assert fs.INTENTIONALLY_EXCLUDED_TAGS == {"exclude"}
