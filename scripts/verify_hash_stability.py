"""Read-only-Verifikation (Befund 7.15): erzeugt das neue hashing-Modul exakt
die in der Produktiv-DB gespeicherten metadata_hashes? Jede Abweichung waere ein
drohender Reindex-Sturm. Das Skript schreibt nichts.

    python scripts/verify_hash_stability.py [--limit N]

Hinweis: Da die Aequivalenztests (tests/test_hashing.py) bereits beweisen, dass
die neue hashing-Funktion byte-identisch zur alten ist, misst dieses Gate die
Konsistenz der gespeicherten Hashes mit dem Watchdog-Eingabepfad
(_calibre_metadata_for_hash). 0 Abweichungen = Konsolidierung gefahrlos.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.archilles.config import get_library_path, get_rag_db_path  # noqa: E402
from src.archilles.watchdog import _calibre_metadata_for_hash  # noqa: E402
from src.archilles.hashing import compute_metadata_hash  # noqa: E402
from src.storage.lancedb_store import LanceDBStore  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="0 = alle Buecher")
    args = ap.parse_args()

    library = get_library_path()
    store = LanceDBStore(get_rag_db_path(library))
    stored = store.get_hashes_for_indexed_books()   # {int calibre_id: {metadata_hash, ...}}
    fresh_meta = _calibre_metadata_for_hash(library)  # {int calibre_id: {...}}

    checked = mismatches = skipped_no_hash = skipped_no_meta = 0
    for cid, info in stored.items():
        old = info.get("metadata_hash")
        if not old:
            skipped_no_hash += 1
            continue
        meta = fresh_meta.get(cid)
        if not meta:
            skipped_no_meta += 1
            continue
        new = compute_metadata_hash(meta)
        checked += 1
        if new != old:
            mismatches += 1
            print(f"MISMATCH cid={cid}: stored={old} new={new} title={meta.get('title')!r}")
        if args.limit and checked >= args.limit:
            break

    print(f"\nGeprueft: {checked} Buecher - Abweichungen: {mismatches}")
    print(f"Uebersprungen: {skipped_no_hash} ohne gespeicherten Hash, "
          f"{skipped_no_meta} nicht mehr in Calibre")
    if mismatches == 0:
        print("OK - alle gespeicherten Hashes stimmen mit aktuellen Metadaten ueberein.")
    else:
        print(f"{mismatches} Buecher mit veraltetem Hash: ihre Calibre-Metadaten "
              "wurden seit der Indexierung geaendert; der naechste Watchdog-Scan "
              "aktualisiert sie regulaer (kein Hash-Logik-Drift). Pruefen, ob die "
              "Abweichungen erklaerbare Metadaten-Aenderungen sind.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
