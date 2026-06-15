"""batch_reindex_comments nutzt IndexingCheckpoint statt Ad-hoc-JSON (7.14)."""
from pathlib import Path

from src.archilles.indexer import IndexingCheckpoint


def test_checkpoint_round_trips_done_ids(tmp_path: Path):
    cp_path = tmp_path / ".archilles_reindex_checkpoint.json"
    cp = IndexingCheckpoint.create_new(cp_path, profile="", book_ids=["10", "11"])
    cp.complete_book("10")
    reloaded = IndexingCheckpoint.load(cp_path)
    assert reloaded is not None
    assert reloaded.get_remaining_books(["10", "11"]) == ["11"]


def test_clean_run_deletes_checkpoint(tmp_path: Path):
    cp_path = tmp_path / ".archilles_reindex_checkpoint.json"
    cp = IndexingCheckpoint.create_new(cp_path, profile="", book_ids=["10"])
    cp.complete_book("10")
    cp.delete()
    assert not cp_path.exists()
