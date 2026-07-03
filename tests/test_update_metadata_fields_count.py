"""Tests for update_metadata_fields's return count (review 2026-07-03,
finding 5.6).

``update_metadata_fields`` "counted" its own update by loading up to 10 000
full rows (vectors included) via ``search().limit(10000).to_list()`` — on
every call, including every ``mark_pending_external``/``clear_pending_external``.
This is a pure efficiency fix (projected ``count_rows`` instead, the same
pattern ``has_parent_chunks`` already uses); behaviour must stay identical.
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


class TestUpdateMetadataFieldsCount:
    def test_returns_chunk_count_for_the_updated_book_only(self, store):
        store.add_chunks(_make_chunks(3, book_id="book_a"), _emb(3))
        store.add_chunks(_make_chunks(2, book_id="book_b"), _emb(2))

        count = store.update_metadata_fields("book_a", {"tags": "new-tag"})

        assert count == 3

    def test_zero_for_unknown_book(self, store):
        store.add_chunks(_make_chunks(2, book_id="book_a"), _emb(2))

        count = store.update_metadata_fields("nonexistent", {"tags": "x"})

        assert count == 0

    def test_field_is_actually_updated(self, store):
        store.add_chunks(_make_chunks(2, book_id="book_a"), _emb(2))

        store.update_metadata_fields("book_a", {"tags": "updated-tag"})

        rows = store.get_by_book_id("book_a", limit=10)
        assert len(rows) == 2
        assert all(r.get("tags") == "updated-tag" for r in rows)

    def test_mark_and_clear_pending_external_use_same_count_path(self, store):
        store.add_chunks(_make_chunks(4, book_id="book_a"), _emb(4))

        marked = store.mark_pending_external("book_a")
        cleared = store.clear_pending_external("book_a")

        assert marked == 4
        assert cleared == 4
