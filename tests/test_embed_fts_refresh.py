"""Tests for the FTS index refresh after embed_prepared (review 2026-07-03,
finding 5.3).

``batch_index`` recreates the FTS index after an indexing run, but the
``embed`` path — the one that ingests the entire externally embedded
corpus — did not, so keyword/hybrid search ran against a stale (or
missing) FTS index until someone remembered to run `create-index` by
hand. ``embed_prepared`` now refreshes it itself once at least one book
was embedded, wrapped in try/except so an index-creation failure never
aborts an otherwise successful embed run.
"""

import json
from types import SimpleNamespace

import numpy as np
import pytest

from src.archilles.engine.indexing import Indexer


def _write_jsonl(dir_path, book_id, n_chunks):
    header = {
        "_header": True, "calibre_id": 0, "book_id": book_id,
        "book_metadata": {}, "chunk_count": n_chunks, "prepared_at": "x",
    }
    path = dir_path / f"{book_id}.jsonl"
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(header) + "\n")
        for i in range(n_chunks):
            f.write(json.dumps({
                "id": f"{book_id}_chunk_{i}", "text": f"text {i}",
                "book_id": book_id, "chunk_index": i, "chunk_type": "child",
            }) + "\n")
    return path


def _fake_encode(texts, show_progress_bar=False, convert_to_numpy=True):
    n = len(texts) if isinstance(texts, list) else 1
    return np.zeros((n, 1024), dtype=np.float32)


def _make_rag(events, *, fts_raises=False):
    def get_book_state(book_id):
        return {"total": 0, "has_content": False, "content_count": 0,
                "metadata_hash": "", "annotation_hash": "", "format": ""}

    def add_chunks(chunks, embeddings):
        events.append(("add", len(chunks)))
        return len(chunks)

    def create_fts_index():
        events.append(("fts",))
        if fts_raises:
            raise RuntimeError("fts backend unavailable")

    store = SimpleNamespace(
        get_book_state=get_book_state,
        add_chunks=add_chunks,
        delete_by_book_id_except_annotations=lambda book_id: 0,
        clear_pending_external=lambda book_id: 0,
        get_pending_external_book_ids=lambda: set(),
        create_fts_index=create_fts_index,
    )
    return SimpleNamespace(
        embedding_model=SimpleNamespace(encode=_fake_encode),
        store=store, device="cpu", batch_size=16,
    )


class TestFtsRefreshAfterEmbed:
    def test_fts_index_created_when_books_embedded(self, tmp_path):
        _write_jsonl(tmp_path, "Book_1", 2)
        events = []
        rag = _make_rag(events)

        result = Indexer(rag).embed_prepared(str(tmp_path), mode="local")

        assert result["total_books"] == 1
        assert ("fts",) in events
        # Refreshed after the book's chunks were added, not before.
        assert events.index(("fts",)) > events.index(("add", 2))

    def test_fts_index_not_created_for_zero_books_embedded(self, tmp_path):
        # Directory has no *.jsonl files at all.
        events = []
        rag = _make_rag(events)

        result = Indexer(rag).embed_prepared(str(tmp_path), mode="local")

        assert result["total_books"] == 0
        assert ("fts",) not in events

    def test_fts_index_failure_does_not_abort_run(self, tmp_path):
        _write_jsonl(tmp_path, "Book_1", 2)
        events = []
        rag = _make_rag(events, fts_raises=True)

        # Must not raise despite create_fts_index raising internally.
        result = Indexer(rag).embed_prepared(str(tmp_path), mode="local")

        assert result["total_books"] == 1
        assert ("fts",) in events
