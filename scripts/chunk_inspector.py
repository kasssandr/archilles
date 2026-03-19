#!/usr/bin/env python3
"""
ARCHILLES Chunk Inspector

Diagnostic tool for analyzing chunk quality, boundaries, and TOC alignment.
Reads chunks from LanceDB and compares them against the original document's
table of contents to identify chunking issues.

Usage:
    python scripts/chunk_inspector.py --calibre-id 1234
    python scripts/chunk_inspector.py --calibre-id 1234 --toc
    python scripts/chunk_inspector.py --calibre-id 1234 --summary-only
    python scripts/chunk_inspector.py --calibre-id 1234 --toc --export report.md
    python scripts/chunk_inspector.py --calibre-id 1234 5678 --summary-only
    python scripts/chunk_inspector.py --book-id "Author/Book/book.pdf"
"""

import argparse
import json
import os
import sys
import statistics
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).parent.parent))

import lancedb


# ---------------------------------------------------------------------------
# Config / path helpers
# ---------------------------------------------------------------------------

def get_library_path() -> Path:
    library_path = os.environ.get('ARCHILLES_LIBRARY_PATH') or os.environ.get('CALIBRE_LIBRARY_PATH')
    if not library_path:
        print("ERROR: ARCHILLES_LIBRARY_PATH (or CALIBRE_LIBRARY_PATH) not set.")
        sys.exit(1)
    return Path(library_path)


def get_rag_db_path(library_path: Path) -> str:
    config_path = library_path / ".archilles" / "config.json"
    if config_path.exists():
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        if 'rag_db_path' in config:
            return config['rag_db_path']
    return str(library_path / ".archilles" / "rag_db")


# ---------------------------------------------------------------------------
# Chunk loading
# ---------------------------------------------------------------------------

def load_chunks(db_path: str, calibre_id: Optional[int] = None,
                book_id: Optional[str] = None) -> List[dict]:
    """Load all chunks for a book from LanceDB."""
    db = lancedb.connect(db_path)
    try:
        table = db.open_table("chunks")
    except Exception as e:
        print(f"ERROR: Tabelle 'chunks' nicht gefunden: {e}")
        sys.exit(1)

    if calibre_id is not None:
        condition = f"calibre_id = {calibre_id}"
    elif book_id is not None:
        safe_id = book_id.replace("'", "''")
        condition = f"book_id = '{safe_id}'"
    else:
        print("ERROR: --calibre-id oder --book-id erforderlich.")
        sys.exit(1)

    df = table.search().where(condition).limit(10000).to_pandas()
    if df.empty:
        return []

    # Drop vector column to save memory
    if 'vector' in df.columns:
        df = df.drop(columns=['vector'])

    return df.to_dict('records')


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SENTENCE_END_CHARS = set('.!?;:\'"»)')


def is_truncated(text: str) -> bool:
    """Check if text ends mid-word/sentence."""
    stripped = text.rstrip()
    if not stripped:
        return False
    return stripped[-1] not in SENTENCE_END_CHARS


def field_coverage(chunks: List[dict], field: str) -> Tuple[int, int]:
    """Count chunks where field is non-empty."""
    filled = sum(1 for c in chunks if c.get(field) not in (None, '', 0, 0.0))
    return filled, len(chunks)


def fmt_pct(n: int, total: int) -> str:
    if total == 0:
        return "0 / 0 (0,0%)"
    return f"{n} / {total} ({100*n/total:.1f}%)"


# ---------------------------------------------------------------------------
# Output: Summary
# ---------------------------------------------------------------------------

