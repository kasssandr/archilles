"""
Integration tests for LanceDB source_id support.

Tests the source_id column in LanceDBStore: add, query, filter, delete,
and backwards compatibility with calibre_id.
"""

import numpy as np
import pytest

from src.storage.lancedb_store import LanceDBStore


@pytest.fixture
def store(tmp_path):
    """Create a fresh LanceDB store in a temp directory."""
    return LanceDBStore(db_path=str(tmp_path / "test_db"))


def _make_chunks(n, book_id="test-book", calibre_id=0, source_id="", **overrides):
    """Create n dummy chunks with metadata."""
    chunks = []
    for i in range(n):
        chunk = {
            "id": f"{book_id}_chunk_{i}",
            "text": f"This is test chunk {i} about interesting topics.",
            "book_id": book_id,
            "book_title": overrides.get("book_title", "Test Book"),
            "author": overrides.get("author", "Test Author"),
            "calibre_id": calibre_id,
            "source_id": source_id,
            "chunk_index": i,
            "chunk_type": "content",
            "language": overrides.get("language", "eng"),
            "tags": overrides.get("tags", ""),
        }
        chunks.append(chunk)
    return chunks


def _random_embeddings(n, dim=1024):
    """Create random normalized embeddings."""
    vecs = np.random.randn(n, dim).astype(np.float32)
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    return vecs / norms


class TestSourceIdBasics:
    def test_source_id_stored(self, store):
        """source_id is written to and readable from the store."""
        chunks = _make_chunks(2, source_id="folder:abc123")
        store.add_chunks(chunks, _random_embeddings(2))
        results = store.get_by_source_id("folder:abc123")
        assert len(results) == 2
        assert all(r["source_id"] == "folder:abc123" for r in results)

    def test_source_id_fallback_from_calibre_id(self, store):
        """When source_id is not set, it falls back to str(calibre_id)."""
        chunks = _make_chunks(2, calibre_id=42)
        store.add_chunks(chunks, _random_embeddings(2))
        results = store.get_by_source_id("42")
        assert len(results) == 2

    def test_source_id_numeric_or_logic(self, store):
        """Numeric source_id queries match both source_id and calibre_id columns."""
        # Old-style chunk: only calibre_id set, source_id empty
        old_chunks = _make_chunks(1, book_id="old-book", calibre_id=99)
        old_chunks[0]["source_id"] = ""
        store.add_chunks(old_chunks, _random_embeddings(1))

        # New-style chunk: source_id = "99"
        new_chunks = _make_chunks(1, book_id="new-book", calibre_id=99, source_id="99")
        store.add_chunks(new_chunks, _random_embeddings(1))

        results = store.get_by_source_id("99")
        book_ids = {r["book_id"] for r in results}
        assert "old-book" in book_ids
        assert "new-book" in book_ids

    def test_source_id_non_numeric(self, store):
        """Non-numeric source_id only matches source_id column, not calibre_id."""
        chunks = _make_chunks(2, source_id="folder:xyz789")
        store.add_chunks(chunks, _random_embeddings(2))
        results = store.get_by_source_id("folder:xyz789")
        assert len(results) == 2

    def test_delete_by_source_id(self, store):
        """delete_by_source_id removes the right chunks."""
        chunks_a = _make_chunks(3, book_id="book-a", source_id="folder:aaa")
        chunks_b = _make_chunks(2, book_id="book-b", source_id="folder:bbb")
        store.add_chunks(chunks_a + chunks_b, _random_embeddings(5))
        assert store.count() == 5

        deleted = store.delete_by_source_id("folder:aaa")
        assert deleted == 3
        assert store.count() == 2

    def test_delete_by_source_id_numeric_fallback(self, store):
        """Numeric delete also catches old calibre_id-only rows."""
        chunks = _make_chunks(2, calibre_id=77)
        chunks[0]["source_id"] = ""
        chunks[1]["source_id"] = ""
        store.add_chunks(chunks, _random_embeddings(2))

        deleted = store.delete_by_source_id("77")
        assert deleted == 2


class TestSourceIdInSearch:
    def test_build_filter_source_id(self, store):
        """_build_filter generates correct SQL for source_id."""
        f = store._build_filter(source_id="folder:abc")
        assert "source_id = 'folder:abc'" in f
        assert "calibre_id" not in f  # non-numeric, no fallback

    def test_build_filter_source_id_numeric(self, store):
        """Numeric source_id generates OR fallback filter."""
        f = store._build_filter(source_id="42")
        assert "source_id = '42'" in f
        assert "calibre_id = 42" in f
        assert " OR " in f

    def test_build_filter_calibre_id_only(self, store):
        """Without source_id, calibre_id filter is used."""
        f = store._build_filter(calibre_id=42)
        assert "calibre_id = 42" in f
        assert "source_id" not in f

    def test_build_filter_source_id_overrides_calibre_id(self, store):
        """When both given, source_id takes precedence."""
        f = store._build_filter(source_id="folder:abc", calibre_id=99)
        assert "source_id = 'folder:abc'" in f
        assert "calibre_id = 99" not in f

    def test_vector_search_with_source_id_filter(self, store):
        """Vector search respects source_id filter."""
        chunks_a = _make_chunks(3, book_id="book-a", source_id="folder:aaa")
        chunks_b = _make_chunks(3, book_id="book-b", source_id="folder:bbb")
        emb = _random_embeddings(6)
        store.add_chunks(chunks_a + chunks_b, emb)

        query_vec = np.random.randn(1024).astype(np.float32)
        results = store.vector_search(query_vec, top_k=10, source_id="folder:aaa")
        assert all(r["source_id"] == "folder:aaa" for r in results)
        assert len(results) == 3


class TestSchemaMigration:
    def test_source_id_in_migratable_columns(self, store):
        """source_id is listed for auto-migration."""
        assert "source_id" in LanceDBStore._MIGRATABLE_COLUMNS

    def test_source_id_in_schema(self, store):
        """source_id is part of the defined schema."""
        assert "source_id" in LanceDBStore.SCHEMA
