#!/usr/bin/env python3
"""
OCR every Calibre book tagged ``_OCR`` with OCRmyPDF, in place.

OCRmyPDF lays an invisible text layer over the *unchanged* page images, so a
JBIG2 scan keeps its size and quality (PDF24 re-encodes the images and can
blow a 4 MB book up to 150 MB). Per book:

1. OCR the PDF into a work folder (``--skip-text``: pages that already carry
   text are left alone).
2. Check the result: same page count, some text, bounded size growth.
3. Copy the original into the backup folder.
4. Replace the PDF in Calibre via ``calibredb add_format`` and swap the tag
   ``_OCR`` for ``OCRmyPDF``.

Calibre is only written through ``calibredb`` (write policy). With the
Calibre GUI open, calibredb refuses a direct library path — close Calibre
first, or pass ``--with-library`` with a content-server URL.

Usage:
    python scripts/ocr_tagged.py --dry-run          # list what would run
    python scripts/ocr_tagged.py --limit 3          # first three (smallest first)
    python scripts/ocr_tagged.py                    # all books tagged _OCR
    python scripts/ocr_tagged.py --ids 2277 840     # only these Calibre ids
    python scripts/ocr_tagged.py --redo --ids 4603  # redo the text layer of a done book
"""

import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.archilles.config import get_library_path

GHOSTSCRIPT_DIRS = [
    Path(r"C:\Program Files\PDF24\gs\bin"),
    Path(r"C:\Program Files\gs"),
]
DEFAULT_BACKUP = Path(r"D:\Calibre-OCR-Originale")
SKIP_TAG = "_OCRed"   # already OCR'd elsewhere, original lost — nothing to gain


def ensure_ghostscript() -> None:
    """Put a Ghostscript bin folder on PATH if none is reachable."""
    if shutil.which("gswin64c") or shutil.which("gs"):
        return
    for base in GHOSTSCRIPT_DIRS:
        hits = [base] if (base / "gswin64c.exe").exists() else list(base.glob("*/bin"))
        for d in hits:
            if (d / "gswin64c.exe").exists():
                os.environ["PATH"] += os.pathsep + str(d)
                return
    sys.exit("Ghostscript not found (looked in PDF24 and C:\\Program Files\\gs).")


def installed_tesseract_langs() -> set[str]:
    out = subprocess.run(["tesseract", "--list-langs"], capture_output=True, text=True)
    return {l.strip() for l in out.stdout.splitlines()[1:] if l.strip()}


def ocr_languages(calibre_langs: list[str], installed: set[str]) -> str:
    """Calibre stores ISO 639-2 codes (deu, eng, fra), which are Tesseract's names."""
    codes = [c for c in calibre_langs if c in installed]
    return "+".join(dict.fromkeys(codes)) or "eng"


def find_books(library: Path, tag: str | None, ids: list[int] | None) -> list[dict]:
    """Books carrying *tag*; with ``tag=None``, the books in *ids* whatever their tags."""
    db = sqlite3.connect(f"file:{library / 'metadata.db'}?mode=ro", uri=True)
    if tag is None:
        where, params = f"b.id IN ({','.join('?' * len(ids))})", tuple(ids)
    else:
        where, params = "b.id IN (SELECT bt.book FROM books_tags_link bt JOIN tags t ON t.id = bt.tag WHERE t.name = ?)", (tag,)
    rows = db.execute(
        f"""
        SELECT b.id, b.title, b.path,
               (SELECT group_concat(l.lang_code) FROM books_languages_link bl
                  JOIN languages l ON l.id = bl.lang_code WHERE bl.book = b.id),
               (SELECT group_concat(t2.name, '|') FROM books_tags_link x
                  JOIN tags t2 ON t2.id = x.tag WHERE x.book = b.id),
               (SELECT d.name FROM data d WHERE d.book = b.id AND d.format = 'PDF')
        FROM books b
        WHERE {where}
        """,
        params,
    ).fetchall()
    db.close()
    books = []
    for bid, title, path, langs, tags, pdf_name in rows:
        if ids and bid not in ids:
            continue
        pdf = library / path / f"{pdf_name}.pdf" if pdf_name else None
        books.append({
            "id": bid, "title": title,
            "langs": (langs or "").split(",") if langs else [],
            "tags": (tags or "").split("|") if tags else [],
            "pdf": pdf,
            "size": pdf.stat().st_size if pdf and pdf.exists() else 0,
        })
    return sorted(books, key=lambda b: b["size"])


def calibredb(args: list[str], library: str) -> subprocess.CompletedProcess:
    return subprocess.run(["calibredb", *args, "--with-library", library],
                          capture_output=True, text=True)


