"""Tests for book_id-based prepared-JSONL naming (review 2026-07-03, finding 5.1).

``prepare_book`` used to name its output ``{calibre_id}.jsonl``. Non-Calibre
sources (Zotero keys, folder ids) have no calibre_id, so every item collided
on ``0.jsonl``: the first item wrote it, every further item was skipped as
"already prepared" — one prepared book per library. The embed checkpoint key
had the same collapse (``file_key = '0'`` for all).

Naming is now keyed by the adapter-unique ``book_id``. For Calibre books,
``book_id`` is the numeric id as a string, so existing ``{calibre_id}.jsonl``
corpora and old embed checkpoints keep matching.
"""

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from src.archilles.engine.indexing import Indexer, prepared_jsonl_name


# ── prepared_jsonl_name ─────────────────────────────────────────────


class TestPreparedJsonlName:
    def test_calibre_numeric_id_unchanged(self):
        # Backward compatibility: existing corpora are named {calibre_id}.jsonl
        # and for Calibre books book_id == str(calibre_id).
        assert prepared_jsonl_name("8127") == "8127.jsonl"

    def test_zotero_key_used_verbatim(self):
        assert prepared_jsonl_name("ABCD1234") == "ABCD1234.jsonl"

    def test_unsafe_characters_replaced(self):
        name = prepared_jsonl_name('notes/sub:file?"x"')
        assert name.endswith(".jsonl")
        assert not set('<>:"/\\|?*') & set(name)

    def test_sanitised_names_cannot_collide(self):
        # Distinct ids that sanitise to the same base must yield distinct names.
        assert prepared_jsonl_name("a/b") != prepared_jsonl_name("a_b")
        assert prepared_jsonl_name("a/b") != prepared_jsonl_name("a:b")

    def test_empty_id_still_yields_usable_name(self):
        name = prepared_jsonl_name("")
        assert name.endswith(".jsonl")
        assert Path(name).stem  # non-empty stem

    def test_deterministic(self):
        assert prepared_jsonl_name("a/b") == prepared_jsonl_name("a/b")


# ── prepare_book: one file per book, adapter-agnostic ───────────────


def _fake_extract(book_path):
    return SimpleNamespace(
        chunks=[{"text": "some meaningful text", "metadata": {}}],
        metadata=SimpleNamespace(
            file_path=Path(book_path),
            detected_format="txt",
            total_words=3,
            total_pages=None,
        ),
    )


def _prepare_rag():
    """Minimal mock covering the surface prepare_book touches.

    ``_adapter=None`` + a book file outside any Calibre library means
    ``_extract_metadata`` returns ``{}`` — i.e. no calibre_id, exactly the
    non-Calibre case that used to collide on 0.jsonl.
    """
    return SimpleNamespace(
        extractor=SimpleNamespace(extract=_fake_extract),
        hierarchical=False,
        _prepare_chunk_size=512,
        _prepare_overlap=64,
        _adapter=None,
        _CHUNK_META_KEYS=[],
    )


class TestPrepareBookPerItemFiles:
    def test_two_non_calibre_books_get_distinct_files(self, tmp_path):
        """Regression 5.1: without a calibre_id, the second book used to be
        skipped as 'already prepared' because both targeted 0.jsonl."""
        book_a = tmp_path / "a.txt"
        book_a.write_text("aaa", encoding="utf-8")
        book_b = tmp_path / "b.txt"
        book_b.write_text("bbb", encoding="utf-8")
        out = tmp_path / "prepared"

        indexer = Indexer(_prepare_rag())
        res_a = indexer.prepare_book(str(book_a), "ZKEYAAA1", output_dir=str(out))
        res_b = indexer.prepare_book(str(book_b), "ZKEYBBB2", output_dir=str(out))

        assert res_a["status"] == "prepared"
        assert res_b["status"] == "prepared", (
            "second non-Calibre book must not be skipped as 'already prepared'"
        )
        files = sorted(p.name for p in out.glob("*.jsonl"))
        assert files == ["ZKEYAAA1.jsonl", "ZKEYBBB2.jsonl"]

    def test_same_book_still_skipped_on_second_prepare(self, tmp_path):
        book = tmp_path / "a.txt"
        book.write_text("aaa", encoding="utf-8")
        out = tmp_path / "prepared"

        indexer = Indexer(_prepare_rag())
        first = indexer.prepare_book(str(book), "ZKEYAAA1", output_dir=str(out))
        second = indexer.prepare_book(str(book), "ZKEYAAA1", output_dir=str(out))

        assert first["status"] == "prepared"
        assert second["status"] == "already_prepared"


