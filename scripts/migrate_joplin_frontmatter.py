"""
Kopiert Joplin-Markdown-Dateien in einen Zielordner und bereinigt dabei
das YAML-Frontmatter:
  - Entfernt: latitude, longitude, altitude
  - Fügt hinzu: tags, type, chunking_strategy
  - Behält: title, created, updated
"""

import re
import shutil
import sys
from pathlib import Path

import yaml

# ── Konfiguration ────────────────────────────────────────────────────────────

SOURCE_DIR = Path(r"D:\temp\joplin-export\NLM-Mindmap KI-Chats")
TARGET_DIR = Path(r"D:\Archilles-Lab\NotebookLM\AI_Chats_Mindmap")

ADD_TAGS = ["gemini", "notebooklm", "chat", "mindmap", "KI-generiert"]
ADD_TYPE = "source"
ADD_CHUNKING = "semantic"
REMOVE_FIELDS = {"latitude", "longitude", "altitude"}

# ── Frontmatter-Parsing ──────────────────────────────────────────────────────

_FM_RE = re.compile(r"^---\r?\n(.*?)\r?\n---\r?\n", re.DOTALL)


def process_file(src: Path, dst: Path) -> str:
    """Liest src, passt Frontmatter an, schreibt nach dst. Gibt Status zurück."""
    text = src.read_text(encoding="utf-8")

    m = _FM_RE.match(text)
    if not m:
        # Kein Frontmatter → einfach kopieren, neues Frontmatter vorne einfügen
        fm: dict = {}
        body = text
    else:
        try:
            fm = yaml.safe_load(m.group(1)) or {}
        except yaml.YAMLError:
            fm = {}
        body = text[m.end():]

    # Felder entfernen
    for field in REMOVE_FIELDS:
        fm.pop(field, None)

    # Felder setzen (nicht überschreiben wenn schon vorhanden)
    fm.setdefault("tags", ADD_TAGS)
    fm.setdefault("type", ADD_TYPE)
    fm.setdefault("chunking_strategy", ADD_CHUNKING)

    # Reihenfolge: title, created, updated, type, chunking_strategy, tags, rest
    ordered_keys = ["title", "created", "updated", "type", "chunking_strategy", "tags"]
    ordered = {k: fm[k] for k in ordered_keys if k in fm}
    for k, v in fm.items():
        if k not in ordered:
            ordered[k] = v

    new_fm = yaml.dump(
        ordered,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
    ).rstrip("\n")

    new_text = f"---\n{new_fm}\n---\n{body}"
    dst.write_text(new_text, encoding="utf-8")
    return "ok"


# ── Hauptprogramm ────────────────────────────────────────────────────────────

def main(dry_run: bool = False):
    TARGET_DIR.mkdir(parents=True, exist_ok=True)

    files = sorted(SOURCE_DIR.glob("*.md"))
    if not files:
        print(f"Keine .md-Dateien in {SOURCE_DIR}")
        sys.exit(1)

    ok = skipped = errors = 0

    for src in files:
        dst = TARGET_DIR / src.name
        if dst.exists():
            skipped += 1
            continue
        if dry_run:
            print(f"[dry-run] {src.name}")
            ok += 1
            continue
        try:
            process_file(src, dst)
            ok += 1
        except Exception as e:
            print(f"FEHLER {src.name}: {e}")
            errors += 1

    print(f"\nFertig — kopiert: {ok}, übersprungen: {skipped}, Fehler: {errors}")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    if dry_run:
        print("=== DRY-RUN — keine Dateien werden geschrieben ===\n")
    main(dry_run)
