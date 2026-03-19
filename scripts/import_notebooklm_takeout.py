#!/usr/bin/env python3
"""
import_notebooklm_takeout.py — Import Google Takeout NotebookLM data into Obsidian

Converts the four content types found in a NotebookLM Takeout export:

  Chat History   → Markdown with YAML frontmatter (type: chat, chunking_strategy: dialogue)
  Notes          → Markdown with YAML frontmatter (type: note)
  Sources (URL)  → Markdown with YAML frontmatter (type: source) — PDFs are SKIPPED
  Research       → Markdown extracted from Discovered Sources JSON (type: deep-research)

Usage:
    python scripts/import_notebooklm_takeout.py \\
        --takeout "C:/Users/me/Downloads/Takeout" \\
        --vault "D:/Archilles-Lab" \\
        [--notebook "My Notebook"]   \\  # process one notebook only
        [--dry-run]                  \\  # preview without writing
        [--skip-existing]            \\  # don't overwrite already-imported files
        [--output-dir "./out"]          # write here instead of vault

Input structure expected inside <takeout>/NotebookLM/:
    <Notebook Name>/
        Chat History.html           (or <title>.html matching "Chat History")
        Notes.html                  (or similar)
        Sources/
            <source title>.html
            <source title>.json     (or <source title> metadata.json)
        Discovered Sources/
            <query>.json

Output structure written to <vault>/NotebookLM/<Notebook Name>/:
    Chats/
        Chat History.md
    Notes/
        Notes.md
    Sources/
        <source title>.md
    Research/
        <query>.md
"""

import argparse
import json
import logging
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


# ── HTML → Markdown conversion ────────────────────────────────────────────────

def _html_to_markdown(html_content: str) -> str:
    """Convert HTML fragment to Markdown using BeautifulSoup."""
    try:
        from bs4 import BeautifulSoup, NavigableString, Tag
    except ImportError:
        logger.error("beautifulsoup4 not installed. Run: pip install beautifulsoup4")
        sys.exit(1)

    soup = BeautifulSoup(html_content, 'lxml')

    def _node_to_md(node) -> str:
        if isinstance(node, NavigableString):
            return str(node)

        if not isinstance(node, Tag):
            return ''

        name = node.name.lower() if node.name else ''
        children_md = ''.join(_node_to_md(c) for c in node.children)

        if name in ('h1',):
            return f"# {children_md.strip()}\n\n"
        if name in ('h2',):
            return f"## {children_md.strip()}\n\n"
        if name in ('h3',):
            return f"### {children_md.strip()}\n\n"
        if name in ('h4',):
            return f"#### {children_md.strip()}\n\n"
        if name in ('h5', 'h6'):
            return f"##### {children_md.strip()}\n\n"
        if name == 'p':
            text = children_md.strip()
            return f"{text}\n\n" if text else ''
        if name == 'br':
            return '\n'
        if name in ('strong', 'b'):
            text = children_md.strip()
            return f"**{text}**" if text else ''
        if name in ('em', 'i'):
            text = children_md.strip()
            return f"*{text}*" if text else ''
        if name == 'a':
            href = node.get('href', '')
            text = children_md.strip() or href
            return f"[{text}]({href})" if href else text
        if name in ('ul', 'ol'):
            return children_md + '\n'
        if name == 'li':
            return f"- {children_md.strip()}\n"
        if name in ('hr',):
            return '\n---\n\n'
        if name in ('div', 'section', 'article', 'main', 'body', 'html',
                    'head', 'span', 'code', 'pre'):
            return children_md
        # Unknown tag: just return children
        return children_md

    md = _node_to_md(soup)
    # Collapse 3+ blank lines → 2
    md = re.sub(r'\n{3,}', '\n\n', md)
    return md.strip()


def _strip_html_tags(html: str) -> str:
    """Quick tag-stripping fallback (no BeautifulSoup needed for simple paragraphs)."""
    clean = re.sub(r'<[^>]+>', '', html)
    import html as html_module
    return html_module.unescape(clean)


# ── Chat History HTML parser ──────────────────────────────────────────────────

