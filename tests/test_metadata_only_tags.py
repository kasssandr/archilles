"""Metadata-only tags: a book's stub (metadata, Comments, annotations) is
indexed, its full text never is.

The softer sibling of ``excluded_tags``. The watchdog must index such a book
as a phase1 stub, keep the stub out of the fulltext backlog, still refresh it
when its metadata changes, and leave an already fully indexed book alone.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.batch_index import get_book_ids_with_tags
from src.archilles.config import (
    DEFAULT_METADATA_ONLY_TAGS,
    get_metadata_only_tags,
)
from src.archilles.watchdog import (
    WatchdogScanner,
    _calibre_metadata_for_hash,
    _compute_metadata_hash,
)
from tests.test_watchdog import _add_book, _create_calibre_db


@pytest.fixture
def calibre_library(tmp_path: Path) -> Path:
    _create_calibre_db(tmp_path)
    return tmp_path


def _scanner(library: Path, indexed_hashes: dict, **kwargs) -> WatchdogScanner:
    scanner = WatchdogScanner(
        library_path=library,
        db_path=str(library / ".archilles" / "rag_db"),
        archilles_dir=library / ".archilles",
        **kwargs,
    )
    scanner._load_indexed_hashes = lambda: indexed_hashes
    scanner._annotation_changed = lambda file_path, stored_hash: False
    return scanner


class _FakeRAG:
    def __init__(self):
        self.calls: list[tuple[str, str | None]] = []

    def index_book(self, path, book_id, force=False, phase=None):
        self.calls.append((book_id, phase))
        return {'status': 'ok'}


def _stub_hash(library: Path, cid: int, *, stale: bool = False) -> dict:
    meta_hash = _compute_metadata_hash(_calibre_metadata_for_hash(library)[cid])
    return {
        'book_id': str(cid),
        'metadata_hash': 'stale' if stale else meta_hash,
        'annotation_hash': '',
        'has_content': False,
    }


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

class TestConfig:
    def test_default_without_library(self):
        assert get_metadata_only_tags(None) == ['metadata-only']
        assert DEFAULT_METADATA_ONLY_TAGS == ['metadata-only']

    def test_default_without_config(self, tmp_path: Path):
        assert get_metadata_only_tags(tmp_path) == ['metadata-only']

    def test_config_replaces_default(self, tmp_path: Path):
        (tmp_path / ".archilles").mkdir()
        (tmp_path / ".archilles" / "config.json").write_text(
            json.dumps({"metadata_only_tags": ["metadata-only", "Übersetzung"]}),
            encoding="utf-8",
        )
        assert get_metadata_only_tags(tmp_path) == ["metadata-only", "Übersetzung"]

    def test_non_list_falls_back(self, tmp_path: Path):
        (tmp_path / ".archilles").mkdir()
        (tmp_path / ".archilles" / "config.json").write_text(
            json.dumps({"metadata_only_tags": "Übersetzung"}), encoding="utf-8",
        )
        assert get_metadata_only_tags(tmp_path) == ['metadata-only']


# ---------------------------------------------------------------------------
# Watchdog classification
# ---------------------------------------------------------------------------

class TestScan:
    def test_new_book_is_flagged_metadata_only(self, calibre_library: Path):
        _add_book(calibre_library, 1, "Translation", authors=["A"],
                  tags=["Metadata-Only"], with_file="x.epub")
        _add_book(calibre_library, 2, "Original", authors=["A"], with_file="x.epub")

        results = _scanner(calibre_library, {}).scan(dry_run=True)

        flags = {b['calibre_id']: b.get('metadata_only', False)
                 for b in results['new_books']}
        assert flags == {1: True, 2: False}
        assert results['metadata_only'] == [1]

    def test_configured_tag_is_honoured(self, calibre_library: Path):
        _add_book(calibre_library, 1, "Ilias", authors=["Homer"],
                  tags=["Übersetzung"], with_file="x.epub")

        results = _scanner(
            calibre_library, {}, metadata_only_tags=["Übersetzung"],
        ).scan(dry_run=True)

        assert results['new_books'][0]['metadata_only'] is True

    def test_excluded_tag_wins(self, calibre_library: Path):
        _add_book(calibre_library, 1, "Both", authors=["A"],
                  tags=["exclude", "metadata-only"], with_file="x.epub")

        results = _scanner(calibre_library, {}).scan(dry_run=True)

        assert not results['new_books']
        assert not results['metadata_only']

    def test_stub_stays_out_of_fulltext_backlog(self, calibre_library: Path):
        _add_book(calibre_library, 1, "Held", authors=["A"],
                  tags=["metadata-only"], with_file="x.epub")
        _add_book(calibre_library, 2, "Waiting", authors=["A"], with_file="x.epub")

        results = _scanner(calibre_library, {
            1: _stub_hash(calibre_library, 1),
            2: _stub_hash(calibre_library, 2),
        }).scan(dry_run=True)

        assert {e['calibre_id'] for e in results['fulltext_pending']} == {2}
        assert 1 in results['unchanged']

    def test_removing_the_tag_releases_the_stub(self, calibre_library: Path):
        _add_book(calibre_library, 1, "Released", authors=["A"], with_file="x.epub")

        results = _scanner(calibre_library, {1: _stub_hash(calibre_library, 1)}
                           ).scan(dry_run=True)

        assert {e['calibre_id'] for e in results['fulltext_pending']} == {1}

    def test_include_excluded_via_empty_list(self, calibre_library: Path):
        _add_book(calibre_library, 1, "X", authors=["A"],
                  tags=["metadata-only"], with_file="x.epub")

        results = _scanner(calibre_library, {1: _stub_hash(calibre_library, 1)},
                           metadata_only_tags=[]).scan(dry_run=True)

        assert {e['calibre_id'] for e in results['fulltext_pending']} == {1}


# ---------------------------------------------------------------------------
# Watchdog indexing phases
# ---------------------------------------------------------------------------

class TestPhases:
    def test_index_new_stubs_a_metadata_only_book(self, calibre_library: Path):
        """Phase 3 under --index-new: full content for the ordinary book,
        a phase1 stub for the held one."""
        _add_book(calibre_library, 1, "Held", authors=["A"],
                  tags=["metadata-only"], with_file="x.epub")
        _add_book(calibre_library, 2, "Ordinary", authors=["A"], with_file="x.epub")
        scanner = _scanner(calibre_library, {})
        rag = _FakeRAG()
        scanner._load_rag = lambda: rag

        scanner.scan(dry_run=False, queue_new=False, index_new=True)

        assert dict(rag.calls) == {'1': 'phase1', '2': None}

    def test_fulltext_drain_skips_metadata_only_stub(self, calibre_library: Path):
        _add_book(calibre_library, 1, "Held", authors=["A"],
                  tags=["metadata-only"], with_file="x.epub")
        _add_book(calibre_library, 2, "Waiting", authors=["A"], with_file="x.epub")
        scanner = _scanner(calibre_library, {
            1: _stub_hash(calibre_library, 1),
            2: _stub_hash(calibre_library, 2),
        })
        rag = _FakeRAG()
        scanner._load_rag = lambda: rag

        results = scanner.scan(dry_run=False, queue_new=False,
                               index_fulltext_pending=True)

        assert rag.calls == [('2', None)]
        assert results['fulltext_indexed'] == 1

    def test_changed_comment_refreshes_stub_during_full_drain(
        self, calibre_library: Path,
    ):
        """A full drain drops stubs from Phase 2 because Phase 4 re-indexes
        them anyway. A metadata-only stub is never drained, so Phase 2 must
        keep refreshing it -- otherwise a new comment would never arrive."""
        _add_book(calibre_library, 1, "Held", authors=["A"],
                  tags=["metadata-only"], with_file="x.epub")
        scanner = _scanner(calibre_library,
                           {1: _stub_hash(calibre_library, 1, stale=True)})
        rag = _FakeRAG()
        scanner._load_rag = lambda: rag

        results = scanner.scan(dry_run=False, queue_new=False,
                               index_fulltext_pending=True)

        assert rag.calls == [('1', 'phase1')]
        assert results['delta_updates'] == 1
        assert results['fulltext_indexed'] == 0

    def test_fully_indexed_book_is_left_alone(self, calibre_library: Path):
        """Tagging a fully indexed book does not downgrade it: its text stays,
        its metadata keep being refreshed."""
        _add_book(calibre_library, 1, "Already full", authors=["A"],
                  tags=["metadata-only"], with_file="x.epub")
        stored = {**_stub_hash(calibre_library, 1, stale=True), 'has_content': True}
        scanner = _scanner(calibre_library, {1: stored})
        rag = _FakeRAG()
        scanner._load_rag = lambda: rag

        results = scanner.scan(dry_run=False, queue_new=False,
                               index_fulltext_pending=True)

        assert rag.calls == [('1', None)]
        assert not results['orphans_found']


# ---------------------------------------------------------------------------
# batch_index
# ---------------------------------------------------------------------------

def test_book_ids_with_tags_case_insensitive(calibre_library: Path):
    _add_book(calibre_library, 1, "A", authors=["X"], tags=["Übersetzung"])
    _add_book(calibre_library, 2, "B", authors=["X"], tags=["METADATA-ONLY"])
    _add_book(calibre_library, 3, "C", authors=["X"], tags=["History"])

    assert get_book_ids_with_tags(
        calibre_library, ["übersetzung", "metadata-only"],
    ) == {1, 2}
    assert get_book_ids_with_tags(calibre_library, []) == set()
