"""Tests for the ``pending_external`` marker in LanceDBStore (Hardware-Tiers-V2 §12).

The marker distinguishes *provisionally light* chunks (mode=full-external, waiting
for an external hierarchical re-embed) from *deliberately light* chunks
(mode=light, final). ``chunk_type`` alone cannot tell them apart — both are flat.

The lifecycle the marker supports:
    light placeholder  → --prepare-pending-external → external embed replaces it
The watchdog sets the marker on provisional indexing; the discovery path reads it;
the external embed replaces the chunks (the new chunks carry no marker → cleared).
"""

import numpy as np
import pytest

from src.storage.lancedb_store import LanceDBStore


@pytest.fixture
def store(tmp_path):
    return LanceDBStore(db_path=str(tmp_path / "test_db"))


def _make_chunks(n, book_id="book", calibre_id=0):
    return [
        {
            "id": f"{book_id}_chunk_{i}",
            "text": f"chunk {i} text about something",
            "book_id": book_id,
            "calibre_id": calibre_id,
            "chunk_index": i,
            "chunk_type": "content",
        }
        for i in range(n)
    ]


def _emb(n, dim=1024):
    v = np.random.randn(n, dim).astype(np.float32)
    return v / np.linalg.norm(v, axis=1, keepdims=True)


class TestSchema:
    def test_pending_external_in_schema(self):
        assert "pending_external" in LanceDBStore.SCHEMA

    def test_pending_external_in_migratable_columns(self):
        assert "pending_external" in LanceDBStore._MIGRATABLE_COLUMNS


class TestDefault:
    def test_normal_chunks_are_not_pending(self, store):
        """Plain add_chunks must default pending_external to 0 (not pending)."""
        store.add_chunks(_make_chunks(2, book_id="plain"), _emb(2))
        assert store.get_pending_external_book_ids() == set()


class TestMarkAndDiscover:
    def test_mark_then_discover(self, store):
        store.add_chunks(_make_chunks(3, book_id="prov", calibre_id=7), _emb(3))
        marked = store.mark_pending_external("prov")
        assert marked == 3
        assert store.get_pending_external_book_ids() == {"prov"}

    def test_only_marked_books_discovered(self, store):
        store.add_chunks(_make_chunks(2, book_id="a"), _emb(2))
        store.add_chunks(_make_chunks(2, book_id="b"), _emb(2))
        store.mark_pending_external("a")
        assert store.get_pending_external_book_ids() == {"a"}


class TestClear:
    def test_clear_removes_from_discovery(self, store):
        store.add_chunks(_make_chunks(2, book_id="prov"), _emb(2))
        store.mark_pending_external("prov")
        assert store.get_pending_external_book_ids() == {"prov"}
        cleared = store.clear_pending_external("prov")
        assert cleared == 2
        assert store.get_pending_external_book_ids() == set()

    def test_replacing_chunks_clears_marker_implicitly(self, store):
        """The external-embed replacement deletes the marked flat chunks and
        adds fresh ones with no marker → the book drops out of discovery."""
        store.add_chunks(_make_chunks(2, book_id="prov"), _emb(2))
        store.mark_pending_external("prov")
        store.delete_by_book_id("prov")
        # hierarchical replacement carries no marker
        store.add_chunks(_make_chunks(4, book_id="prov"), _emb(4))
        assert store.get_pending_external_book_ids() == set()
