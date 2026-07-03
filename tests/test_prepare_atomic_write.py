"""Tests for atomic prepare writes + skip-check validation (review 2026-07-03,
finding 2.3, remaining half — the embed-side chunk-count validation landed
with 2.1).

An interrupted prepare (process killed mid-write) used to leave a file with
a valid header and fewer chunk lines than ``header['chunk_count']`` promised.
Both skip checks (``prepare_book``'s own and ``batch_prepare``'s pre-check)
accepted that file forever as "already prepared" because they only parsed
the header line, never compared it against the actual chunk count. Fix:
``prepare_book`` now writes to a ``*.jsonl.tmp`` file and atomically
``os.replace()``s it onto the final name (a `*.jsonl` glob never matches a
leftover `.tmp`, so a crash mid-write is inert); both skip checks share
``read_prepared_header()``, which validates header AND line count and
returns ``None`` on any mismatch, causing a fall-through to re-prepare.
"""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts.batch_index import batch_prepare
from src.archilles.engine.indexing import (
    Indexer,
    prepared_jsonl_name,
    read_prepared_header,
)


def _write_raw(path, header, n_lines):
    """Write a header plus `n_lines` dummy chunk lines — used to simulate a
    file whose actual content may or may not match header['chunk_count']."""
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps(header) + "\n")
        for i in range(n_lines):
            f.write(json.dumps({"id": f"c{i}", "text": "x"}) + "\n")


# ── read_prepared_header: the shared validation helper ──────────────


class TestReadPreparedHeader:
    def test_valid_matching_file_returns_header(self, tmp_path):
        path = tmp_path / "book.jsonl"
        header = {"_header": True, "book_id": "b1", "chunk_count": 2,
                  "book_metadata": {}, "prepared_at": "x"}
        _write_raw(path, header, n_lines=2)

        result = read_prepared_header(path)

        assert result is not None
        assert result["chunk_count"] == 2

    def test_truncated_file_returns_none(self, tmp_path):
        # Header promises 5 chunks, only 2 are actually present — a kill
        # mid-write.
        path = tmp_path / "book.jsonl"
        header = {"_header": True, "book_id": "b1", "chunk_count": 5,
                  "book_metadata": {}, "prepared_at": "x"}
        _write_raw(path, header, n_lines=2)

        assert read_prepared_header(path) is None

    def test_missing_header_flag_returns_none(self, tmp_path):
        path = tmp_path / "book.jsonl"
        _write_raw(path, {"book_id": "b1", "chunk_count": 0}, n_lines=0)

        assert read_prepared_header(path) is None

    def test_malformed_json_returns_none(self, tmp_path):
        path = tmp_path / "book.jsonl"
        path.write_text("not json at all\n", encoding="utf-8")

        assert read_prepared_header(path) is None

    def test_zero_chunk_count_matching_zero_lines_is_valid(self, tmp_path):
        # A legitimately empty prepare (e.g. scanned PDF, no OCR) is not
        # "truncated" — chunk_count and actual lines both being 0 matches.
        path = tmp_path / "book.jsonl"
        header = {"_header": True, "book_id": "b1", "chunk_count": 0,
                  "book_metadata": {}, "prepared_at": "x"}
        _write_raw(path, header, n_lines=0)

        result = read_prepared_header(path)

        assert result is not None
        assert result["chunk_count"] == 0

    def test_missing_file_returns_none(self, tmp_path):
        assert read_prepared_header(tmp_path / "nope.jsonl") is None


# ── prepare_book's own skip check must re-prepare on truncation ─────


def _fake_extract(book_path):
    return SimpleNamespace(
        chunks=[{"text": "freshly prepared content", "metadata": {}}],
        metadata=SimpleNamespace(
            file_path=Path(book_path), detected_format="txt",
            total_words=3, total_pages=None,
        ),
    )


def _prepare_rag():
    return SimpleNamespace(
        extractor=SimpleNamespace(extract=_fake_extract),
        hierarchical=False,
        _prepare_chunk_size=512,
        _prepare_overlap=64,
        _adapter=None,
        _CHUNK_META_KEYS=[],
    )


