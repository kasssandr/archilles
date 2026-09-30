"""Every attachment of a Zotero item is indexed, not just one.

The adapter used to pick the best attachment per item and drop the rest
without a word. In a collection of reviews — several PDFs filed under the book
they discuss — that was a third of the material: 95 of 288 files.

Each attachment is now a unit of its own. The first keeps the bare item key,
so nothing indexed before moves; a further one is ``ITEMKEY#ATTACHMENTKEY``.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.adapters.zotero_adapter import ZoteroAdapter, split_unit_id
from src.archilles.watchdog import (
    _compute_zotero_metadata_hash,
    _zotero_metadata_for_scan,
)
from tests.test_zotero_adapter import _create_zotero_db
from tests.test_zotero_watchdog import _build_zotero_db, _make_scanner

PDF = "application/pdf"
HTML = "text/html"


def _att(item_id: int, key: str, name: str, content_type: str = PDF) -> dict:
    return {"itemID": item_id, "key": key, "linkMode": 0,
            "contentType": content_type, "path": f"storage:{name}", "filename": name}


@pytest.fixture
def adapter(tmp_path, monkeypatch):
    """A book with three reviews, and a plain single-file book beside it."""
    monkeypatch.setenv("ARCHILLES_CONFIG_PATH", str(tmp_path / "absent.json"))
    _create_zotero_db(tmp_path, items=[
        {
            "itemID": 1, "key": "BOOK0001", "itemTypeID": 7,
            "title": "The King's Two Bodies", "authors": [("Ernst", "Kantorowicz")],
            "attachments": [
                _att(100, "REVAAAAA", "Review Southern.pdf"),
                _att(101, "REVBBBBB", "Review Post.pdf"),
                _att(102, "REVCCCCC", "Review Smalley.pdf"),
            ],
            "notes": ["<p>Three reviews collected.</p>"],
        },
        {
            "itemID": 2, "key": "BOOK0002", "itemTypeID": 7, "title": "A Plain Book",
            "attachments": [_att(110, "PLAIN001", "plain.pdf")],
        },
    ])
    return ZoteroAdapter(tmp_path)


# ── The adapter ─────────────────────────────────────────────────


class TestUnitsInTheAdapter:
    def test_split_unit_id(self):
        assert split_unit_id("BOOK0001") == ("BOOK0001", None)
        assert split_unit_id("BOOK0001#REVBBBBB") == ("BOOK0001", "REVBBBBB")

    def test_every_attachment_is_a_document(self, adapter):
        docs = {d.doc_id: d for d in adapter.list_documents()}
        assert set(docs) == {
            "BOOK0001", "BOOK0001#REVBBBBB", "BOOK0001#REVCCCCC", "BOOK0002",
        }
        assert docs["BOOK0001"].file_path.name == "Review Southern.pdf"
        assert docs["BOOK0001#REVBBBBB"].file_path.name == "Review Post.pdf"
        assert docs["BOOK0001#REVCCCCC"].file_path.name == "Review Smalley.pdf"

    def test_a_work_is_listed_once(self, adapter):
        """A bibliography must not name the book three times."""
        assert [d.doc_id for d in adapter.list_works()] == ["BOOK0001", "BOOK0002"]

    def test_single_attachment_item_is_untouched(self, adapter):
        doc = adapter.get_metadata("BOOK0002")
        assert doc.doc_id == "BOOK0002"
        assert doc.title == "A Plain Book"

    def test_further_unit_names_its_attachment(self, adapter):
        assert adapter.get_metadata("BOOK0001").title == "The King's Two Bodies"
        further = adapter.get_metadata("BOOK0001#REVBBBBB")
        assert further.title == "The King's Two Bodies · Review Post"
        assert further.authors == ["Ernst Kantorowicz"]

    def test_file_path_per_unit(self, adapter):
        assert adapter.get_file_path("BOOK0001").name == "Review Southern.pdf"
        assert adapter.get_file_path("BOOK0001#REVCCCCC").name == "Review Smalley.pdf"

    def test_first_attachment_has_exactly_one_id(self, adapter):
        """Two ids for one file would index it twice."""
        assert adapter.get_file_path("BOOK0001#REVAAAAA") is None
        assert adapter.get_metadata("BOOK0001#REVAAAAA") is None

    def test_unknown_attachment(self, adapter):
        assert adapter.get_file_path("BOOK0001#NOPE0000") is None
        assert adapter.get_metadata("BOOK0001#NOPE0000") is None
        assert adapter.get_annotations("BOOK0001#NOPE0000") == []

    def test_units_share_the_items_metadata_hash(self, adapter):
        assert (adapter.compute_metadata_hash("BOOK0001#REVBBBBB")
                == adapter.compute_metadata_hash("BOOK0001") != "")

    def test_format_beats_age(self, tmp_path, monkeypatch):
        """The bare key stays with the PDF, as before units existed, even when
        a snapshot was saved first."""
        monkeypatch.setenv("ARCHILLES_CONFIG_PATH", str(tmp_path / "absent.json"))
        _create_zotero_db(tmp_path, items=[{
            "itemID": 1, "key": "MIXED001", "itemTypeID": 7, "title": "Mixed",
            "attachments": [
                _att(100, "SNAPSHOT", "page.html", HTML),
                _att(101, "THEPDF00", "paper.pdf"),
            ],
        }])
        adapter = ZoteroAdapter(tmp_path)
        assert adapter.get_file_path("MIXED001").name == "paper.pdf"
        assert adapter.get_file_path("MIXED001#SNAPSHOT").name == "page.html"

    def test_a_missing_file_does_not_shift_the_ids(self, adapter, tmp_path):
        """An id that moved whenever a file was unreachable would turn one
        offline drive into a round of deletions and re-indexing."""
        (tmp_path / "storage" / "REVAAAAA" / "Review Southern.pdf").unlink()
        assert adapter.get_file_path("BOOK0001") is None
        assert adapter.get_file_path("BOOK0001#REVBBBBB").name == "Review Post.pdf"
        category, _ = adapter.describe_unresolved("BOOK0001")
        assert category == "stored file missing from storage/"


class TestAnnotationsFollowTheirFile:
    @pytest.fixture
    def highlighted(self, adapter, tmp_path):
        conn = sqlite3.connect(str(tmp_path / "zotero.sqlite"))
        for ann_id, att_id, text in ((900, 100, "in the first"), (901, 101, "in the second")):
            conn.execute("INSERT INTO items (itemID, itemTypeID, key) VALUES (?, 1, ?)",
                         (ann_id, f"ANN{ann_id}"))
            conn.execute(
                "INSERT INTO itemAnnotations (itemID, parentItemID, type, text, comment) "
                "VALUES (?, ?, 'highlight', ?, '')", (ann_id, att_id, text))
        conn.commit()
        conn.close()
        return adapter

    def test_further_unit_gets_only_its_own_highlights(self, highlighted):
        texts = [a.text for a in highlighted.get_annotations("BOOK0001#REVBBBBB")]
        assert texts == ["in the second"]

    def test_bare_key_keeps_its_highlights_and_the_items_notes(self, highlighted):
        texts = [a.text for a in highlighted.get_annotations("BOOK0001")]
        assert texts == ["in the first", "Three reviews collected."]


class TestOrphansInTheAdapter:
    def test_all_units_are_current(self, adapter):
        indexed = {"BOOK0001", "BOOK0001#REVBBBBB", "BOOK0001#REVCCCCC", "BOOK0002"}
        assert adapter.compute_orphan_ids(indexed) == set()

    def test_a_deleted_attachment_orphans_only_its_unit(self, adapter, tmp_path):
        conn = sqlite3.connect(str(tmp_path / "zotero.sqlite"))
        conn.execute("INSERT INTO deletedItems (itemID) VALUES (101)")
        conn.commit()
        conn.close()
        indexed = {"BOOK0001", "BOOK0001#REVBBBBB", "BOOK0001#REVCCCCC", "BOOK0002"}
        assert adapter.compute_orphan_ids(indexed) == {"BOOK0001#REVBBBBB"}


# ── The watchdog scanner ────────────────────────────────────────


def _add_attachment(library: Path, att_id: int, key: str, parent_id: int,
                    modified: str = "2025-06-01T00:00:00") -> None:
    conn = sqlite3.connect(str(library / "zotero.sqlite"))
    conn.execute("INSERT INTO items VALUES (?, 3, 1, ?, ?, ?)",
                 (att_id, key, modified, modified))
    conn.execute("INSERT INTO itemAttachments VALUES (?, ?, 0, ?, 'storage:more.pdf')",
                 (att_id, parent_id, PDF))
    conn.commit()
    conn.close()


@pytest.fixture
def library(tmp_path):
    """One item, ``BOOK01``, with attachments ATT1001 (first) and ATT2000."""
    lib = tmp_path / "lib"
    lib.mkdir()
    _build_zotero_db(lib, [{"itemID": 1, "key": "BOOK01", "title": "Reviewed"}])
    _add_attachment(lib, 2000, "ATT2000", parent_id=1)
    return lib


def _stored(library: Path) -> dict:
    h = _compute_zotero_metadata_hash(_zotero_metadata_for_scan(library)["BOOK01"])
    return {"metadata_hash": h, "annotation_hash": ""}


def _dry_scan(library: Path, tmp_path: Path, indexed: dict, first_cache: dict | None = None):
    scanner = _make_scanner(library, tmp_path)
    if first_cache is not None:
        scanner.first_attachment_cache_file.write_text(json.dumps(first_cache))
    with patch.object(scanner, "_load_indexed_hashes", return_value=indexed):
        return scanner.scan(dry_run=True)


class TestUnitsInTheScanner:
    def test_scan_data_lists_units_in_order(self, library):
        units = _zotero_metadata_for_scan(library)["BOOK01"]["units"]
        assert [u["unit_id"] for u in units] == ["BOOK01", "BOOK01#ATT2000"]

    def test_further_attachment_of_an_indexed_item_is_new(self, library, tmp_path):
        """The case the whole change is for: the item is in the index, its
        second file never was."""
        results = _dry_scan(library, tmp_path, {"BOOK01": _stored(library)})
        assert [b["doc_id"] for b in results["new_books"]] == ["BOOK01#ATT2000"]
        assert results["unchanged"] == ["BOOK01"]

    def test_indexed_units_are_not_orphans(self, library, tmp_path):
        """A cleanup that knew only item keys would delete every further unit
        on the scan after it was indexed."""
        stored = _stored(library)
        results = _dry_scan(library, tmp_path,
                            {"BOOK01": stored, "BOOK01#ATT2000": stored})
        assert results["orphans_found"] == []
        assert results["new_books"] == []
        assert sorted(results["unchanged"]) == ["BOOK01", "BOOK01#ATT2000"]

    def test_unit_of_a_deleted_attachment_is_an_orphan(self, library, tmp_path):
        stored = _stored(library)
        results = _dry_scan(library, tmp_path, {
            "BOOK01": stored, "BOOK01#ATT2000": stored, "BOOK01#GONE0000": stored,
        })
        assert results["orphans_found"] == ["BOOK01#GONE0000"]

    def test_annotation_change_is_tracked_per_attachment(self, tmp_path):
        lib = tmp_path / "lib"
        lib.mkdir()
        _build_zotero_db(lib, [{"itemID": 1, "key": "BOOK01", "title": "Reviewed",
                                "att_modified": "2025-06-01T00:00:00"}])
        _add_attachment(lib, 2000, "ATT2000", parent_id=1, modified="2025-09-20T00:00:00")
        stored = _stored(lib)
        scanner = _make_scanner(lib, tmp_path)
        scanner.annotation_cache_file.write_text(json.dumps({
            "BOOK01": "2025-06-01T00:00:00", "BOOK01#ATT2000": "2025-06-01T00:00:00",
        }))
        with patch.object(scanner, "_load_indexed_hashes",
                          return_value={"BOOK01": stored, "BOOK01#ATT2000": stored}):
            results = scanner.scan(dry_run=True)
        assert results["annotations_changed"] == ["BOOK01#ATT2000"]


class TestReplacedFirstAttachment:
    """The bare key names whichever attachment comes first. Delete that one in
    Zotero and the key passes to the next file — while the index still holds
    the deleted one's text under it."""

    def test_first_scan_only_remembers(self, library, tmp_path):
        results = _dry_scan(library, tmp_path, {"BOOK01": _stored(library)})
        assert results["attachment_replaced"] == []

    def test_same_first_attachment_is_unchanged(self, library, tmp_path):
        results = _dry_scan(library, tmp_path, {"BOOK01": _stored(library)},
                            first_cache={"BOOK01": "ATT1001"})
        assert results["attachment_replaced"] == []
        assert "BOOK01" in results["unchanged"]

    def test_a_different_first_attachment_is_flagged(self, library, tmp_path):
        results = _dry_scan(library, tmp_path, {"BOOK01": _stored(library)},
                            first_cache={"BOOK01": "OLDFIRST"})
        assert results["attachment_replaced"] == ["BOOK01"]
        assert "BOOK01" not in results["unchanged"]

    def test_it_is_re_indexed_by_force_and_remembered(self, library, tmp_path, monkeypatch):
        stored = _stored(library)
        scanner = _make_scanner(library, tmp_path)
        scanner.first_attachment_cache_file.write_text(json.dumps({"BOOK01": "OLDFIRST"}))
        scanner._load_indexed_hashes = lambda: {"BOOK01": stored, "BOOK01#ATT2000": stored}
        plan = MagicMock()
        plan.embed_local = True
        plan.mode = "balanced"
        scanner._resolve_plan = lambda: plan

        calls: list[tuple[str, bool]] = []

        class RecordingRAG:
            def index_book(self, path, key, force=False):
                calls.append((key, force))
                return {}

        scanner._load_rag = lambda: RecordingRAG()
        monkeypatch.setattr(ZoteroAdapter, "get_file_path", lambda self, key: Path("f.pdf"))

        scanner.scan(queue_new=False)

        assert calls == [("BOOK01", True)]
        remembered = json.loads(scanner.first_attachment_cache_file.read_text())
        assert remembered == {"BOOK01": "ATT1001"}


