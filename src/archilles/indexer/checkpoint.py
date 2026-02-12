"""
ARCHILLES Indexing Checkpoint System

Provides chunk-level checkpointing for robust, resumable indexing.

Features:
- Save progress after each book or batch of chunks
- Resume interrupted indexing sessions
- Retry failed books
- Track partial book progress for very large books

Usage:
    checkpoint = IndexingCheckpoint(checkpoint_path)
    checkpoint.start_session(profile_name, book_ids)

    for book_id in checkpoint.get_remaining_books():
        checkpoint.start_book(book_id)
        try:
            # Index chunks...
            for i, chunk in enumerate(chunks):
                index_chunk(chunk)
                checkpoint.update_chunk_progress(i + 1, len(chunks))
            checkpoint.complete_book(book_id, chunk_count)
        except Exception as e:
            checkpoint.fail_book(book_id, str(e))

    checkpoint.end_session()
"""

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any
import uuid
import logging

logger = logging.getLogger(__name__)


@dataclass
class ChunkProgress:
    """Progress within a single book."""
    book_id: str
    total_chunks: int = 0
    chunks_done: int = 0
    started_at: str = ""

    @property
    def is_complete(self) -> bool:
        return self.chunks_done >= self.total_chunks and self.total_chunks > 0

    @property
    def progress_percent(self) -> float:
        if self.total_chunks == 0:
            return 0.0
        return (self.chunks_done / self.total_chunks) * 100


