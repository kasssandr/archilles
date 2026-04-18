#!/usr/bin/env python3
"""
Backfill metadata_hash for books in LanceDB indexed before hash tracking was added.

Reads current Calibre metadata, computes the hash, and writes it directly via
LanceDB table.update() — no re-embedding, no file parsing, no GPU needed.

Usage
-----
    python scripts/backfill_metadata_hash.py               # run backfill
    python scripts/backfill_metadata_hash.py --dry-run     # show count only
    python scripts/backfill_metadata_hash.py --limit 100   # process at most N books
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.archilles.config import get_library_path
from src.archilles.watchdog import WatchdogScanner, _calibre_metadata_for_hash, _compute_metadata_hash


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Backfill metadata_hash for books indexed without hash tracking"
    )
    parser.add_argument('--dry-run', action='store_true',
                        help='Show how many books need backfilling, write nothing')
    parser.add_argument('--limit', type=int, default=0,
                        help='Process at most N books (0 = all)')
    args = parser.parse_args()

    library_path = get_library_path()
    archilles_dir = library_path / ".archilles"
    db_path = str(archilles_dir / "rag_db")

    print(f"Library:  {library_path}")
    print(f"Database: {db_path}\n")

    scanner = WatchdogScanner(library_path, db_path, archilles_dir)
    print("Loading indexed books from LanceDB...")
    indexed = scanner._load_indexed_hashes()
    without_hash = {cid: info for cid, info in indexed.items() if not info.get('metadata_hash')}

    print(f"  Total indexed:       {len(indexed)}")
    print(f"  With hash (ok):      {len(indexed) - len(without_hash)}")
    print(f"  Without hash:        {len(without_hash)}")

    if not without_hash:
        print("\nAll books already have a metadata_hash.")
        return

    print("\nReading current Calibre metadata...")
    calibre_meta = _calibre_metadata_for_hash(library_path)

    # Split: books still in Calibre vs. orphans (deleted from Calibre)
    to_backfill = {cid: info for cid, info in without_hash.items() if cid in calibre_meta}
    orphans = {cid: info for cid, info in without_hash.items() if cid not in calibre_meta}

    print(f"  Backfillable (in Calibre): {len(to_backfill)}")
    print(f"  Orphans (deleted from Calibre, skipped): {len(orphans)}")

    if not to_backfill:
        print("\nNothing to backfill.")
        return

    if args.dry_run:
        print(f"\nDry-run: {len(to_backfill)} books would receive a metadata_hash.")
        return

    to_process = list(to_backfill.items())
    if args.limit:
        to_process = to_process[:args.limit]

    # Load LanceDB table directly — skip embedding model
    from scripts.rag_demo import archillesRAG
    rag = archillesRAG(db_path=db_path, skip_model=True)
    table = rag.store.table
    if table is None:
        print("ERROR: LanceDB table not available.")
        sys.exit(1)

    print(f"\nBackfilling {len(to_process)} books (no re-embedding)...\n")

    updated = errors = 0
    t0 = time.time()

    for i, (cid, info) in enumerate(to_process, 1):
        meta = calibre_meta[cid]
        book_id = info.get('book_id') or str(cid)
        try:
            new_hash = _compute_metadata_hash(meta)
            # Direct update — no count query afterwards
            table.update(
                where=f"book_id = '{book_id}'",
                values={'metadata_hash': new_hash},
            )
            updated += 1
        except Exception as exc:
            print(f"  ERROR calibre_id={cid} book_id={book_id}: {exc}")
            errors += 1

        if i % 100 == 0 or i == len(to_process):
            elapsed = time.time() - t0
            rate = i / elapsed if elapsed > 0 else 0
            remaining = (len(to_process) - i) / rate if rate else 0
            print(f"  {i:>5}/{len(to_process)}  updated={updated}  errors={errors}  "
                  f"({rate:.1f}/s, ~{remaining:.0f}s left)")

    elapsed = time.time() - t0
    print(f"\nDone in {elapsed:.1f}s.")
    print(f"  Updated: {updated}")
    print(f"  Errors:  {errors}")
    print(f"\nRun 'python scripts/watchdog.py --dry-run' to verify.")


if __name__ == '__main__':
    main()
