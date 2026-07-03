"""Tests for review 4.1 — Zotero metadata change detection must be stable.

The scanner compared a Zotero-style hash (title/authors/tags/abstract/date)
against a stored Calibre-style hash (comments/tags/title/author/publisher) —
they can never match, so every indexed item was re-flagged every scan and the
adapterless delta pass wiped the hash + deleted the abstract chunk.

Fix, three parts:
  (a) adapter-backed items store the adapter's source-specific hash at index
      time (Indexer._resolve_metadata_hash), so it matches the scanner;
  (b) the Zotero scanner's RAG is built WITH the ZoteroAdapter, so delta
      re-indexing extracts real metadata instead of {};
  (c) _update_metadata_only refuses to act on empty metadata against a
      non-empty stored hash (never wipe / delete on an extraction failure).

The Calibre stored hash must stay byte-identical (reindex-storm gate).
"""

from __future__ import annotations

import sqlite3
from types import SimpleNamespace

import numpy as np
import pytest

from src.archilles.engine.indexing import Indexer
from src.archilles import hashing
from src.adapters.zotero_adapter import ZoteroAdapter
from src.archilles.watchdog import (
    ZoteroWatchdogScanner,
    _compute_zotero_metadata_hash,
    _zotero_metadata_for_scan,
)

# Reuse the Zotero sqlite builder + scanner helper from the sibling test module.
from tests.test_zotero_watchdog import _build_zotero_db, _make_scanner


ITEM = {
    "itemID": 1, "key": "ZKEY0001", "itemTypeID": 7,
    "title": "A Study of Something", "abstract": "The abstract text.",
    "date": "2021", "authors": [("Jane", "Doe"), ("Karl", "Roe")],
    "tags": ["history", "method"],
}


# ── (a) core: adapter hash == scanner hash → unchanged on rescan ─────


def test_zotero_adapter_hash_matches_scanner_hash(tmp_path):
    """The hash the adapter stores at index time must equal what the scanner
    computes — the Zotero analogue of the Calibre golden test. If these differ,
    every scan re-flags the item (the 4.1 failure)."""
    _build_zotero_db(tmp_path, [ITEM])
    adapter_hash = ZoteroAdapter(tmp_path).compute_metadata_hash("ZKEY0001")
    scanner_hash = _compute_zotero_metadata_hash(_zotero_metadata_for_scan(tmp_path)["ZKEY0001"])
    assert adapter_hash and adapter_hash == scanner_hash


# ── (a) wiring: Indexer prefers the adapter, falls back cleanly ──────


class _FakeAdapter:
    def __init__(self, mapping):
        self._mapping = mapping

    def compute_metadata_hash(self, doc_id):
        return self._mapping.get(doc_id, "")


def _indexer_with_adapter(adapter):
    rag = SimpleNamespace(_adapter=adapter)
    return Indexer(rag)


def test_resolve_hash_uses_adapter_when_present():
    idx = _indexer_with_adapter(_FakeAdapter({"ZKEY0001": "zoterohash"}))
    # book_metadata is deliberately different from the adapter's field set:
    # the adapter must win.
    result = idx._resolve_metadata_hash("ZKEY0001", {"title": "x", "comments": "y"})
    assert result == "zoterohash"


def test_resolve_hash_falls_back_without_adapter():
    idx = _indexer_with_adapter(None)
    meta = {"title": "T", "author": "A", "comments": "C"}
    assert idx._resolve_metadata_hash("bk", meta) == hashing.compute_metadata_hash(meta)


def test_resolve_hash_falls_back_when_adapter_returns_empty():
    idx = _indexer_with_adapter(_FakeAdapter({}))  # returns "" for unknown id
    meta = {"title": "T", "author": "A"}
    assert idx._resolve_metadata_hash("unknown", meta) == hashing.compute_metadata_hash(meta)


def test_resolve_hash_empty_metadata_no_adapter_is_empty():
    idx = _indexer_with_adapter(None)
    assert idx._resolve_metadata_hash("bk", {}) == ""


# ── (b) the Zotero scanner builds its RAG WITH the adapter ───────────