def render_summary(chunks: List[dict]) -> List[str]:
    """Render chunk overview and statistics."""
    lines = []
    if not chunks:
        lines.append("Keine Chunks gefunden.")
        return lines

    first = chunks[0]
    title = first.get('book_title', '?')
    calibre_id = first.get('calibre_id', '?')
    fmt = first.get('format', '?')
    lang = first.get('language', '?')
    indexed = first.get('indexed_at', '?')
    if isinstance(indexed, str) and 'T' in indexed:
        indexed = indexed.split('T')[0]

    # Chunk type counts
    type_counts = Counter(c.get('chunk_type', 'content') for c in chunks)
    type_str = ", ".join(f"{k}={v}" for k, v in sorted(type_counts.items()))

    lines.append(f'=== Chunk-Inspektion: "{title}" (Calibre ID: {calibre_id}) ===')
    lines.append(f"Format: {fmt} | Sprache: {lang} | Indexiert: {indexed}")
    lines.append(f"Chunks gesamt: {len(chunks)} | Davon: {type_str}")
    lines.append("")

    # Token statistics (whitespace split)
    word_counts = [len(c.get('text', '').split()) for c in chunks if c.get('text')]
    if word_counts:
        lines.append("--- Chunk-Statistiken ---")
        lines.append("Chunk-Längen (Wörter, Whitespace-Split):")
        lines.append(f"  Min: {min(word_counts)} | Max: {max(word_counts)} | "
                      f"Median: {statistics.median(word_counts):.0f} | "
                      f"Mean: {statistics.mean(word_counts):.0f}")
        if len(word_counts) > 1:
            lines.append(f"  Standardabweichung: {statistics.stdev(word_counts):.0f}")
        lines.append("")

    # Metadata coverage
    lines.append("--- Strukturelle Metadaten ---")
    meta_fields = [
        ('chapter', 'chapter-Info'),
        ('section_title', 'section_title'),
        ('section_type', 'section_type'),
        ('page_label', 'page_label'),
        ('page_number', 'page_number'),
        ('parent_id', 'parent_id'),
        ('window_text', 'window_text'),
    ]
    for field, label in meta_fields:
        filled, total = field_coverage(chunks, field)
        suffix = ""
        if field in ('page_label', 'page_number'):
            suffix = "  [nur PDF]"
        lines.append(f"Chunks mit {label:16s}: {fmt_pct(filled, total)}{suffix}")

        # Section type breakdown
        if field == 'section_type':
            st_counts = Counter(c.get('section_type', '') for c in chunks if c.get('section_type'))
            if st_counts:
                parts = " | ".join(f"{k}: {v}" for k, v in sorted(st_counts.items()))
                lines.append(f"  → {parts}")

    lines.append("")
    return lines


# ---------------------------------------------------------------------------
# Output: Boundaries
# ---------------------------------------------------------------------------

def render_boundaries(chunks: List[dict]) -> List[str]:
    """Render first/last 80 chars of each chunk to show cut points."""
    lines = []
    content_chunks = sorted(
        [c for c in chunks if c.get('chunk_type', 'content') == 'content'],
        key=lambda c: c.get('chunk_index', 0)
    )
    if not content_chunks:
        lines.append("Keine Content-Chunks für Grenzen-Ansicht.")
        return lines

    lines.append("--- Chunk-Grenzen (erste/letzte 80 Zeichen) ---")
    lines.append("")

    for i, chunk in enumerate(content_chunks, 1):
        text = chunk.get('text', '')
        sec = chunk.get('section_type', '')
        chap = chunk.get('chapter', '')
        page = chunk.get('page_label') or chunk.get('page_number', '')

        meta_parts = []
        if sec:
            meta_parts.append(f"section={sec}")
        if chap:
            meta_parts.append(f'chapter="{chap}"')
        if page:
            meta_parts.append(f"page={page}")
        meta_str = " ".join(meta_parts)

        start_text = text[:80].replace('\n', ' ')
        end_text = text[-80:].replace('\n', ' ')

        truncated = is_truncated(text)
        trunc_marker = "  ← ABBRUCH?" if truncated else ""

        lines.append(f"[Chunk {i:03d}] {meta_str}")
        lines.append(f'  START: "{start_text}"')
        lines.append(f'  END:   "{end_text}"{trunc_marker}')
        lines.append("")

    return lines


# ---------------------------------------------------------------------------
# Output: TOC Analysis
# ---------------------------------------------------------------------------

def resolve_source_file(chunks: List[dict], library_path: Path) -> Optional[Path]:
    """Resolve path to the original book file."""
    source = None
    for c in chunks:
        s = c.get('source_file', '')
        if s:
            source = s
            break
    if not source:
        return None

    p = Path(source)
    if p.is_file():
        return p

    # Try relative to library
    candidate = library_path / source
    if candidate.is_file():
        return candidate

    return None


def extract_pdf_toc(file_path: Path) -> List[dict]:
    """Extract TOC from PDF using PyMuPDF."""
    try:
        import fitz
    except ImportError:
        print("WARNUNG: PyMuPDF (fitz) nicht installiert, PDF-TOC übersprungen.")
        return []

    doc = fitz.open(str(file_path))
    toc = doc.get_toc()
    doc.close()
    return [{'level': entry[0], 'title': entry[1], 'page': entry[2]} for entry in toc]


