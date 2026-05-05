"""
Scan a 'My Kindle Content' directory and report per-book annotation
counts and Calibre matches in a tabular form. Reading-only convenience
wrapper around KindleProvider + BookMatcher (which is what
``rag_demo.py import-annotations`` uses).

For actual writing into the LanceDB index, use::

    python scripts/rag_demo.py import-annotations \\
        --source kindle --path "C:/Users/.../My Kindle Content"

Examples
--------
    # Whole library overview
    python scripts/scan_kindle_library.py

    # Notes-only, with full text
    python scripts/scan_kindle_library.py --with-notes-only --show-notes

    # Single ASIN
    python scripts/scan_kindle_library.py --asin B0BRWVJ3PS --show-notes
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.archilles.annotation_providers import KindleProvider  # noqa: E402
from src.archilles.config import get_library_path  # noqa: E402
from src.calibre_db import CalibreDB  # noqa: E402
from src.calibre_mcp.book_matcher import BookMatcher, load_asin_index  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, ValueError):
    pass


DEFAULT_KINDLE_DIR = Path.home() / "Documents" / "My Kindle Content"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Scan Kindle for PC library and match books to Calibre.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--kindle-dir",
        type=Path,
        default=DEFAULT_KINDLE_DIR,
        help=f"Path to 'My Kindle Content' (default: {DEFAULT_KINDLE_DIR})",
    )
    p.add_argument("--fuzzy-threshold", type=float, default=80.0)
    p.add_argument("--asin", help="Only scan this single ASIN (e.g. B0BRWVJ3PS)")
    p.add_argument(
        "--with-notes-only",
        action="store_true",
        help="Skip books that have no user notes",
    )
    p.add_argument(
        "--show-notes",
        action="store_true",
        help="After the table, print each note text grouped by Calibre book",
    )
    return p.parse_args()


def main() -> int:
    args = parse_args()
    kindle_dir: Path = args.kindle_dir
    if not kindle_dir.is_dir():
        print(f"ERROR: Kindle directory not found: {kindle_dir}", file=sys.stderr)
        return 2

    # Iterate _EBOK directories so we can build a per-book table
    book_dirs = sorted(
        d for d in kindle_dir.iterdir() if d.is_dir() and d.name.endswith("_EBOK")
    )
    if args.asin:
        book_dirs = [d for d in book_dirs if d.name.startswith(args.asin)]
        if not book_dirs:
            print(f"No _EBOK directory found for ASIN {args.asin}", file=sys.stderr)
            return 2
    print(f"Found {len(book_dirs)} _EBOK directories under {kindle_dir}")

    library = get_library_path(required=False)
    if library is None:
        print("WARNING: Calibre library path not configured (CALIBRE_LIBRARY_PATH).")
        return 1

    with CalibreDB(library) as db:
        calibre_books = db.get_all_books_brief()
    asin_index = load_asin_index(library)
    print(
        f"Calibre library: {len(calibre_books)} books "
        f"({len(asin_index)} with ASIN identifier)"
    )
    matcher = BookMatcher(
        calibre_books,
        fuzzy_threshold=args.fuzzy_threshold,
        asin_index=asin_index,
    )

    provider = KindleProvider()

    print()
    header = (
        f"{'ASIN':<12} {'Notes':>5} {'Hi':>4}  "
        f"{'Match':<7} {'CalID':>6}  Title"
    )
    print(header)
    print("-" * (len(header) * 2))

    matched_rows: list[tuple[str, list, object]] = []
    n_matched = 0
    n_with_notes = 0
    n_no_meta = 0
    n_no_match = 0
    skipped = 0

    for d in book_dirs:
        asin = d.name.removesuffix("_EBOK")
        annots = provider.extract(str(d))
        notes = [a for a in annots if a.type == "note" and a.text]
        highlights = [a for a in annots if a.type == "highlight"]
        title = annots[0].book_title if annots else ""
        author = annots[0].book_author if annots else ""

        if args.with_notes_only and not notes:
            skipped += 1
            continue

        result = matcher.match(title or "", author, asin=asin)
        n_notes = len(notes)
        n_hi = len(highlights)

        if result:
            n_matched += 1
            if n_notes:
                n_with_notes += 1
            matched_rows.append((asin, notes, result))
            print(
                f"{asin:<12} {n_notes:>5} {n_hi:>4}  "
                f"{result.match_type[:7]:<7} {result.calibre_id:>6}  "
                f"{result.calibre_title[:70]}"
            )
        elif not title:
            n_no_meta += 1
            print(
                f"{asin:<12} {n_notes:>5} {n_hi:>4}  "
                f"{'NO META':<7} {'-':>6}  -"
            )
        else:
            n_no_match += 1
            print(
                f"{asin:<12} {n_notes:>5} {n_hi:>4}  "
                f"{'NO HIT':<7} {'-':>6}  {title[:70]}"
            )

    total = len(book_dirs) - skipped
    print()
    print(
        f"Summary ({total} of {len(book_dirs)} shown): "
        f"{n_matched} matched ({n_with_notes} with notes), "
        f"{n_no_match} unmatched, {n_no_meta} without metadata."
    )
    if matched_rows:
        print(
            "\nTo write notes into LanceDB, run:\n"
            f"  python scripts/rag_demo.py import-annotations "
            f"--source kindle --path \"{kindle_dir}\""
        )

    if args.show_notes and matched_rows:
        print("\n--- Notes per matched book ---")
        for _asin, notes, result in matched_rows:
            if not notes:
                continue
            print(f"\n[{result.calibre_id}] {result.calibre_title}")
            for n in notes:
                print(f"  - {n.text}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