def _parse_chat_history_html(html_path: Path) -> str:
    """Convert NotebookLM Chat History HTML to dialogue-format Markdown.

    The HTML file uses per-line prefixes: ``MODEL: <p>...</p>`` or ``USER: <p>...</p>``.
    Each prefix marks one turn; paragraphs within a turn are separated by newlines.
    """
    try:
        text = html_path.read_text(encoding='utf-8', errors='replace')
    except OSError as exc:
        logger.warning("Cannot read %s: %s", html_path, exc)
        return ''

    # The file may be a line-oriented format or a full HTML document.
    # Try line-oriented first (Takeout Chat History format).
    lines = text.splitlines()
    turn_pattern = re.compile(r'^(MODEL|USER)\s*:\s*(.*)', re.IGNORECASE)

    turns: list[tuple[str, str]] = []  # (role, html_content) accumulator
    current_role: Optional[str] = None
    current_parts: list[str] = []

    for line in lines:
        m = turn_pattern.match(line)
        if m:
            if current_role is not None:
                turns.append((current_role, '\n'.join(current_parts)))
            current_role = m.group(1).upper()
            current_parts = [m.group(2)] if m.group(2).strip() else []
        elif current_role is not None:
            # Include blank lines too — they separate HTML blocks within a turn
            current_parts.append(line)

    if current_role is not None:
        turns.append((current_role, '\n'.join(current_parts)))

    if not turns:
        # Fallback: treat the whole file as HTML and convert directly
        return _html_to_markdown(text)

    # Convert each turn to Markdown
    md_parts: list[str] = []
    for role, html_content in turns:
        label = "**User:**" if role == 'USER' else "**Gemini:**"
        # Join accumulated lines with newlines to preserve HTML block structure
        full_html = html_content if isinstance(html_content, str) else '\n'.join(html_content)
        body = _html_to_markdown(full_html) if '<' in full_html else _strip_html_tags(full_html)
        body = body.strip()
        if body:
            md_parts.append(f"{label}\n{body}")

    return '\n\n'.join(md_parts)


# ── Notes HTML parser ─────────────────────────────────────────────────────────

def _parse_notes_html(html_path: Path) -> str:
    """Convert NotebookLM Notes HTML to Markdown."""
    try:
        text = html_path.read_text(encoding='utf-8', errors='replace')
    except OSError as exc:
        logger.warning("Cannot read %s: %s", html_path, exc)
        return ''

    return _html_to_markdown(text)


# ── Source file parsers ───────────────────────────────────────────────────────

SOURCE_TYPE_PDF = 'SOURCE_CONTENT_TYPE_PDF'
SOURCE_TYPE_URL = 'SOURCE_CONTENT_TYPE_URL'
SOURCE_TYPE_TEXT = 'SOURCE_CONTENT_TYPE_TEXT'

# Source types that are always skipped — only PDF, because it's already in Calibre.
# YouTube and Audio are NOT skipped: NotebookLM exports their transcripts as text,
# which is unique content not available elsewhere. Empty transcripts are caught later
# by the empty-body check.
SOURCE_TYPES_SKIP = {
    SOURCE_TYPE_PDF,
}

# File extensions that reveal a TEXT source is actually an uploaded book/document
# (e.g. user uploaded a .txt extracted from a PDF → treat same as PDF)
_DOCUMENT_EXTENSIONS = {'.pdf', '.txt', '.epub', '.mobi', '.azw3', '.djvu', '.doc', '.docx'}

# Subdirectory names (lowercase) that are handled separately — skip when scanning for chat/notes
_SOURCES_SUBDIRS = {'sources', 'discovered sources', 'artifacts'}

# Patterns that reliably indicate an uploaded book/document rather than a web source.
# Checked against the first ~3 KB of raw HTML to avoid false positives from article body text.
_BOOK_MARKERS = re.compile(
    r'ISBN[-\s–—]?\d'                           # ISBN-10/13 in any notation
    r'|[Aa]ll [Rr]ights [Rr]eserved'            # copyright boilerplate
    r'|©\s*\d{4}'                               # © year
    r'|[Cc]opyright\s*©?\s*\d{4}'              # Copyright 2021 / Copyright © 2021
    r'|[Tt]able of [Cc]ontents'                 # ToC heading
    r'|[Ff]irst [Pp]rinting'                    # edition info
    r'|[Ss]econd [Pp]rinting'
    r'|[Nn]o part of this (?:book|work|publication) may'  # reproduction notice
    r'|[Pp]ublished by\b'                        # publisher line
)


def _is_book_content(raw_html: str) -> bool:
    """Return True if *raw_html* looks like an uploaded book rather than a web article.

    Only the first 3 000 characters are scanned — copyright pages and title
    pages always appear at the very start of a book export, never in a web article.
    """
    return bool(_BOOK_MARKERS.search(raw_html[:3000]))


