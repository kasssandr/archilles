#!/usr/bin/env python3
"""
ARCHILLES Watchdog — Automatic Calibre→LanceDB synchronisation.

Runs a lightweight scan (SQLite + hash comparison) and applies delta updates
for books whose metadata or annotations have changed.  New books are queued
for later indexing (or indexed immediately with --index-new).

Intended to be called:
  • Via Claude Routines (MCP tool `watchdog_scan`) — recommended, no setup needed
  • As a cron / Task Scheduler job for fully autonomous operation

Usage
-----
    python scripts/watchdog.py                  # scan + update changed books
    python scripts/watchdog.py --dry-run        # show changes only, nothing written
    python scripts/watchdog.py --queue-new      # queue new books (default)
    python scripts/watchdog.py --index-new      # index new books immediately (slow)
    python scripts/watchdog.py --json           # machine-readable JSON output
    python scripts/watchdog.py --log-file PATH  # custom log path

Environment
-----------
    ARCHILLES_LIBRARY_PATH   Path to Calibre library (required)
    CALIBRE_LIBRARY_PATH     Legacy alias (also accepted)
    RAG_DB_PATH              Override LanceDB path
"""

import argparse
import json
import os
import sys
from pathlib import Path

# Allow running from repo root without installing the package
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.archilles.config import get_library_path
from src.archilles.watchdog import WatchdogScanner


def _resolve_paths() -> tuple[Path, str, Path]:
    """Return (library_path, db_path, archilles_dir) from env / config."""
    library_path_str = (
        os.getenv('ARCHILLES_LIBRARY_PATH')
        or os.getenv('CALIBRE_LIBRARY_PATH')
    )
    if not library_path_str:
        try:
            library_path_str = str(get_library_path())
        except Exception:
            pass
    if not library_path_str:
        print(
            "ERROR: Library path not set.\n"
            "Export ARCHILLES_LIBRARY_PATH or CALIBRE_LIBRARY_PATH.",
            file=sys.stderr,
        )
        sys.exit(1)

    library_path = Path(library_path_str)
    archilles_dir = library_path / ".archilles"

    config_path = archilles_dir / "config.json"
    config: dict = {}
    if config_path.exists():
        try:
            config = json.loads(config_path.read_text(encoding='utf-8'))
        except Exception:
            pass

    db_path = (
        os.getenv('RAG_DB_PATH')
        or config.get('rag_db_path')
        or str(archilles_dir / "rag_db")
    )
    return library_path, db_path, archilles_dir


def _print_results(results: dict, json_mode: bool) -> None:
    if json_mode:
        print(json.dumps(results, indent=2, ensure_ascii=False))
        return

    n_new  = len(results['new_books'])
    n_meta = len(results['metadata_changed'])
    n_anno = len(results['annotations_changed'])
    n_unch = len(results['unchanged'])
    n_err  = len(results['errors'])

    print(f"\nARCHILLES Watchdog — scan complete in {results['total_time']}s")
    print(f"  Scanned:              {results['scanned']} books")
    print(f"  New (not indexed):    {n_new}")
    print(f"  Metadata changed:     {n_meta}")
    print(f"  Annotations changed:  {n_anno}")
    print(f"  Unchanged:            {n_unch}")
    print(f"  Delta updates done:   {results['delta_updates']}"
          + (f" in {results['delta_time']}s" if results['delta_updates'] else ""))
    if n_err:
        print(f"  Errors:               {n_err}")
        for e in results['errors']:
            print(f"    calibre_id={e['calibre_id']}: {e['error']}")

    if results['new_books']:
        print(f"\n  New books queued for indexing:")
        for b in results['new_books'][:10]:
            print(f"    [{b['calibre_id']}] {b['title']}")
        if n_new > 10:
            print(f"    … and {n_new - 10} more")

    if results['metadata_changed']:
        ids = results['metadata_changed'][:10]
        suffix = f" … +{len(results['metadata_changed']) - 10}" if len(results['metadata_changed']) > 10 else ""
        print(f"\n  Metadata updated: calibre_ids {ids}{suffix}")

    if results['annotations_changed']:
        ids = results['annotations_changed'][:10]
        suffix = f" … +{len(results['annotations_changed']) - 10}" if len(results['annotations_changed']) > 10 else ""
        print(f"  Annotations updated: calibre_ids {ids}{suffix}")

    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="ARCHILLES Watchdog — sync Calibre changes into LanceDB",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        '--dry-run', action='store_true',
        help='Show detected changes without modifying LanceDB or the queue'
    )
    parser.add_argument(
        '--queue-new', action='store_true', default=True,
        help='Write newly discovered Calibre IDs to index_queue.json (default: on)'
    )
    parser.add_argument(
        '--no-queue', dest='queue_new', action='store_false',
        help='Do not write new books to the queue'
    )
    parser.add_argument(
        '--index-new', action='store_true',
        help='Index new books immediately (slow: ~90s/book with embeddings)'
    )
    parser.add_argument(
        '--json', dest='json_mode', action='store_true',
        help='Output results as JSON (useful for scripting or Claude Routines)'
    )
    parser.add_argument(
        '--log-file', metavar='PATH',
        help='Override log file path (default: <library>/.archilles/watchdog.log)'
    )
    args = parser.parse_args()

    library_path, db_path, archilles_dir = _resolve_paths()

    scanner = WatchdogScanner(
        library_path=library_path,
        db_path=db_path,
        archilles_dir=archilles_dir,
    )
    if args.log_file:
        scanner.log_file = Path(args.log_file)

    if not args.json_mode:
        print(f"Library:  {library_path}")
        print(f"Database: {db_path}")
        if args.dry_run:
            print("Mode:     dry-run (no changes will be written)\n")
        else:
            print()

    results = scanner.scan(
        dry_run=args.dry_run,
        queue_new=args.queue_new,
        index_new=args.index_new,
    )

    _print_results(results, json_mode=args.json_mode)

    # Exit with non-zero code if there were errors
    sys.exit(1 if results['errors'] else 0)


if __name__ == '__main__':
    main()