def test_zotero_scanner_load_rag_passes_adapter(tmp_path, monkeypatch):
    lib = tmp_path / "lib"
    lib.mkdir()
    _build_zotero_db(lib, [ITEM])
    scanner = _make_scanner(lib, tmp_path)

    captured = {}

    def fake_rag(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(**kwargs)

    monkeypatch.setattr("src.archilles.engine.ArchillesRAG", fake_rag)
    scanner._load_rag()

    assert isinstance(captured.get("adapter"), ZoteroAdapter), (
        "delta re-indexing without the adapter extracts {} metadata and wipes hashes"
    )


# ── (c) refuse destructive empty updates ────────────────────────────


class _RecordingStore:
    def __init__(self):
        self.calls = []

    def update_metadata_fields(self, book_id, updates):
        self.calls.append(("update", book_id, updates))
        return 1

    def delete_by_book_id_and_type(self, book_id, chunk_type):
        self.calls.append(("delete", book_id, chunk_type))
        return 1

    def add_chunks(self, chunks, embeddings):
        self.calls.append(("add", len(chunks)))
        return len(chunks)


def test_update_metadata_only_refuses_empty_metadata_vs_stored_hash():
    store = _RecordingStore()
    rag = SimpleNamespace(store=store, _adapter=None)
    idx = Indexer(rag)

    result = idx._update_metadata_only(
        "ZKEY0001", {}, "", state={"metadata_hash": "abc123", "format": "pdf"}
    )

    assert result.get("status") == "metadata_extract_failed"
    assert store.calls == [], "must not wipe the hash or delete comment chunks on empty metadata"


def test_update_metadata_only_proceeds_when_stored_hash_empty():
    """A genuinely new/empty book (stored hash '') is not a failure — the guard
    must only fire when there is a non-empty stored hash to protect."""
    store = _RecordingStore()
    rag = SimpleNamespace(store=store, _adapter=None, _format_tags=lambda t: t)
    idx = Indexer(rag)

    result = idx._update_metadata_only(
        "NEWBOOK", {}, "", state={"metadata_hash": "", "format": ""}
    )
    assert result.get("status") != "metadata_extract_failed"


# ── (F) user's concern: the flat/simple path detects correctly ──────


def test_flat_indexed_zotero_item_is_unchanged_on_rescan(tmp_path):
    """Weak-hardware flat path: a Zotero item indexed as a single flat content
    chunk carrying the adapter hash must classify as 'unchanged' on the next
    scan — end-to-end through the real LanceDB store, no hierarchy involved."""
    from src.storage.lancedb_store import LanceDBStore

    lib = tmp_path / "lib"
    lib.mkdir()
    _build_zotero_db(lib, [ITEM])
    scanner = _make_scanner(lib, tmp_path)

    # Simulate a flat index: one content chunk with the adapter-computed hash.
    adapter_hash = ZoteroAdapter(lib).compute_metadata_hash("ZKEY0001")
    store = LanceDBStore(db_path=scanner.db_path)
    store.add_chunks(
        [{
            "id": "ZKEY0001_content_0", "text": "flat body text",
            "book_id": "ZKEY0001", "source_id": "ZKEY0001",
            "chunk_index": 0, "chunk_type": "content",
            "metadata_hash": adapter_hash,
        }],
        np.random.rand(1, 1024).astype(np.float32),
    )

    results = scanner.scan(dry_run=True)
    assert "ZKEY0001" in results["unchanged"]
    assert "ZKEY0001" not in results["metadata_changed"]


# ── reindex-storm gate: Calibre hash via the Indexer stays identical ─


def test_calibre_resolve_hash_matches_extracted_hash(tmp_path):
    """The reindex-storm gate: routing Calibre through the adapter must NOT
    change the stored hash relative to the extracted-metadata hash. If this
    breaks, every Calibre book re-indexes on the next scan."""
    from src.archilles.watchdog import _calibre_metadata_for_hash
    from src.adapters.calibre_adapter import CalibreAdapter

    # Minimal Calibre library (mirrors the calibre_library fixture).
    con = sqlite3.connect(tmp_path / "metadata.db")
    con.executescript(
        """
        CREATE TABLE books (id INTEGER PRIMARY KEY, title TEXT, path TEXT, pubdate TEXT, has_cover INTEGER DEFAULT 0);
        CREATE TABLE authors (id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE books_authors_link (id INTEGER PRIMARY KEY, book INTEGER, author INTEGER);
        CREATE TABLE tags (id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE books_tags_link (id INTEGER PRIMARY KEY, book INTEGER, tag INTEGER);
        CREATE TABLE comments (book INTEGER, text TEXT);
        CREATE TABLE publishers (id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE books_publishers_link (id INTEGER PRIMARY KEY, book INTEGER, publisher INTEGER);
        CREATE TABLE ratings (id INTEGER PRIMARY KEY, rating INTEGER);
        CREATE TABLE books_ratings_link (id INTEGER PRIMARY KEY, book INTEGER, rating INTEGER);
        """
    )
    con.execute("INSERT INTO books (id, title, path, pubdate) VALUES (1, 'Testbuch', 'A/T (1)', '2019-03-01 00:00:00+00:00')")
    con.execute("INSERT INTO authors (id, name) VALUES (1, 'Anna Autor')")
    con.execute("INSERT INTO books_authors_link (book, author) VALUES (1, 1)")
    con.execute("INSERT INTO tags (id, name) VALUES (1, 'History')")
    con.execute("INSERT INTO books_tags_link (book, tag) VALUES (1, 1)")
    con.execute("INSERT INTO comments (book, text) VALUES (1, 'A comment.')")
    con.execute("INSERT INTO publishers (id, name) VALUES (1, 'Verlag')")
    con.execute("INSERT INTO books_publishers_link (book, publisher) VALUES (1, 1)")
    con.commit()
    con.close()

    adapter = CalibreAdapter(tmp_path)
    idx = _indexer_with_adapter(adapter)
    extracted_meta = _calibre_metadata_for_hash(tmp_path)[1]

    # The value _resolve_metadata_hash stores (adapter path) must equal the old
    # extracted-metadata hash for the identical book.
    assert idx._resolve_metadata_hash("1", extracted_meta) == hashing.compute_metadata_hash(extracted_meta)