def extract_epub_toc(file_path: Path) -> List[dict]:
    """Extract TOC from EPUB using ebooklib."""
    try:
        import ebooklib
        from ebooklib import epub
    except ImportError:
        print("WARNUNG: ebooklib nicht installiert, EPUB-TOC übersprungen.")
        return []

    book = epub.read_epub(str(file_path), options={'ignore_ncx': False})
    toc_entries = []

    def walk_toc(items, level=1):
        for item in items:
            if isinstance(item, tuple) and len(item) == 2:
                section, children = item
                if hasattr(section, 'title'):
                    toc_entries.append({
                        'level': level,
                        'title': section.title,
                        'href': section.href if hasattr(section, 'href') else '',
                    })
                walk_toc(children, level + 1)
            elif hasattr(item, 'title'):
                toc_entries.append({
                    'level': level,
                    'title': item.title,
                    'href': item.href if hasattr(item, 'href') else '',
                })

    walk_toc(book.toc)
    return toc_entries


def render_toc_analysis(chunks: List[dict], library_path: Path) -> List[str]:
    """Compare document TOC against chunk boundaries."""
    lines = []
    file_path = resolve_source_file(chunks, library_path)
    if not file_path:
        lines.append("--- TOC-Analyse ---")
        lines.append("WARNUNG: Originaldatei nicht gefunden, TOC-Analyse übersprungen.")
        lines.append(f"  source_file in Chunks: {chunks[0].get('source_file', '(leer)')}")
        lines.append("")
        return lines

    fmt = (chunks[0].get('format', '') or '').upper()
    if not fmt:
        fmt = file_path.suffix[1:].upper()

    if fmt == 'PDF':
        toc = extract_pdf_toc(file_path)
        return _render_pdf_toc(toc, chunks, lines)
    elif fmt == 'EPUB':
        toc = extract_epub_toc(file_path)
        return _render_epub_toc(toc, chunks, lines)
    else:
        lines.append("--- TOC-Analyse ---")
        lines.append(f"TOC-Analyse für Format '{fmt}' nicht unterstützt.")
        lines.append("")
        return lines


def _render_pdf_toc(toc: List[dict], chunks: List[dict], lines: List[str]) -> List[str]:
    """Render PDF TOC analysis with chapter boundary conflict detection."""
    lines.append("--- TOC-Analyse ---")

    if not toc:
        lines.append("Kein Inhaltsverzeichnis im PDF gefunden.")
        lines.append("")
        return lines

    lines.append(f"TOC-Einträge im Dokument: {len(toc)}")
    for entry in toc:
        indent = "  " * entry['level']
        lines.append(f"  {indent}[{entry['level']}] \"{entry['title']}\" (p. {entry['page']})")
    lines.append("")

    # Build TOC page ranges: each entry covers from its page to the next entry's page - 1
    content_chunks = sorted(
        [c for c in chunks if c.get('chunk_type', 'content') == 'content'],
        key=lambda c: c.get('chunk_index', 0)
    )

    if not content_chunks:
        return lines

    # Map TOC entries to chunk ranges
    lines.append("TOC → Chunk-Mapping:")
    toc_sorted = sorted(toc, key=lambda t: t['page'])
    for i, entry in enumerate(toc_sorted):
        start_page = entry['page']
        end_page = toc_sorted[i + 1]['page'] - 1 if i + 1 < len(toc_sorted) else 99999
        matching = [
            j for j, c in enumerate(content_chunks, 1)
            if start_page <= (c.get('page_number') or 0) <= end_page
        ]
        indent = "  " * entry['level']
        if matching:
            lines.append(f"  {indent}\"{entry['title']}\" → Chunks {matching[0]:03d}-{matching[-1]:03d}")
        else:
            lines.append(f"  {indent}\"{entry['title']}\" → keine Chunks  ⚠")
    lines.append("")

    # Detect chapter boundary conflicts
    conflicts = []
    for i, chunk in enumerate(content_chunks):
        page = chunk.get('page_number') or 0
        if page == 0:
            continue
        for j, entry in enumerate(toc_sorted):
            if j == 0:
                continue
            boundary_page = entry['page']
            # Check if chunk's page_number equals the boundary page but chapter
            # still references the previous TOC entry
            chunk_chapter = chunk.get('chapter', '')
            prev_title = toc_sorted[j - 1]['title']
            curr_title = entry['title']
            if (page == boundary_page and chunk_chapter
                    and chunk_chapter != curr_title
                    and chunk_chapter == prev_title):
                conflicts.append(
                    f"Chunk {i+1:03d} (page {page}): chapter=\"{chunk_chapter}\" "
                    f"liegt auf Grenze zu \"{curr_title}\""
                )

    if conflicts:
        lines.append("Kapitelgrenzen-Konflikte:")
        for c in conflicts:
            lines.append(f"  {c}")
    else:
        lines.append("Keine Kapitelgrenzen-Konflikte erkannt.")
    lines.append("")
    return lines


