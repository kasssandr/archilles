#!/usr/bin/env python3
"""
Sync Calibre Annotations to Comments Field

This standalone script syncs filtered annotations from Calibre Viewer
into the Comments field of Calibre's metadata.

IMPORTANT: This script WRITES to Calibre's metadata.db.
- Run this when Calibre is NOT running to avoid database conflicts
- Creates backups before modifying the database
- Use at your own risk

Usage:
    python sync_annotations_to_comments.py /path/to/Calibre\ Library
    python sync_annotations_to_comments.py /path/to/Calibre\ Library --book-ids 123,456,789
    python sync_annotations_to_comments.py /path/to/Calibre\ Library --tag Judenkönige
"""

import argparse
import sqlite3
import sys
import re
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional

# Import from the calibre_mcp module
sys.path.insert(0, str(Path(__file__).parent / 'src'))

try:
    from calibre_mcp.annotations import get_combined_annotations, list_all_annotated_books
    from calibre_analyzer import CalibreAnalyzer
except ImportError as e:
    print(f"Error importing required modules: {e}")
    print("Make sure you run this script from the project root.")
    sys.exit(1)


def backup_database(db_path: Path) -> Path:
    """
    Create a backup of the database.

    Args:
        db_path: Path to metadata.db

    Returns:
        Path to backup file
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = db_path.parent / f"metadata_backup_{timestamp}.db"

    # Copy database
    import shutil
    shutil.copy2(db_path, backup_path)

    print(f"✓ Database backed up to: {backup_path}")
    return backup_path


def get_book_path_from_calibre(library_path: Path, book_id: int) -> Optional[str]:
    """
    Get the full path to a book's file from Calibre metadata.

    Args:
        library_path: Path to Calibre library
        book_id: Book ID

    Returns:
        Full path to book file, or None if not found
    """
    db_path = library_path / "metadata.db"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Get book path and format
    query = """
    SELECT b.path, d.format, d.name
    FROM books b
    JOIN data d ON b.id = d.book
    WHERE b.id = ?
    LIMIT 1
    """

    cursor.execute(query, (book_id,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    # Construct full path
    book_rel_path = row['path']
    format_ext = row['format'].lower()
    filename = row['name']

    full_path = library_path / book_rel_path / f"{filename}.{format_ext}"

    return str(full_path) if full_path.exists() else None


def build_annotations_section(annotations: List[Dict[str, Any]]) -> str:
    """
    Format annotations as a markdown section.

    Args:
        annotations: List of annotation dictionaries

    Returns:
        Formatted markdown string
    """
    if not annotations:
        return ""

    lines = ["## 📝 My Annotations", ""]

    # Sort by position if available
    sorted_annotations = sorted(
        annotations,
        key=lambda a: (
            a.get('pos_frac', 0),
            a.get('spine_index', 0),
            a.get('page', 0)
        )
    )

    for anno in sorted_annotations:
        # Determine position info
        page = anno.get('page')
        pos_percent = anno.get('pos_frac')
        if pos_percent:
            location = f"~{int(pos_percent * 100)}%"
        elif page:
            location = f"p. {page}"
        else:
            location = "unknown"

        # Format based on type
        if anno.get('type') == 'highlight':
            text = anno.get('highlighted_text', '').strip()
            if text:
                lines.append(f"**[{location}]** \"{text}\"")

                # Add note if present
                note = anno.get('notes', '').strip()
                if note:
                    lines.append(f"  *Note:* {note}")

                lines.append("")  # Blank line

        elif anno.get('type') == 'note':
            note = anno.get('notes', '').strip()
            if note:
                lines.append(f"**[{location}]** 💭 {note}")
                lines.append("")

        elif anno.get('type') == 'bookmark':
            # Skip bookmarks by default
            continue

    # Add timestamp
    timestamp = datetime.now().strftime("%Y-%m-%d")
    lines.append("")
    lines.append(f"*Synced: {timestamp}*")

    return "\n".join(lines)


def upsert_annotations_section(existing_comments: str, annotations_section: str) -> str:
    """
    Insert or update the annotations section in comments.

    Preserves other sections in the comments field.

    Args:
        existing_comments: Current comments field content
        annotations_section: New annotations section to insert

    Returns:
        Updated comments string
    """
    if not existing_comments:
        return annotations_section

    # Pattern to find existing annotations section
    # Matches: ## 📝 My Annotations (or variations)
    pattern = r'##\s*📝?\s*My Annotations.*?(?=##|\Z)'

    # Check if annotations section already exists
    if re.search(pattern, existing_comments, re.DOTALL | re.IGNORECASE):
        # Replace existing section
        updated = re.sub(
            pattern,
            annotations_section,
            existing_comments,
            flags=re.DOTALL | re.IGNORECASE
        )
    else:
        # Append new section
        updated = existing_comments.rstrip() + "\n\n" + annotations_section

    return updated


def write_comments_to_calibre(
    library_path: Path,
    book_id: int,
    comments: str
) -> bool:
    """
    Write comments back to Calibre database.

    Args:
        library_path: Path to Calibre library
        book_id: Book ID
        comments: New comments content

    Returns:
        True if successful
    """
    db_path = library_path / "metadata.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Update or insert into comments table
        # First check if comments entry exists
        cursor.execute("SELECT book FROM comments WHERE book = ?", (book_id,))
        exists = cursor.fetchone()

        if exists:
            cursor.execute(
                "UPDATE comments SET text = ? WHERE book = ?",
                (comments, book_id)
            )
        else:
            cursor.execute(
                "INSERT INTO comments (book, text) VALUES (?, ?)",
                (book_id, comments)
            )

        conn.commit()
        return True

    except sqlite3.Error as e:
        print(f"Database error: {e}")
        return False

    finally:
        conn.close()


def sync_book_annotations(
    library_path: Path,
    book_id: int,
    exclude_toc_markers: bool = True,
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    Sync annotations for a single book to its comments field.

    Args:
        library_path: Path to Calibre library
        book_id: Book ID
        exclude_toc_markers: Whether to exclude TOC markers
        dry_run: If True, don't actually write to database

    Returns:
        Dictionary with sync results
    """
    result = {
        'book_id': book_id,
        'success': False,
        'annotations_count': 0,
        'message': ''
    }

    # Get book path
    book_path = get_book_path_from_calibre(library_path, book_id)
    if not book_path:
        result['message'] = 'Book file not found'
        return result

    # Get annotations
    anno_result = get_combined_annotations(
        book_path=book_path,
        exclude_toc_markers=exclude_toc_markers,
        min_length=20
    )

    annotations = anno_result.get('annotations', [])
    if not annotations:
        result['message'] = 'No annotations found'
        return result

    result['annotations_count'] = len(annotations)

    # Build annotations section
    annotations_section = build_annotations_section(annotations)

    # Get existing comments
    db_path = library_path / "metadata.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT text FROM comments WHERE book = ?", (book_id,))
    row = cursor.fetchone()
    existing_comments = row[0] if row else ""
    conn.close()

    # Update comments
    updated_comments = upsert_annotations_section(existing_comments, annotations_section)

    if dry_run:
        result['success'] = True
        result['message'] = f'Dry run: Would sync {len(annotations)} annotations'
        return result

    # Write to database
    success = write_comments_to_calibre(library_path, book_id, updated_comments)

    if success:
        result['success'] = True
        result['message'] = f'Synced {len(annotations)} annotations'
    else:
        result['message'] = 'Failed to write to database'

    return result


