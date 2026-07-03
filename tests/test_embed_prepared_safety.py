"""Tests for embed_prepared failure safety (review 2026-07-03, finding 2.1).

The old flow deleted a book's existing chunks BEFORE reading the chunk lines
and BEFORE the (network-dependent) embedding succeeded: a truncated prepare
file or a mid-run embedder failure left the book deleted with nothing
re-added. The replace now happens only after embeddings exist, and
unreadable/truncated files are skipped per book without touching LanceDB.
"""

import json
from types import SimpleNamespace

import numpy as np
import pytest

from src.archilles.engine.indexing import Indexer


def _write_jsonl(dir_path, book_id, n_chunks, header_count=None):
    """Write a prepared JSONL; header_count overrides the true chunk count
    to simulate a truncated file."""
    header = {
        "_header": True, "calibre_id": 0, "book_id": book_id,
        "book_metadata": {},
        "chunk_count": n_chunks if header_count is None else header_count,
        "prepared_at": "x",
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


def _make_rag(events, *, content_books=(), pending=(), encode=None):
    """Recording mock; ``events`` collects ('embed'|'delete'|'add', detail)
    in call order so tests can assert the delete-after-embed ordering."""

    def default_encode(texts, show_progress_bar=False, convert_to_numpy=True):
        events.append(("embed", len(texts)))
        return np.zeros((len(texts), 1024), dtype=np.float32)

    def get_by_book_id(book_id, limit=1):
        return [{"chunk_type": "content"}] if book_id in content_books else []

    def add_chunks(chunks, embeddings):
        events.append(("add", len(chunks)))
        return len(chunks)

    def delete_by_book_id(book_id):
        events.append(("delete", book_id))
        return 2

    store = SimpleNamespace(
        get_by_book_id=get_by_book_id,
        add_chunks=add_chunks,
        delete_by_book_id=delete_by_book_id,
        get_pending_external_book_ids=lambda: set(pending),
    )
    return SimpleNamespace(
        embedding_model=SimpleNamespace(encode=encode or default_encode),
        store=store, device="cpu", batch_size=16,
    )


class TestReplaceOrdering:
    def test_delete_happens_only_after_successful_embed(self, tmp_path):
        book = "Prov_Book_7"
        _write_jsonl(tmp_path, book, 2)
        events = []
        rag = _make_rag(events, content_books={book}, pending={book})

        result = Indexer(rag).embed_prepared(str(tmp_path), mode="local")

        assert result["total_books"] == 1
        assert events == [("embed", 2), ("delete", book), ("add", 2)], (
            "delete must run after embedding succeeded, immediately before add"
        )

    def test_embedder_failure_leaves_existing_chunks_intact(self, tmp_path):
        book = "Prov_Book_7"
        _write_jsonl(tmp_path, book, 2)
        events = []

        def broken_encode(texts, show_progress_bar=False, convert_to_numpy=True):
            raise RuntimeError("remote embedder unreachable")

        rag = _make_rag(events, content_books={book}, pending={book},
                        encode=broken_encode)

        with pytest.raises(RuntimeError):
            Indexer(rag).embed_prepared(str(tmp_path), mode="local")

        assert ("delete", book) not in events, (
            "an embedder failure must not delete the provisional chunks"
        )
        # Checkpoint survives the abort so a retry resumes the run.
        assert (tmp_path / ".embed_checkpoint.json").exists()


class TestBrokenPrepareFiles:
    def test_truncated_file_skipped_without_delete(self, tmp_path):
        bad, good = "A_truncated", "B_good"
        _write_jsonl(tmp_path, bad, 1, header_count=5)  # header says 5, has 1
        _write_jsonl(tmp_path, good, 2)
        events = []
        rag = _make_rag(events, content_books={bad}, pending={bad})

        result = Indexer(rag).embed_prepared(str(tmp_path), mode="local")

        assert result["failed"] == 1
        assert result["total_books"] == 1  # the good book still embeds
        assert ("delete", bad) not in events, (
            "a truncated prepare file must never replace existing chunks"
        )

    def test_corrupt_chunk_line_skips_book_and_continues(self, tmp_path):
        good = "B_good"
        _write_jsonl(tmp_path, good, 2)
        header = {"_header": True, "calibre_id": 0, "book_id": "A_corrupt",
                  "book_metadata": {}, "chunk_count": 1, "prepared_at": "x"}
        with open(tmp_path / "A_corrupt.jsonl", "w", encoding="utf-8") as f:
            f.write(json.dumps(header) + "\n")
            f.write("{this is not json\n")
        events = []
        rag = _make_rag(events, content_books={"A_corrupt"},
                        pending={"A_corrupt"})

        result = Indexer(rag).embed_prepared(str(tmp_path), mode="local")

        assert result["failed"] == 1
        assert result["total_books"] == 1
        assert ("delete", "A_corrupt") not in events

    def test_header_only_zero_count_is_quiet_skip(self, tmp_path):
        # prepare_book legitimately writes chunk_count=0 for scanned PDFs
        # (no text without OCR) — that is a skip, not a failure.
        _write_jsonl(tmp_path, "Scanned_Book", 0)
        events = []
        rag = _make_rag(events)

        result = Indexer(rag).embed_prepared(str(tmp_path), mode="local")

        assert result["skipped"] == 1
        assert result["failed"] == 0
        assert events == []