def _render_epub_toc(toc: List[dict], chunks: List[dict], lines: List[str]) -> List[str]:
    """Render EPUB TOC analysis with chapter mapping."""
    lines.append("--- TOC-Analyse ---")

    if not toc:
        lines.append("Kein Inhaltsverzeichnis im EPUB gefunden.")
        lines.append("")
        return lines

    lines.append(f"TOC-Einträge im Dokument: {len(toc)}")
    for entry in toc:
        indent = "  " * entry['level']
        lines.append(f"  {indent}[{entry['level']}] \"{entry['title']}\"")
    lines.append("")

    # Map TOC entries to chunks via chapter/section_title fields
    content_chunks = sorted(
        [c for c in chunks if c.get('chunk_type', 'content') == 'content'],
        key=lambda c: c.get('chunk_index', 0)
    )

    toc_titles = {entry['title'] for entry in toc}
    chunk_chapters = set()
    for c in content_chunks:
        ch = c.get('chapter', '')
        if ch:
            chunk_chapters.add(ch)
        st = c.get('section_title', '')
        if st:
            chunk_chapters.add(st)

    lines.append("TOC → Chunk-Mapping:")
    for entry in toc:
        indent = "  " * entry['level']
        title = entry['title']
        matching = [
            j for j, c in enumerate(content_chunks, 1)
            if c.get('chapter', '') == title or c.get('section_title', '') == title
        ]
        if matching:
            lines.append(
                f"  {indent}\"{title}\" → Chunks {matching[0]:03d}-{matching[-1]:03d} ✓"
            )
        else:
            lines.append(f"  {indent}\"{title}\" → keine Chunks  ⚠")
    lines.append("")

    # TOC entries not represented in chunks
    unmatched = [t['title'] for t in toc if t['title'] not in chunk_chapters]
    if unmatched:
        lines.append("TOC-Einträge ohne Chunk-Zuordnung:")
        for t in unmatched:
            lines.append(f"  ⚠ \"{t}\"")
    else:
        lines.append("Alle TOC-Einträge in Chunks vertreten.")
    lines.append("")
    return lines


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------

def inspect_book(db_path: str, library_path: Path,
                 calibre_id: Optional[int] = None,
                 book_id: Optional[str] = None,
                 summary_only: bool = False,
                 show_toc: bool = False) -> List[str]:
    """Run full inspection for one book, return output lines."""
    chunks = load_chunks(db_path, calibre_id=calibre_id, book_id=book_id)
    if not chunks:
        id_str = f"calibre_id={calibre_id}" if calibre_id else f"book_id={book_id}"
        return [f"Keine Chunks gefunden für {id_str}.", ""]

    output = render_summary(chunks)

    if not summary_only:
        output += render_boundaries(chunks)

    if show_toc:
        output += render_toc_analysis(chunks, library_path)

    return output


def main():
    parser = argparse.ArgumentParser(
        description="ARCHILLES Chunk Inspector — Chunk-Qualität und TOC-Alignment analysieren"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--calibre-id', type=int, nargs='+',
                       help='Calibre-ID(s) der zu inspizierenden Bücher')
    group.add_argument('--book-id', type=str,
                       help='book_id (LanceDB) des zu inspizierenden Buchs')

    parser.add_argument('--summary-only', action='store_true',
                        help='Nur Übersicht, keine Chunk-Grenzen')
    parser.add_argument('--toc', action='store_true',
                        help='TOC-Analyse (braucht Zugriff auf Originaldatei)')
    parser.add_argument('--export', type=str, metavar='FILE',
                        help='Ausgabe als Markdown-Datei speichern')

    args = parser.parse_args()

    library_path = get_library_path()
    db_path = get_rag_db_path(library_path)

    all_output = []

    if args.calibre_id:
        for cid in args.calibre_id:
            result = inspect_book(
                db_path, library_path,
                calibre_id=cid,
                summary_only=args.summary_only,
                show_toc=args.toc,
            )
            all_output += result
            if len(args.calibre_id) > 1:
                all_output.append("=" * 60)
                all_output.append("")
    else:
        all_output = inspect_book(
            db_path, library_path,
            book_id=args.book_id,
            summary_only=args.summary_only,
            show_toc=args.toc,
        )

    # Output
    text = "\n".join(all_output)

    if args.export:
        with open(args.export, 'w', encoding='utf-8') as f:
            f.write(text)
        print(f"Report exportiert nach: {args.export}")
    else:
        print(text)


if __name__ == '__main__':
    main()
