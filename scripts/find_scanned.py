#!/usr/bin/env python3
"""
Find PDFs that were likely scanned (too little text relative to page count).

Identifies books where words-per-page is suspiciously low — a sign that the
PDF has no text layer and needs re-indexing with OCR.

Usage:
    # List suspicious books (default threshold: 100 words/page)
    python scripts/find_scanned.py

    # Custom threshold
    python scripts/find_scanned.py --threshold 80

    # Filter to a specific Calibre tag
    python scripts/find_scanned.py --tag "Judenkönige"

    # Output as JSON
    python scripts/find_scanned.py --json

    # Re-index all found books with OCR (dry run first!)
    python scripts/find_scanned.py --tag "Judenkönige" --reindex --dry-run
    python scripts/find_scanned.py --tag "Judenkönige" --reindex
"""

import sys
import json
import argparse
import subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd

from src.archilles.constants import ChunkType
from src.storage.lancedb_store import LanceDBStore

# Books with these tags are intentionally excluded from indexing — low chunk counts are expected
INTENTIONALLY_EXCLUDED_TAGS = {'Übersetzung', 'exclude'}

DEFAULT_DB_PATH = "D:/Calibre-Bibliothek/.archilles/rag_db"
DEFAULT_THRESHOLD = 100  # words per page below which we flag a book


def find_scanned_books(
    db_path: str = DEFAULT_DB_PATH,
    threshold: int = DEFAULT_THRESHOLD,
    tag_filter: str = None,
) -> list[dict]:
    """
    Query LanceDB for PDF books with a low words-per-page ratio.

    Returns a list of dicts sorted ascending by words_per_page (worst first).
    Books with zero content chunks (completely unextracted) are included
    regardless of threshold and sorted to the top.
    """
    store = LanceDBStore(db_path)
    if store.table is None:
        print("❌ No data in database yet.", file=sys.stderr)
        return []

    df = store.table.to_pandas()

    # Optional tag filter (tags stored as comma-separated string)
    if tag_filter:
        mask = df['tags'].str.contains(tag_filter, na=False, regex=False)
        df = df[mask]
        if df.empty:
            print(f"❌ No chunks found for tag '{tag_filter}'.", file=sys.stderr)
            return []

    # --- Book metadata: one row per book_id (from any chunk) ---
    meta = (
        df.sort_values('chunk_type')          # calibre_comment sorts first alphabetically — good
        .groupby('book_id', as_index=False)
        .first()[['book_id', 'book_title', 'author', 'format', 'source_file', 'tags', 'indexed_at']]
    )

    # --- Content chunk stats per book ---
    content_df = df[~df['chunk_type'].isin(ChunkType.NON_CONTENT_TYPES)]

    if not content_df.empty:
        def word_count(texts):
            return sum(len(str(t).split()) for t in texts)

        stats = (
            content_df.groupby('book_id', as_index=False)
            .agg(
                word_count=('text', word_count),
                max_page=('page_number', 'max'),
                chunk_count=('chunk_type', 'count'),
            )
        )
    else:
        stats = pd.DataFrame(columns=['book_id', 'word_count', 'max_page', 'chunk_count'])

    # --- Join ---
    book_df = meta.merge(stats, on='book_id', how='left')
    book_df['word_count'] = book_df['word_count'].fillna(0).astype(int)
    book_df['max_page'] = book_df['max_page'].fillna(0).astype(int)
    book_df['chunk_count'] = book_df['chunk_count'].fillna(0).astype(int)

    # Only PDFs can be scanned; EPUBs/MOBIs don't have this problem
    pdf_df = book_df[book_df['format'].str.lower().fillna('') == 'pdf'].copy()

    # words_per_page: only meaningful when we know the page count
    pdf_df['words_per_page'] = pdf_df.apply(
        lambda r: round(r['word_count'] / r['max_page'], 1) if r['max_page'] > 0 else 0.0,
        axis=1,
    )

    # Flag books:
    # - Completely empty (0 content chunks) — always flagged
    # - Low words/page below threshold (only meaningful when max_page > 0)
    flagged = pdf_df[
        (pdf_df['chunk_count'] == 0) |
        ((pdf_df['max_page'] > 0) & (pdf_df['words_per_page'] < threshold))
    ].copy()

    # Exclude books that carry an intentionally-excluded tag (Übersetzung, exclude).
    # These are skipped during normal indexing on purpose — low counts are expected.
    def has_excluded_tag(tags_str: str) -> bool:
        if not tags_str:
            return False
        book_tags = {t.strip() for t in tags_str.split(',')}
        return bool(book_tags & INTENTIONALLY_EXCLUDED_TAGS)

    excluded_mask = flagged['tags'].apply(has_excluded_tag)
    silently_skipped = flagged[excluded_mask]
    flagged = flagged[~excluded_mask]

    if not silently_skipped.empty:
        print(f"ℹ️  {len(silently_skipped)} book(s) skipped (tagged 'Übersetzung' or 'exclude' — intentionally not indexed):")
        for _, row in silently_skipped.iterrows():
            print(f"   · {row['book_title']} [{row['tags']}]")
        print()

    flagged = flagged.sort_values('words_per_page')

    result = []
    for _, row in flagged.iterrows():
        result.append({
            'book_id': row['book_id'],
            'title': row['book_title'],
            'author': row['author'],
            'words_per_page': row['words_per_page'],
            'word_count': int(row['word_count']),
            'max_page': int(row['max_page']),
            'chunk_count': int(row['chunk_count']),
            'source_file': row['source_file'],
            'indexed_at': row['indexed_at'],
            'tags': row['tags'],
        })
    return result