def _read_source_metadata(html_path: Path) -> dict:
    """Read the JSON sidecar for a source file.

    NotebookLM Takeout places metadata either as:
      - ``<stem>.json``          (same stem as the HTML)
      - ``<stem> metadata.json`` (explicit 'metadata' suffix)
    """
    candidates = [
        html_path.with_suffix('.json'),
        html_path.parent / f"{html_path.stem} metadata.json",
    ]
    for cand in candidates:
        if cand.is_file():
            try:
                return json.loads(cand.read_text(encoding='utf-8'))
            except (json.JSONDecodeError, OSError) as exc:
                logger.debug("Failed to read sidecar %s: %s", cand, exc)
    return {}


def _parse_source_html(html_path: Path) -> tuple[str, dict]:
    """Convert a source HTML file to Markdown.

    Returns (markdown_text, metadata_dict).
    metadata_dict keys of interest: originalSourceContentType, url, title.
    Caller should skip if content type is SOURCE_CONTENT_TYPE_PDF.
    """
    meta = _read_source_metadata(html_path)

    content_type = meta.get('originalSourceContentType', '')
    if content_type in SOURCE_TYPES_SKIP:
        return '', meta  # caller must skip

    try:
        html_text = html_path.read_text(encoding='utf-8', errors='replace')
    except OSError as exc:
        logger.warning("Cannot read source %s: %s", html_path, exc)
        return '', meta

    if _is_book_content(html_text):
        return '', {**meta, '_skip_reason': 'book_content'}

    md = _html_to_markdown(html_text)
    return md, meta


# ── Discovered Sources / Deep Research JSON parser ───────────────────────────

def _parse_discovered_sources_json(json_path: Path) -> list[dict]:
    """Extract deep-research reports from a Discovered Sources JSON file.

    Returns a list of dicts with keys: title, query, markdown.
    """
    try:
        data = json.loads(json_path.read_text(encoding='utf-8'))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("Cannot read %s: %s", json_path, exc)
        return []

    job = data.get('discoverSourcesJob', {})
    query = job.get('query', json_path.stem)
    results = job.get('discoverSourcesResults', {})
    sources = results.get('discoveredSources', [])

    entries: list[dict] = []
    for src in sources:
        report = (
            src.get('deepResearchMetadata', {}).get('deepResearchReport', '').strip()
        )
        if not report:
            continue
        entries.append({
            'title': src.get('title', 'Untitled'),
            'query': query,
            'markdown': report,
        })

    return entries


# ── Filename helpers ──────────────────────────────────────────────────────────

def _slugify(name: str, max_len: int = 80) -> str:
    """Convert *name* to a safe filesystem name."""
    # Normalise unicode (NFKD → ASCII where possible)
    name = unicodedata.normalize('NFKD', name)
    name = name.encode('ascii', 'ignore').decode('ascii')
    # Replace path-unsafe characters
    name = re.sub(r'[\\/:*?"<>|]', '_', name)
    # Collapse whitespace/underscores
    name = re.sub(r'[\s_]+', '_', name).strip('_')
    return name[:max_len] or 'untitled'


def _safe_stem(path: Path) -> str:
    """Return a slugified version of path.stem."""
    return _slugify(path.stem)


# ── YAML frontmatter builder ──────────────────────────────────────────────────

def _yaml_str(value: str) -> str:
    """Wrap a string value for inline YAML (quote if needed)."""
    if not value:
        return '""'
    # Needs quoting if it contains special YAML chars or starts with certain chars
    if re.search(r'[:#\[\]{},|>&*!\'"%@`]', value) or value[0] in '-?':
        escaped = value.replace('"', '\\"')
        return f'"{escaped}"'
    return value


def _build_frontmatter(fields: dict) -> str:
    """Produce a YAML frontmatter block from *fields*."""
    lines = ['---']
    for key, val in fields.items():
        if val is None:
            continue
        if isinstance(val, list):
            if not val:
                lines.append(f"{key}: []")
            else:
                lines.append(f"{key}:")
                for item in val:
                    lines.append(f"  - {_yaml_str(str(item))}")
        elif isinstance(val, bool):
            lines.append(f"{key}: {'true' if val else 'false'}")
        elif isinstance(val, (int, float)):
            lines.append(f"{key}: {val}")
        else:
            lines.append(f"{key}: {_yaml_str(str(val))}")
    lines.append('---')
    return '\n'.join(lines) + '\n\n'