# ── embed_prepared: checkpoint key per book, not per calibre_id ─────


def _fake_encode(texts, show_progress_bar=False, convert_to_numpy=True):
    n = len(texts) if isinstance(texts, list) else 1
    return np.zeros((n, 1024), dtype=np.float32)


def _embed_rag():
    return SimpleNamespace(
        embedding_model=SimpleNamespace(encode=_fake_encode),
        store=SimpleNamespace(
            get_book_state=lambda book_id: {
                "total": 0, "has_content": False, "content_count": 0,
                "metadata_hash": "", "annotation_hash": "", "format": "",
            },
            add_chunks=lambda chunks, embeddings: len(chunks),
            delete_by_book_id_except_annotations=lambda book_id: 0,
            clear_pending_external=lambda book_id: 0,
            get_pending_external_book_ids=lambda: set(),
        ),
        device="cpu",
        batch_size=16,
    )


def _write_jsonl(dir_path, book_id, calibre_id=0):
    header = {
        "_header": True,
        "calibre_id": calibre_id,
        "book_id": book_id,
        "book_metadata": {},
        "chunk_count": 1,
        "prepared_at": "x",
    }
    with open(dir_path / f"{book_id}.jsonl", "w", encoding="utf-8") as f:
        f.write(json.dumps(header) + "\n")
        f.write(json.dumps({
            "id": f"{book_id}_chunk_0", "text": "t",
            "book_id": book_id, "chunk_index": 0, "chunk_type": "content",
        }) + "\n")


class TestEmbedCheckpointKey:
    def test_two_non_calibre_books_both_embedded(self, tmp_path):
        """Regression 5.1: file_key was str(header['calibre_id']) — '0' for
        every non-Calibre book, so the second file was skipped as already
        embedded within the same run."""
        _write_jsonl(tmp_path, "KEYAAAA1")
        _write_jsonl(tmp_path, "KEYBBBB2")

        result = Indexer(_embed_rag()).embed_prepared(str(tmp_path), mode="local")

        assert result["total_books"] == 2, (
            f"both non-Calibre books must be embedded, got {result['total_books']}"
        )


# ── batch_prepare: pre-check uses the same name prepare_book writes ─


class TestBatchPreparePrecheck:
    def test_precheck_matches_prepare_book_naming(self, tmp_path):
        """The outer skip check in batch_prepare must look for the same file
        name prepare_book writes — for ids needing sanitisation the old
        f"{book['id']}.jsonl" diverged from the written file."""
        from scripts.batch_index import batch_prepare

        key = "vault:notes/one"
        header = {
            "_header": True, "calibre_id": 0, "book_id": key,
            "book_metadata": {}, "chunk_count": 3, "prepared_at": "x",
        }
        with open(tmp_path / prepared_jsonl_name(key), "w", encoding="utf-8") as f:
            f.write(json.dumps(header) + "\n")

        class ExplodingRAG:
            def prepare_book(self, *a, **k):
                raise AssertionError(
                    "prepare_book must not run for an already-prepared book"
                )

        books = [{
            "id": key, "title": "T", "author": "A",
            "formats": [{"format": "PDF", "path": "x.pdf"}],
        }]
        stats = batch_prepare(books, ExplodingRAG(), output_dir=str(tmp_path),
                              dry_run=False)

        assert stats["skipped"] == 1
        assert stats["prepared"] == 0
        assert stats["failed"] == 0
