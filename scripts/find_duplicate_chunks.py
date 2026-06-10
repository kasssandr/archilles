#!/usr/bin/env python3
"""
ARCHILLES Duplicate Chunk Finder (finding 1.11, code review 2026-06-10)

Read-only inventory of duplicate chunk IDs in a LanceDB database.
LanceDB does not enforce ID uniqueness, so re-indexing without a prior
delete (pre-fix behaviour) silently accumulated duplicate rows.

This tool only REPORTS duplicates — cleanup is a separate, deliberate
step to be designed once the inventory is known.

Usage:
    python scripts/find_duplicate_chunks.py                  # configured rag_db
    python scripts/find_duplicate_chunks.py --db D:/path/to/rag_db
    python scripts/find_duplicate_chunks.py --json           # machine-readable
"""

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import lancedb

from src.archilles.config import get_rag_db_path

_PROJECTION = ["id", "book_id", "chunk_type", "indexed_at"]


def summarize_duplicates(rows: list) -> dict:
    """Summarize duplicate IDs in projected rows (dicts with id/book_id).

    Returns a report dict:
        total_rows     -- number of rows scanned
        duplicate_ids  -- number of distinct IDs occurring more than once
        excess_rows    -- rows that would be removed by a dedup (copies - 1)
        books          -- {book_id: {duplicate_ids, excess_rows}}
    """
    id_counts = Counter(r["id"] for r in rows)
    dup_ids = {i for i, n in id_counts.items() if n > 1}

    books: dict = defaultdict(lambda: {"duplicate_ids": 0, "excess_rows": 0})
    seen_per_book = set()
    for r in rows:
        if r["id"] not in dup_ids:
            continue
        key = (r.get("book_id", ""), r["id"])
        if key in seen_per_book:
            continue
        seen_per_book.add(key)
        entry = books[r.get("book_id", "")]
        entry["duplicate_ids"] += 1
        entry["excess_rows"] += id_counts[r["id"]] - 1

    return {
        "total_rows": len(rows),
        "duplicate_ids": len(dup_ids),
        "excess_rows": sum(id_counts[i] - 1 for i in dup_ids),
        "books": dict(books),
    }


def scan_table(table) -> dict:
    """Scan one LanceDB table for duplicate IDs (column projection, no vectors)."""
    try:
        lance_dataset = table.to_lance()
        existing = set(lance_dataset.schema.names)
        projection = [c for c in _PROJECTION if c in existing]
        rows = lance_dataset.to_table(columns=projection).to_pylist()
    except Exception:
        df = table.search().select(_PROJECTION).limit(10_000_000).to_pandas()
        rows = df.to_dict(orient="records")
    return summarize_duplicates(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1].strip())
    parser.add_argument("--db", help="Path to the LanceDB directory (default: configured rag_db)")
    parser.add_argument("--json", action="store_true", help="Emit the raw report as JSON")
    parser.add_argument("--top", type=int, default=20, help="Show the N most affected books (default: 20)")
    args = parser.parse_args()

    db_path = args.db or get_rag_db_path()
    db = lancedb.connect(db_path)

    reports = {}
    for table_name in sorted(db.table_names()):
        reports[table_name] = scan_table(db.open_table(table_name))

    if args.json:
        print(json.dumps({"db": str(db_path), "tables": reports}, indent=2, ensure_ascii=False))
        return 0

    print(f"Duplicate chunk inventory — {db_path}\n")
    any_dups = False
    for name, report in reports.items():
        print(f"Table '{name}': {report['total_rows']} rows, "
              f"{report['duplicate_ids']} duplicate IDs, "
              f"{report['excess_rows']} excess rows")
        if not report["books"]:
            continue
        any_dups = True
        ranked = sorted(report["books"].items(),
                        key=lambda kv: kv[1]["excess_rows"], reverse=True)
        for book_id, entry in ranked[: args.top]:
            print(f"    {book_id}: {entry['duplicate_ids']} duplicate IDs, "
                  f"{entry['excess_rows']} excess rows")
        if len(ranked) > args.top:
            print(f"    ... and {len(ranked) - args.top} more books")
        print()

    if not any_dups:
        print("\nNo duplicates found — database is clean.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