# ── Markdown file writers ─────────────────────────────────────────────────────

def _write_md(path: Path, frontmatter: dict, body: str, dry_run: bool,
              skip_existing: bool) -> bool:
    """Write a Markdown file with YAML frontmatter.

    Returns True if the file was written (or would be in dry-run), False if skipped.
    """
    if skip_existing and path.exists():
        logger.debug("Skipping existing: %s", path)
        return False

    content = _build_frontmatter(frontmatter) + body.strip() + '\n'

    if dry_run:
        print(f"  [DRY-RUN] → {path}")
        return True

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding='utf-8')
    return True


# ── Per-notebook processing ───────────────────────────────────────────────────

def _detect_html_type(path: Path) -> str:
    """Return 'chat' or 'note' based on file content and name.

    Chat detection: the file contains ``MODEL:`` or ``USER:`` prefix lines
    (NotebookLM Chat History format).  Everything else is treated as a note.
    Filename hints (chat/note) are checked first as a fast path.
    """
    stem_lower = path.stem.lower()
    if 'chat' in stem_lower:
        return 'chat'

    # Content-based detection: peek at the first 4 KB
    try:
        with path.open(encoding='utf-8', errors='replace') as fh:
            sample = fh.read(4096)
    except OSError:
        return 'note'

    if re.search(r'^(MODEL|USER)\s*:', sample, re.MULTILINE | re.IGNORECASE):
        return 'chat'
    return 'note'


def _is_uploaded_document(title: str) -> bool:
    """True if the source title suggests an uploaded file rather than a web URL.

    When a user uploads a .txt (extracted from a PDF) to NotebookLM the
    originalSourceContentType becomes SOURCE_CONTENT_TYPE_TEXT, not PDF.
    We detect this by looking for a document extension in the title.
    """
    return Path(title).suffix.lower() in _DOCUMENT_EXTENSIONS