# ── Notes written after indexing ────────────────────────────────


def _add_note(library: Path, note_id: int, parent_id: int,
              modified: str = "2025-07-01T00:00:00") -> None:
    conn = sqlite3.connect(str(library / "zotero.sqlite"))
    conn.execute("INSERT INTO items VALUES (?, 27, 1, ?, ?, ?)",
                 (note_id, f"NOTE{note_id}", modified, modified))
    conn.execute("INSERT INTO itemNotes VALUES (?, ?, '<p>a thought</p>', '')",
                 (note_id, parent_id))
    conn.commit()
    conn.close()


class TestNotesWrittenLater:
    """A note is an item of its own: writing one changes neither the parent's
    metadata nor any attachment's date. Nothing used to notice it, so a note
    written after its item was indexed stayed out of the index for good."""

    def _scan(self, library, tmp_path, cache: dict | None):
        stored = _stored(library)
        scanner = _make_scanner(library, tmp_path)
        if cache is not None:
            scanner.annotation_cache_file.write_text(json.dumps(cache))
        with patch.object(scanner, "_load_indexed_hashes",
                          return_value={"BOOK01": stored, "BOOK01#ATT2000": stored}):
            return scanner.scan(dry_run=True)

    def test_signal_counts_and_dates_the_notes(self, library):
        assert _zotero_metadata_for_scan(library)["BOOK01"]["notes_signal"] == ""
        _add_note(library, 5000, parent_id=1)
        _add_note(library, 5001, parent_id=1, modified="2025-08-01T00:00:00")
        signal = _zotero_metadata_for_scan(library)["BOOK01"]["notes_signal"]
        assert signal == "2:2025-08-01T00:00:00"

    def test_first_sight_is_not_a_change(self, library, tmp_path):
        _add_note(library, 5000, parent_id=1)
        results = self._scan(library, tmp_path, cache={})
        assert results["annotations_changed"] == []

    def test_first_note_on_a_known_item_is_a_change(self, library, tmp_path):
        """"No notes" has to be a recorded state, or this looks like a first sight."""
        _add_note(library, 5000, parent_id=1)
        results = self._scan(library, tmp_path, cache={"BOOK01@notes": ""})
        assert results["annotations_changed"] == ["BOOK01"]

    def test_a_deleted_note_is_a_change(self, library, tmp_path):
        results = self._scan(library, tmp_path,
                             cache={"BOOK01@notes": "1:2025-07-01T00:00:00"})
        assert results["annotations_changed"] == ["BOOK01"]

    def test_notes_belong_to_the_bare_key_only(self, library, tmp_path):
        _add_note(library, 5000, parent_id=1)
        results = self._scan(library, tmp_path, cache={"BOOK01@notes": ""})
        assert "BOOK01#ATT2000" in results["unchanged"]

    def test_the_new_state_is_kept_once_the_update_succeeded(
        self, library, tmp_path, monkeypatch,
    ):
        _add_note(library, 5000, parent_id=1)
        stored = _stored(library)
        scanner = _make_scanner(library, tmp_path)
        scanner.annotation_cache_file.write_text(json.dumps({"BOOK01@notes": ""}))
        scanner._load_indexed_hashes = lambda: {"BOOK01": stored, "BOOK01#ATT2000": stored}
        plan = MagicMock()
        plan.embed_local = True
        plan.mode = "balanced"
        scanner._resolve_plan = lambda: plan
        calls: list[tuple[str, bool]] = []

        class RecordingRAG:
            def index_book(self, path, key, force=False):
                calls.append((key, force))
                return {}

        scanner._load_rag = lambda: RecordingRAG()
        monkeypatch.setattr(ZoteroAdapter, "get_file_path", lambda self, key: Path("f.pdf"))

        scanner.scan(queue_new=False)

        assert calls == [("BOOK01", False)]
        cache = json.loads(scanner.annotation_cache_file.read_text())
        assert cache["BOOK01@notes"] == "1:2025-07-01T00:00:00"


