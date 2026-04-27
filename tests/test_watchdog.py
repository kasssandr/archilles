"""Tests for the WatchdogScanner core logic.

Exercises the three pieces that were previously untested:
  1. Hash equivalence with ``archillesRAG._compute_metadata_hash`` — the
     watchdog must produce the exact same hash as the indexer, otherwise
     every scan would show false-positive metadata changes.
  2. ``_calibre_metadata_for_hash`` SQL: author ordering, tag aggregation,
     HTML stripping of comments.
  3. ``WatchdogScanner.scan()`` classification (new / metadata_changed /
     annotations_changed / unchanged / excluded-tag) against an in-memory
     Calibre metadata.db and a mocked LanceDB hash store.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest

from src.archilles.watchdog import (
    DEFAULT_EXCLUDED_TAGS,
    WatchdogScanner,
    _calibre_metadata_for_hash,
    _clean_html,
    _compute_metadata_hash,
)


# ---------------------------------------------------------------------------
# Helpers: build a minimal Calibre metadata.db in a tmp directory
# ---------------------------------------------------------------------------

def _create_calibre_db(library_path: Path) -> None:
    """Create the Calibre SQLite tables the watchdog actually reads."""
    db = sqlite3.connect(str(library_path / "metadata.db"))
    db.executescript("""
        CREATE TABLE books (
            id INTEGER PRIMARY KEY,
            title TEXT,
            path TEXT
        );
        CREATE TABLE authors (
            id INTEGER PRIMARY KEY,
            name TEXT
        );
        CREATE TABLE books_authors_link (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            book INTEGER,
            author INTEGER
        );
        CREATE TABLE comments (
            book INTEGER PRIMARY KEY,
            text TEXT
        );
        CREATE TABLE tags (
            id INTEGER PRIMARY KEY,
            name TEXT
        );
        CREATE TABLE books_tags_link (
            book INTEGER,
            tag INTEGER
        );
        CREATE TABLE publishers (
            id INTEGER PRIMARY KEY,
            name TEXT
        );
        CREATE TABLE books_publishers_link (
            book INTEGER,
            publisher INTEGER
        );
    """)
    db.commit()
    db.close()


def _add_book(
    library_path: Path,
    calibre_id: int,
    title: str,
    authors: list[str] | None = None,
    tags: list[str] | None = None,
    comments_html: str | None = None,
    publisher: str | None = None,
    book_dir: str | None = None,
    with_file: str | None = None,
) -> None:
    """Insert a book row plus optional tags/authors/comments/publisher.

    If ``with_file`` is given (e.g. "book.epub"), a zero-byte file with that
    extension is created in the book directory so that ``_discover_formats``
    picks it up.
    """
    book_dir = book_dir or f"{(authors or ['Unknown'])[0]}/{title} ({calibre_id})"
    full_book_path = library_path / book_dir
    full_book_path.mkdir(parents=True, exist_ok=True)
    if with_file:
        (full_book_path / with_file).touch()

    db = sqlite3.connect(str(library_path / "metadata.db"))
    db.execute("INSERT INTO books (id, title, path) VALUES (?, ?, ?)",
               (calibre_id, title, book_dir))

    for name in (authors or []):
        row = db.execute("SELECT id FROM authors WHERE name = ?", (name,)).fetchone()
        if row:
            author_id = row[0]
        else:
            cur = db.execute("INSERT INTO authors (name) VALUES (?)", (name,))
            author_id = cur.lastrowid
        db.execute(
            "INSERT INTO books_authors_link (book, author) VALUES (?, ?)",
            (calibre_id, author_id),
        )

    for name in (tags or []):
        row = db.execute("SELECT id FROM tags WHERE name = ?", (name,)).fetchone()
        if row:
            tag_id = row[0]
        else:
            cur = db.execute("INSERT INTO tags (name) VALUES (?)", (name,))
            tag_id = cur.lastrowid
        db.execute(
            "INSERT INTO books_tags_link (book, tag) VALUES (?, ?)",
            (calibre_id, tag_id),
        )

    if comments_html is not None:
        db.execute(
            "INSERT INTO comments (book, text) VALUES (?, ?)",
            (calibre_id, comments_html),
        )

    if publisher:
        row = db.execute("SELECT id FROM publishers WHERE name = ?", (publisher,)).fetchone()
        if row:
            pub_id = row[0]
        else:
            cur = db.execute("INSERT INTO publishers (name) VALUES (?)", (publisher,))
            pub_id = cur.lastrowid
        db.execute(
            "INSERT INTO books_publishers_link (book, publisher) VALUES (?, ?)",
            (calibre_id, pub_id),
        )

    db.commit()
    db.close()


@pytest.fixture
def calibre_library(tmp_path: Path) -> Path:
    _create_calibre_db(tmp_path)
    return tmp_path


# ---------------------------------------------------------------------------
# _clean_html
# ---------------------------------------------------------------------------

class TestCleanHtml:
    def test_strips_tags(self):
        assert _clean_html("<p>Hello <b>world</b>.</p>") == "Hello world."

    def test_decodes_entities(self):
        assert _clean_html("a &amp; b &lt;c&gt;") == "a & b <c>"

    def test_collapses_whitespace(self):
        assert _clean_html("a\n\n  b\t c") == "a b c"

    def test_empty_string(self):
        assert _clean_html("") == ""
        assert _clean_html(None) == ""  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# _compute_metadata_hash equivalence with archillesRAG
# ---------------------------------------------------------------------------

class TestMetadataHashEquivalence:
    """The watchdog must produce the same hash as the indexer — any drift
    would make every scan flag every book as ``metadata_changed``."""

    @staticmethod
    def _rag_hash(meta: dict) -> str:
        # Imported lazily so test collection doesn't require heavy RAG deps
        from scripts.rag_demo import archillesRAG
        return archillesRAG._compute_metadata_hash(meta)

    def test_identical_input_yields_identical_hash(self):
        meta = {
            'title': 'De Bello Gallico',
            'author': 'Julius Caesar',
            'tags': ['History', 'Latin'],
            'comments': 'A commentary on the Gallic Wars.',
            'publisher': 'Loeb',
        }
        assert _compute_metadata_hash(meta) == self._rag_hash(meta)

    def test_tag_order_irrelevant(self):
        meta_a = {
            'title': 'X', 'author': 'Y', 'publisher': 'Z',
            'comments': '', 'tags': ['B', 'A', 'C'],
        }
        meta_b = {**meta_a, 'tags': ['C', 'A', 'B']}
        assert _compute_metadata_hash(meta_a) == _compute_metadata_hash(meta_b)
        assert _compute_metadata_hash(meta_a) == self._rag_hash(meta_a)

    def test_different_comment_changes_hash(self):
        base = {
            'title': 'X', 'author': 'Y', 'publisher': 'Z',
            'comments': 'Original.', 'tags': [],
        }
        changed = {**base, 'comments': 'Revised.'}
        assert _compute_metadata_hash(base) != _compute_metadata_hash(changed)

    def test_tags_as_comma_string_matches_list(self):
        """The watchdog path passes ``tags`` as list, but the helper also
        accepts a comma-string for robustness."""
        as_list = {'title': '', 'author': '', 'publisher': '',
                   'comments': '', 'tags': ['A', 'B']}
        as_str = {**as_list, 'tags': 'B, A'}
        assert _compute_metadata_hash(as_list) == _compute_metadata_hash(as_str)


# ---------------------------------------------------------------------------
# _calibre_metadata_for_hash
# ---------------------------------------------------------------------------

class TestCalibreMetadataForHash:
    def test_reads_single_book(self, calibre_library: Path):
        _add_book(
            calibre_library, 1, "Test Book",
            authors=["Alice"],
            tags=["History"],
            comments_html="<p>Desc.</p>",
            publisher="PubCo",
        )
        result = _calibre_metadata_for_hash(calibre_library)
        assert 1 in result
        book = result[1]
        assert book['title'] == "Test Book"
        assert book['author'] == "Alice"
        assert book['tags'] == ["History"]
        assert book['comments'] == "Desc."
        assert book['publisher'] == "PubCo"

    def test_multi_author_joined_in_link_order(self, calibre_library: Path):
        _add_book(calibre_library, 1, "Collab",
                  authors=["First Author", "Second Author", "Third Author"])
        result = _calibre_metadata_for_hash(calibre_library)
        # link-insertion order is preserved via ORDER BY bal2.id
        assert result[1]['author'] == "First Author & Second Author & Third Author"

    def test_tags_sorted(self, calibre_library: Path):
        _add_book(calibre_library, 1, "Tagged",
                  authors=["A"], tags=["Zulu", "Alpha", "Mike"])
        result = _calibre_metadata_for_hash(calibre_library)
        assert result[1]['tags'] == ["Alpha", "Mike", "Zulu"]

    def test_comments_html_stripped(self, calibre_library: Path):
        _add_book(calibre_library, 1, "X", authors=["A"],
                  comments_html="<b>Bold</b>&nbsp;text &amp; more.")
        assert _calibre_metadata_for_hash(calibre_library)[1]['comments'] == \
            "Bold text & more."

    def test_missing_comments_is_empty_string(self, calibre_library: Path):
        _add_book(calibre_library, 1, "X", authors=["A"])
        assert _calibre_metadata_for_hash(calibre_library)[1]['comments'] == ""

    def test_missing_db_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            _calibre_metadata_for_hash(tmp_path)


# ---------------------------------------------------------------------------
# WatchdogScanner.scan classification
# ---------------------------------------------------------------------------

class TestScannerClassification:
    """Drive the scanner with a real SQLite DB + mocked hash store."""

    @pytest.fixture
    def scanner_factory(self, tmp_path: Path):
        def _make(indexed_hashes: dict, excluded: list[str] | None = None):
            scanner = WatchdogScanner(
                library_path=tmp_path,
                db_path=str(tmp_path / ".archilles" / "rag_db"),
                archilles_dir=tmp_path / ".archilles",
                excluded_tags=excluded,
            )
            scanner._load_indexed_hashes = lambda: indexed_hashes
            scanner._annotation_changed = lambda file_path, stored_hash: False
            return scanner
        return _make

    def test_new_book_detected(self, calibre_library: Path, scanner_factory):
        _add_book(calibre_library, 42, "Fresh Book",
                  authors=["Alice"], with_file="book.epub")
        scanner = scanner_factory(indexed_hashes={})

        results = scanner.scan(dry_run=True)

        assert results['scanned'] == 1
        assert len(results['new_books']) == 1
        assert results['new_books'][0]['calibre_id'] == 42
        assert results['new_books'][0]['title'] == "Fresh Book"
        assert not results['metadata_changed']
        assert not results['unchanged']

    def test_metadata_changed_detected(self, calibre_library: Path, scanner_factory):
        _add_book(calibre_library, 1, "T", authors=["A"],
                  comments_html="Old comment", with_file="x.epub")

        # Pretend it was indexed with a different metadata hash
        scanner = scanner_factory(indexed_hashes={
            1: {'book_id': '1',
                'metadata_hash': 'stale-hash-from-old-metadata',
                'annotation_hash': ''}
        })

        results = scanner.scan(dry_run=True)
        assert 1 in results['metadata_changed']
        assert 1 not in results['unchanged']
        assert not results['new_books']

    def test_unchanged_when_hash_matches(self, calibre_library: Path, scanner_factory):
        _add_book(calibre_library, 7, "Stable", authors=["A"],
                  comments_html="x", with_file="x.epub")

        # Compute the current hash and feed it back as the stored hash
        current_hash = _compute_metadata_hash(
            _calibre_metadata_for_hash(calibre_library)[7]
        )
        scanner = scanner_factory(indexed_hashes={
            7: {'book_id': '7', 'metadata_hash': current_hash,
                'annotation_hash': ''}
        })

        results = scanner.scan(dry_run=True)
        assert 7 in results['unchanged']
        assert 7 not in results['metadata_changed']

    def test_missing_stored_hash_does_not_flag_change(
        self, calibre_library: Path, scanner_factory,
    ):
        """Books indexed before hash tracking have stored_hash=''. The
        scanner must NOT classify these as metadata_changed; they should
        remain in ``unchanged`` until a separate backfill populates hashes."""
        _add_book(calibre_library, 5, "Pre-hash", authors=["A"],
                  with_file="x.epub")
        scanner = scanner_factory(indexed_hashes={
            5: {'book_id': '5', 'metadata_hash': '', 'annotation_hash': ''}
        })
        results = scanner.scan(dry_run=True)
        assert 5 in results['unchanged']
        assert 5 not in results['metadata_changed']

    def test_excluded_tag_skipped(self, calibre_library: Path, scanner_factory):
        _add_book(calibre_library, 1, "Skip Me",
                  authors=["A"], tags=["exclude"], with_file="x.epub")
        _add_book(calibre_library, 2, "Keep Me",
                  authors=["A"], tags=["History"], with_file="x.epub")
        scanner = scanner_factory(indexed_hashes={})

        results = scanner.scan(dry_run=True)
        new_ids = {b['calibre_id'] for b in results['new_books']}
        assert new_ids == {2}
        assert 1 not in new_ids

    def test_custom_excluded_tag_from_config(
        self, calibre_library: Path, scanner_factory,
    ):
        """Users can extend exclusions by configuring custom tags (e.g.
        a language-specific ``Übersetzung`` or ``draft``). The scanner
        must honour whatever list the caller passes in."""
        _add_book(calibre_library, 1, "Die Ilias (Übersetzung)",
                  authors=["Homer"], tags=["Übersetzung"], with_file="x.epub")
        scanner = scanner_factory(
            indexed_hashes={},
            excluded=["exclude", "Übersetzung"],
        )
        results = scanner.scan(dry_run=True)
        assert not results['new_books']

    def test_excluded_tag_case_insensitive(self, calibre_library: Path, scanner_factory):
        _add_book(calibre_library, 1, "X", authors=["A"],
                  tags=["EXCLUDE"], with_file="x.epub")
        scanner = scanner_factory(indexed_hashes={})
        results = scanner.scan(dry_run=True)
        assert not results['new_books']

    def test_include_excluded_via_empty_list(
        self, calibre_library: Path, scanner_factory,
    ):
        """Passing ``excluded_tags=[]`` (via ``--include-excluded``)
        must disable the filter."""
        _add_book(calibre_library, 1, "X", authors=["A"],
                  tags=["exclude"], with_file="x.epub")
        scanner = scanner_factory(indexed_hashes={}, excluded=[])
        results = scanner.scan(dry_run=True)
        assert len(results['new_books']) == 1

    def test_book_without_readable_file_is_skipped(
        self, calibre_library: Path, scanner_factory,
    ):
        """Books whose directory contains no supported format are ignored."""
        _add_book(calibre_library, 1, "No File", authors=["A"],
                  with_file=None)  # no file on disk
        scanner = scanner_factory(indexed_hashes={})
        results = scanner.scan(dry_run=True)
        assert not results['new_books']

    def test_annotation_change_detected_bidirectionally(
        self, calibre_library: Path, scanner_factory,
    ):
        """An empty stored hash paired with a non-empty current hash must
        flag the book as annotations_changed — regression for the gate that
        previously skipped first-time annotations."""
        _add_book(calibre_library, 1, "X", authors=["A"], with_file="x.epub")

        current_hash = _compute_metadata_hash(
            _calibre_metadata_for_hash(calibre_library)[1]
        )
        scanner = scanner_factory(indexed_hashes={
            1: {'book_id': '1', 'metadata_hash': current_hash,
                'annotation_hash': ''}
        })
        # Simulate "first-time annotations appeared": current hash != stored ''
        scanner._annotation_changed = lambda file_path, stored_hash: True

        results = scanner.scan(dry_run=True)
        assert 1 in results['annotations_changed']


# ---------------------------------------------------------------------------
# Queue file handling
# ---------------------------------------------------------------------------

class TestQueueFile:
    def test_queue_new_creates_file(self, tmp_path: Path):
        scanner = WatchdogScanner(
            library_path=tmp_path,
            db_path=str(tmp_path / "rag_db"),
            archilles_dir=tmp_path / ".archilles",
        )
        scanner._queue_new_books([3, 1, 2])
        assert scanner.queue_file.exists()
        assert json.loads(scanner.queue_file.read_text()) == [1, 2, 3]

    def test_queue_merges_and_deduplicates(self, tmp_path: Path):
        archilles_dir = tmp_path / ".archilles"
        archilles_dir.mkdir()
        (archilles_dir / "index_queue.json").write_text("[1, 2, 3]")

        scanner = WatchdogScanner(
            library_path=tmp_path,
            db_path=str(tmp_path / "rag_db"),
            archilles_dir=archilles_dir,
        )
        scanner._queue_new_books([3, 4, 5])
        assert json.loads(scanner.queue_file.read_text()) == [1, 2, 3, 4, 5]

    def test_queue_handles_corrupt_file(self, tmp_path: Path):
        archilles_dir = tmp_path / ".archilles"
        archilles_dir.mkdir()
        (archilles_dir / "index_queue.json").write_text("not-json!!")

        scanner = WatchdogScanner(
            library_path=tmp_path,
            db_path=str(tmp_path / "rag_db"),
            archilles_dir=archilles_dir,
        )
        scanner._queue_new_books([7])
        assert json.loads(scanner.queue_file.read_text()) == [7]


# ---------------------------------------------------------------------------
# Counter semantics (Issue #5 regression)
# ---------------------------------------------------------------------------

class TestCounters:
    def test_delta_updates_separate_from_new_indexed(
        self, calibre_library: Path, tmp_path: Path,
    ):
        """Phase-2 delta updates and Phase-3 new-book indexes must use
        distinct counters."""
        _add_book(calibre_library, 1, "Existing-Changed",
                  authors=["A"], with_file="x.epub")
        _add_book(calibre_library, 2, "Brand-New",
                  authors=["A"], with_file="x.epub")

        scanner = WatchdogScanner(
            library_path=calibre_library,
            db_path=str(calibre_library / ".archilles" / "rag_db"),
            archilles_dir=calibre_library / ".archilles",
        )
        scanner._load_indexed_hashes = lambda: {
            1: {'book_id': '1',
                'metadata_hash': 'stale', 'annotation_hash': ''},
            # book 2 not in index → new book
        }
        scanner._annotation_changed = lambda file_path, stored_hash: False

        class FakeRAG:
            def index_book(self, path, book_id, force=False):
                return None
        scanner._load_rag = lambda: FakeRAG()

        results = scanner.scan(dry_run=False, queue_new=False, index_new=True)
        assert results['delta_updates'] == 1      # book 1
        assert results['new_indexed'] == 1        # book 2
        assert 'new_indexed_time' in results


# ---------------------------------------------------------------------------
# Annotation cache (regression for the "scan opens every PDF every run" bug)
# ---------------------------------------------------------------------------

class TestAnnotationCache:
    """Cold path opens the book once; warm path reuses cached signature."""

    @pytest.fixture
    def scanner(self, tmp_path: Path):
        return WatchdogScanner(
            library_path=tmp_path,
            db_path=str(tmp_path / "rag_db"),
            archilles_dir=tmp_path / ".archilles",
        )

    def test_first_call_opens_and_seeds_cache(self, tmp_path: Path, scanner):
        book = tmp_path / "book.pdf"
        book.write_bytes(b"%PDF-1.4 fake")

        with patch("src.calibre_mcp.annotations.get_combined_annotations") as mock_get, \
             patch("scripts.rag_demo.archillesRAG._compute_annotation_hash") as mock_hash:
            mock_get.return_value = {"annotations": [{"text": "x"}]}
            mock_hash.return_value = "abc123"

            changed = scanner._annotation_changed(book, stored_hash="")

        assert mock_get.call_count == 1
        assert changed is True  # current 'abc123' != stored ''
        assert str(book) in scanner._annotation_cache
        assert scanner._annotation_cache[str(book)]["annotation_hash"] == "abc123"
        assert scanner._annotation_cache_dirty is True

    def test_warm_cache_skips_book_open(self, tmp_path: Path, scanner):
        book = tmp_path / "book.pdf"
        book.write_bytes(b"%PDF-1.4 fake")

        # Cold call seeds cache
        with patch("src.calibre_mcp.annotations.get_combined_annotations") as mock_get, \
             patch("scripts.rag_demo.archillesRAG._compute_annotation_hash") as mock_hash:
            mock_get.return_value = {"annotations": []}
            mock_hash.return_value = "deadbeef"
            scanner._annotation_changed(book, stored_hash="deadbeef")
            assert mock_get.call_count == 1

        # Second call with unchanged mtime/size must NOT open the book
        with patch("src.calibre_mcp.annotations.get_combined_annotations") as mock_get, \
             patch("scripts.rag_demo.archillesRAG._compute_annotation_hash") as mock_hash:
            changed = scanner._annotation_changed(book, stored_hash="deadbeef")
            assert mock_get.call_count == 0
            assert changed is False  # cached hash matches stored

    def test_warm_cache_detects_change_against_old_stored_hash(
        self, tmp_path: Path, scanner,
    ):
        """Cache hit but stored_hash is stale → still flag annotations_changed."""
        book = tmp_path / "book.pdf"
        book.write_bytes(b"%PDF-1.4 fake")

        with patch("src.calibre_mcp.annotations.get_combined_annotations") as mock_get, \
             patch("scripts.rag_demo.archillesRAG._compute_annotation_hash") as mock_hash:
            mock_get.return_value = {"annotations": [{"text": "x"}]}
            mock_hash.return_value = "current-hash"
            scanner._annotation_changed(book, stored_hash="current-hash")

        # File hasn't changed but the index still has the *previous* hash
        with patch("src.calibre_mcp.annotations.get_combined_annotations") as mock_get:
            changed = scanner._annotation_changed(book, stored_hash="old-stored-hash")
            assert mock_get.call_count == 0  # cache hit
            assert changed is True  # cached 'current-hash' differs from old stored

    def test_changed_size_invalidates_cache(self, tmp_path: Path, scanner):
        book = tmp_path / "book.pdf"
        book.write_bytes(b"%PDF-1.4 fake")

        with patch("src.calibre_mcp.annotations.get_combined_annotations") as mock_get, \
             patch("scripts.rag_demo.archillesRAG._compute_annotation_hash") as mock_hash:
            mock_get.return_value = {"annotations": []}
            mock_hash.return_value = "v1"
            scanner._annotation_changed(book, stored_hash="v1")

        # Rewrite the file with different content (forces new size)
        book.write_bytes(b"%PDF-1.4 fake plus more bytes here to change size")

        with patch("src.calibre_mcp.annotations.get_combined_annotations") as mock_get, \
             patch("scripts.rag_demo.archillesRAG._compute_annotation_hash") as mock_hash:
            mock_get.return_value = {"annotations": [{"text": "new"}]}
            mock_hash.return_value = "v2"
            changed = scanner._annotation_changed(book, stored_hash="v1")
            assert mock_get.call_count == 1  # reopened
            assert changed is True

    def test_cache_persists_across_scanner_instances(
        self, tmp_path: Path, scanner,
    ):
        book = tmp_path / "book.pdf"
        book.write_bytes(b"%PDF-1.4 fake")

        with patch("src.calibre_mcp.annotations.get_combined_annotations") as mock_get, \
             patch("scripts.rag_demo.archillesRAG._compute_annotation_hash") as mock_hash:
            mock_get.return_value = {"annotations": []}
            mock_hash.return_value = "h"
            scanner._annotation_changed(book, stored_hash="h")
            scanner._save_annotation_cache()

        assert scanner.annotation_cache_file.exists()

        # Fresh scanner reads cache from disk
        scanner2 = WatchdogScanner(
            library_path=tmp_path,
            db_path=str(tmp_path / "rag_db"),
            archilles_dir=tmp_path / ".archilles",
        )
        with patch("src.calibre_mcp.annotations.get_combined_annotations") as mock_get:
            scanner2._annotation_changed(book, stored_hash="h")
            assert mock_get.call_count == 0  # cache hit — no PDF open

    def test_corrupt_cache_falls_back_to_fresh(self, tmp_path: Path, scanner):
        scanner.archilles_dir.mkdir(parents=True, exist_ok=True)
        scanner.annotation_cache_file.write_text("not-json!!", encoding='utf-8')

        book = tmp_path / "book.pdf"
        book.write_bytes(b"%PDF-1.4 fake")

        with patch("src.calibre_mcp.annotations.get_combined_annotations") as mock_get, \
             patch("scripts.rag_demo.archillesRAG._compute_annotation_hash") as mock_hash:
            mock_get.return_value = {"annotations": []}
            mock_hash.return_value = "x"
            scanner._annotation_changed(book, stored_hash="x")
            assert mock_get.call_count == 1
            assert scanner._annotation_cache == {str(book): {
                'sig': scanner._annotation_files_signature(book),
                'annotation_hash': 'x',
            }}

    def test_extraction_failure_does_not_poison_cache(self, tmp_path: Path, scanner):
        book = tmp_path / "book.pdf"
        book.write_bytes(b"%PDF-1.4 fake")

        with patch("src.calibre_mcp.annotations.get_combined_annotations") as mock_get:
            mock_get.side_effect = RuntimeError("PDF parser blew up")
            changed = scanner._annotation_changed(book, stored_hash="x")
            assert changed is False  # treat-as-unchanged on error
            # No cache entry written for the failure
            assert str(book) not in scanner._annotation_cache


# ---------------------------------------------------------------------------
# Default excluded tags constant stays stable (batch_index.py sibling)
# ---------------------------------------------------------------------------

def test_default_excluded_tags_single_source_of_truth():
    # ``DEFAULT_EXCLUDED_TAGS`` lives in ``src.archilles.config``; both
    # the watchdog and batch_index re-export the same list. If anyone
    # redefines it locally, this guard catches the divergence.
    from scripts import batch_index
    from src.archilles import config
    assert DEFAULT_EXCLUDED_TAGS is config.DEFAULT_EXCLUDED_TAGS
    assert batch_index.DEFAULT_EXCLUDED_TAGS is config.DEFAULT_EXCLUDED_TAGS
    assert DEFAULT_EXCLUDED_TAGS == ['exclude']