def _process_notebook(
    notebook_dir: Path,
    out_base: Path,
    dry_run: bool,
    skip_existing: bool,
    all_sources: bool = False,
) -> dict[str, int]:
    """Process one NotebookLM notebook folder.

    Returns a counter dict: written, skipped, skipped_nontextual, skipped_empty, errors.
    """
    stats = {'written': 0, 'skipped': 0, 'skipped_nontextual': 0, 'skipped_empty': 0, 'errors': 0}
    notebook_name = notebook_dir.name
    out_nb = out_base / _slugify(notebook_name)
    now_iso = datetime.now(tz=timezone.utc).isoformat()

    print(f"\n  Notebook: {notebook_name}")

    # ── Chat History & Notes ─────────────────────────────────────
    # Scan ALL HTML files in the notebook tree except Sources / Discovered Sources.
    # Type is detected by content (MODEL:/USER: lines → chat, else → note).
    for html_file in sorted(notebook_dir.rglob('*.html')):
        # Skip files inside source/research subdirs
        try:
            rel_parts = [p.lower() for p in html_file.relative_to(notebook_dir).parts[:-1]]
        except ValueError:
            continue
        if any(part in _SOURCES_SUBDIRS for part in rel_parts):
            continue

        html_type = _detect_html_type(html_file)

        if html_type == 'chat':
            body = _parse_chat_history_html(html_file)
            if not body.strip():
                logger.warning("Empty chat history: %s", html_file)
                stats['errors'] += 1
                continue
            out_path = out_nb / 'Chats' / f"{_safe_stem(html_file)}.md"
            fm = {
                'title': html_file.stem,
                'type': 'chat',
                'source_llm': 'gemini',
                'chunking_strategy': 'dialogue',
                'notebook': notebook_name,
                'imported_at': now_iso,
                'tags': ['notebooklm', 'chat', 'gemini'],
            }
            written = _write_md(out_path, fm, body, dry_run, skip_existing)
            stats['written' if written else 'skipped'] += 1
            if written and not dry_run:
                print(f"    ✓ Chat: {out_path.name}")
        else:
            body = _parse_notes_html(html_file)
            if not body.strip():
                logger.warning("Empty notes file: %s", html_file)
                stats['errors'] += 1
                continue
            out_path = out_nb / 'Notes' / f"{_safe_stem(html_file)}.md"
            fm = {
                'title': html_file.stem,
                'type': 'note',
                'source': 'notebooklm',
                'notebook': notebook_name,
                'imported_at': now_iso,
                'tags': ['notebooklm', 'note'],
            }
            written = _write_md(out_path, fm, body, dry_run, skip_existing)
            stats['written' if written else 'skipped'] += 1
            if written and not dry_run:
                print(f"    ✓ Note: {out_path.name}")

    # ── Sources ──────────────────────────────────────────────────
    sources_dir = notebook_dir / 'Sources'
    if sources_dir.is_dir():
        for html_file in sorted(sources_dir.glob('*.html')):
            body, meta = _parse_source_html(html_file)
            content_type = meta.get('originalSourceContentType', '')

            url = meta.get('url', '') or meta.get('sourceUrl', '')
            title = meta.get('title', '') or html_file.stem

            if not all_sources:
                if content_type in SOURCE_TYPES_SKIP:
                    logger.debug("Skipping non-textual source (%s): %s", content_type, html_file.name)
                    stats['skipped_nontextual'] += 1
                    continue
                # Skip uploaded documents regardless of declared content_type.
                # Covers: (a) PDF/EPUB/TXT files uploaded by user (title ends in .pdf etc.),
                # (b) cases where the JSON sidecar is missing and content_type is empty.
                # Exception: explicit URL sources are always included even if title looks odd.
                if content_type != SOURCE_TYPE_URL and _is_uploaded_document(title):
                    logger.debug("Skipping uploaded document (%s): %s", title, html_file.name)
                    stats['skipped_nontextual'] += 1
                    continue

            if not body.strip():
                if not all_sources and meta.get('_skip_reason') == 'book_content':
                    logger.debug("Skipping book content: %s", html_file.name)
                    stats['skipped_nontextual'] += 1
                else:
                    logger.debug("Skipping empty source: %s", html_file.name)
                    stats['skipped_empty'] += 1
                continue

            out_path = out_nb / 'Sources' / f"{_safe_stem(html_file)}.md"
            fm = {
                'title': title,
                'type': 'source',
                'source': 'notebooklm',
                'notebook': notebook_name,
                'imported_at': now_iso,
                'tags': ['notebooklm', 'source'],
            }
            if url:
                fm['url'] = url
            if content_type:
                fm['source_content_type'] = content_type

            written = _write_md(out_path, fm, body, dry_run, skip_existing)
            stats['written' if written else 'skipped'] += 1
            if written and not dry_run:
                print(f"    ✓ Source: {out_path.name}")

    # ── Artifacts ────────────────────────────────────────────────
    # Artifacts are Markdown files generated by NotebookLM (study guides,
    # FAQs, timelines, etc.) — already in Markdown, just add frontmatter.
    artifacts_dir = notebook_dir / 'Artifacts'
    if artifacts_dir.is_dir():
        for md_file in sorted(artifacts_dir.glob('*.md')):
            try:
                body = md_file.read_text(encoding='utf-8', errors='replace').strip()
            except OSError as exc:
                logger.warning("Cannot read artifact %s: %s", md_file, exc)
                stats['errors'] += 1
                continue
            if not body:
                stats['skipped_empty'] += 1
                continue

            out_path = out_nb / 'Artifacts' / f"{_safe_stem(md_file)}.md"
            fm = {
                'title': md_file.stem,
                'type': 'artifact',
                'source': 'notebooklm',
                'notebook': notebook_name,
                'imported_at': now_iso,
                'tags': ['notebooklm', 'artifact'],
            }
            written = _write_md(out_path, fm, body, dry_run, skip_existing)
            stats['written' if written else 'skipped'] += 1
            if written and not dry_run:
                print(f"    ✓ Artifact: {out_path.name}")

    # ── Discovered Sources / Deep Research ───────────────────────
    research_dir = notebook_dir / 'Discovered Sources'
    if not research_dir.is_dir():
        # Some exports use slightly different folder names
        for candidate in notebook_dir.iterdir():
            if candidate.is_dir() and 'discover' in candidate.name.lower():
                research_dir = candidate
                break

    if research_dir.is_dir():
        for json_file in sorted(research_dir.glob('*.json')):
            entries = _parse_discovered_sources_json(json_file)
            if not entries:
                logger.debug("No deep-research entries in %s", json_file.name)
                continue

            for entry in entries:
                slug = _slugify(entry['title'])
                out_path = out_nb / 'Research' / f"{slug}.md"
                fm = {
                    'title': entry['title'],
                    'type': 'deep-research',
                    'source': 'notebooklm',
                    'notebook': notebook_name,
                    'research_query': entry['query'],
                    'imported_at': now_iso,
                    'tags': ['notebooklm', 'deep-research'],
                }
                written = _write_md(out_path, fm, entry['markdown'], dry_run, skip_existing)
                stats['written' if written else 'skipped'] += 1
                if written and not dry_run:
                    print(f"    ✓ Research: {out_path.name}")

    return stats


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description='Import Google Takeout NotebookLM data into an Obsidian vault.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        '--takeout', required=True,
        help='Path to the Google Takeout directory (containing NotebookLM/ subfolder)',
    )
    parser.add_argument(
        '--vault',
        help='Path to the Obsidian vault root (output goes to <vault>/NotebookLM/)',
    )
    parser.add_argument(
        '--output-dir',
        help='Alternative output directory (use instead of --vault)',
    )
    parser.add_argument(
        '--notebook',
        help='Process only this notebook (by name or partial match)',
    )
    parser.add_argument(
        '--dry-run', action='store_true',
        help='Preview actions without writing any files',
    )
    parser.add_argument(
        '--skip-existing', action='store_true',
        help='Skip files that already exist in the output directory',
    )
    parser.add_argument(
        '--all-sources', action='store_true',
        help=(
            'Import ALL sources without filtering — disables book/document detection. '
            'Useful if you want everything and will clean up manually.'
        ),
    )
    parser.add_argument(
        '--verbose', '-v', action='store_true',
        help='Show debug output',
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format='%(levelname)s: %(message)s',
    )

    # ── Resolve paths ────────────────────────────────────────────
    takeout_root = Path(args.takeout).expanduser()
    if not takeout_root.is_dir():
        print(f"ERROR: Takeout path not found: {takeout_root}", file=sys.stderr)
        sys.exit(1)

    notebooklm_dir = takeout_root / 'NotebookLM'
    if not notebooklm_dir.is_dir():
        # Try one level up — user may have passed the NotebookLM folder directly
        if (takeout_root / 'NotebookLM').is_dir():
            notebooklm_dir = takeout_root / 'NotebookLM'
        else:
            notebooklm_dir = takeout_root  # assume it IS the NotebookLM folder

    if args.output_dir:
        out_base = Path(args.output_dir).expanduser()
    elif args.vault:
        out_base = Path(args.vault).expanduser() / 'NotebookLM'
    else:
        print("ERROR: Provide --vault or --output-dir", file=sys.stderr)
        sys.exit(1)

    # ── Discover notebooks ───────────────────────────────────────
    notebooks = [d for d in sorted(notebooklm_dir.iterdir()) if d.is_dir()]
    if not notebooks:
        print(f"No notebook folders found in {notebooklm_dir}", file=sys.stderr)
        sys.exit(1)

    if args.notebook:
        needle = args.notebook.lower()
        notebooks = [nb for nb in notebooks if needle in nb.name.lower()]
        if not notebooks:
            print(f"No notebook matching '{args.notebook}'", file=sys.stderr)
            sys.exit(1)

    # ── Process ──────────────────────────────────────────────────
    print(f"NotebookLM Takeout Import")
    print(f"  Source : {notebooklm_dir}")
    print(f"  Output : {out_base}")
    if args.dry_run:
        print("  Mode   : DRY-RUN (no files will be written)")
    print(f"  Notebooks found: {len(notebooks)}")

    total = {'written': 0, 'skipped': 0, 'skipped_nontextual': 0, 'skipped_empty': 0, 'errors': 0}

    for nb_dir in notebooks:
        stats = _process_notebook(nb_dir, out_base, args.dry_run, args.skip_existing, args.all_sources)
        for k in total:
            total[k] += stats[k]

    print(f"\nDone.")
    print(f"  Written        : {total['written']}")
    print(f"  Skipped        : {total['skipped']}")
    print(f"  Skip non-text  : {total['skipped_nontextual']} (PDFs / uploaded documents / books)")
    if total['skipped_empty']:
        print(f"  Skip empty     : {total['skipped_empty']} (no text content after conversion)")
    if total['errors']:
        print(f"  Errors         : {total['errors']}")


if __name__ == '__main__':
    main()