class TestPrepareBookSkipCheckValidatesTruncation:
    def test_truncated_existing_file_is_re_prepared(self, tmp_path):
        book_id = "Kill_Mid_Write"
        out_dir = tmp_path / "prepared"
        out_dir.mkdir()
        existing = out_dir / prepared_jsonl_name(book_id)
        # Simulate a kill mid-write: header promises 9 chunks, 0 are present.
        _write_raw(existing, {
            "_header": True, "book_id": book_id, "chunk_count": 9,
            "book_metadata": {}, "prepared_at": "x",
        }, n_lines=0)

        book_path = tmp_path / "book.txt"
        book_path.write_text("content", encoding="utf-8")

        result = Indexer(_prepare_rag()).prepare_book(
            str(book_path), book_id, output_dir=str(out_dir)
        )

        assert result["status"] == "prepared", (
            "a truncated prepare file must be treated as not-prepared and "
            "re-prepared, not silently accepted as already_prepared"
        )
        # The file is now genuinely complete.
        header = read_prepared_header(existing)
        assert header is not None
        assert header["chunk_count"] == 1

    def test_valid_existing_file_still_skipped(self, tmp_path):
        book_id = "Genuinely_Done"
        out_dir = tmp_path / "prepared"
        out_dir.mkdir()
        book_path = tmp_path / "book.txt"
        book_path.write_text("content", encoding="utf-8")

        indexer = Indexer(_prepare_rag())
        first = indexer.prepare_book(str(book_path), book_id, output_dir=str(out_dir))
        second = indexer.prepare_book(str(book_path), book_id, output_dir=str(out_dir))

        assert first["status"] == "prepared"
        assert second["status"] == "already_prepared"


# ── batch_prepare's outer pre-check must also validate ───────────────


class ExplodingRAG:
    def prepare_book(self, *a, **k):
        raise AssertionError(
            "prepare_book must not run for a genuinely complete file"
        )


class RecordingRAG:
    def __init__(self):
        self.calls = []

    def prepare_book(self, book_path, book_id, output_dir=None):
        self.calls.append(book_id)
        return {"book_id": book_id, "status": "prepared", "chunk_count": 1}


class TestBatchPreparePrecheckValidatesTruncation:
    def test_truncated_existing_file_triggers_re_prepare(self, tmp_path):
        book_id = "Kill_Mid_Write"
        _write_raw(tmp_path / prepared_jsonl_name(book_id), {
            "_header": True, "book_id": book_id, "chunk_count": 9,
            "book_metadata": {}, "prepared_at": "x",
        }, n_lines=0)

        rag = RecordingRAG()
        books = [{"id": book_id, "title": "T", "author": "A",
                 "formats": [{"format": "PDF", "path": "x.pdf"}]}]

        stats = batch_prepare(books, rag, output_dir=str(tmp_path), dry_run=False)

        assert rag.calls == [book_id], (
            "a truncated prepare file must not be accepted by the outer "
            "pre-check either"
        )
        assert stats["prepared"] == 1
        assert stats["skipped"] == 0

    def test_valid_existing_file_still_skipped(self, tmp_path):
        book_id = "Genuinely_Done"
        _write_raw(tmp_path / prepared_jsonl_name(book_id), {
            "_header": True, "book_id": book_id, "chunk_count": 1,
            "book_metadata": {}, "prepared_at": "x",
        }, n_lines=1)

        books = [{"id": book_id, "title": "T", "author": "A",
                 "formats": [{"format": "PDF", "path": "x.pdf"}]}]

        stats = batch_prepare(books, ExplodingRAG(), output_dir=str(tmp_path),
                              dry_run=False)

        assert stats["skipped"] == 1
        assert stats["prepared"] == 0


# ── atomic write: a crash mid-write must not produce a partial *.jsonl ──


class TestAtomicWrite:
    def test_crash_mid_write_leaves_no_partial_final_file(self, tmp_path, monkeypatch):
        import src.archilles.engine.indexing as indexing_module

        book_id = "Crashes_Mid_Write"
        out_dir = tmp_path / "prepared"
        out_dir.mkdir()
        book_path = tmp_path / "book.txt"
        book_path.write_text("content", encoding="utf-8")

        real_dumps = indexing_module.json.dumps
        call_count = {"n": 0}

        def flaky_dumps(obj, **kwargs):
            call_count["n"] += 1
            if call_count["n"] > 1:  # header line succeeds, first chunk crashes
                raise RuntimeError("simulated crash mid-write")
            return real_dumps(obj, **kwargs)

        monkeypatch.setattr(indexing_module.json, "dumps", flaky_dumps)

        with pytest.raises(RuntimeError):
            Indexer(_prepare_rag()).prepare_book(
                str(book_path), book_id, output_dir=str(out_dir)
            )

        final_file = out_dir / prepared_jsonl_name(book_id)
        assert not final_file.exists(), (
            "a crash mid-write must never leave a partial file at the final "
            "name — only a completed write may be renamed onto it"
        )
        # A leftover .tmp file (if any) must be invisible to the *.jsonl glob
        # embed_prepared and batch_prepare's discovery use.
        assert list(out_dir.glob("*.jsonl")) == []
