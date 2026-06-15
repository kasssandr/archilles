"""Regression tests for the P0 fixes from the 2026-06-10 code review.

Each test corresponds to a numbered finding in
docs/internal/CODE_REVIEW_2026-06-10.md and is written so that it FAILS
on the pre-fix code and passes after the fix.

Findings covered:
    7.1  batch_index --all crashes (ORDER BY ratings.rating without JOIN)
    1.1  missing SQL quoting in LanceDB filter strings (apostrophes)
    8.1  tag_filter documented as AND but implemented as OR
    5.2  TypeError when sorting mixed str/int years in unified merge
    7.6  KeyError printing Zotero scan errors (doc_id vs calibre_id)
    2.6  chardet {'encoding': None} breaks the txt/html encoding fallback
    7.3  tags containing commas corrupt the watchdog metadata hash
    7.5  --reset-db leaves a stale progress.db behind
"""

import sqlite3

import numpy as np
import pytest


# ── Shared fixture: minimal Calibre-like metadata.db ─────────────────────

@pytest.fixture
def calibre_library(tmp_path):
    """Temp library dir with a minimal Calibre-like metadata.db (one book).

    The book carries a tag WITH a comma ("Blut, Bund, Buch") to exercise
    finding 7.3, plus a rating and an author for 7.1 / 5.2.
    """
    con = sqlite3.connect(tmp_path / "metadata.db")
    con.executescript(
        """
        CREATE TABLE books (id INTEGER PRIMARY KEY, title TEXT, path TEXT,
                            pubdate TEXT, has_cover INTEGER DEFAULT 0);
        CREATE TABLE authors (id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE books_authors_link (id INTEGER PRIMARY KEY, book INTEGER, author INTEGER);
        CREATE TABLE tags (id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE books_tags_link (id INTEGER PRIMARY KEY, book INTEGER, tag INTEGER);
        CREATE TABLE comments (book INTEGER, text TEXT);
        CREATE TABLE publishers (id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE books_publishers_link (id INTEGER PRIMARY KEY, book INTEGER, publisher INTEGER);
        CREATE TABLE ratings (id INTEGER PRIMARY KEY, rating INTEGER);
        CREATE TABLE books_ratings_link (id INTEGER PRIMARY KEY, book INTEGER, rating INTEGER);
        CREATE TABLE identifiers (id INTEGER PRIMARY KEY, book INTEGER, type TEXT, val TEXT);
        CREATE TABLE data (id INTEGER PRIMARY KEY, book INTEGER, format TEXT);
        """
    )
    con.execute(
        "INSERT INTO books (id, title, path, pubdate) "
        "VALUES (1, 'Testbuch', 'Anna Autor/Testbuch (1)', '2019-03-01 00:00:00+00:00')"
    )
    con.execute("INSERT INTO authors (id, name) VALUES (1, 'Anna Autor')")
    con.execute("INSERT INTO books_authors_link (book, author) VALUES (1, 1)")
    con.execute("INSERT INTO tags (id, name) VALUES (1, 'Blut, Bund, Buch')")
    con.execute("INSERT INTO tags (id, name) VALUES (2, 'History')")
    con.execute("INSERT INTO books_tags_link (book, tag) VALUES (1, 1)")
    con.execute("INSERT INTO books_tags_link (book, tag) VALUES (1, 2)")
    con.execute("INSERT INTO ratings (id, rating) VALUES (1, 8)")
    con.execute("INSERT INTO books_ratings_link (book, rating) VALUES (1, 1)")
    con.commit()
    con.close()
    return tmp_path


# ── 7.1: batch_index --all must not crash on a Calibre library ───────────

def test_get_all_books_executes_without_sql_error(calibre_library):
    """ORDER BY referenced ratings.rating without joining the ratings tables."""
    from scripts.batch_index import get_all_books

    # Pre-fix: sqlite3.OperationalError ("no such column: ratings.rating").
    # The book has no files on disk, so an empty list is the expected result —
    # the point is that the SQL executes at all.
    books = get_all_books(calibre_library)
    assert isinstance(books, list)


# ── 1.1: SQL quoting in LanceDB filter strings ────────────────────────────

class TestLanceDBQuoting:
    def test_sql_quote_doubles_apostrophes(self):
        from src.storage.lancedb_store import _sql_quote

        assert _sql_quote("O'Brien") == "O''Brien"
        assert _sql_quote("no quotes") == "no quotes"

    def test_build_filter_escapes_book_id(self, tmp_path):
        from src.storage.lancedb_store import LanceDBStore

        store = LanceDBStore(db_path=str(tmp_path / "db"))
        filt = store._build_filter(book_id="O'Brien_Ulysses_42")
        assert "O''Brien_Ulysses_42" in filt

    def test_roundtrip_with_apostrophe_in_book_id(self, tmp_path):
        """get/delete by book_id must work for books like O'Brien."""
        from src.storage.lancedb_store import LanceDBStore

        store = LanceDBStore(db_path=str(tmp_path / "db"))
        book_id = "O'Brien_Ulysses_42"
        chunks = [
            {"id": f"{book_id}_chunk_{i}", "text": f"chunk {i}", "book_id": book_id}
            for i in range(2)
        ]
        store.add_chunks(chunks, np.random.rand(2, 8).astype(np.float32))

        assert len(store.get_by_book_id(book_id)) == 2
        assert store.delete_by_book_id(book_id) == 2


