"""The local query log of the MCP server.

Until this existed the server log counted tool calls without their text: 866
calls since February, not one query recoverable. The log is off by default
and, when on, must never be the reason a search fails.
"""

import json

import pytest

import mcp_server
from src.archilles.config import load_master_config
from src.archilles.query_log import FILE_NAME, QueryLog


class _Server:
    """Duck-typed MCP server with one search tool and one that raises."""

    def search_books_with_citations_tool(self, query, top_k=10):
        return {
            "query": query,
            "num_results": 2,
            "user_prompt": "a long prompt that must not be logged",
            "raw_results": [
                {
                    "rank": 1,
                    "source": "calibre",
                    "text_preview": "passage text that must not be logged",
                    "similarity": 0.031,
                    "metadata": {"author": "Gussmann", "title": "Priesterverständnis",
                                 "year": None, "page_label": "78"},
                },
                {
                    "rank": 2,
                    "source": "zotero",
                    "similarity": 0.016,
                    "metadata": {"author": "Ben-Zion", "title": "Roadmap",
                                 "page_label": "21"},
                },
            ],
        }

    def verify_citation_tool(self, **_):
        raise RuntimeError("database is locked")


def _lines(path):
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines()]


@pytest.fixture
def log(tmp_path, monkeypatch):
    query_log = QueryLog(tmp_path / FILE_NAME)
    monkeypatch.setattr(mcp_server, "_query_log", query_log)
    return query_log


class TestDispatchWritesTheLog:
    def test_search_is_logged_with_query_and_places(self, log):
        mcp_server._dispatch_tool(
            _Server(), "search_books_with_citations",
            {"query": "Priester nach der Tempelzerstörung", "top_k": 5},
        )

        (entry,) = _lines(log.path)
        assert entry["tool"] == "search_books_with_citations"
        assert entry["arguments"] == {
            "query": "Priester nach der Tempelzerstörung", "top_k": 5,
        }
        assert entry["num_results"] == 2
        assert entry["hits"] == [
            {"rank": 1, "source": "calibre", "author": "Gussmann",
             "title": "Priesterverständnis", "page_label": "78", "score": 0.031},
            {"rank": 2, "source": "zotero", "author": "Ben-Zion",
             "title": "Roadmap", "page_label": "21", "score": 0.016},
        ]
        assert entry["seconds"] >= 0
        assert entry["ts"]

    def test_umlauts_are_written_as_text(self, log):
        mcp_server._dispatch_tool(
            _Server(), "search_books_with_citations", {"query": "Königswahl"},
        )

        assert "Königswahl" in log.path.read_text(encoding="utf-8")

    def test_neither_passage_text_nor_prompt_is_logged(self, log):
        mcp_server._dispatch_tool(
            _Server(), "search_books_with_citations", {"query": "x"},
        )

        written = log.path.read_text(encoding="utf-8")
        assert "must not be logged" not in written

    def test_failed_and_unknown_calls_are_logged_with_their_error(self, log):
        mcp_server._dispatch_tool(_Server(), "verify_citation", {"quote": "q"})
        mcp_server._dispatch_tool(_Server(), "no_such_tool", {})

        failed, unknown = _lines(log.path)
        assert failed["error"] == "database is locked"
        assert failed["arguments"] == {"quote": "q"}
        assert "Unknown tool" in unknown["error"]

    def test_calls_append(self, log):
        for query in ("a", "b", "c"):
            mcp_server._dispatch_tool(
                _Server(), "search_books_with_citations", {"query": query},
            )

        assert [e["arguments"]["query"] for e in _lines(log.path)] == ["a", "b", "c"]


class TestTheLogNeverBreaksACall:
    def test_unwritable_path_still_returns_the_result(self, tmp_path, monkeypatch):
        blocker = tmp_path / "a_file"
        blocker.write_text("", encoding="utf-8")
        # The parent of the log is a file: every write must fail.
        monkeypatch.setattr(
            mcp_server, "_query_log", QueryLog(blocker / "sub" / FILE_NAME)
        )

        result = mcp_server._dispatch_tool(
            _Server(), "search_books_with_citations", {"query": "x"},
        )

        assert result["num_results"] == 2

    def test_unserialisable_argument_is_written_as_text(self, log):
        log.record("t", {"when": object()}, {}, 0.0)

        (entry,) = _lines(log.path)
        assert entry["arguments"]["when"].startswith("<object")


class TestSwitch:
    def test_off_writes_nothing(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ARCHILLES_CONFIG_PATH", str(tmp_path / "config.json"))
        monkeypatch.setattr(mcp_server, "_query_log", None)

        assert mcp_server._start_query_log(False) is None
        mcp_server._dispatch_tool(
            _Server(), "search_books_with_citations", {"query": "x"},
        )

        assert not (tmp_path / FILE_NAME).exists()

    def test_on_logs_beside_the_master_config(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ARCHILLES_CONFIG_PATH", str(tmp_path / "config.json"))
        monkeypatch.setattr(mcp_server, "_query_log", None)

        started = mcp_server._start_query_log(True)

        assert started.path == tmp_path / FILE_NAME
        mcp_server._dispatch_tool(
            _Server(), "search_books_with_citations", {"query": "x"},
        )
        assert len(_lines(tmp_path / FILE_NAME)) == 1


class TestConfig:
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

    def test_off_by_default(self, tmp_path):
        master = load_master_config(self._write_master(tmp_path, {}))
        assert master.query_log is False

    def test_explicit_true_switches_it_on(self, tmp_path):
        master = load_master_config(
            self._write_master(tmp_path, {"query_log": True})
        )
        assert master.query_log is True