# ── What the user can leave out ─────────────────────────────────


def _tag(library: Path, item_id: int, name: str) -> None:
    conn = sqlite3.connect(str(library / "zotero.sqlite"))
    tag_id = conn.execute("SELECT COALESCE(MAX(tagID), 0) + 1 FROM tags").fetchone()[0]
    conn.execute("INSERT INTO tags (tagID, name) VALUES (?, ?)", (tag_id, name))
    conn.execute("INSERT INTO itemTags (itemID, tagID) VALUES (?, ?)", (item_id, tag_id))
    conn.commit()
    conn.close()


class TestAttachmentTaggedOut:
    """Two editions in one item, one of them not for the index: the tag that
    excludes a whole item excludes a single attachment too, and the file
    stays where it is."""

    def test_tagged_attachment_is_no_unit(self, adapter, tmp_path):
        _tag(tmp_path, 101, "exclude")
        ids = [d.doc_id for d in adapter.list_documents()]
        assert ids == ["BOOK0001", "BOOK0001#REVCCCCC", "BOOK0002"]
        assert adapter.get_file_path("BOOK0001#REVBBBBB") is None

    def test_tag_is_matched_case_insensitively(self, adapter, tmp_path):
        _tag(tmp_path, 101, "Exclude")
        assert "BOOK0001#REVBBBBB" not in [d.doc_id for d in adapter.list_documents()]

    def test_any_other_tag_changes_nothing(self, adapter, tmp_path):
        _tag(tmp_path, 101, "to-read")
        assert "BOOK0001#REVBBBBB" in [d.doc_id for d in adapter.list_documents()]

    def test_configured_tags_replace_the_default(self, adapter, tmp_path):
        (tmp_path / ".archilles").mkdir()
        (tmp_path / ".archilles" / "config.json").write_text(
            json.dumps({"excluded_tags": ["Zweitausgabe"]}), encoding="utf-8")
        _tag(tmp_path, 101, "Zweitausgabe")
        _tag(tmp_path, 102, "exclude")
        ids = [d.doc_id for d in ZoteroAdapter(tmp_path).list_documents()]
        assert ids == ["BOOK0001", "BOOK0001#REVCCCCC", "BOOK0002"]

    def test_tagging_the_first_passes_the_bare_key_on(self, adapter, tmp_path):
        """The scanner's replaced-attachment check is what then re-indexes it."""
        _tag(tmp_path, 100, "exclude")
        assert adapter.get_file_path("BOOK0001").name == "Review Post.pdf"
        assert [d.doc_id for d in adapter.list_documents()][:2] == [
            "BOOK0001", "BOOK0001#REVCCCCC"]

    def test_its_unit_becomes_an_orphan(self, adapter, tmp_path):
        _tag(tmp_path, 101, "exclude")
        indexed = {"BOOK0001", "BOOK0001#REVBBBBB", "BOOK0001#REVCCCCC"}
        assert adapter.compute_orphan_ids(indexed) == {"BOOK0001#REVBBBBB"}

    def test_the_scanner_agrees(self, library, tmp_path):
        _tag(library, 2000, "exclude")
        units = _zotero_metadata_for_scan(library)["BOOK01"]["units"]
        assert [u["unit_id"] for u in units] == ["BOOK01"]


