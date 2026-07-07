"""Phase-1 stub indexing must persist annotations + annotation_hash.

Regression for the watchdog re-index loop: books that carry PDF/viewer
annotations but are only indexed as phase1 metadata stubs stored NO
annotation chunks and NO annotation_hash. The watchdog scan then compared
stored '' against the freshly computed hash, flagged the book as
annotations_changed on EVERY scan, and the phase-2 delta update rewrote the
stub — again without the hash — so the same books looped forever (observed
with calibre_ids 9960/9961/9963/10053/10073/10546).

Fix: _index_book_phase1 extracts annotations like the phase-2 path and
stores annotation chunks carrying the annotation_hash the scanner compares
against.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from src.archilles.constants import ChunkType
from src.archilles.engine.indexing import Indexer
from src.archilles.hashing import compute_annotation_hash


ANNOTATIONS = [
    {
        "type": "highlight", "source": "pdf", "page": 3,
        "highlighted_text": "A sentence worth remembering.", "notes": "",
    },
    {
        "type": "highlight", "source": "pdf", "page": 7,
        "highlighted_text": "Another highlighted passage.", "notes": "check this",
    },
]


def _fake_encode(texts, **kwargs):
    """Shape-compatible stand-in for SentenceTransformer.encode."""
    if isinstance(texts, str):
        return np.zeros(1024, dtype=np.float32)
    return np.zeros((len(texts), 1024), dtype=np.float32)


class _RecordingStore:
    def __init__(self):
        self.chunks = []
        self.embedding_rows = 0

    def add_chunks(self, chunks, embeddings):
        self.chunks.extend(chunks)
        self.embedding_rows += len(embeddings)
        return len(chunks)

    def count(self):
        return len(self.chunks)


def _make_indexer(store):
    rag = SimpleNamespace(
        store=store,
        embedding_model=SimpleNamespace(encode=_fake_encode),
        _format_tags=lambda t: ", ".join(t) if isinstance(t, list) else t,
        _adapter=None,
    )
    return Indexer(rag)


def _dummy_book(tmp_path):
    book = tmp_path / "book.pdf"
    book.write_bytes(b"%PDF-1.4 dummy")
    return book


class TestPhase1PersistsAnnotations:
    def test_annotation_chunks_written_with_hash(self, tmp_path):
        """The stored annotation_hash must equal what the watchdog computes —
        otherwise the book is re-flagged on every scan."""
        store = _RecordingStore()
        idx = _make_indexer(store)
        with patch(
            "src.archilles.engine.indexing.get_combined_annotations",
            return_value={"annotations": ANNOTATIONS},
        ):
            result = idx._index_book_phase1(
                _dummy_book(tmp_path), "42", {"title": "T", "author": "A"}
            )

        annot_chunks = [c for c in store.chunks if c["chunk_type"] == ChunkType.ANNOTATION]
        assert annot_chunks, "phase1 stub must persist annotation chunks"
        expected = compute_annotation_hash(ANNOTATIONS)
        assert all(c["annotation_hash"] == expected for c in annot_chunks)
        # stub + annotations, embeddings row-aligned with chunks
        assert store.embedding_rows == len(store.chunks)
        assert result["chunks_indexed"] == 1 + len(annot_chunks)

    def test_no_annotations_writes_stub_only(self, tmp_path):
        store = _RecordingStore()
        idx = _make_indexer(store)
        with patch(
            "src.archilles.engine.indexing.get_combined_annotations",
            return_value={"annotations": []},
        ):
            result = idx._index_book_phase1(
                _dummy_book(tmp_path), "42", {"title": "T"}
            )

        assert [c["chunk_type"] for c in store.chunks] == [ChunkType.PHASE1_METADATA]
        assert result["chunks_indexed"] == 1

    def test_annotation_failure_is_non_fatal(self, tmp_path):
        """Extraction errors must not break stub indexing (matches phase-2)."""
        store = _RecordingStore()
        idx = _make_indexer(store)
        with patch(
            "src.archilles.engine.indexing.get_combined_annotations",
            side_effect=RuntimeError("boom"),
        ):
            result = idx._index_book_phase1(
                _dummy_book(tmp_path), "42", {"title": "T"}
            )

        assert [c["chunk_type"] for c in store.chunks] == [ChunkType.PHASE1_METADATA]
        assert result["chunks_indexed"] == 1


class TestWatchdogLoopRegression:
    def test_scan_hash_matches_after_phase1_index(self, tmp_path):
        """End-to-end through the real LanceDB store: after phase1-indexing an
        annotated book, the hash the watchdog scan loads must equal the freshly
        computed one — the exact comparison that looped before the fix."""
        from src.storage.lancedb_store import LanceDBStore

        store = LanceDBStore(db_path=str(tmp_path / "rag_db"))
        idx = _make_indexer(store)
        with patch(
            "src.archilles.engine.indexing.get_combined_annotations",
            return_value={"annotations": ANNOTATIONS},
        ):
            idx._index_book_phase1(
                _dummy_book(tmp_path), "42",
                {"title": "T", "author": "A", "calibre_id": 42},
            )

        stored = store.get_hashes_for_indexed_books()[42]["annotation_hash"]
        assert stored == compute_annotation_hash(ANNOTATIONS), (
            "watchdog would flag this book as annotations_changed on every scan"
        )