def check_result(original: Path, result: Path, max_growth: float) -> tuple[bool, str]:
    import fitz
    a, b = fitz.open(original), fitz.open(result)
    try:
        if a.page_count != b.page_count:
            return False, f"page count {a.page_count} -> {b.page_count}"
        chars = sum(len(p.get_text()) for p in b)
        if chars == 0:
            return False, "no text recognised"
        growth = result.stat().st_size / max(original.stat().st_size, 1)
        if growth > max_growth:
            return False, f"file grew x{growth:.1f} (limit x{max_growth})"
        return True, f"{chars} chars, {chars // max(b.page_count, 1)}/page, size x{growth:.2f}"
    finally:
        a.close(); b.close()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tag", default="_OCR", help="Calibre tag that marks books to OCR")
    ap.add_argument("--done-tag", default="OCRmyPDF", help="tag set after a successful run")
    ap.add_argument("--ids", type=int, nargs="*", help="only these Calibre book ids")
    ap.add_argument("--limit", type=int, help="process at most N books")
    ap.add_argument("--jobs", type=int, default=6, help="CPU workers for OCRmyPDF")
    ap.add_argument("--oversample", type=int, default=300,
                    help="upscale page images below this DPI before OCR (text layer only; "
                    "the stored image is untouched). Rescues small caps in low-res scans")
    ap.add_argument("--redo", action="store_true",
                    help="re-OCR the books given by --ids whatever their tags: replaces only "
                    "the hidden text layer (--redo-ocr), images stay as they are")
    ap.add_argument("--max-growth", type=float, default=2.0,
                    help="reject a result larger than this multiple of the original")
    ap.add_argument("--backup-dir", type=Path, default=DEFAULT_BACKUP)
    ap.add_argument("--with-library", help="calibredb target (default: library path; "
                    "a content-server URL lets the Calibre GUI stay open)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    library = get_library_path()
    target = args.with_library or str(library)
    installed = installed_tesseract_langs()
    if args.redo and not args.ids:
        sys.exit("--redo needs --ids (which books to re-OCR).")
    books = find_books(library, None if args.redo else args.tag, args.ids)

    todo, skipped = [], []
    for b in books:
        if SKIP_TAG in b["tags"] and not args.redo:
            skipped.append((b, f"also tagged {SKIP_TAG}"))
        elif not b["pdf"] or not b["pdf"].exists():
            skipped.append((b, "no PDF"))
        else:
            todo.append(b)
    if args.limit:
        todo = todo[: args.limit]

    scope = "selected for re-OCR" if args.redo else f"tagged {args.tag}"
    print(f"{len(books)} books {scope}: {len(todo)} to OCR, {len(skipped)} skipped")
    for b, why in skipped:
        print(f"  skip [{b['id']}] {b['title'][:60]} — {why}")
    for b in todo:
        print(f"  [{b['id']}] {b['size'] / 1e6:7.1f} MB  {ocr_languages(b['langs'], installed):8}  {b['title'][:60]}")
    if args.dry_run or not todo:
        return

    probe = calibredb(["list", "--limit", "1", "--fields", "title"], target)
    if probe.returncode != 0:
        sys.exit("calibredb cannot open the library — is the Calibre GUI open? Close it "
                 "(or use --with-library with a content-server URL).\n" + probe.stderr.strip())

    ensure_ghostscript()
    work = args.backup_dir / "_work"
    work.mkdir(parents=True, exist_ok=True)
    log_path = args.backup_dir / "ocr_log.jsonl"

    for n, b in enumerate(todo, 1):
        print(f"\n=== {n}/{len(todo)}  [{b['id']}] {b['title'][:70]}", flush=True)
        lang = ocr_languages(b["langs"], installed)
        out = work / f"{b['id']}.pdf"
        t0 = time.time()
        proc = subprocess.run([
            sys.executable, "-m", "ocrmypdf", "-l", lang,
            "--output-type", "pdf", "--optimize", "0",
            "--redo-ocr" if args.redo else "--skip-text",
            "--oversample", str(args.oversample),
            "--jobs", str(args.jobs), str(b["pdf"]), str(out),
        ])
        entry = {"id": b["id"], "title": b["title"], "lang": lang,
                 "seconds": round(time.time() - t0), "time": datetime.now().isoformat(timespec="seconds")}

        if proc.returncode != 0 or not out.exists():
            entry.update(status="ocr_failed", detail=f"ocrmypdf exit {proc.returncode}")
        else:
            ok, detail = check_result(b["pdf"], out, args.max_growth)
            entry["detail"] = detail
            if not ok:
                entry["status"] = "rejected"   # result stays in _work for a look
            else:
                backup = args.backup_dir / f"{b['id']} - {b['pdf'].name}"
                if not backup.exists():   # a redo must not overwrite the true original
                    shutil.copy2(b["pdf"], backup)
                r = calibredb(["add_format", str(b["id"]), str(out)], target)
                if r.returncode != 0:
                    entry.update(status="calibre_failed", detail=r.stderr.strip()[-300:])
                else:
                    tags = [t for t in b["tags"] if t != args.tag]
                    if args.done_tag not in tags:
                        tags.append(args.done_tag)
                    r = calibredb(["set_metadata", str(b["id"]), "--field", "tags:" + ",".join(tags)], target)
                    entry["status"] = "done" if r.returncode == 0 else "done_tags_failed"
                    out.unlink()
        print(f"  -> {entry['status']}: {entry.get('detail', '')}  ({entry['seconds']} s)", flush=True)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    print(f"\nLog: {log_path}")


if __name__ == "__main__":
    main()
