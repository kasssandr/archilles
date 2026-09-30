"""``linked_attachment_base`` must reach the ZoteroAdapter on its own.

The key sat in the master config for months and did nothing: no call site —
neither ``create_adapter`` nor the watchdog's three ``ZoteroAdapter(...)``
calls — handed it over. Relative linked files (``attachments:NNNN/x.pdf``)
therefore never resolved, and a collection of 195 reviews showed up as 4.

The adapter now looks the value up itself, by library path, so every call
site that knows only the library gets it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.adapters.zotero_adapter import ZoteroAdapter
from src.archilles.config import get_linked_attachment_base
from tests.test_zotero_adapter import _create_zotero_db


def _write_master(tmp_path: Path, monkeypatch, sources: list[dict]) -> None:
    cfg = tmp_path / "master" / "config.json"
    cfg.parent.mkdir()
    cfg.write_text(json.dumps({"sources": sources}), encoding="utf-8")
    monkeypatch.setenv("ARCHILLES_CONFIG_PATH", str(cfg))


class TestGetLinkedAttachmentBase:
    def test_returns_base_of_matching_source(self, tmp_path, monkeypatch):
        library = tmp_path / "Zotero"
        base = tmp_path / "Reviews"
        _write_master(tmp_path, monkeypatch, [
            {"name": "calibre", "library_path": str(tmp_path / "Calibre")},
            {"name": "zotero", "library_path": str(library),
             "linked_attachment_base": str(base)},
        ])
        assert get_linked_attachment_base(library) == base

    def test_path_spelling_does_not_matter(self, tmp_path, monkeypatch):
        """The config and the caller rarely spell a path identically."""
        library = tmp_path / "Zotero"
        base = tmp_path / "Reviews"
        _write_master(tmp_path, monkeypatch, [
            {"name": "zotero", "library_path": str(library),
             "linked_attachment_base": str(base)},
        ])
        assert get_linked_attachment_base(library / "sub" / "..") == base

    def test_no_matching_source(self, tmp_path, monkeypatch):
        _write_master(tmp_path, monkeypatch, [
            {"name": "zotero", "library_path": str(tmp_path / "Zotero"),
             "linked_attachment_base": str(tmp_path / "Reviews")},
        ])
        assert get_linked_attachment_base(tmp_path / "Elsewhere") is None

    def test_key_unset(self, tmp_path, monkeypatch):
        library = tmp_path / "Zotero"
        _write_master(tmp_path, monkeypatch, [
            {"name": "zotero", "library_path": str(library)},
        ])
        assert get_linked_attachment_base(library) is None

    def test_no_master_config(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ARCHILLES_CONFIG_PATH", str(tmp_path / "absent.json"))
        assert get_linked_attachment_base(tmp_path / "Zotero") is None


class TestAdapterPicksUpTheBase:
    @pytest.fixture
    def library(self, tmp_path):
        """One item whose only attachment is a relative linked file."""
        library = tmp_path / "Zotero"
        library.mkdir()
        _create_zotero_db(library, items=[{
            "itemID": 1, "key": "REVIEW01", "itemTypeID": 7,
            "title": "A Reviewed Book",
            "attachments": [{
                "itemID": 100, "key": "ATT00001", "linkMode": 2,
                "contentType": "application/pdf",
                "path": "attachments:0042/review.pdf",
            }],
        }])
        base = tmp_path / "Reviews"
        (base / "0042").mkdir(parents=True)
        (base / "0042" / "review.pdf").write_bytes(b"%PDF-1.4")
        return library, base

    def test_resolves_without_being_told(self, library, tmp_path, monkeypatch):
        library, base = library
        _write_master(tmp_path, monkeypatch, [
            {"name": "zotero", "library_path": str(library),
             "linked_attachment_base": str(base)},
        ])
        adapter = ZoteroAdapter(library)
        assert adapter.get_file_path("REVIEW01") == base / "0042" / "review.pdf"

    def test_unresolved_without_config(self, library, tmp_path, monkeypatch):
        library, _ = library
        monkeypatch.setenv("ARCHILLES_CONFIG_PATH", str(tmp_path / "absent.json"))
        assert ZoteroAdapter(library).get_file_path("REVIEW01") is None

    def test_explicit_argument_wins(self, library, tmp_path, monkeypatch):
        library, base = library
        _write_master(tmp_path, monkeypatch, [
            {"name": "zotero", "library_path": str(library),
             "linked_attachment_base": str(tmp_path / "Wrong")},
        ])
        adapter = ZoteroAdapter(library, linked_attachment_base=base)
        assert adapter.get_file_path("REVIEW01") == base / "0042" / "review.pdf"