def _snapshot(item_id: int, key: str) -> dict:
    return {"itemID": item_id, "key": key, "linkMode": 1, "contentType": HTML,
            "path": "storage:landing.html", "filename": "landing.html"}


class TestSnapshotBesideTheDocument:
    """The browser connector saves the publisher's landing page along with the
    paper. Nobody chose to have two files there."""

    def _library(self, tmp_path, monkeypatch, attachments):
        monkeypatch.setenv("ARCHILLES_CONFIG_PATH", str(tmp_path / "absent.json"))
        _create_zotero_db(tmp_path, items=[{
            "itemID": 1, "key": "PAPER001", "itemTypeID": 12, "title": "A Paper",
            "attachments": attachments,
        }])
        return ZoteroAdapter(tmp_path)

    def test_snapshot_beside_a_pdf_is_left_out(self, tmp_path, monkeypatch):
        adapter = self._library(tmp_path, monkeypatch, [
            _snapshot(100, "SNAPSHOT"), _att(101, "THEPDF00", "paper.pdf")])
        assert [d.doc_id for d in adapter.list_documents()] == ["PAPER001"]
        assert adapter.get_file_path("PAPER001").name == "paper.pdf"

    def test_snapshot_on_its_own_is_the_content(self, tmp_path, monkeypatch):
        adapter = self._library(tmp_path, monkeypatch, [_snapshot(100, "SNAPSHOT")])
        assert adapter.get_file_path("PAPER001").name == "landing.html"

    def test_two_snapshots_without_a_document_both_stay(self, tmp_path, monkeypatch):
        adapter = self._library(tmp_path, monkeypatch, [
            _snapshot(100, "SNAPSHOT"), _snapshot(101, "SNAPSHO2")])
        assert [d.doc_id for d in adapter.list_documents()] == [
            "PAPER001", "PAPER001#SNAPSHO2"]

    def test_an_html_file_attached_on_purpose_stays(self, tmp_path, monkeypatch):
        """Only the connector's snapshot is a by-product; a stored or linked
        HTML file was put there by hand."""
        adapter = self._library(tmp_path, monkeypatch, [
            _att(100, "HTMLFILE", "notes.html", HTML), _att(101, "THEPDF00", "paper.pdf")])
        assert [d.doc_id for d in adapter.list_documents()] == [
            "PAPER001", "PAPER001#HTMLFILE"]

    def test_tagged_out_pdf_leaves_the_snapshot_as_content(self, tmp_path, monkeypatch):
        adapter = self._library(tmp_path, monkeypatch, [
            _snapshot(100, "SNAPSHOT"), _att(101, "THEPDF00", "paper.pdf")])
        _tag(tmp_path, 101, "exclude")
        assert adapter.get_file_path("PAPER001").name == "landing.html"
