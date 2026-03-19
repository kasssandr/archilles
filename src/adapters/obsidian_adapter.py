"""
Obsidian adapter — indexes an Obsidian vault as a structured document source.

Extends FolderAdapter with Obsidian-specific intelligence:
- YAML frontmatter parsing for title, tags, authors, timestamps, custom fields
- Wikilink extraction ([[Target]]) stored in custom_fields["wikilinks"]
- Inline tag extraction (#tag) merged with frontmatter tags
- Exclusion of .trash/ directory
- Auto-detection via .obsidian/ directory presence
"""

import logging
import os
import re
from pathlib import Path
from typing import Optional

from src.adapters.base import DocumentMetadata, DocumentTimestamps
from src.adapters.folder_adapter import (
    FolderAdapter,
    IGNORED_DIRS,
    SUPPORTED_EXTENSIONS,
    _stable_doc_id,
    _file_timestamps,
    _parse_filename,
)

logger = logging.getLogger(__name__)

# Directories to exclude in addition to FolderAdapter.IGNORED_DIRS
OBSIDIAN_EXTRA_EXCLUDED = {'.trash'}

WIKILINK_PATTERN = re.compile(
    r'\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]+)?\]\]'
)
INLINE_TAG_PATTERN = re.compile(
    r'(?<!\w)#([a-zA-Z\u00C0-\u024F][\w\u00C0-\u024F/\-]*)'
)


def parse_frontmatter(file_path: Path) -> tuple[dict, str]:
    """Read a Markdown file and separate YAML frontmatter from body text.

    Returns
    -------
    (frontmatter_dict, body_text)
        If the file begins with ``---`` and a closing ``---`` is found,
        the block is parsed as YAML.  Any error yields an empty dict.
        If no frontmatter is present, the whole file content is returned as body.
    """
    try:
        text = file_path.read_text(encoding='utf-8', errors='replace')
    except OSError as exc:
        logger.warning("Cannot read %s: %s", file_path, exc)
        return {}, ""

    if not text.startswith('---'):
        return {}, text

    end = text.find('\n---', 3)
    if end == -1:
        return {}, text

    yaml_block = text[3:end].strip()
    body = text[end + 4:].lstrip('\n')

    try:
        import yaml  # lazy import — PyYAML
        fm = yaml.safe_load(yaml_block) or {}
        if not isinstance(fm, dict):
            fm = {}
    except Exception as exc:
        logger.debug("Frontmatter parse error in %s: %s", file_path, exc)
        fm = {}

    return fm, body


def extract_wikilinks(body: str) -> list[str]:
    """Return unique wikilink targets from *body*, preserving order."""
    seen: set[str] = set()
    result: list[str] = []
    for m in WIKILINK_PATTERN.finditer(body):
        target = m.group(1).strip()
        if target and target not in seen:
            seen.add(target)
            result.append(target)
    return result


def extract_inline_tags(body: str) -> list[str]:
    """Return unique inline tags (``#tag``) from *body*.

    Markdown headings (``# Heading``) are excluded because they are
    preceded by whitespace at the start of a line and the lookbehind
    ``(?<!\\w)`` will still match them — we additionally skip matches
    where the preceding character is a newline or the match is at the
    very start of the line.
    """
    seen: set[str] = set()
    result: list[str] = []
    for m in INLINE_TAG_PATTERN.finditer(body):
        # Exclude heading-style matches: # at start of line
        start = m.start()
        if start == 0 or body[start - 1] in ('\n', '\r'):
            continue
        tag = m.group(1)
        if tag not in seen:
            seen.add(tag)
            result.append(tag)
    return result


def _normalize_list(value) -> list[str]:
    """Coerce a frontmatter value to a list of strings."""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value if v is not None]
    return [str(value)]


