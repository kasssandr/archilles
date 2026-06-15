#!/usr/bin/env python3
"""
ARCHILLES Safe Indexer

Crash-safe wrapper around indexing with:
- Signal handlers for graceful CTRL+C shutdown
- Auto-backup every N books
- Corruption detection and recovery
"""

import sys
import signal
import shutil
from pathlib import Path
from datetime import datetime
from typing import Optional
import time

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


class SafeIndexer:
    """
    Crash-safe indexing wrapper.

    Handles:
    - CTRL+C graceful shutdown (finish current book, then stop)
    - Auto-backup every N books
    - Resume after interruption (skip-existing comes from LanceDB, not here)
    """

    def __init__(
        self,
        db_path: Path,
        backup_interval: int = 50,
        max_backups: int = 2,
    ):
        """
        Initialize safe indexer.

        Args:
            db_path: Path to LanceDB directory
            backup_interval: Create backup every N books (default: 50)
            max_backups: Maximum number of backups to keep (default: 2)
        """
        self.db_path = Path(db_path)
        self.backup_interval = backup_interval
        self.max_backups = max_backups

        # State
        self.shutdown_requested = False
        self.books_since_backup = 0

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

    def note_indexed(self) -> None:
        """Count one successfully indexed book and back up periodically."""
        self.books_since_backup += 1
        if self.books_since_backup >= self.backup_interval:
            self.create_backup()
            self.books_since_backup = 0

    def should_shutdown(self) -> bool:
        """Check if shutdown was requested."""
        return self.shutdown_requested

    def create_backup(self):
        """Create a backup of the LanceDB directory."""
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
        # Test signal handling
        print("Simulating indexing... (Press CTRL+C to test graceful shutdown)")
        for i in range(20):
            if safe_indexer.should_shutdown():
                print("Shutdown requested, stopping...")
                break

            book_id = f"test_book_{i}"
            print(f"Indexing {book_id}...")
            time.sleep(0.5)  # Simulate work

            safe_indexer.note_indexed()

        safe_indexer.list_backups()
