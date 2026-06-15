"""Tests für das kanonische Resume-Modul IndexingCheckpoint (Befund 7.14)."""
from pathlib import Path

from src.archilles.indexer import IndexingCheckpoint


def test_phase_roundtrips_through_save_and_load(tmp_path: Path):
    cp_path = tmp_path / "cp.json"
    cp = IndexingCheckpoint.create_new(cp_path, profile="balanced",
                                       book_ids=["1", "2"], phase="phase1")
    assert cp.phase == "phase1"
    loaded = IndexingCheckpoint.load(cp_path)
    assert loaded is not None
    assert loaded.phase == "phase1"


def test_book_ids_are_normalised_to_str(tmp_path: Path):
    cp_path = tmp_path / "cp.json"
    cp = IndexingCheckpoint.create_new(cp_path, profile="", book_ids=[1, 2, 3])
    cp.complete_book(1)          # int hineingeben
    cp.skip_book(2)
    assert cp.completed_books == ["1"]
    assert cp.skipped_books == ["2"]
    # get_remaining_books vergleicht typunabhängig
    assert cp.get_remaining_books([1, 2, 3]) == [3]


def test_load_returns_none_for_old_watchdog_format(tmp_path: Path):
    # Alte Schwundform {total, done} darf keinen Crash auslösen, sondern None.
    cp_path = tmp_path / "index_new_checkpoint.json"
    cp_path.write_text('{"total": 5, "done": [1, 2]}', encoding="utf-8")
    assert IndexingCheckpoint.load(cp_path) is None


def test_load_or_create_resumes_existing(tmp_path: Path):
    cp_path = tmp_path / "cp.json"
    first = IndexingCheckpoint.create_new(cp_path, profile="", book_ids=["1", "2"])
    first.complete_book("1")
    again = IndexingCheckpoint.load_or_create(cp_path, profile="", book_ids=["1", "2"])
    assert again.session_id == first.session_id
    assert again.get_remaining_books(["1", "2"]) == ["2"]


def test_load_or_create_starts_fresh_when_absent(tmp_path: Path):
    cp_path = tmp_path / "cp.json"
    cp = IndexingCheckpoint.load_or_create(cp_path, profile="", book_ids=["9"])
    assert cp.get_remaining_books(["9"]) == ["9"]