class ObsidianAdapter(FolderAdapter):
    """Adapter for Obsidian vaults.

    Inherits recursive file scanning from :class:`FolderAdapter` and adds:
    - YAML frontmatter → structured metadata for ``.md`` files
    - Wikilink extraction into ``custom_fields["wikilinks"]``
    - Inline tag merging with frontmatter tags
    - ``.trash/`` directory exclusion
    """

    @property
    def adapter_type(self) -> str:
        return "obsidian"

    def _get_attachment_folder(self) -> Optional[str]:
        """Read ``attachmentFolderPath`` from ``.obsidian/app.json`` if present."""
        app_json = self._library_path / ".obsidian" / "app.json"
        if not app_json.is_file():
            return None
        try:
            import json
            data = json.loads(app_json.read_text(encoding='utf-8'))
            return data.get("attachmentFolderPath")
        except Exception:
            return None

    def _scan(self) -> dict[str, DocumentMetadata]:
        """Scan vault, additionally excluding ``.trash/``."""
        effective_ignored = IGNORED_DIRS | OBSIDIAN_EXTRA_EXCLUDED
        result = {}
        for dirpath, dirnames, filenames in os.walk(self._library_path):
            dirnames[:] = [d for d in dirnames if d not in effective_ignored]
            for fname in filenames:
                fp = Path(dirpath) / fname
                if fp.suffix.lower() not in SUPPORTED_EXTENSIONS:
                    continue
                rel_posix = fp.relative_to(self._library_path).as_posix()
                result[rel_posix] = self._build_metadata(fp)
        return result

    def _build_metadata(self, file_path: Path) -> DocumentMetadata:
        """Build metadata, enriched with frontmatter for ``.md`` files."""
        if file_path.suffix.lower() not in {'.md', '.markdown'}:
            return super()._build_metadata(file_path)

        doc_id = _stable_doc_id(self._library_path, file_path)
        fm, body = parse_frontmatter(file_path)

        # ── Title ────────────────────────────────────────────────
        title = fm.get('title') or file_path.stem

        # ── Authors ──────────────────────────────────────────────
        authors = _normalize_list(fm.get('authors') or fm.get('author'))

        # ── Tags: frontmatter + inline ───────────────────────────
        fm_tags = _normalize_list(fm.get('tags') or fm.get('tag'))
        inline_tags = extract_inline_tags(body)
        all_tags: list[str] = []
        seen_tags: set[str] = set()
        for t in fm_tags + inline_tags:
            if t not in seen_tags:
                seen_tags.add(t)
                all_tags.append(t)

        # ── Year ─────────────────────────────────────────────────
        year = None
        raw_created = fm.get('created') or fm.get('date')
        if raw_created:
            try:
                year = int(str(raw_created)[:4])
            except (ValueError, TypeError):
                pass

        # ── Language ─────────────────────────────────────────────
        language = str(fm.get('language', '') or '')

        # ── Timestamps ───────────────────────────────────────────
        fs_ts = _file_timestamps(file_path)
        created_iso = None
        if raw_created:
            try:
                created_iso = str(raw_created)
            except Exception:
                pass
        timestamps = DocumentTimestamps(
            created_at=created_iso or fs_ts.created_at,
            modified_at=fs_ts.modified_at,
            imported_at=None,
            indexed_at=None,
        )

        # ── Custom fields ────────────────────────────────────────
        custom: dict = {
            'wikilinks': extract_wikilinks(body),
        }
        note_type = fm.get('type', '')
        if note_type:
            custom['type'] = str(note_type)
        source_llm = fm.get('source_llm', '')
        if source_llm:
            custom['source_llm'] = str(source_llm)
        aliases = _normalize_list(fm.get('aliases'))
        if aliases:
            custom['aliases'] = aliases

        # ── First paragraph as comment/preview ───────────────────
        comments = ''
        for para in body.split('\n\n'):
            stripped = para.strip()
            if stripped and not stripped.startswith('#'):
                comments = stripped
                break

        return DocumentMetadata(
            doc_id=doc_id,
            title=title,
            authors=authors,
            file_path=file_path,
            file_format='md',
            tags=all_tags,
            comments=comments,
            language=language,
            year=year,
            publisher='',
            series='',
            identifiers={},
            custom_fields=custom,
            timestamps=timestamps,
        )

    def get_comments(self, doc_id: str) -> str:
        meta = self.get_metadata(doc_id)
        return meta.comments if meta else ""