@dataclass
class IndexingCheckpoint:
    """
    Checkpoint for resumable indexing.

    Saves state to a JSON file after each significant operation,
    allowing the process to resume after interruption.
    """

    checkpoint_path: Path
    session_id: str = ""
    profile: str = ""
    started_at: str = ""
    last_updated: str = ""
    total_books: int = 0
    completed_books: List[str] = field(default_factory=list)
    failed_books: Dict[str, str] = field(default_factory=dict)  # {book_id: error_message}
    skipped_books: List[str] = field(default_factory=list)
    current_book: Optional[ChunkProgress] = None

    def __post_init__(self):
        """Convert path to Path object if needed."""
        self.checkpoint_path = Path(self.checkpoint_path)

    @classmethod
    def create_new(
        cls,
        checkpoint_path: Path,
        profile: str,
        book_ids: List[str]
    ) -> "IndexingCheckpoint":
        """
        Create a new checkpoint for a fresh indexing session.

        Args:
            checkpoint_path: Where to save the checkpoint file
            profile: Name of the hardware profile being used
            book_ids: List of all book IDs to be indexed

        Returns:
            New IndexingCheckpoint instance
        """
        now = datetime.now().isoformat()
        checkpoint = cls(
            checkpoint_path=checkpoint_path,
            session_id=f"idx_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}",
            profile=profile,
            started_at=now,
            last_updated=now,
            total_books=len(book_ids),
            completed_books=[],
            failed_books={},
            skipped_books=[],
            current_book=None
        )
        checkpoint.save()
        logger.info(f"Created new checkpoint: {checkpoint.session_id}")
        return checkpoint

    @classmethod
    def load(cls, checkpoint_path: Path) -> Optional["IndexingCheckpoint"]:
        """
        Load checkpoint from file.

        Args:
            checkpoint_path: Path to checkpoint file

        Returns:
            IndexingCheckpoint if file exists, None otherwise
        """
        checkpoint_path = Path(checkpoint_path)
        if not checkpoint_path.exists():
            return None

        try:
            with open(checkpoint_path, 'r') as f:
                data = json.load(f)

            # Reconstruct ChunkProgress if present
            current_book = None
            if data.get('current_book'):
                current_book = ChunkProgress(**data['current_book'])

            checkpoint = cls(
                checkpoint_path=checkpoint_path,
                session_id=data['session_id'],
                profile=data['profile'],
                started_at=data['started_at'],
                last_updated=data['last_updated'],
                total_books=data['total_books'],
                completed_books=data['completed_books'],
                failed_books=data['failed_books'],
                skipped_books=data.get('skipped_books', []),
                current_book=current_book
            )
            logger.info(f"Loaded checkpoint: {checkpoint.session_id}")
            return checkpoint

        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"Failed to load checkpoint: {e}")
            return None

    def save(self) -> None:
        """Save checkpoint to file."""
        self.last_updated = datetime.now().isoformat()

        data = {
            'session_id': self.session_id,
            'profile': self.profile,
            'started_at': self.started_at,
            'last_updated': self.last_updated,
            'total_books': self.total_books,
            'completed_books': self.completed_books,
            'failed_books': self.failed_books,
            'skipped_books': self.skipped_books,
            'current_book': asdict(self.current_book) if self.current_book else None
        }

        # Write atomically using temp file
        temp_path = self.checkpoint_path.with_suffix('.tmp')
        with open(temp_path, 'w') as f:
            json.dump(data, f, indent=2)
        temp_path.rename(self.checkpoint_path)

    def start_book(self, book_id: str, total_chunks: int = 0) -> None:
        """
        Mark a book as currently being processed.

        Args:
            book_id: ID of the book being started
            total_chunks: Expected total chunks (0 if unknown)
        """
        self.current_book = ChunkProgress(
            book_id=book_id,
            total_chunks=total_chunks,
            chunks_done=0,
            started_at=datetime.now().isoformat()
        )
        self.save()
        logger.debug(f"Started book: {book_id}")

    def update_chunk_progress(self, chunks_done: int, total_chunks: int = None) -> None:
        """
        Update progress within current book.

        Call this periodically during long indexing operations.

        Args:
            chunks_done: Number of chunks processed so far
            total_chunks: Optional update to total (if discovered during processing)
        """
        if self.current_book:
            self.current_book.chunks_done = chunks_done
            if total_chunks is not None:
                self.current_book.total_chunks = total_chunks
            self.save()

    def complete_book(self, book_id: str, chunk_count: int = 0) -> None:
        """
        Mark a book as successfully indexed.

        Args:
            book_id: ID of the completed book
            chunk_count: Number of chunks indexed
        """
        if book_id not in self.completed_books:
            self.completed_books.append(book_id)

        # Remove from failed if it was there (retry succeeded)
        if book_id in self.failed_books:
            del self.failed_books[book_id]

        self.current_book = None
        self.save()
        logger.info(f"Completed book: {book_id} ({chunk_count} chunks)")

    def fail_book(self, book_id: str, error: str) -> None:
        """
        Mark a book as failed.

        Args:
            book_id: ID of the failed book
            error: Error message
        """
        self.failed_books[book_id] = error[:500]  # Limit error message length
        self.current_book = None
        self.save()
        logger.warning(f"Failed book: {book_id} - {error[:100]}")

    def skip_book(self, book_id: str) -> None:
        """
        Mark a book as skipped (already indexed).

        Args:
            book_id: ID of the skipped book
        """
        if book_id not in self.skipped_books:
            self.skipped_books.append(book_id)
        self.current_book = None
        self.save()
        logger.debug(f"Skipped book: {book_id}")

    def get_remaining_books(self, all_book_ids: List[str]) -> List[str]:
        """
        Get list of books that still need to be processed.

        Args:
            all_book_ids: Complete list of book IDs to index

        Returns:
            List of book IDs not yet completed or skipped
        """
        processed = set(self.completed_books) | set(self.skipped_books)
        return [bid for bid in all_book_ids if bid not in processed]

    def get_failed_books(self) -> Dict[str, str]:
        """
        Get dict of failed books with their errors.

        Returns:
            Dict mapping book_id -> error_message
        """
        return dict(self.failed_books)

    def clear_failures(self) -> int:
        """
        Clear the failed books list (for retry).

        Returns:
            Number of failures cleared
        """
        count = len(self.failed_books)
        self.failed_books = {}
        self.save()
        return count

    def delete(self) -> None:
        """Delete the checkpoint file."""
        if self.checkpoint_path.exists():
            self.checkpoint_path.unlink()
            logger.info(f"Deleted checkpoint: {self.checkpoint_path}")

    @property
    def summary(self) -> Dict[str, Any]:
        """Get summary statistics."""
        return {
            'session_id': self.session_id,
            'profile': self.profile,
            'started_at': self.started_at,
            'last_updated': self.last_updated,
            'total_books': self.total_books,
            'completed': len(self.completed_books),
            'failed': len(self.failed_books),
            'skipped': len(self.skipped_books),
            'remaining': self.total_books - len(self.completed_books) - len(self.skipped_books),
            'current_book': self.current_book.book_id if self.current_book else None,
            'current_progress': f"{self.current_book.chunks_done}/{self.current_book.total_chunks}" if self.current_book else None
        }

    def print_status(self) -> None:
        """Print current checkpoint status."""
        s = self.summary

        print()
        print("=" * 64)
        print("  INDEXING CHECKPOINT STATUS")
        print("=" * 64)
        print(f"  Session:    {s['session_id']}")
        print(f"  Profile:    {s['profile']}")
        print(f"  Started:    {s['started_at'][:19]}")
        print(f"  Updated:    {s['last_updated'][:19]}")
        print()
        print(f"  Progress:")
        print(f"    {s['completed']}/{s['total_books']} books completed")
        if s['failed'] > 0:
            print(f"    {s['failed']} books failed")
        if s['skipped'] > 0:
            print(f"    {s['skipped']} books skipped")
        print(f"    {s['remaining']} books remaining")

        if s['current_book']:
            print()
            print(f"  Currently processing: {s['current_book']}")
            print(f"    Chunk progress: {s['current_progress']}")

        print("=" * 64)
        print()


