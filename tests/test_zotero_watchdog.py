"""Tests for the ZoteroWatchdogScanner and related helpers.

Covers:
  1. _zotero_metadata_for_scan() — batch SQLite read
  2. _compute_zotero_metadata_hash() — hash stability
  3. ZoteroWatchdogScanner.scan() — classification (new / metadata_changed /
     annotations_changed / unchanged / excluded-tag / no-attachment)
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.archilles.watchdog import (
    ZoteroWatchdogScanner,
    _compute_zotero_metadata_hash,
    _zotero_metadata_for_scan,
)


# ── Fixture helpers ──────────────────────────────────────────────


def _build_zotero_db(library_path: Path, items: list[dict], *, att_content_type: str = "application/pdf") -> None:
    """Create a minimal zotero.sqlite for watchdog tests."""
    db_path = library_path / "zotero.sqlite"
    conn = sqlite3.connect(str(db_path))
    conn.executescript("""
        CREATE TABLE itemTypes (itemTypeID INTEGER PRIMARY KEY, typeName TEXT);
        INSERT INTO itemTypes VALUES (1, 'annotation');
        INSERT INTO itemTypes VALUES (3, 'attachment');
        INSERT INTO itemTypes VALUES (7, 'book');
        INSERT INTO itemTypes VALUES (12, 'journalArticle');
        INSERT INTO itemTypes VALUES (27, 'note');

        CREATE TABLE items (
            itemID INTEGER PRIMARY KEY, itemTypeID INTEGER,
            libraryID INTEGER DEFAULT 1, key TEXT UNIQUE,
            dateAdded TEXT, dateModified TEXT
        );
        CREATE TABLE deletedItems (itemID INTEGER PRIMARY KEY);
        CREATE TABLE fields (fieldID INTEGER PRIMARY KEY, fieldName TEXT);
        INSERT INTO fields VALUES (1, 'title');
        INSERT INTO fields VALUES (2, 'abstractNote');
        INSERT INTO fields VALUES (3, 'date');
        CREATE TABLE itemDataValues (valueID INTEGER PRIMARY KEY, value TEXT);
        CREATE TABLE itemData (itemID INTEGER, fieldID INTEGER, valueID INTEGER, PRIMARY KEY (itemID, fieldID));
        CREATE TABLE creatorTypes (creatorTypeID INTEGER PRIMARY KEY, creatorType TEXT);
        INSERT INTO creatorTypes VALUES (1, 'author');
        CREATE TABLE creators (creatorID INTEGER PRIMARY KEY, firstName TEXT, lastName TEXT NOT NULL);
        CREATE TABLE itemCreators (itemID INTEGER, creatorID INTEGER, creatorTypeID INTEGER, orderIndex INTEGER DEFAULT 0);
        CREATE TABLE tags (tagID INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE itemTags (itemID INTEGER, tagID INTEGER, type INTEGER DEFAULT 0);
        CREATE TABLE itemAttachments (itemID INTEGER PRIMARY KEY, parentItemID INTEGER, linkMode INTEGER, contentType TEXT, path TEXT);
        CREATE TABLE collections (collectionID INTEGER PRIMARY KEY, collectionName TEXT, parentCollectionID INTEGER, libraryID INTEGER, key TEXT);
        CREATE TABLE collectionItems (collectionID INTEGER, itemID INTEGER);
    """)

    val_id = [0]

    def _set_field(item_id, field_id, value):
        val_id[0] += 1
        conn.execute("INSERT INTO itemDataValues VALUES (?, ?)", (val_id[0], value))
        conn.execute("INSERT INTO itemData VALUES (?, ?, ?)", (item_id, field_id, val_id[0]))

    cr_id = [0]
    tag_id = [0]
    att_id = [1000]

    for item in items:
        conn.execute(
            "INSERT INTO items VALUES (?, ?, 1, ?, ?, ?)",
            (item["itemID"], item.get("itemTypeID", 7), item["key"],
             item.get("dateAdded", "2025-01-01T00:00:00"),
             item.get("dateModified", "2025-06-01T00:00:00")),
        )
        if item.get("deleted"):
            conn.execute("INSERT INTO deletedItems VALUES (?)", (item["itemID"],))
        if item.get("title"):
            _set_field(item["itemID"], 1, item["title"])
        if item.get("abstract"):
            _set_field(item["itemID"], 2, item["abstract"])
        if item.get("date"):
            _set_field(item["itemID"], 3, item["date"])

        for first, last in item.get("authors", []):
            cr_id[0] += 1
            conn.execute("INSERT INTO creators VALUES (?, ?, ?)", (cr_id[0], first, last))
            conn.execute("INSERT INTO itemCreators VALUES (?, ?, 1, ?)", (item["itemID"], cr_id[0], cr_id[0]))

        for tag in item.get("tags", []):
            tag_id[0] += 1
            conn.execute("INSERT OR IGNORE INTO tags VALUES (?, ?)", (tag_id[0], tag))
            conn.execute("INSERT INTO itemTags (itemID, tagID, type) VALUES (?, ?, 0)", (item["itemID"], tag_id[0]))

        if item.get("has_attachment", True) and not item.get("deleted"):
            att_id[0] += 1
            att_modified = item.get("att_modified", item.get("dateModified", "2025-06-01T00:00:00"))
            conn.execute(
                "INSERT INTO items VALUES (?, 3, 1, ?, ?, ?)",
                (att_id[0], f"ATT{att_id[0]:04d}", item.get("dateAdded"), att_modified),
            )
            conn.execute(
                "INSERT INTO itemAttachments VALUES (?, ?, 0, ?, 'storage:file.pdf')",
                (att_id[0], item["itemID"], att_content_type),
            )

    conn.commit()
    conn.close()


def _make_scanner(library_path: Path, tmp_path: Path) -> ZoteroWatchdogScanner:
    archilles_dir = tmp_path / ".archilles"
    archilles_dir.mkdir()
    return ZoteroWatchdogScanner(
        library_path=library_path,
        db_path=str(tmp_path / "rag_db"),
        archilles_dir=archilles_dir,
    )


def _mock_hashes(stored: dict[str, dict]) -> MagicMock:
    """Return a mock rag with get_hashes_by_book_id returning stored."""
    rag = MagicMock()
    rag.store.get_hashes_by_book_id.return_value = stored
    return rag


# ── Tests: _zotero_metadata_for_scan ────────────────────────────


class TestZoteroMetadataForScan:
    def test_basic_fields(self, tmp_path):
        _build_zotero_db(tmp_path, [
            {"itemID": 1, "key": "ABC001", "title": "Test Book",
             "authors": [("Jane", "Doe")], "tags": ["History"],
             "date": "2020", "abstract": "A summary.",
             "dateModified": "2025-06-01T00:00:00"},
        ])
        data = _zotero_metadata_for_scan(tmp_path)
        assert "ABC001" in data
        item = data["ABC001"]
        assert item["title"] == "Test Book"
        assert item["authors"] == ["Jane Doe"]
        assert item["tags"] == ["History"]
        assert item["date"] == "2020"
        assert item["abstract"] == "A summary."
        assert item["has_attachment"] is True

    def test_authors_sorted(self, tmp_path):
        _build_zotero_db(tmp_path, [
            {"itemID": 1, "key": "ABC001", "title": "T",
             "authors": [("Bob", "Zed"), ("Alice", "Apple")]},
        ])
        item = _zotero_metadata_for_scan(tmp_path)["ABC001"]
        assert item["authors"] == ["Alice Apple", "Bob Zed"]

    def test_tags_sorted(self, tmp_path):
        _build_zotero_db(tmp_path, [
            {"itemID": 1, "key": "ABC001", "title": "T",
             "tags": ["Zotero", "History", "Ancient"]},
        ])
        item = _zotero_metadata_for_scan(tmp_path)["ABC001"]
        assert item["tags"] == ["Ancient", "History", "Zotero"]

    def test_deleted_items_excluded(self, tmp_path):
        _build_zotero_db(tmp_path, [
            {"itemID": 1, "key": "LIVE001", "title": "Live"},
            {"itemID": 2, "key": "DEAD001", "title": "Deleted", "deleted": True},
        ])
        data = _zotero_metadata_for_scan(tmp_path)
        assert "LIVE001" in data
        assert "DEAD001" not in data

    def test_no_attachment_flagged(self, tmp_path):
        _build_zotero_db(tmp_path, [
            {"itemID": 1, "key": "NOATT1", "title": "No file", "has_attachment": False},
        ])
        item = _zotero_metadata_for_scan(tmp_path)["NOATT1"]
        assert item["has_attachment"] is False

    def test_attachment_modified_at_captured(self, tmp_path):
        _build_zotero_db(tmp_path, [
            {"itemID": 1, "key": "ABC001", "title": "T",
             "att_modified": "2025-09-15T12:00:00"},
        ])
        item = _zotero_metadata_for_scan(tmp_path)["ABC001"]
        assert item["attachment_modified_at"] == "2025-09-15T12:00:00"

    def test_missing_db_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            _zotero_metadata_for_scan(tmp_path)


# ── Tests: _compute_zotero_metadata_hash ────────────────────────


class TestComputeZoteroMetadataHash:
    def _data(self, **kw):
        base = {"title": "T", "authors": ["A", "B"], "tags": ["x"], "abstract": "abs", "date": "2020"}
        base.update(kw)
        return base

    def test_identical_data_same_hash(self):
        d = self._data()
        assert _compute_zotero_metadata_hash(d) == _compute_zotero_metadata_hash(d)

    def test_title_change_changes_hash(self):
        a = _compute_zotero_metadata_hash(self._data(title="A"))
        b = _compute_zotero_metadata_hash(self._data(title="B"))
        assert a != b

    def test_author_change_changes_hash(self):
        a = _compute_zotero_metadata_hash(self._data(authors=["Alice"]))
        b = _compute_zotero_metadata_hash(self._data(authors=["Bob"]))
        assert a != b

    def test_tag_change_changes_hash(self):
        a = _compute_zotero_metadata_hash(self._data(tags=["old"]))
        b = _compute_zotero_metadata_hash(self._data(tags=["new"]))
        assert a != b

    def test_extra_fields_ignored(self):
        base = _compute_zotero_metadata_hash(self._data())
        with_extra = _compute_zotero_metadata_hash({**self._data(), "has_attachment": True, "modified_at": "now"})
        assert base == with_extra


# ── Tests: ZoteroWatchdogScanner.scan() ─────────────────────────


class TestZoteroWatchdogScan:

    def _scan(self, library_path, tmp_path, stored_hashes: dict, ann_cache: dict | None = None):
        """Run a dry-run scan with mocked LanceDB hashes."""
        scanner = _make_scanner(library_path, tmp_path)
        if ann_cache is not None:
            scanner.annotation_cache_file.write_text(json.dumps(ann_cache))

        with patch.object(scanner, '_load_indexed_hashes', return_value=stored_hashes):
            return scanner.scan(dry_run=True)

    def test_new_item_detected(self, tmp_path):
        lib = tmp_path / "lib"
        lib.mkdir()
        _build_zotero_db(lib, [{"itemID": 1, "key": "NEW001", "title": "New"}])
        results = self._scan(lib, tmp_path, stored_hashes={})
        doc_ids = [b['doc_id'] for b in results['new_books']]
        assert "NEW001" in doc_ids

    def test_unchanged_item(self, tmp_path):
        lib = tmp_path / "lib"
        lib.mkdir()
        _build_zotero_db(lib, [
            {"itemID": 1, "key": "SAME01", "title": "Same", "authors": [("A", "B")],
             "tags": [], "abstract": "", "date": "2020"},
        ])
        items = _zotero_metadata_for_scan(lib)
        h = _compute_zotero_metadata_hash(items["SAME01"])
        results = self._scan(lib, tmp_path, stored_hashes={"SAME01": {"metadata_hash": h, "annotation_hash": ""}})
        assert "SAME01" in results['unchanged']
        assert results['metadata_changed'] == []

    def test_metadata_change_detected(self, tmp_path):
        lib = tmp_path / "lib"
        lib.mkdir()
        _build_zotero_db(lib, [
            {"itemID": 1, "key": "CHG01", "title": "New Title"},
        ])
        results = self._scan(lib, tmp_path, stored_hashes={
            "CHG01": {"metadata_hash": "old_hash_that_will_not_match", "annotation_hash": ""}
        })
        assert "CHG01" in results['metadata_changed']

    def test_annotation_change_detected(self, tmp_path):
        lib = tmp_path / "lib"
        lib.mkdir()
        _build_zotero_db(lib, [
            {"itemID": 1, "key": "ANN01", "title": "T", "att_modified": "2025-09-20T00:00:00"},
        ])
        items = _zotero_metadata_for_scan(lib)
        h = _compute_zotero_metadata_hash(items["ANN01"])
        # Cache shows old att_modified → annotation change
        old_cache = {"ANN01": "2025-01-01T00:00:00"}
        results = self._scan(lib, tmp_path,
                             stored_hashes={"ANN01": {"metadata_hash": h, "annotation_hash": ""}},
                             ann_cache=old_cache)
        assert "ANN01" in results['annotations_changed']
        assert "ANN01" not in results['metadata_changed']

    def test_excluded_tag_skipped(self, tmp_path):
        lib = tmp_path / "lib"
        lib.mkdir()
        _build_zotero_db(lib, [
            {"itemID": 1, "key": "EXCL1", "title": "Excluded", "tags": ["exclude"]},
        ])
        scanner = _make_scanner(lib, tmp_path)
        scanner.excluded_tags_lower = {"exclude"}
        with patch.object(scanner, '_load_indexed_hashes', return_value={}):
            results = scanner.scan(dry_run=True)
        doc_ids = [b['doc_id'] for b in results['new_books']]
        assert "EXCL1" not in doc_ids

    def test_item_without_attachment_skipped(self, tmp_path):
        lib = tmp_path / "lib"
        lib.mkdir()
        _build_zotero_db(lib, [
            {"itemID": 1, "key": "NOATT1", "title": "No file", "has_attachment": False},
        ])
        results = self._scan(lib, tmp_path, stored_hashes={})
        doc_ids = [b['doc_id'] for b in results['new_books']]
        assert "NOATT1" not in doc_ids

    def test_first_scan_seeds_annotation_cache(self, tmp_path):
        """On first scan of a known item (no cache entry), cache is seeded without marking changed."""
        lib = tmp_path / "lib"
        lib.mkdir()
        _build_zotero_db(lib, [
            {"itemID": 1, "key": "SEED1", "title": "T", "att_modified": "2025-06-01T00:00:00"},
        ])
        items = _zotero_metadata_for_scan(lib)
        h = _compute_zotero_metadata_hash(items["SEED1"])
        # Known to LanceDB, but no annotation cache entry yet
        results = self._scan(lib, tmp_path,
                             stored_hashes={"SEED1": {"metadata_hash": h, "annotation_hash": ""}},
                             ann_cache={})
        assert "SEED1" not in results['annotations_changed']
        assert "SEED1" in results['unchanged']