def reindex_book(book: dict, dry_run: bool = False, profile: str = 'minimal', enable_ocr: bool = False) -> bool:
    """Re-index a single book with --force (optionally with --enable-ocr)."""
    source_file = book['source_file']
    book_id = book['book_id']

    cmd = [
        sys.executable, 'scripts/rag_demo.py', 'index',
        source_file,
        '--book-id', book_id,
        '--force',
        '--profile', profile,
    ]
    if enable_ocr:
        cmd.append('--enable-ocr')

    if dry_run:
        print(f"  [dry-run] {' '.join(cmd)}")
        return True

    print(f"  ▶ {book['author']}: {book['title']}")
    result = subprocess.run(cmd, cwd=str(Path(__file__).parent.parent))
    return result.returncode == 0


def main():
    parser = argparse.ArgumentParser(
        description='Find scanned PDFs by low words-per-page ratio'
    )
    parser.add_argument(
        '--threshold', type=int, default=DEFAULT_THRESHOLD,
        help=f'Words-per-page below this are flagged (default: {DEFAULT_THRESHOLD})'
    )
    parser.add_argument('--tag', metavar='TAG', help='Filter to books with this Calibre tag')
    parser.add_argument('--db-path', default=DEFAULT_DB_PATH, help='Path to LanceDB database')
    parser.add_argument('--json', action='store_true', help='Output as JSON')
    parser.add_argument(
        '--reindex', action='store_true',
        help='Re-index all flagged books with --enable-ocr (use --dry-run first!)'
    )
    parser.add_argument('--dry-run', action='store_true', help='Show what would be re-indexed')
    parser.add_argument(
        '--enable-ocr', action='store_true',
        help='Add --enable-ocr to the re-index command (only needed for still-scanned PDFs)'
    )
    parser.add_argument(
        '--profile', default='minimal', choices=['minimal', 'balanced', 'maximal'],
        help='Hardware profile for re-indexing (default: minimal)'
    )
    args = parser.parse_args()

    books = find_scanned_books(
        db_path=args.db_path,
        threshold=args.threshold,
        tag_filter=args.tag,
    )

    if args.json:
        print(json.dumps(books, indent=2, ensure_ascii=False))
        return

    if not books:
        print(f"✅ No suspicious PDFs found (threshold: {args.threshold} words/page).")
        return

    scope = f" in tag '{args.tag}'" if args.tag else ""
    print(f"\n⚠️  Found {len(books)} suspicious PDFs{scope} (threshold: {args.threshold} w/p):\n")
    print(f"{'#':<4} {'W/p':>5}  {'Words':>7}  {'Pages':>5}  {'Chunks':>6}  Title")
    print("-" * 80)

    for i, book in enumerate(books, 1):
        wpp = book['words_per_page']
        wpp_str = f"{wpp:.0f}" if wpp > 0 else "—"
        pages_str = str(book['max_page']) if book['max_page'] > 0 else "?"
        flag = "🔴" if wpp < 20 else "🟡"
        title_short = book['title'][:50] + '…' if len(book['title']) > 50 else book['title']
        print(f"{i:<4} {flag} {wpp_str:>4}  {book['word_count']:>7,}  {pages_str:>5}  {book['chunk_count']:>6}  {title_short}")
        print(f"     {'':>5}  {'':>7}  {'':>5}  {'':>6}  {book['author']}")
        print()

    print("-" * 80)
    tag_arg = f' --tag "{args.tag}"' if args.tag else ''
    thr_arg = f' --threshold {args.threshold}'
    print(f"\n💡 Neu indexieren (normales PDF, z.B. nach PDF24-OCR):")
    print(f"   python scripts/find_scanned.py{tag_arg}{thr_arg} --reindex --dry-run")
    print(f"   python scripts/find_scanned.py{tag_arg}{thr_arg} --reindex")
    print(f"\n   Mit OCR (für noch nicht lesbare Scans):")
    print(f"   python scripts/find_scanned.py{tag_arg}{thr_arg} --reindex --enable-ocr")

    if not args.reindex:
        return

    print(f"\n{'='*60}")
    action = "Would re-index" if args.dry_run else "Re-indexing"
    print(f"{action} {len(books)} books with --enable-ocr ...\n")

    success, failed = 0, []
    for book in books:
        ok = reindex_book(book, dry_run=args.dry_run, profile=args.profile, enable_ocr=args.enable_ocr)
        if ok:
            success += 1
        else:
            failed.append(book['title'])

    print(f"\n{'='*60}")
    print(f"Done: {success} ok, {len(failed)} failed")
    if failed:
        print("Failed:")
        for t in failed:
            print(f"  - {t}")


if __name__ == '__main__':
    main()