def prompt_checkpoint_action(checkpoint: IndexingCheckpoint, all_book_ids: List[str]) -> str:
    """
    Interactive prompt for handling existing checkpoint.

    Args:
        checkpoint: Existing checkpoint
        all_book_ids: All book IDs that would be indexed

    Returns:
        Action: 'continue', 'retry', 'restart', or 'abort'
    """
    remaining = checkpoint.get_remaining_books(all_book_ids)
    failed = checkpoint.get_failed_books()

    print()
    print("=" * 64)
    print("  EXISTING CHECKPOINT FOUND")
    print("=" * 64)
    print(f"  Session:    {checkpoint.session_id}")
    print(f"  Profile:    {checkpoint.profile}")
    print(f"  Started:    {checkpoint.started_at[:19]}")
    print()
    print(f"  Progress:")
    print(f"    {len(checkpoint.completed_books)}/{checkpoint.total_books} books completed")
    if len(failed) > 0:
        print(f"    {len(failed)} books failed")
    print(f"    {len(remaining)} books remaining")
    print()
    print("-" * 64)
    print()
    print(f"  [C] Continue - Index the {len(remaining)} remaining books")
    if len(failed) > 0:
        print(f"  [R] Retry - Re-index the {len(failed)} failed books")
    print(f"  [N] New - Start fresh (delete checkpoint)")
    print(f"  [A] Abort - Exit without changes")
    print()
    print("=" * 64)
    print()

    while True:
        try:
            choice = input("Choose an option [C/r/n/a]: ").strip().upper()

            if choice in ['', 'C']:
                return 'continue'
            elif choice == 'R' and len(failed) > 0:
                return 'retry'
            elif choice == 'N':
                return 'restart'
            elif choice == 'A':
                return 'abort'
            else:
                print("  Invalid choice.")
        except (EOFError, KeyboardInterrupt):
            print("\n  Aborting.")
            return 'abort'


# Quick test
if __name__ == "__main__":
    import tempfile
    import os

    # Create temp checkpoint file
    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        checkpoint_path = Path(f.name)

    try:
        # Create new checkpoint
        book_ids = [f"book_{i}" for i in range(10)]
        cp = IndexingCheckpoint.create_new(checkpoint_path, "balanced", book_ids)

        # Simulate indexing
        cp.start_book("book_0", total_chunks=100)
        cp.update_chunk_progress(50, 100)
        cp.complete_book("book_0", 100)

        cp.start_book("book_1", total_chunks=200)
        cp.fail_book("book_1", "Test error")

        cp.skip_book("book_2")

        # Print status
        cp.print_status()

        # Test loading
        loaded = IndexingCheckpoint.load(checkpoint_path)
        if loaded:
            print("Loaded checkpoint successfully!")
            print(f"Remaining books: {loaded.get_remaining_books(book_ids)}")
            print(f"Failed books: {loaded.get_failed_books()}")

    finally:
        os.unlink(checkpoint_path)
