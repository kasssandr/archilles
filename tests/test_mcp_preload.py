"""Model preload at MCP server start.

MCP clients built on Claude Code abort tool calls after 60 s
(``MCP error -32001``). A cold first search used to trigger the lazy
BGE-M3/reranker load inside that window (2-6 min on CPU), so every
semantic search timed out. The server therefore warms the RAG stack in a
background daemon thread right after startup, before the first call.
"""

import json
import threading

import pytest

import mcp_server
from src.archilles.config import load_master_config
from src.calibre_mcp.server import CalibreMCPServer
from src.calibre_mcp.unified_server import UnifiedMCPServer


class _RecordingInnerServer:
    """Duck-typed stand-in for a CalibreMCPServer inside the unified server."""

    def __init__(self):
        self.preload_calls = 0

    def preload(self):
        self.preload_calls += 1


class TestCalibreServerPreload:
    def test_preload_initialises_rag_and_reranker(self, tmp_path, monkeypatch):
        server = CalibreMCPServer(
            library_path=str(tmp_path),
            rag_db_path=str(tmp_path / "rag_db"),
        )
        calls = []
        monkeypatch.setattr(
            server.service, "_ensure_initialized", lambda: calls.append("rag") or True
        )
        monkeypatch.setattr(
            server.service, "_get_reranker", lambda: calls.append("reranker")
        )

        server.preload()

        assert "rag" in calls
        assert "reranker" in calls

    def test_preload_survives_init_failure(self, tmp_path, monkeypatch):
        server = CalibreMCPServer(
            library_path=str(tmp_path),
            rag_db_path=str(tmp_path / "rag_db"),
        )

        def _boom():
            raise RuntimeError("model load failed")

        monkeypatch.setattr(server.service, "_ensure_initialized", _boom)

        server.preload()  # must not raise


class TestUnifiedServerPreload:
    def test_preload_reaches_every_source(self, tmp_path):
        inner = {"a": _RecordingInnerServer(), "b": _RecordingInnerServer()}
        server = UnifiedMCPServer(
            servers=inner, default_source="a", master_dir=tmp_path
        )

        server.preload()

        assert inner["a"].preload_calls == 1
        assert inner["b"].preload_calls == 1


class TestStartPreload:
    def test_disabled_returns_none(self):
        assert mcp_server._start_preload(_RecordingInnerServer(), enabled=False) is None

    def test_enabled_runs_preload_in_daemon_thread(self):
        stub = _RecordingInnerServer()

        thread = mcp_server._start_preload(stub, enabled=True)

        assert isinstance(thread, threading.Thread)
        assert thread.daemon
        thread.join(timeout=10)
        assert stub.preload_calls == 1


class TestPreloadConfig:
    def _write_master(self, tmp_path, extra):
        cfg = {
            "sources": [
                {"name": "lib", "library_path": str(tmp_path), "adapter": "folder"}
            ],
        }
        cfg.update(extra)
        path = tmp_path / "config.json"
        path.write_text(json.dumps(cfg), encoding="utf-8")
        return path

    def test_defaults_to_true(self, tmp_path):
        master = load_master_config(self._write_master(tmp_path, {}))
        assert master.preload_models is True

    def test_explicit_false_wins(self, tmp_path):
        master = load_master_config(
            self._write_master(tmp_path, {"preload_models": False})
        )
        assert master.preload_models is False
