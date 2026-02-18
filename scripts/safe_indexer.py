#!/usr/bin/env python3
"""
ARCHILLES Safe Indexer

Crash-safe wrapper around indexing with:
- Signal handlers for graceful CTRL+C shutdown
- Auto-backup every N books
- Progress tracking
- Corruption detection and recovery
"""

import sys
import signal
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional, Callable
import time

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.progress_tracker import ProgressTracker


class SafeIndexer:
    """
    Crash-safe indexing wrapper.

    Handles:
    - CTRL+C graceful shutdown (finish current book, then stop)
    - Auto-backup every N books
    - Progress tracking
    - Resume after interruption
    """

    def __init__(
        self,
        db_path: Path,
        progress_db_path: Optional[Path] = None,
        backup_interval: int = 50,
        max_backups: int = 2
    ):
        """
        Initialize safe indexer.

        Args:
            db_path: Path to ChromaDB directory
            progress_db_path: Path to progress database (default: db_path/../progress.db)
            backup_interval: Create backup every N books (default: 50)
            max_backups: Maximum number of backups to keep (default: 2)
        """
        self.db_path = Path(db_path)
        self.backup_interval = backup_interval
        self.max_backups = max_backups

        # Progress tracker
        if progress_db_path is None:
            progress_db_path = self.db_path.parent / "progress.db"
        self.tracker = ProgressTracker(progress_db_path)

        # State
        self.shutdown_requested = False
        self.books_since_backup = 0
        self.current_session_id = None

        # Register signal handlers
        self._register_signal_handlers()

    def _register_signal_handlers(self):
        """Register handlers for graceful shutdown."""
        def signal_handler(signum, frame):
            if not self.shutdown_requested:
                print(f"\n\n{'='*60}")
                print(f"⏸️  SHUTDOWN REQUESTED (CTRL+C)")
                print(f"{'='*60}")
                print(f"  Finishing current book, then stopping...")
                print(f"  Press CTRL+C again to force quit (may corrupt database!)")
                print(f"{'='*60}\n")
                self.shutdown_requested = True
            else:
                print(f"\n⚠️  FORCE QUIT - Database may be corrupted!")
                print(f"   Use --reset-db on next run if needed.\n")
                sys.exit(1)

        signal.signal(signal.SIGINT, signal_handler)
        # Also handle SIGTERM (systemd, Docker, etc.)
        if hasattr(signal, 'SIGTERM'):
            signal.signal(signal.SIGTERM, signal_handler)

    def start_session(self, phase: str = 'both', interactive: bool = None) -> str:
        """
        Start a new indexing session.

        Args:
            phase: 'phase1', 'phase2', or 'both'
            interactive: If True, prompt user for resume. If False, auto-resume.
                        If None, auto-detect based on stdin.

        Returns:
            session_id
        """
        # Auto-detect interactive mode if not specified
        if interactive is None:
            interactive = sys.stdin.isatty()

        # Check for interrupted sessions
        resume_info = self.tracker.get_resume_info()
        if resume_info:
            print(f"\n{'='*60}")
            print(f"📋 INTERRUPTED SESSION FOUND")
            print(f"{'='*60}")
            print(f"  Session: {resume_info['session_id']}")
            print(f"  Started: {resume_info['start_time']}")
            print(f"  Phase: {resume_info['phase']}")
            print(f"  Progress: {resume_info['successful']}/{resume_info['total_processed']} books")
            print(f"{'='*60}\n")

            # In interactive mode, ask user
            if interactive:
                try:
                    response = input("Resume this session? [Y/n]: ").strip().lower()
                    should_resume = response in ['', 'y', 'yes']
                except (EOFError, KeyboardInterrupt):
                    # If input fails, default to resuming
                    print("(Auto-resuming due to input error)")
                    should_resume = True
            else:
                # In non-interactive mode, auto-resume
                print("🔄 Auto-resuming session (non-interactive mode)\n")
                should_resume = True

            if should_resume:
                self.current_session_id = resume_info['session_id']
                print(f"✅ Resuming session {self.current_session_id}\n")
                return self.current_session_id
            else:
                # Mark old session as abandoned and start new one
                print(f"⏭️  Starting new session (old session abandoned)\n")

        # Start new session
        self.current_session_id = self.tracker.start_session(phase)
        print(f"✅ Started new session: {self.current_session_id}\n")
        return self.current_session_id

    def end_session(self, status: str = 'completed'):
        """
        End the current session.

        Args:
            status: 'completed' or 'interrupted'
        """
        if self.current_session_id:
            self.tracker.end_session(self.current_session_id, status)

            # Print final stats
            stats = self.tracker.get_session_stats(self.current_session_id)
            print(f"\n{'='*60}")
            print(f"📊 SESSION {status.upper()}")
            print(f"{'='*60}")
            print(f"  Session ID: {self.current_session_id}")
            print(f"  Total books: {stats.get('total_books', 0)}")
            print(f"  Successfully indexed: {stats.get('books_indexed', 0)}")
            print(f"  Failed: {stats.get('books_failed', 0)}")
            print(f"{'='*60}\n")

    def record_book(
        self,
        book_id: str,
        phase: str,
        status: str,
        chunks: int = 0,
        duration: float = 0,
        error: Optional[str] = None
    ):
        """
        Record that a book was processed.

        Args:
            book_id: Book identifier
            phase: 'phase1' or 'phase2'
            status: 'success', 'failed', or 'skipped'
            chunks: Number of chunks indexed
            duration: Time taken in seconds
            error: Error message if failed
        """
        if not self.current_session_id:
            raise RuntimeError("No active session! Call start_session() first.")

        self.tracker.record_book(
            self.current_session_id,
            book_id,
            phase,
            status,
            chunks,
            duration,
            error
        )

        # Trigger backup if needed
        if status == 'success':
            self.books_since_backup += 1
            if self.books_since_backup >= self.backup_interval:
                self.create_backup()
                self.books_since_backup = 0

    def is_book_indexed(self, book_id: str, phase: str) -> bool:
        """Check if a book has been successfully indexed."""
        return self.tracker.is_book_indexed(book_id, phase)

    def should_shutdown(self) -> bool:
        """Check if shutdown was requested."""
        return self.shutdown_requested

    def create_backup(self):
        """Create a backup of the ChromaDB directory."""
        if not self.db_path.exists():
            print(f"  ⚠️  Database not found, skipping backup")
            return

        # Create backup directory
        backup_dir = self.db_path.parent / "backups"
        backup_dir.mkdir(exist_ok=True)

        # Backup filename with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_name = f"rag_db_backup_{timestamp}"
        backup_path = backup_dir / backup_name

        print(f"  💾 Creating backup: {backup_name}...", end='', flush=True)
        start_time = time.time()

        try:
            # Copy entire database directory
            shutil.copytree(self.db_path, backup_path)
            elapsed = time.time() - start_time
            print(f" ✅ ({elapsed:.1f}s)")

            # Rotate old backups
            self._rotate_backups(backup_dir)

        except Exception as e:
            print(f" ❌ Failed: {e}")

    def _rotate_backups(self, backup_dir: Path):
        """Keep only the latest N backups."""
        backups = sorted(
            [d for d in backup_dir.iterdir() if d.is_dir() and d.name.startswith('rag_db_backup_')],
            key=lambda d: d.name,
            reverse=True
        )

        # Delete old backups
        for old_backup in backups[self.max_backups:]:
            try:
                shutil.rmtree(old_backup)
                print(f"  🗑️  Deleted old backup: {old_backup.name}")
            except Exception as e:
                print(f"  ⚠️  Could not delete {old_backup.name}: {e}")

    def restore_from_backup(self, backup_name: Optional[str] = None):
        """
        Restore database from backup.

        Args:
            backup_name: Specific backup to restore, or None for latest
        """
        backup_dir = self.db_path.parent / "backups"
        if not backup_dir.exists():
            raise FileNotFoundError("No backups found!")

        # Find backup
        if backup_name:
            backup_path = backup_dir / backup_name
            if not backup_path.exists():
                raise FileNotFoundError(f"Backup not found: {backup_name}")
        else:
            # Get latest backup
            backups = sorted(
                [d for d in backup_dir.iterdir() if d.is_dir() and d.name.startswith('rag_db_backup_')],
                key=lambda d: d.name,
                reverse=True
            )
            if not backups:
                raise FileNotFoundError("No backups found!")
            backup_path = backups[0]

        print(f"\n{'='*60}")
        print(f"🔄 RESTORING FROM BACKUP")
        print(f"{'='*60}")
        print(f"  Backup: {backup_path.name}")
        print(f"  Target: {self.db_path}")
        print(f"{'='*60}\n")

        # Confirm
        response = input("This will DELETE the current database. Continue? [y/N]: ").strip().lower()
        if response not in ['y', 'yes']:
            print("Cancelled.")
            return

        # Delete current database
        if self.db_path.exists():
            shutil.rmtree(self.db_path)
            print(f"  🗑️  Deleted current database")

        # Restore from backup
        shutil.copytree(backup_path, self.db_path)
        print(f"  ✅ Restored from backup\n")

    def list_backups(self):
        """List all available backups."""
        backup_dir = self.db_path.parent / "backups"
        if not backup_dir.exists():
            print("No backups found.")
            return

        backups = sorted(
            [d for d in backup_dir.iterdir() if d.is_dir() and d.name.startswith('rag_db_backup_')],
            key=lambda d: d.name,
            reverse=True
        )

        if not backups:
            print("No backups found.")
            return

        print(f"\n{'='*60}")
        print(f"💾 AVAILABLE BACKUPS")
        print(f"{'='*60}")
        for i, backup in enumerate(backups, 1):
            # Get size
            size_mb = sum(f.stat().st_size for f in backup.rglob('*') if f.is_file()) / (1024 * 1024)
            print(f"  [{i}] {backup.name} ({size_mb:.1f} MB)")
        print(f"{'='*60}\n")


