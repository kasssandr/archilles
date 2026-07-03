"""Tests for CHILD/PARENT in the metadata_hash preference sets (review
2026-07-03, finding 5.7).

``get_hashes_for_indexed_books``/``get_hashes_by_book_id`` pick a single
representative ``metadata_hash`` per book across its chunk rows, preferring
"real content" chunks over annotation rows. The preference check only
matched ``chunk_type in (CONTENT, CALIBRE_COMMENT)`` — hierarchical
``CHILD``/``PARENT`` rows never won, so whichever row happened to be
scanned first could stick even when a later CHILD/PARENT row carried the
correct hash. This worked by accident only because
``update_metadata_fields`` syncs all rows of a book to the same hash; any
per-type write path diverging would silently break change detection.
"""

import numpy as np
import pytest

from src.storage.lancedb_store import LanceDBStore


@pytest.fixture
def store(tmp_path):
    return LanceDBStore(db_path=str(tmp_path / "test_db"))


def _emb(n, dim=1024):
    v = np.random.randn(n, dim).astype(np.float32)
    return v / np.linalg.norm(v, axis=1, keepdims=True)


def _chunk(book_id, i, chunk_type, metadata_hash, calibre_id=0):
    return {
        "id": f"{book_id}_{chunk_type}_{i}",
        "text": f"text {i} about the subject",
        "book_id": book_id,
        "calibre_id": calibre_id,
        "chunk_index": i,
        "chunk_type": chunk_type,
        "metadata_hash": metadata_hash,
    }


class TestGetHashesForIndexedBooks:
    def test_child_hash_wins_over_earlier_annotation_row(self, store):
        # Annotation row scanned first (empty metadata_hash, as real
        # annotation rows carry), CHILD row with the real hash second.
        chunks = [
            _chunk("book_a", 0, "annotation", "", calibre_id=42),
            _chunk("book_a", 1, "child", "real-hash-abc", calibre_id=42),
        ]
        store.add_chunks(chunks, _emb(2))

        result = store.get_hashes_for_indexed_books()

        assert result[42]["metadata_hash"] == "real-hash-abc"

    def test_parent_hash_wins_over_earlier_annotation_row(self, store):
        chunks = [
            _chunk("book_b", 0, "annotation", "", calibre_id=43),
            _chunk("book_b", 1, "parent", "real-hash-xyz", calibre_id=43),
        ]
        store.add_chunks(chunks, _emb(2))

        result = store.get_hashes_for_indexed_books()

        assert result[43]["metadata_hash"] == "real-hash-xyz"


class TestGetHashesByBookId:
    def test_child_hash_wins_over_earlier_annotation_row(self, store):
        chunks = [
            _chunk("ZoteroKey1", 0, "annotation", ""),
            _chunk("ZoteroKey1", 1, "child", "real-hash-abc"),
        ]
        store.add_chunks(chunks, _emb(2))

        result = store.get_hashes_by_book_id()

        assert result["ZoteroKey1"]["metadata_hash"] == "real-hash-abc"

    def test_parent_hash_wins_over_earlier_annotation_row(self, store):
        chunks = [
            _chunk("ZoteroKey2", 0, "annotation", ""),
            _chunk("ZoteroKey2", 1, "parent", "real-hash-xyz"),
        ]
        store.add_chunks(chunks, _emb(2))

        result = store.get_hashes_by_book_id()

        assert result["ZoteroKey2"]["metadata_hash"] == "real-hash-xyz"
