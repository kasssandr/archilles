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


def test_integration_partial_run_writes_canonical_checkpoint(tmp_path: Path):
    """batch_reindex_comments writes a canonical IndexingCheckpoint on a partial/failed run.

    Two books: the first succeeds (goes through the success path),
    the second raises inside the try block (stats['failed'] == 1).
    Because failed > 0 the checkpoint is NOT deleted, so we can inspect it.
    """
    from src.archilles.constants import ChunkType
    from scripts.batch_index import batch_reindex_comments

    # Real temp files so path.exists() passes for both books
    real_file1 = tmp_path / "book1.pdf"
    real_file1.write_bytes(b"%PDF fake1")
    real_file2 = tmp_path / "book2.pdf"
    real_file2.write_bytes(b"%PDF fake2")

    call_count = [0]

    class FakeStore:
        def delete_by_book_id_and_type(self, book_id, chunk_type):
            return 0

        def add_chunks(self, chunks, embeddings):
            pass

    class FakeRAG:
        store = FakeStore()

        def _extract_calibre_metadata(self, book_path):
            call_count[0] += 1
            if call_count[0] == 1:
                # First book: has comments → continues to success path
                return {'comments': 'A short review', 'comments_html': None}
            # Second book: simulate a processing failure
            raise RuntimeError("simulated failure in book 2")

        def _compute_metadata_hash(self, book_metadata):
            return "deadbeef"

        def _build_comment_chunks(self, book_metadata, book_id, book_format, metadata_hash):
            # One chunk + one matching embedding (list-of-list; numpy.array()-able)
            return [{'text': 'review text', 'book_id': book_id}], [[0.1] * 4]

    books = [
        {
            'id': 1,
            'title': 'Book One',
            'author': 'Author A',
            'best_format': {'path': str(real_file1), 'format': 'PDF'},
            'formats': [{'path': str(real_file1), 'format': 'PDF'}],
        },
        {
            'id': 2,
            'title': 'Book Two',
            'author': 'Author B',
            'best_format': {'path': str(real_file2), 'format': 'PDF'},
            'formats': [{'path': str(real_file2), 'format': 'PDF'}],
        },
    ]

    cp_path = tmp_path / ".archilles_reindex_checkpoint.json"
    stats = batch_reindex_comments(
        books=books,
        rag=FakeRAG(),
        dry_run=False,
        checkpoint_path=cp_path,
    )

    # Second book failed → checkpoint must NOT have been deleted
    assert stats['failed'] == 1, f"Expected 1 failure, got {stats['failed']}"
    assert cp_path.exists(), "Checkpoint file must survive a partial/failed run"

    # The file must be a canonical IndexingCheckpoint (not a bare JSON list)
    cp = IndexingCheckpoint.load(cp_path)
    assert cp is not None, "Checkpoint must be readable as IndexingCheckpoint"
    assert cp.session_id, "Checkpoint must have a session_id field"

    # First book must be recorded as completed (success path)
    assert "1" in cp.completed_books, (
        f"Book 1 must be in completed_books; got completed={cp.completed_books}"
    )
