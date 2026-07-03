"""Tests for embed_prepared's replace path preserving annotations (review 2.2)
and using book state instead of an arbitrary sampled row (review 2.4).

Prepared JSONL files carry only freshly parsed content/comment chunks — never
user annotations (highlights are imported separately and can be weeks newer
than the prepare files). The old replace deleted *every* chunk of the book,
silently dropping those annotations. The replace now keeps
``ChunkType.ANNOTATION`` rows.

2.4: the existence check reads full book state (``get_book_state``) instead of
sampling one arbitrary row, so a stub-only book (only a ``phase1_metadata``
chunk) gets its stub cleaned up when the real content arrives via embed.
"""

import json
from types import SimpleNamespace

import numpy as np
import pytest

from src.archilles.constants import ChunkType
from src.archilles.engine.indexing import Indexer
from src.storage.lancedb_store import LanceDBStore


@pytest.fixture
def store(tmp_path):
    return LanceDBStore(db_path=str(tmp_path / "test_db"))


def _emb(n, dim=1024):
    v = np.random.randn(n, dim).astype(np.float32)
    return v / np.linalg.norm(v, axis=1, keepdims=True)


def _chunk(book_id, i, chunk_type, text_prefix="text"):
    return {
        "id": f"{book_id}_{chunk_type}_{i}",
        "text": f"{text_prefix} {i} about the subject matter",
        "book_id": book_id,
        "calibre_id": 0,
        "chunk_index": i,
        "chunk_type": chunk_type,
    }


def _write_jsonl(dir_path, book_id, n_chunks, chunk_type="child"):
    header = {
        "_header": True, "calibre_id": 0, "book_id": book_id,
        "book_metadata": {}, "chunk_count": n_chunks, "prepared_at": "x",
    }
    path = dir_path / f"{book_id}.jsonl"
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(header) + "\n")
        for i in range(n_chunks):
            f.write(json.dumps(_chunk(book_id, i, chunk_type, "fresh")) + "\n")
    return path


def _make_rag(store):
    def fake_encode(texts, show_progress_bar=False, convert_to_numpy=True):
        n = len(texts) if isinstance(texts, list) else 1
        return np.zeros((n, 1024), dtype=np.float32)

    return SimpleNamespace(
        embedding_model=SimpleNamespace(encode=fake_encode),
        store=store, device="cpu", batch_size=16,
    )


def _types(store, book_id):
    rows = store.get_by_book_id(book_id, limit=1000)
    return sorted(r.get("chunk_type") for r in rows)


class TestAnnotationsSurviveReplace:
    def test_pending_replace_keeps_annotations_drops_old_content(self, tmp_path, store):
        book = "Prov_Book"
        # Existing provisional flat content + a user annotation.
        store.add_chunks(
            [_chunk(book, 0, ChunkType.CONTENT, "old"),
             _chunk(book, 1, ChunkType.CONTENT, "old")],
            _emb(2),
        )
        store.add_chunks([_chunk(book, 0, ChunkType.ANNOTATION, "highlight")], _emb(1))
        store.mark_pending_external(book)

        _write_jsonl(tmp_path, book, 3, chunk_type=ChunkType.CHILD)
        Indexer(_make_rag(store)).embed_prepared(str(tmp_path), mode="local")

        types = _types(store, book)
        # Old flat content gone, replaced by 3 fresh child chunks.
        assert types.count(ChunkType.CONTENT) == 0
        assert types.count(ChunkType.CHILD) == 3
        # The annotation survived the replace.
        assert types.count(ChunkType.ANNOTATION) == 1

    def test_pending_replace_clears_marker_even_via_annotation_rows(self, tmp_path, store):
        """mark_pending_external stamps the marker on ALL chunks incl. an
        already-present annotation. Since the annotation now survives the
        replace, the book must be explicitly de-flagged — otherwise the
        lingering marked annotation keeps it 'pending' forever."""
        book = "Prov_Book"
        store.add_chunks([_chunk(book, 0, ChunkType.CONTENT, "old")], _emb(1))
        store.add_chunks([_chunk(book, 0, ChunkType.ANNOTATION, "highlight")], _emb(1))
        store.mark_pending_external(book)
        assert store.get_pending_external_book_ids() == {book}

        _write_jsonl(tmp_path, book, 2, chunk_type=ChunkType.CHILD)
        Indexer(_make_rag(store)).embed_prepared(str(tmp_path), mode="local")

        assert store.get_pending_external_book_ids() == set()


class TestStubCleanup:
    def test_stub_only_book_replaced_and_annotation_survives(self, tmp_path, store):
        """2.4: a book that is only a phase1_metadata stub (no content) is not
        'skipped as existing' — embed adds content AND removes the stale stub,
        while any annotation survives."""
        book = "Stub_Book"
        store.add_chunks([_chunk(book, 0, ChunkType.PHASE1_METADATA, "stub")], _emb(1))
        store.add_chunks([_chunk(book, 0, ChunkType.ANNOTATION, "note")], _emb(1))

        _write_jsonl(tmp_path, book, 2, chunk_type=ChunkType.CHILD)
        result = Indexer(_make_rag(store)).embed_prepared(str(tmp_path), mode="local")

        assert result["total_books"] == 1
        types = _types(store, book)
        assert types.count(ChunkType.PHASE1_METADATA) == 0  # stub removed
        assert types.count(ChunkType.CHILD) == 2            # content added
        assert types.count(ChunkType.ANNOTATION) == 1       # annotation survived

    def test_final_content_book_still_skipped(self, tmp_path, store):
        """A non-pending book that already has real content is skipped (no
        duplicate embed) — has_content drives the skip, not total row count."""
        book = "Final_Book"
        store.add_chunks(
            [_chunk(book, 0, ChunkType.CHILD, "existing"),
             _chunk(book, 1, ChunkType.CHILD, "existing")],
            _emb(2),
        )
        _write_jsonl(tmp_path, book, 3, chunk_type=ChunkType.CHILD)
        result = Indexer(_make_rag(store)).embed_prepared(str(tmp_path), mode="local")

        assert result["total_books"] == 0
        assert result["skipped"] == 1
        assert _types(store, book).count(ChunkType.CHILD) == 2  # untouched
