"""Concurrent initialization must wait, not report failure.

``_ensure_initialized`` had a lock-free fast path ``if self._init_attempted:
return False`` that cannot tell "a previous attempt failed" from "another
thread is initializing right now". With the preload thread warming sources
at server start, a search arriving during the (minutes-long) model load got
``False`` for that source and silently returned zero results — Cowork saw
``per_source_counts: archilles: 0`` while the small sources answered.
"""

import threading
import time

import pytest

import src.service.archilles_service as service_mod
from src.service.archilles_service import ArchillesService


class _BlockingRAG:
    """Stand-in for ArchillesRAG whose construction blocks on an event."""

    entered = threading.Event()
    release = threading.Event()

    def __init__(self, **kwargs):
        type(self).entered.set()
        assert type(self).release.wait(timeout=10), "test forgot to release"


@pytest.fixture(autouse=True)
def _fresh_events():
    _BlockingRAG.entered = threading.Event()
    _BlockingRAG.release = threading.Event()
    yield
    _BlockingRAG.release.set()  # never leave the worker thread hanging


def test_concurrent_ensure_initialized_waits_for_running_init(tmp_path, monkeypatch):
    import src.archilles.engine
    monkeypatch.setattr(src.archilles.engine, "ArchillesRAG", _BlockingRAG)

    svc = ArchillesService(db_path=str(tmp_path / "db"))

    preload = threading.Thread(target=svc._ensure_initialized, daemon=True)
    preload.start()
    assert _BlockingRAG.entered.wait(timeout=10), "init never started"

    # Second caller (the search) while the first is mid-initialization:
    # must block and then report success — not short-circuit to False.
    result = {}

    def _search_side():
        result["ok"] = svc._ensure_initialized()

    searcher = threading.Thread(target=_search_side, daemon=True)
    searcher.start()

    time.sleep(0.2)  # give the searcher time to (wrongly) short-circuit
    assert "ok" not in result, (
        "second caller returned during a running init instead of waiting"
    )

    _BlockingRAG.release.set()
    preload.join(timeout=10)
    searcher.join(timeout=10)

    assert result.get("ok") is True
    assert svc.is_initialized


def test_failed_init_still_short_circuits(tmp_path, monkeypatch):
    import src.archilles.engine

    class _BoomRAG:
        def __init__(self, **kwargs):
            raise RuntimeError("no model")

    monkeypatch.setattr(src.archilles.engine, "ArchillesRAG", _BoomRAG)

    svc = ArchillesService(db_path=str(tmp_path / "db"))
    assert svc._ensure_initialized() is False
    # After a genuinely failed attempt the fast negative answer remains.
    assert svc._ensure_initialized() is False