# Example usage
if __name__ == '__main__':
    """
    Test the safe indexer.
    """
    import argparse

    parser = argparse.ArgumentParser(description="Safe Indexer Test")
    parser.add_argument('--db-path', default='./test_db')
    parser.add_argument('--list-backups', action='store_true')
    parser.add_argument('--restore', metavar='BACKUP_NAME')

    args = parser.parse_args()

    safe_indexer = SafeIndexer(
        db_path=Path(args.db_path),
        backup_interval=5
    )

    if args.list_backups:
        safe_indexer.list_backups()
    elif args.restore:
        safe_indexer.restore_from_backup(args.restore)
    else:
        # Test session
        session_id = safe_indexer.start_session('phase1')

        print("Simulating indexing... (Press CTRL+C to test graceful shutdown)")
        for i in range(20):
            if safe_indexer.should_shutdown():
                print("Shutdown requested, stopping...")
                break

            book_id = f"test_book_{i}"
            print(f"Indexing {book_id}...")
            time.sleep(0.5)  # Simulate work

            safe_indexer.record_book(
                book_id=book_id,
                phase='phase1',
                status='success',
                chunks=100,
                duration=0.5
            )

        safe_indexer.end_session('completed' if not safe_indexer.should_shutdown() else 'interrupted')
        safe_indexer.list_backups()