def get_books_by_tag(library_path: Path, tag: str) -> List[int]:
    """
    Get all book IDs with a specific tag.

    Args:
        library_path: Path to Calibre library
        tag: Tag name

    Returns:
        List of book IDs
    """
    db_path = library_path / "metadata.db"

    with CalibreAnalyzer(db_path) as analyzer:
        conn = analyzer.conn
        cursor = conn.cursor()

        query = """
        SELECT DISTINCT b.id
        FROM books b
        JOIN books_tags_link btl ON b.id = btl.book
        JOIN tags t ON btl.tag = t.id
        WHERE t.name = ?
        """

        cursor.execute(query, (tag,))
        rows = cursor.fetchall()

        return [row[0] for row in rows]


def main():
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(
        description='Sync Calibre annotations to Comments field',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Sync all annotated books
  %(prog)s /path/to/Calibre\ Library

  # Sync specific books by ID
  %(prog)s /path/to/Calibre\ Library --book-ids 123,456,789

  # Sync all books with a specific tag
  %(prog)s /path/to/Calibre\ Library --tag Judenkönige

  # Dry run (preview without writing)
  %(prog)s /path/to/Calibre\ Library --dry-run

WARNING: This script modifies Calibre's metadata.db.
         Close Calibre before running this script!
        """
    )

    parser.add_argument(
        'library_path',
        help='Path to Calibre library directory'
    )

    parser.add_argument(
        '--book-ids',
        help='Comma-separated list of book IDs to sync'
    )

    parser.add_argument(
        '--tag',
        help='Sync all books with this tag'
    )

    parser.add_argument(
        '--all',
        action='store_true',
        help='Sync all annotated books'
    )

    parser.add_argument(
        '--exclude-toc-markers',
        action='store_true',
        default=True,
        help='Exclude TOC markers (default: True)'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview changes without writing to database'
    )

    parser.add_argument(
        '--no-backup',
        action='store_true',
        help='Skip database backup (not recommended)'
    )

    args = parser.parse_args()

    # Validate library path
    library_path = Path(args.library_path)
    if not library_path.exists():
        print(f"Error: Library path does not exist: {library_path}")
        sys.exit(1)

    db_path = library_path / "metadata.db"
    if not db_path.exists():
        print(f"Error: metadata.db not found in: {library_path}")
        sys.exit(1)

    # Determine which books to sync
    book_ids = []

    if args.book_ids:
        book_ids = [int(x.strip()) for x in args.book_ids.split(',')]
    elif args.tag:
        book_ids = get_books_by_tag(library_path, args.tag)
        if not book_ids:
            print(f"No books found with tag: {args.tag}")
            sys.exit(0)
        print(f"Found {len(book_ids)} books with tag '{args.tag}'")
    elif args.all:
        # Get all books with annotations
        annotated_books = list_all_annotated_books()
        # We have hashes, but we need book IDs
        # This requires mapping, which is complex
        print("Error: --all flag requires implementation of hash-to-book-id mapping")
        print("Use --book-ids or --tag instead")
        sys.exit(1)
    else:
        print("Error: Must specify --book-ids, --tag, or --all")
        parser.print_help()
        sys.exit(1)

    # Backup database (unless disabled or dry run)
    if not args.no_backup and not args.dry_run:
        print("\nBacking up database...")
        backup_database(db_path)

    # Sync books
    print(f"\n{'[DRY RUN] ' if args.dry_run else ''}Syncing {len(book_ids)} books...\n")

    success_count = 0
    error_count = 0

    for book_id in book_ids:
        result = sync_book_annotations(
            library_path=library_path,
            book_id=book_id,
            exclude_toc_markers=args.exclude_toc_markers,
            dry_run=args.dry_run
        )

        status = "✓" if result['success'] else "✗"
        print(f"{status} Book {book_id}: {result['message']}")

        if result['success']:
            success_count += 1
        else:
            error_count += 1

    # Summary
    print(f"\n{'=' * 60}")
    print(f"Sync Complete")
    print(f"{'=' * 60}")
    print(f"Success: {success_count}")
    print(f"Errors: {error_count}")

    if args.dry_run:
        print("\nThis was a dry run. No changes were made.")
        print("Run without --dry-run to apply changes.")


if __name__ == '__main__':
    main()
