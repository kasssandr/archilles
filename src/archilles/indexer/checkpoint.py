"""
ARCHILLES Indexing Checkpoint System

Book-level checkpointing for robust, resumable indexing.

Usage:
    checkpoint = IndexingCheckpoint.load_or_create(path, profile, book_ids)

    for book_id in checkpoint.get_remaining_books(book_ids):
        try:
            # Index the book...
            checkpoint.complete_book(book_id, chunk_count)
        except Exception as e:
            checkpoint.fail_book(book_id, str(e))
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Union
import uuid
import logging

logger = logging.getLogger(__name__)


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
    phase: str = "both"  # 'phase1' | 'phase2' | 'both'
    started_at: str = ""
    last_updated: str = ""
    total_books: int = 0
    completed_books: List[str] = field(default_factory=list)
    failed_books: Dict[str, str] = field(default_factory=dict)  # {book_id: error_message}
    skipped_books: List[str] = field(default_factory=list)

    def __post_init__(self):
        """Convert path to Path object and build set mirrors for O(1) membership."""
        self.checkpoint_path = Path(self.checkpoint_path)
        self._completed_set = {str(b) for b in self.completed_books}
        self._skipped_set = {str(b) for b in self.skipped_books}

    @classmethod
    def create_new(
        cls,
        checkpoint_path: Path,
        profile: str,
        book_ids: List[str],
        phase: str = "both",
    ) -> "IndexingCheckpoint":
        """
        Create a new checkpoint for a fresh indexing session.

        Args:
            checkpoint_path: Where to save the checkpoint file
            profile: Name of the hardware profile being used
            book_ids: List of all book IDs to be indexed
            phase: Indexing phase ('phase1', 'phase2', or 'both')

        Returns:
            New IndexingCheckpoint instance
        """
        now = datetime.now().isoformat()
        checkpoint = cls(
            checkpoint_path=checkpoint_path,
            session_id=f"idx_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}",
            profile=profile,
            phase=phase,
            started_at=now,
            last_updated=now,
            total_books=len(book_ids),
            completed_books=[],
            failed_books={},
            skipped_books=[],
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

            checkpoint = cls(
                checkpoint_path=checkpoint_path,
                session_id=data['session_id'],
                profile=data['profile'],
                phase=data.get('phase', 'both'),
                started_at=data['started_at'],
                last_updated=data['last_updated'],
                total_books=data['total_books'],
                completed_books=data['completed_books'],
                failed_books=data['failed_books'],
                skipped_books=data.get('skipped_books', []),
            )
            logger.info(f"Loaded checkpoint: {checkpoint.session_id}")
            return checkpoint

        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"Failed to load checkpoint: {e}")
            return None

    @classmethod
    def load_or_create(
        cls,
        checkpoint_path: Path,
        profile: str,
        book_ids: List[str],
        phase: str = "both",
    ) -> "IndexingCheckpoint":
        """Non-interaktiver Resume-Pfad: vorhandenen Checkpoint laden, sonst neu.

        Eine unlesbare oder fremdformatige Datei (z. B. die alte
        ``{total, done}``-Schwundform) liefert via :meth:`load` ``None`` und
        führt damit zu einem frischen Lauf — skip-existing/Resume der Abnehmer
        fängt Doppelarbeit ab.
        """
        existing = cls.load(checkpoint_path)
        if existing is not None:
            return existing
        return cls.create_new(checkpoint_path, profile, book_ids, phase)

    def save(self) -> None:
        """Save checkpoint to file (atomic via temp-file rename)."""
        self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        self.last_updated = datetime.now().isoformat()

        data = {
            'session_id': self.session_id,
            'profile': self.profile,
            'phase': self.phase,
            'started_at': self.started_at,
            'last_updated': self.last_updated,
            'total_books': self.total_books,
            'completed_books': self.completed_books,
            'failed_books': self.failed_books,
            'skipped_books': self.skipped_books,
        }

        # Write atomically using temp file
        temp_path = self.checkpoint_path.with_suffix('.tmp')
        with open(temp_path, 'w') as f:
            json.dump(data, f, indent=2)
        temp_path.replace(self.checkpoint_path)

    def complete_book(self, book_id: Union[int, str], chunk_count: int = 0) -> None:
        """
        Mark a book as successfully indexed.

        Args:
            book_id: ID of the completed book
            chunk_count: Number of chunks indexed
        """
        book_id = str(book_id)
        if book_id not in self._completed_set:
            self.completed_books.append(book_id)
            self._completed_set.add(book_id)

        # Remove from failed if it was there (retry succeeded)
        if book_id in self.failed_books:
            del self.failed_books[book_id]

        self.save()
        logger.info(f"Completed book: {book_id} ({chunk_count} chunks)")

    def fail_book(self, book_id: Union[int, str], error: str) -> None:
        """
        Mark a book as failed.

        Args:
            book_id: ID of the failed book
            error: Error message
        """
        book_id = str(book_id)
        self.failed_books[book_id] = error[:500]  # Limit error message length
        self.save()
        logger.warning(f"Failed book: {book_id} - {error[:100]}")

    def skip_book(self, book_id: Union[int, str]) -> None:
        """
        Mark a book as skipped (already indexed).

        Args:
            book_id: ID of the skipped book
        """
        book_id = str(book_id)
        if book_id not in self._skipped_set:
            self.skipped_books.append(book_id)
            self._skipped_set.add(book_id)
        self.save()
        logger.debug(f"Skipped book: {book_id}")

    def get_remaining_books(self, all_book_ids: List[Union[int, str]]) -> List[Union[int, str]]:
        """
        Get list of books that still need to be processed.

        Args:
            all_book_ids: Complete list of book IDs to index

        Returns:
            List of book IDs not yet completed or skipped
        """
        processed = self._completed_set | self._skipped_set
        return [bid for bid in all_book_ids if str(bid) not in processed]

    def delete(self) -> None:
        """Delete the checkpoint file."""
        if self.checkpoint_path.exists():
            self.checkpoint_path.unlink()
            logger.info(f"Deleted checkpoint: {self.checkpoint_path}")