# ── 8.1: tag_filter must use AND logic (as documented in the MCP schema) ──

def test_tag_filter_requires_all_tags():
    from src.service.archilles_service import matches_tag_filter

    tags = "Geschichte, Philosophie, Antike"
    assert matches_tag_filter(tags, ["Geschichte", "Philosophie"])
    assert matches_tag_filter(tags, ["antike"])  # case-insensitive
    # Pre-fix OR logic returned True here:
    assert not matches_tag_filter(tags, ["Geschichte", "Theologie"])
    assert not matches_tag_filter("", ["Geschichte"])


# ── 5.2: year sorting across sources with mixed str/int years ────────────

def test_year_sort_key_handles_mixed_types():
    from src.calibre_mcp.unified_server import _year_sort_key

    rows = [{"year": "2019"}, {"year": 2003}, {"year": None}, {"year": "n.d."}]
    # Pre-fix: TypeError ('<' not supported between str and int).
    ordered = sorted(rows, key=lambda x: _year_sort_key(x.get("year")), reverse=True)
    assert [r["year"] for r in ordered][:2] == ["2019", 2003]


def test_analyzer_returns_int_year(calibre_library):
    from src.calibre_mcp.calibre_analyzer import CalibreAnalyzer

    with CalibreAnalyzer(calibre_library / "metadata.db") as analyzer:
        res = analyzer.list_books_by_author("Autor")
    assert res["books"], "fixture book not found by author"
    assert isinstance(res["books"][0]["year"], int)


# ── 7.6: error printing must survive Zotero-style error dicts ─────────────

def test_print_results_handles_zotero_errors(capsys):
    from scripts.watchdog import _print_results

    results = {
        "new_books": [],
        "fulltext_pending": [],
        "metadata_changed": [],
        "annotations_changed": [],
        "unchanged": [],
        "errors": [
            {"doc_id": "AB3CD9EF", "error": "boom"},      # Zotero shape
            {"calibre_id": 5, "error": "kaputt"},          # Calibre shape
        ],
        "delta_updates": 0,
        "delta_time": 0.0,
        "scanned": 1,
        "total_time": 0.1,
    }
    # Pre-fix: KeyError 'calibre_id' on the Zotero-shaped error dict.
    _print_results(results, json_mode=False)
    out = capsys.readouterr().out
    assert "AB3CD9EF" in out and "kaputt" in out


# ── 2.6: chardet returning {'encoding': None} must not break extraction ──

def test_txt_extractor_survives_chardet_none(tmp_path, monkeypatch):
    from src.extractors import txt_extractor as te

    monkeypatch.setattr(te.chardet, "detect", lambda raw: {"encoding": None})
    p = tmp_path / "note.txt"
    p.write_text("Grüße aus Köln und München. " * 20, encoding="utf-8")

    # Pre-fix: raw_data.decode(None) -> TypeError, wrapped as ExtractionError.
    result = te.TXTExtractor().extract(p)
    assert "Grüße" in result.full_text


def test_html_extractor_survives_chardet_none(tmp_path, monkeypatch):
    from src.extractors import html_extractor as he

    monkeypatch.setattr(he.chardet, "detect", lambda raw: {"encoding": None})
    p = tmp_path / "page.html"
    p.write_text("<html><body><p>Grüße aus Köln.</p></body></html>", encoding="utf-8")

    result = he.HTMLExtractor().extract(p)
    assert "Grüße" in result.full_text


# ── 7.3: tags containing commas must survive the watchdog hash path ──────

def test_watchdog_metadata_preserves_comma_tags(calibre_library):
    from src.archilles.watchdog import _calibre_metadata_for_hash

    meta = _calibre_metadata_for_hash(calibre_library)[1]
    # Pre-fix: GROUP_CONCAT + comma split exploded the tag into
    # ['Blut', 'Buch', 'Bund', 'History'] -> permanently diverging hash.
    assert meta["tags"] == ["Blut, Bund, Buch", "History"]


def test_watchdog_hash_matches_adapter_hash(calibre_library):
    """The watchdog hash must equal CalibreAdapter.compute_metadata_hash —
    otherwise every scan re-indexes the book (finding 7.3 consequence)."""
    from src.archilles.watchdog import _calibre_metadata_for_hash, _compute_metadata_hash
    from src.adapters.calibre_adapter import CalibreAdapter

    meta = _calibre_metadata_for_hash(calibre_library)[1]
    adapter_hash = CalibreAdapter(calibre_library).compute_metadata_hash("1")
    assert _compute_metadata_hash(meta) == adapter_hash


# ── 7.5: obsolet seit 7.14 — kein ProgressTracker mehr ───────────────────
# _reset_progress_tracker und progress.db wurden in 7.14 Task 1 entfernt.
# Skip-existing kommt ausschließlich aus LanceDB (get_indexed_book_ids, phase-aware).
# Der Test ist absichtlich leer gelassen statt gelöscht, damit der Kommentar sichtbar bleibt.
