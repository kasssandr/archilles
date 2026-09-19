"""The context head: ``Chapter › Section`` in front of what is embedded.

The head exists for the vector and for nothing else. It must therefore reach
the embedding on both indexing paths -- the live one and the two-phase one,
which embeds hours later out of a JSONL -- and reach neither the stored text
nor the store's columns. The switch is index-wide (``IndexRecipe.context_head``)
because it changes what a vector means, and it is off until P-M1 has measured
whether the head helps at all.
"""

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from src.archilles.context_head import context_head, embed_text_for
from src.archilles.engine.core import ArchillesRAG
from src.archilles.engine.indexing import Indexer
from src.archilles.recipe import IndexRecipe, default_recipe
from src.storage.lancedb_store import LanceDBStore

TEXT = "Vielmehr ging es um die Aneignung der Form und der Motive."
HEAD = "I. Aneignung als Rechtsbegriff › A. Der Begriff"


def _chunk(text=TEXT, **meta):
    return {"text": text, "metadata": {"chapter": "I. Aneignung als Rechtsbegriff",
                                       "section_title": "A. Der Begriff", **meta}}


# what the head is ----------------------------------------------------------

def test_the_head_is_the_chapter_and_the_section():
    assert context_head(_chunk()["metadata"]) == HEAD


def test_a_missing_part_falls_away_rather_than_leaving_a_separator():
    assert context_head({"chapter": "I. Aneignung"}) == "I. Aneignung"
    assert context_head({"section_title": "A. Der Begriff"}) == "A. Der Begriff"
    assert context_head({"chapter": "", "section_title": None}) == ""
    assert context_head({}) == ""


def test_without_the_switch_there_is_no_embed_text():
    assert embed_text_for(_chunk(), False) is None


def test_with_the_switch_the_head_stands_in_front_of_the_text():
    assert embed_text_for(_chunk(), True) == f"{HEAD}\n\n{TEXT}"


def test_a_chunk_that_knows_neither_chapter_nor_section_is_embedded_as_it_is():
    """No head is not an empty head: the caller embeds the text unchanged."""
    assert embed_text_for({"text": TEXT, "metadata": {}}, True) is None


# the live path -------------------------------------------------------------

class _Store:
    """The store, as much of it as the two indexing paths touch."""

    def __init__(self):
        self.rows = []

    def add_chunks(self, chunks, vectors):
        self.rows.extend(chunks)
        return len(chunks)

    def get_book_state(self, book_id):
        return {"total": 0, "has_content": False, "content_count": 0,
                "metadata_hash": "", "annotation_hash": "", "format": ""}

    def delete_by_book_id(self, book_id):
        return 0

    def delete_by_book_id_except_annotations(self, book_id):
        return 0

    def get_by_book_id(self, book_id, limit=100):
        return []

    def get_pending_external_book_ids(self):
        return set()

    def clear_pending_external(self, book_id):
        return 0

    def create_fts_index(self):
        return None


def _extraction(tmp_path, chunks):
    return SimpleNamespace(
        chunks=chunks,
        metadata=SimpleNamespace(detected_format="scriptor", file_path=tmp_path / "book.md",
                                 total_words=10, total_pages=1, extraction_method="test",
                                 language=None),
    )


def _rag(store, recipe, embedded):
    def encode(texts, **kw):
        embedded.extend(texts)
        return np.zeros((len(texts), 8), dtype=np.float32)

    return SimpleNamespace(
        _CHUNK_META_KEYS=ArchillesRAG._CHUNK_META_KEYS, store=store, _adapter=None,
        use_modular_pipeline=False, hierarchical=False, batch_size=8, device="cpu",
        _prepare_chunk_size=512, _prepare_overlap=64, languages=None, recipe=recipe,
        embedding_model=SimpleNamespace(encode=encode),
    )


def _indexer(tmp_path, recipe, embedded, store=None):
    rag = _rag(store or _Store(), recipe, embedded)
    rag.extractor = SimpleNamespace(
        extract=lambda path: _extraction(tmp_path, [_chunk()]))
    indexer = Indexer(rag)
    indexer._extract_metadata = lambda p: {"title": "T", "author": "A"}
    return indexer


def test_the_live_path_embeds_the_head_and_stores_the_text_without_it(tmp_path):
    book = tmp_path / "book.pdf"
    book.write_bytes(b"%PDF-1.4")
    store, embedded = _Store(), []
    _indexer(tmp_path, IndexRecipe(context_head=True), embedded, store).index_book(
        str(book), book_id="b1", force=True)

    assert embedded == [f"{HEAD}\n\n{TEXT}"]
    assert store.rows[0]["text"] == TEXT
    assert store.rows[0]["embed_text"] == f"{HEAD}\n\n{TEXT}"


def test_without_the_switch_the_live_path_is_what_it_was(tmp_path):
    book = tmp_path / "book.pdf"
    book.write_bytes(b"%PDF-1.4")
    store, embedded = _Store(), []
    _indexer(tmp_path, default_recipe(), embedded, store).index_book(
        str(book), book_id="b1", force=True)

    assert embedded == [TEXT]
    assert "embed_text" not in store.rows[0]


# the two-phase path --------------------------------------------------------

def test_prepare_writes_the_head_into_the_jsonl_and_embed_prepared_reads_it(tmp_path):
    """prepare_book and embed_prepared are separate runs, hours apart. The head
    travels in the file, or the two-phase path embeds something else than the
    live path does for the same book."""
    book = tmp_path / "book.pdf"
    book.write_bytes(b"%PDF-1.4")
    out = tmp_path / "prepared"
    embedded = []
    _indexer(tmp_path, IndexRecipe(context_head=True), embedded).prepare_book(
        str(book), book_id="b1", output_dir=str(out))

    lines = [json.loads(line) for line in
             next(out.glob("*.jsonl")).read_text(encoding="utf-8").splitlines()]
    chunk = lines[1]
    assert chunk["text"] == TEXT
    assert chunk["embed_text"] == f"{HEAD}\n\n{TEXT}"

    store, embedded = _Store(), []
    Indexer(_rag(store, IndexRecipe(context_head=True), embedded)).embed_prepared(
        str(out), mode="local")
    assert embedded == [f"{HEAD}\n\n{TEXT}"]
    assert store.rows[0]["text"] == TEXT


def test_a_prepared_chunk_without_a_head_is_embedded_as_it_stands(tmp_path):
    out = tmp_path / "prepared"
    out.mkdir()
    (out / "b1.jsonl").write_text(
        json.dumps({"_header": True, "book_id": "b1", "chunk_count": 1}) + "\n"
        + json.dumps({"id": "c1", "book_id": "b1", "text": TEXT, "chunk_index": 0}) + "\n",
        encoding="utf-8")
    store, embedded = _Store(), []
    Indexer(_rag(store, default_recipe(), embedded)).embed_prepared(str(out), mode="local")
    assert embedded == [TEXT]


# the store -----------------------------------------------------------------

def test_the_head_is_no_column_of_the_store(tmp_path):
    """add_chunks composes its records field by field, so a row is the same
    whether or not the chunk carried a head -- and a search result never shows
    a reader a heading the page does not print."""
    store = LanceDBStore(str(tmp_path / "db"))
    store.add_chunks([{"id": "c1", "book_id": "b1", "text": TEXT, "chunk_index": 0,
                       "embed_text": f"{HEAD}\n\n{TEXT}"}],
                     np.zeros((1, 1024), dtype=np.float32))
    row = store.get_by_id("c1")
    assert row["text"] == TEXT
    assert "embed_text" not in row


if __name__ == "__main__":
    pytest.main([__file__])
