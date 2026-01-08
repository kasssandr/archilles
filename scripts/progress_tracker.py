#!/usr/bin/env python3
"""
ARCHILLES Progress Tracker

SQLite-based progress tracking for crash-safe indexing.
Tracks which books have been indexed, when, and in which phase.

Features:
- Resume after crash/interruption
- Track Phase 1 (metadata) vs Phase 2 (full content)
- Session management
- Statistics and reporting
"""

import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any
from contextlib import contextmanager


class ProgressTracker:
    """
    Tracks indexing progress in a separate SQLite database.

    This allows us to know exactly what was indexed even if ChromaDB corrupts.
    """

    def __init__(self, db_path: Path):
        """
        Initialize progress tracker.

        Args:
            db_path: Path to progress database (e.g., /path/to/.archilles/progress.db)
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_database()

    def _init_database(self):
        """Initialize database schema."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Sessions table - track indexing runs
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    start_time TEXT NOT NULL,
                    end_time TEXT,
                    status TEXT NOT NULL,  -- 'running', 'completed', 'interrupted'
                    total_books INTEGER DEFAULT 0,
                    books_indexed INTEGER DEFAULT 0,
                    books_failed INTEGER DEFAULT 0,
                    phase TEXT NOT NULL  -- 'phase1', 'phase2', 'both'
                )
            """)

            # Books table - track individual book indexing
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS books (
                    book_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    indexed_at TEXT NOT NULL,
                    phase TEXT NOT NULL,  -- 'phase1', 'phase2'
                    status TEXT NOT NULL,  -- 'success', 'failed', 'skipped'
                    chunks INTEGER DEFAULT 0,
                    duration_seconds REAL DEFAULT 0,
                    error_message TEXT,
                    PRIMARY KEY (book_id, session_id, phase),
                    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
                )
            """)

            # Create indices for fast lookups
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_books_book_id
                ON books(book_id)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_books_status
                ON books(status)
            """)

            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_books_phase
                ON books(phase)
            """)

            conn.commit()

    @contextmanager
    def _get_connection(self):
        """Context manager for database connections."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def start_session(self, phase: str = 'both') -> str:
        """
        Start a new indexing session.

        Args:
            phase: 'phase1' (metadata only), 'phase2' (full content), or 'both'

        Returns:
            session_id
        """
        session_id = datetime.now().strftime('%Y%m%d_%H%M%S')

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO sessions (session_id, start_time, status, phase)
                VALUES (?, ?, 'running', ?)
            """, (session_id, datetime.now().isoformat(), phase))
            conn.commit()

        return session_id

    def end_session(self, session_id: str, status: str = 'completed'):
        """
        Mark session as ended.

        Args:
            session_id: Session to end
            status: 'completed' or 'interrupted'
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Get statistics
            cursor.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as indexed,
                    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed
                FROM books
                WHERE session_id = ?
            """, (session_id,))

            stats = cursor.fetchone()

            # Update session
            cursor.execute("""
                UPDATE sessions
                SET end_time = ?,
                    status = ?,
                    total_books = ?,
                    books_indexed = ?,
                    books_failed = ?
                WHERE session_id = ?
            """, (
                datetime.now().isoformat(),
                status,
                stats['total'] or 0,
                stats['indexed'] or 0,
                stats['failed'] or 0,
                session_id
            ))

            conn.commit()

    def record_book(
        self,
        session_id: str,
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
            session_id: Current session
            book_id: Book identifier
            phase: 'phase1' or 'phase2'
            status: 'success', 'failed', or 'skipped'
            chunks: Number of chunks indexed
            duration: Time taken in seconds
            error: Error message if failed
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT OR REPLACE INTO books
                (book_id, session_id, indexed_at, phase, status, chunks, duration_seconds, error_message)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                book_id,
                session_id,
                datetime.now().isoformat(),
                phase,
                status,
                chunks,
                duration,
                error
            ))
            conn.commit()

    def is_book_indexed(self, book_id: str, phase: str) -> bool:
        """
        Check if a book has been successfully indexed in a specific phase.

        Args:
            book_id: Book to check
            phase: 'phase1' or 'phase2'

        Returns:
            True if book was successfully indexed
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT 1 FROM books
                WHERE book_id = ? AND phase = ? AND status = 'success'
                LIMIT 1
            """, (book_id, phase))

            return cursor.fetchone() is not None

    def get_indexed_books(self, phase: Optional[str] = None) -> List[str]:
        """
        Get list of successfully indexed book IDs.

        Args:
            phase: Filter by phase ('phase1' or 'phase2'), or None for all

        Returns:
            List of book_id strings
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            if phase:
                cursor.execute("""
                    SELECT DISTINCT book_id FROM books
                    WHERE phase = ? AND status = 'success'
                """, (phase,))
            else:
                cursor.execute("""
                    SELECT DISTINCT book_id FROM books
                    WHERE status = 'success'
                """)

            return [row['book_id'] for row in cursor.fetchall()]

    def get_failed_books(self, phase: Optional[str] = None, session_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get list of failed books with their error messages.

        Args:
            phase: Filter by phase ('phase1' or 'phase2'), or None for all
            session_id: Filter by session, or None for all sessions

        Returns:
            List of dicts with book_id, error_message, phase, indexed_at
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()

            conditions = ["status = 'failed'"]
            params = []

            if phase:
                conditions.append("phase = ?")
                params.append(phase)

            if session_id:
                conditions.append("session_id = ?")
                params.append(session_id)

            query = f"""
                SELECT book_id, error_message, phase, indexed_at, session_id
                FROM books
                WHERE {' AND '.join(conditions)}
                ORDER BY indexed_at DESC
            """
            cursor.execute(query, params)

            return [
                {
                    'book_id': row['book_id'],
                    'error': row['error_message'],
                    'phase': row['phase'],
                    'indexed_at': row['indexed_at'],
                    'session_id': row['session_id']
                }
                for row in cursor.fetchall()
            ]

    def clear_failed_status(self, book_ids: List[str], phase: Optional[str] = None) -> int:
        """
        Clear failed status for specific books (to allow retry).

        Args:
            book_ids: List of book IDs to clear
            phase: Phase to clear, or None for all phases

        Returns:
            Number of records deleted
        """
        if not book_ids:
            return 0

        with self._get_connection() as conn:
            cursor = conn.cursor()

            placeholders = ','.join('?' * len(book_ids))

            if phase:
                cursor.execute(f"""
                    DELETE FROM books
                    WHERE book_id IN ({placeholders})
                    AND phase = ?
                    AND status = 'failed'
                """, (*book_ids, phase))
            else:
                cursor.execute(f"""
                    DELETE FROM books
                    WHERE book_id IN ({placeholders})
                    AND status = 'failed'
                """, book_ids)

            deleted = cursor.rowcount
            conn.commit()
            return deleted

    def get_session_stats(self, session_id: str) -> Dict[str, Any]:
        """Get statistics for a session."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM sessions WHERE session_id = ?
            """, (session_id,))

            session = cursor.fetchone()
            if not session:
                return {}

            return dict(session)

    def get_latest_session(self) -> Optional[Dict[str, Any]]:
        """Get the most recent session."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM sessions
                ORDER BY start_time DESC
                LIMIT 1
            """)

            session = cursor.fetchone()
            if session:
                return dict(session)
            return None

    def get_interrupted_sessions(self) -> List[Dict[str, Any]]:
        """Get all interrupted sessions that can be resumed."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM sessions
                WHERE status = 'running' OR status = 'interrupted'
                ORDER BY start_time DESC
            """)

            return [dict(row) for row in cursor.fetchall()]

    def get_resume_info(self) -> Optional[Dict[str, Any]]:
        """
        Get information about what can be resumed.

        Returns:
            Dict with resume info, or None if nothing to resume
        """
        interrupted = self.get_interrupted_sessions()
        if not interrupted:
            return None

        latest = interrupted[0]

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT
                    COUNT(*) as total_processed,
                    SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as successful,
                    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed
                FROM books
                WHERE session_id = ?
            """, (latest['session_id'],))

            stats = cursor.fetchone()

        return {
            'session_id': latest['session_id'],
            'phase': latest['phase'],
            'start_time': latest['start_time'],
            'total_processed': stats['total_processed'] or 0,
            'successful': stats['successful'] or 0,
            'failed': stats['failed'] or 0,
            'can_resume': True
        }

    def print_stats(self):
        """Print overall statistics."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Session stats
            cursor.execute("""
                SELECT
                    COUNT(*) as total_sessions,
                    SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
                    SUM(CASE WHEN status = 'interrupted' THEN 1 ELSE 0 END) as interrupted
                FROM sessions
            """)
            sessions = cursor.fetchone()

            # Book stats
            cursor.execute("""
                SELECT
                    COUNT(DISTINCT book_id) as unique_books,
                    SUM(chunks) as total_chunks,
                    phase,
                    status
                FROM books
                GROUP BY phase, status
            """)
            books = cursor.fetchall()

        print(f"\n{'='*60}")
        print(f"📊 PROGRESS TRACKER STATISTICS")
        print(f"{'='*60}")
        print(f"  Total sessions: {sessions['total_sessions']}")
        print(f"  Completed: {sessions['completed']}")
        print(f"  Interrupted: {sessions['interrupted']}")
        print(f"\n  Books by Phase & Status:")
        for book in books:
            print(f"    {book['phase']}/{book['status']}: {book['unique_books']} books, {book['total_chunks']} chunks")
        print(f"{'='*60}\n")


# Example usage
if __name__ == '__main__':
    # Test the progress tracker
    tracker = ProgressTracker(Path("./test_progress.db"))

    # Start session
    session_id = tracker.start_session(phase='phase1')
    print(f"Started session: {session_id}")

    # Record some books
    tracker.record_book(session_id, "book1", "phase1", "success", chunks=100, duration=5.2)
    tracker.record_book(session_id, "book2", "phase1", "success", chunks=150, duration=7.8)
    tracker.record_book(session_id, "book3", "phase1", "failed", error="File not found")

    # Check status
    print(f"Book1 indexed? {tracker.is_book_indexed('book1', 'phase1')}")
    print(f"Book3 indexed? {tracker.is_book_indexed('book3', 'phase1')}")

    # End session
    tracker.end_session(session_id, 'completed')

    # Print stats
    tracker.print_stats()

    # Check resume
    resume_info = tracker.get_resume_info()
    if resume_info:
        print(f"Can resume: {resume_info}")
