"""
Delete all indexed chunks for Calibre books carrying a given tag.

Useful when a book was indexed before it received an exclude-style tag
(e.g. ``exclude``, ``draft``, ``Übersetzung``) — the watchdog now skips
the book but its existing chunks remain in LanceDB and keep surfacing
in search results.

Usage:
    python scripts/cleanup_by_tag.py --tag "Übersetzung" --dry-run
    python scripts/cleanup_by_tag.py --tag "draft"
    python scripts/cleanup_by_tag.py --tag "exclude" --yes
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.archilles.config import get_library_path, get_rag_db_path
from src.archilles.sqlite_ro import connect_readonly
from src.storage.lancedb_store import LanceDBStore


def _find_books_with_tag(metadata_db: Path, tag: str) -> list[tuple[int, str]]:
    conn = connect_readonly(metadata_db)
    try:
        rows = conn.execute(
            """
            SELECT b.id, b.title
            FROM books b
            JOIN books_tags_link btl ON btl.book = b.id
            JOIN tags t ON t.id = btl.tag
            WHERE t.name = ?
            ORDER BY b.id
            """,
            (tag,),
        ).fetchall()
    finally:
        conn.close()
    return [(int(cid), title) for cid, title in rows]


def _count_chunks_for_calibre_id(store: LanceDBStore, calibre_id: int) -> int:
    if store.table is None:
        return 0
    try:
        df = (
            store.table.search()
            .where(f"calibre_id = {calibre_id}")
            .limit(100000)
            .to_pandas()
        )
        return len(df)
    except Exception:
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument(
        "--tag", required=True,
        help="Calibre tag whose books should be purged from LanceDB",
    )
    parser.add_argument(
        "--library-path", type=Path, default=None,
        help="Calibre library path (default: ARCHILLES_LIBRARY_PATH env var)",
    )
    parser.add_argument(
        "--db-path", default=None,
        help="LanceDB directory (default: <library>/.archilles/rag_db)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be deleted without touching LanceDB",
    )
    parser.add_argument(
        "--yes", action="store_true",
        help="Skip the interactive confirmation prompt",
    )
    args = parser.parse_args()

    library_path = args.library_path or get_library_path()
    metadata_db = library_path / "metadata.db"
    if not metadata_db.exists():
        print(f"ERROR: {metadata_db} not found", file=sys.stderr)
        return 1

    db_path = args.db_path or get_rag_db_path(library_path)
    print(f"Library:     {library_path}")
    print(f"LanceDB:     {db_path}")
    print(f"Tag:         {args.tag}")
    print()

    books = _find_books_with_tag(metadata_db, args.tag)
    if not books:
        print(f"No books found with tag '{args.tag}'.")
        return 0

    store = LanceDBStore(db_path=str(db_path))
    if store.table is None:
        print("ERROR: LanceDB not available or empty", file=sys.stderr)
        return 1

    targets: list[tuple[int, str, int]] = []
    for cid, title in books:
        n = _count_chunks_for_calibre_id(store, cid)
        if n > 0:
            targets.append((cid, title, n))

    if not targets:
        print(
            f"Found {len(books)} book(s) tagged '{args.tag}', "
            "but none are currently indexed in LanceDB."
        )
        return 0

    print(f"Found {len(targets)} indexed book(s) tagged '{args.tag}':")
    for cid, title, n in targets:
        print(f"  [{cid:>5}] {title} — {n} chunks")
    total_chunks = sum(n for _, _, n in targets)
    print(f"\nTotal chunks to delete: {total_chunks}")

    if args.dry_run:
        print("\n(dry-run — nothing was deleted)")
        return 0

    if not args.yes:
        resp = input("\nProceed with deletion? [y/N] ").strip().lower()
        if resp not in ("y", "yes"):
            print("Aborted.")
            return 0

    deleted = 0
    for cid, title, _ in targets:
        n = store.delete_by_calibre_id(cid)
        deleted += n
        print(f"  [{cid:>5}] {title}: {n} chunks deleted")

    print(f"\nDone. Deleted {deleted} chunks across {len(targets)} book(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
