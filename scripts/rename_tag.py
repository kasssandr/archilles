#!/usr/bin/env python3
"""
Umbenennt ein Calibre-Tag in allen LanceDB-Chunks, ohne Embeddings neu zu berechnen.

Hintergrund: Calibre-Tags werden beim Indizieren in die LanceDB-Metadaten
geschrieben und bei einer Calibre-Umbenennung nicht automatisch synchronisiert.
Dieses Skript korrigiert die gespeicherten `tags`-Felder direkt per UPDATE.

Usage
-----
    python scripts/rename_tag.py --old "Old-Tag" --new "New-Tag"
    python scripts/rename_tag.py --old "Old-Tag" --new "New-Tag" --dry-run
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.archilles.config import get_library_path


def _replace_tag(tags_str: str, old: str, new: str) -> str:
    """Ersetzt `old` durch `new` in einem kommaseparierten Tags-String."""
    tags = [t.strip() for t in tags_str.split(",") if t.strip()]
    tags = [new if t == old else t for t in tags]
    return ", ".join(tags)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Umbenennt ein Tag in LanceDB-Metadaten (kein Re-Embedding)"
    )
    parser.add_argument("--old", required=True, help="Alter Tag-Name (exakt)")
    parser.add_argument("--new", required=True, help="Neuer Tag-Name")
    parser.add_argument("--dry-run", action="store_true",
                        help="Nur anzeigen, was geändert würde — nichts schreiben")
    args = parser.parse_args()

    old_tag, new_tag = args.old, args.new

    library_path = get_library_path()
    db_path = str(library_path / ".archilles" / "rag_db")

    print(f"Library:  {library_path}")
    print(f"Database: {db_path}")
    print(f"Tag:      '{old_tag}' → '{new_tag}'\n")

    from scripts.rag_demo import archillesRAG
    rag = archillesRAG(db_path=db_path, skip_model=True)
    table = rag.store.table
    if table is None:
        print("FEHLER: LanceDB-Tabelle nicht verfügbar.")
        sys.exit(1)

    print("Lade betroffene Chunks aus LanceDB...")
    # DuckDB LIKE mit %-Wildcards — findet den Tag als Substring im Tags-String
    df = table.search().where(f"tags LIKE '%{old_tag}%'", prefilter=True).to_pandas()

    if df.empty:
        print(f"Keine Chunks mit Tag '{old_tag}' gefunden.")
        return

    # Gruppiere nach book_id — Tags sind pro Buch einheitlich
    book_updates: dict[str, str] = {}
    for book_id, group in df.groupby("book_id"):
        sample_tags = group["tags"].iloc[0]
        new_tags = _replace_tag(sample_tags, old_tag, new_tag)
        if new_tags != sample_tags:
            book_updates[str(book_id)] = new_tags

    chunk_count = len(df)
    book_count = len(book_updates)

    print(f"  Chunks gefunden: {chunk_count}")
    print(f"  Bücher betroffen: {book_count}")

    if not book_updates:
        print("\nNichts zu tun (Tag-String bereits korrekt).")
        return

    if args.dry_run:
        print("\nDry-run — keine Änderungen werden geschrieben.")
        print("\nBeispiele (max. 10):")
        for book_id, new_tags in list(book_updates.items())[:10]:
            old_tags = df[df["book_id"] == book_id]["tags"].iloc[0]
            print(f"  book_id={book_id}: '{old_tags}' → '{new_tags}'")
        return

    print(f"\nAktualisiere {book_count} Bücher (kein Re-Embedding)...\n")

    updated = errors = 0
    t0 = time.time()

    for i, (book_id, new_tags) in enumerate(book_updates.items(), 1):
        try:
            table.update(
                where=f"book_id = '{book_id}'",
                values={"tags": new_tags},
            )
            updated += 1
        except Exception as exc:
            print(f"  FEHLER book_id={book_id}: {exc}")
            errors += 1

        if i % 50 == 0 or i == book_count:
            elapsed = time.time() - t0
            rate = i / elapsed if elapsed > 0 else 0
            remaining = (book_count - i) / rate if rate else 0
            print(f"  {i:>4}/{book_count}  ok={updated}  fehler={errors}  "
                  f"({rate:.1f}/s, noch ~{remaining:.0f}s)")

    elapsed = time.time() - t0
    print(f"\nFertig in {elapsed:.1f}s.")
    print(f"  Aktualisiert: {updated} Bücher ({chunk_count} Chunks)")
    print(f"  Fehler:       {errors}")


if __name__ == "__main__":
    main()
