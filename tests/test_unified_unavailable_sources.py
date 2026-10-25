"""An aggregated result names the sources it could not read.

Observed 2026-10-23: with the Zotero app open, zotero.sqlite stays locked.
The list tools counted the Zotero source as 0 hits and said nothing else, so
"Zotero has none" and "Zotero could not be read" looked the same. The other
sources still answer; the result now says which one is missing and why.
"""

from types import SimpleNamespace

from src.calibre_mcp.unified_server import UnifiedMCPServer

_LOCKED = {"error": "Failed to list tags: database is locked"}


def _make_unified(tmp_path, zotero_result):
    calibre = SimpleNamespace(
        list_tags_tool=lambda **kw: {"tags": [{"name": "BBB", "book_count": 17}]},
        list_books_by_author_tool=lambda **kw: {"books": [{"title": "Sein und Zeit"}]},
    )
    zotero = SimpleNamespace(
        list_tags_tool=lambda **kw: zotero_result,
        list_books_by_author_tool=lambda **kw: zotero_result,
    )
    return UnifiedMCPServer(
        servers={"archilles": calibre, "archilles-zotero": zotero},
        default_source="archilles",
        master_dir=tmp_path,
    )


class TestUnavailableSources:
    def test_a_locked_source_is_named_and_explained(self, tmp_path):
        server = _make_unified(tmp_path, _LOCKED)

        response = server.list_tags_tool()

        reason = response["unavailable_sources"]["archilles-zotero"]
        assert "database is locked" in reason
        assert "Zotero" in reason and "close it" in reason

    def test_the_other_sources_still_answer(self, tmp_path):
        server = _make_unified(tmp_path, _LOCKED)

        response = server.list_books_by_author_tool(author="Heidegger")

        assert [b["title"] for b in response["books"]] == ["Sein und Zeit"]
        assert response["per_source_counts"] == {"archilles": 1, "archilles-zotero": 0}

    def test_a_plain_error_is_passed_on_without_the_lock_hint(self, tmp_path):
        server = _make_unified(tmp_path, {"error": "Failed to list tags: disk I/O error"})

        reason = server.list_tags_tool()["unavailable_sources"]["archilles-zotero"]

        assert reason == "Failed to list tags: disk I/O error"

    def test_no_failure_adds_no_field(self, tmp_path):
        server = _make_unified(tmp_path, {"tags": []})

        assert "unavailable_sources" not in server.list_tags_tool()
