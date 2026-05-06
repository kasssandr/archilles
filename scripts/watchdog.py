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
import signal
import sys
from pathlib import Path

# Allow running from repo root without installing the package
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.archilles.config import get_library_path, get_rag_db_path
from src.archilles.watchdog import WatchdogScanner, ZoteroWatchdogScanner


def _resolve_paths() -> tuple[Path, str, Path]:
    """Return ``(library_path, db_path, archilles_dir)`` from env / config.

    Delegates to :func:`src.archilles.config.get_library_path` and
    :func:`src.archilles.config.get_rag_db_path`; the legacy ``RAG_DB_PATH``
    env var is still honoured for scripting back-compat.
    """
    library_path = get_library_path()  # exits with helpful message if unset
    archilles_dir = library_path / ".archilles"
    db_path = os.getenv('RAG_DB_PATH') or get_rag_db_path(library_path)
    return library_path, db_path, archilles_dir


def _detect_scanner_type(library_path: Path) -> str:
    """Return 'zotero' if the library contains zotero.sqlite, else 'calibre'."""
    if (library_path / "zotero.sqlite").exists():
        return "zotero"
    return "calibre"


def _install_shutdown_handler(scanner) -> None:
    """Forward SIGINT/SIGTERM into a graceful shutdown of the scanner.

    First signal: request stop after the currently-indexing book finishes.
    Second signal: hard exit (mirrors :class:`scripts.safe_indexer.SafeIndexer`).
    """
    def handler(signum, frame):
        if not scanner.shutdown_requested:
            print("\n\n" + "=" * 60)
            print("⏸️  ABBRUCH ANGEFORDERT (CTRL+C)")
            print("=" * 60)
            print("  Aktuelles Buch wird zu Ende indexiert, dann gestoppt.")
            print("  Für sofortigen Abbruch nochmals CTRL+C drücken")
            print("  (kann das gerade laufende Buch unvollständig hinterlassen).")
            print("=" * 60 + "\n")
            scanner.request_shutdown()
        else:
            print("\n⚠️  HARTER ABBRUCH — gerade laufendes Buch ggf. unvollständig.")
            print("   Beim nächsten Lauf wird es über den Checkpoint erneut versucht.\n")
            sys.exit(1)

    signal.signal(signal.SIGINT, handler)
    if hasattr(signal, 'SIGTERM'):
        signal.signal(signal.SIGTERM, handler)


def _print_results(results: dict, json_mode: bool) -> None:
    if json_mode:
        print(json.dumps(results, indent=2, ensure_ascii=False))
        return

    n_new  = len(results['new_books'])
    n_meta = len(results['metadata_changed'])
    n_anno = len(results['annotations_changed'])
    n_unch = len(results['unchanged'])
    n_err  = len(results['errors'])

    header = "scan complete" if not results.get('interrupted') else "scan INTERRUPTED"
    print(f"\nARCHILLES Watchdog — {header} in {results['total_time']}s")
    print(f"  Scanned:              {results['scanned']} books")
    print(f"  New (not indexed):    {n_new}")
    print(f"  Metadata changed:     {n_meta}")
    print(f"  Annotations changed:  {n_anno}")
    print(f"  Unchanged:            {n_unch}")
    print(f"  Delta updates done:   {results['delta_updates']}"
          + (f" in {results['delta_time']}s" if results['delta_updates'] else ""))
    if results.get('new_indexed'):
        print(f"  New books indexed:    {results['new_indexed']}"
              + f" in {results.get('new_indexed_time', 0)}s")
    if n_err:
        print(f"  Errors:               {n_err}")
        for e in results['errors']:
            print(f"    calibre_id={e['calibre_id']}: {e['error']}")

    if results['new_books']:
        print(f"\n  New books queued for indexing:")
        for b in results['new_books'][:10]:
            book_id = b.get('calibre_id') or b.get('doc_id', '?')
            print(f"    [{book_id}] {b['title']}")
        if n_new > 10:
            print(f"    … and {n_new - 10} more")

    if results['metadata_changed']:
        ids = results['metadata_changed'][:10]
        suffix = f" … +{len(results['metadata_changed']) - 10}" if len(results['metadata_changed']) > 10 else ""
        print(f"\n  Metadata updated: {ids}{suffix}")

    if results['annotations_changed']:
        ids = results['annotations_changed'][:10]
        suffix = f" … +{len(results['annotations_changed']) - 10}" if len(results['annotations_changed']) > 10 else ""
        print(f"  Annotations updated: {ids}{suffix}")

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
        '--include-excluded', action='store_true',
        help='Process books carrying any of the configured excluded tags '
             '(see .archilles/config.json → excluded_tags, default: "exclude")'
    )
    parser.add_argument(
        '--json', dest='json_mode', action='store_true',
        help='Output results as JSON (useful for scripting or Claude Routines)'
    )
    parser.add_argument(
        '--log-file', metavar='PATH',
        help='Override log file path (default: <library>/.archilles/watchdog.log)'
    )
    parser.add_argument(
        '--first-author', metavar='AUTHOR', dest='first_authors',
        action='append', default=[],
        help='Index books by this author first (substring, case-insensitive); repeatable'
    )
    parser.add_argument(
        '--first-tag', metavar='TAG', dest='first_tags',
        action='append', default=[],
        help='Index books with this tag first (case-insensitive); repeatable'
    )
    parser.add_argument(
        '--first-title', metavar='TITLE', dest='first_titles',
        action='append', default=[],
        help='Index books whose title contains this substring first; repeatable'
    )
    args = parser.parse_args()

    library_path, db_path, archilles_dir = _resolve_paths()

    from src.archilles.config import get_excluded_tags
    excluded = [] if args.include_excluded else get_excluded_tags(library_path)
    scanner_type = _detect_scanner_type(library_path)

    if scanner_type == "zotero":
        scanner = ZoteroWatchdogScanner(
            library_path=library_path,
            db_path=db_path,
            archilles_dir=archilles_dir,
            excluded_tags=excluded,
        )
        if not args.json_mode:
            print(f"Scanner:  Zotero")
    else:
        scanner = WatchdogScanner(
            library_path=library_path,
            db_path=db_path,
            archilles_dir=archilles_dir,
            excluded_tags=excluded,
        )

    if args.log_file:
        scanner.log_file = Path(args.log_file)

    # Graceful CTRL+C / SIGTERM: finish current book, then stop. Mirrors the
    # behaviour of batch_index.py via SafeIndexer so both tools react the same
    # way to interrupts.
    _install_shutdown_handler(scanner)

    if not args.json_mode:
        print(f"Library:  {library_path}")
        print(f"Database: {db_path}")
        if args.dry_run:
            print("Mode:     dry-run (no changes will be written)\n")
        else:
            print()

    scan_kwargs: dict = {
        'dry_run': args.dry_run,
        'queue_new': args.queue_new,
        'index_new': args.index_new,
    }
    if scanner_type == "calibre":
        scan_kwargs['first_authors'] = args.first_authors
        scan_kwargs['first_tags'] = args.first_tags
        scan_kwargs['first_titles'] = args.first_titles

    results = scanner.scan(**scan_kwargs)

    _print_results(results, json_mode=args.json_mode)

    # Exit with non-zero code if there were errors
    sys.exit(1 if results['errors'] else 0)


if __name__ == '__main__':
    main()
