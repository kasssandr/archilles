#!/usr/bin/env python3
"""Chat inbox for an Obsidian vault: collect AI chats, triage, review, file.

One folder receives every new chat, however it arrives — a Web Clipper note,
or a platform export (Claude or ChatGPT ``conversations.json``, or the export
ZIP) dropped there as is. ``run`` does the rest, once per logon from the Lab
routine wrapper:

1. **apply** — if the review note is ticked as done, file the ticked chats
   into ``<chats>/YYYY-MM/<date>_<platform>_<slug>.md`` and move the unticked
   ones to ``<chats>/_Verworfen/`` (never deleted).
2. **scan** — unpack exports into one note per conversation (skipping what
   the vault or the ledger already knows), bring every inbox note's
   frontmatter to the shared schema, let Claude (``claude -p``, the user's
   subscription, no API key) sort trivial from substantive and propose title,
   summary and tags from the vault's own tag vocabulary, and list the result
   in the review note ``_INBOX/KI-Chat-Review.md``.

``normalize`` brings the frontmatter of the existing archive to the same
schema; it is a dry run unless ``--apply`` is given. File bodies are never
touched, and each file keeps its line endings.

Schema (key order as written)::

    title, type, source_llm, model, source, authors, created, modified,
    description, chunking_strategy, message_count, tags, <other keys>

The inbox, the rejected folder and the review note must be excluded from
indexing (``exclude_patterns`` in the vault's ``.archilles/config.json``).
Known gap: a conversation that continues after it was filed is not updated.

Usage:
    python scripts/chat_inbox.py run D:\\Archilles-Lab --lang de
    python scripts/chat_inbox.py scan D:\\Archilles-Lab --no-triage
    python scripts/chat_inbox.py apply D:\\Archilles-Lab
    python scripts/chat_inbox.py normalize D:\\Archilles-Lab [--apply]
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlparse

import yaml

SCRIPTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPTS_DIR.parent
for _p in (str(REPO_ROOT), str(SCRIPTS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import import_chatgpt_to_vault  # noqa: E402
import import_claude_to_vault  # noqa: E402
from src.archilles.i18n import t  # noqa: E402
from vault_import import make_filename, slugify  # noqa: E402

DEFAULT_CHATS = "KI-Chats"
DEFAULT_INBOX = "_Eingang"
DEFAULT_REJECTED = "_Verworfen"
DEFAULT_REVIEW_NOTE = "_INBOX/KI-Chat-Review.md"
LEDGER = ".archilles/chat_inbox.json"
EXPORT_ARCHIVE = ".archilles/chat_exports"
SKIP_DIRS = {".archilles", ".git", ".obsidian", ".trash", "__pycache__"}

KEY_ORDER = [
    "title", "type", "source_llm", "model", "source", "authors", "created",
    "modified", "description", "chunking_strategy", "message_count", "tags",
]
DISPLAY = {
    "claude": "Claude", "chatgpt": "ChatGPT", "gemini": "Gemini",
    "perplexity": "Perplexity", "grok": "Grok", "brave": "Brave",
    "notebooklm": "Gemini Notebook",    # formerly NotebookLM; key kept for the archive
}
_LLM_ALIASES = {
    "claude": "claude", "claude.ai": "claude", "anthropic": "claude",
    "chatgpt": "chatgpt", "chatgpt.com": "chatgpt", "openai": "chatgpt",
    "gpt": "chatgpt", "gemini": "gemini", "google-ai": "gemini",
    "google": "gemini", "bard": "gemini", "perplexity": "perplexity",
    "grok": "grok", "brave": "brave", "notebooklm": "notebooklm",
    "gemini notebook": "notebooklm",
}
# Order matters: subdomains of google.com before google.com itself.
_HOSTS = [
    ("claude.ai", "claude"), ("chatgpt.com", "chatgpt"),
    ("chat.openai.com", "chatgpt"), ("gemini.google.com", "gemini"),
    ("aistudio.google.com", "gemini"), ("notebooklm.google.com", "notebooklm"),
    ("notebook.google.com", "notebooklm"),
    ("google.com", "gemini"), ("perplexity.ai", "perplexity"),
    ("grok.com", "grok"), ("search.brave.com", "brave"),
]
# Web Clipper copies the site's <meta description> — platform advertising.
_BOILERPLATE = (
    "suchen sie ganz privat im web", "search privately",
    "use the power of ai", "talk with claude", "chatgpt helps you",
    "meet gemini", "perplexity is a free", "grok is",
)
_BOILERPLATE_RE = re.compile(r"^(chatgpt|claude|gemini) conversation with \d+ messages?$", re.I)
_DROP_TAGS = {"clippings"}

_FM_RE = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(?:\r?\n|\Z)", re.S)
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")
_STEM_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})_([A-Za-z.]+)_")
_MONTH_DIR_RE = re.compile(r"^\d{4}-\d{2}$")
_PAREN_PLATFORM_RE = re.compile(r"\((claude|chatgpt|gemini|grok|perplexity)\b", re.I)


# ── Frontmatter I/O ───────────────────────────────────────────────────────────

@dataclass
class Note:
    fm: dict
    body: str
    newline: str = "\n"
    had_frontmatter: bool = True
    repaired: bool = False      # YAML was invalid and was parsed leniently
    raw: str = ""               # file text as read, for change detection


def _lenient_parse(text: str) -> dict:
    """Parse flat ``key: value`` / ``- item`` frontmatter that YAML rejects.

    Hand-written headers break YAML in predictable ways, typically an
    apostrophe inside a single-quoted title. Values stay strings; a value
    wrapped in matching quotes loses them.
    """
    out: dict = {}
    current: Optional[str] = None
    for line in text.splitlines():
        item = re.match(r"^\s+-\s*(.*)$", line)
        if item and current is not None:
            if not isinstance(out.get(current), list):
                out[current] = []
            out[current].append(_unquote(item.group(1)))
            continue
        kv = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
        if kv:
            current = kv.group(1)
            value = kv.group(2).strip()
            out[current] = _unquote(value) if value else None
    return out


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
        return value[1:-1]
    return value


def read_note(path: Path) -> Note:
    raw = path.read_bytes().decode("utf-8-sig")
    newline = "\r\n" if "\r\n" in raw else "\n"
    note = read_note_text(raw)
    note.newline = newline
    return note


def read_note_text(raw: str) -> Note:
    m = _FM_RE.match(raw)
    if not m:
        return Note(fm={}, body=raw, had_frontmatter=False, raw=raw)
    fm_text = m.group(1)
    repaired = False
    try:
        fm = yaml.safe_load(fm_text) or {}
        if not isinstance(fm, dict):
            raise yaml.YAMLError("frontmatter is not a mapping")
    except yaml.YAMLError:
        fm = _lenient_parse(fm_text)
        repaired = True
    return Note(fm=fm, body=raw[m.end():], repaired=repaired, raw=raw)


def _scalar(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    s = str(value)
    if _DATE_RE.fullmatch(s):
        return s
    plain_ok = (
        s and s == s.strip() and "\n" not in s and ": " not in s
        and " #" not in s and s[0] not in "'\"[]{}&*!|>%@`#-?:,"
    )
    if plain_ok:
        try:
            if yaml.safe_load(s) == s:
                return s
        except yaml.YAMLError:
            pass
    return json.dumps(s, ensure_ascii=False)


def dump_frontmatter(fm: dict) -> str:
    """Emit frontmatter in schema order; lists in block style."""
    keys = [k for k in KEY_ORDER if k in fm] + [k for k in fm if k not in KEY_ORDER]
    lines = []
    for key in keys:
        value = fm[key]
        if isinstance(value, list):
            if not value:
                lines.append(f"{key}: []")
            else:
                lines.append(f"{key}:")
                lines.extend(f"  - {_scalar(v)}" for v in value)
        elif isinstance(value, dict):
            dumped = yaml.safe_dump(value, allow_unicode=True, default_flow_style=True)
            lines.append(f"{key}: {dumped.strip()}")
        else:
            lines.append(f"{key}: {_scalar(value)}".rstrip())
    return "\n".join(lines)


def render_note(note: Note) -> str:
    text = "---\n" + dump_frontmatter(note.fm) + "\n---\n"
    if note.newline != "\n":
        text = text.replace("\n", note.newline)
    body = note.body
    if not note.had_frontmatter and body and not body.startswith(("\n", "\r\n")):
        body = note.newline + body
    return text + body


def write_note(path: Path, note: Note) -> None:
    path.write_bytes(render_note(note).encode("utf-8"))


# ── Normalisation ─────────────────────────────────────────────────────────────

def platform_from_url(url) -> Optional[str]:
    if not isinstance(url, str) or "://" not in url:
        return None
    host = (urlparse(url).hostname or "").lower()
    for suffix, platform in _HOSTS:
        if host == suffix or host.endswith("." + suffix):
            return platform
    return None


def _as_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [p.strip() for p in value.split(",") if p.strip()]
    if isinstance(value, list):
        return [str(v).strip() for v in value if v is not None and str(v).strip()]
    return [str(value)]


def _iso_date(value) -> Optional[str]:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        m = _DATE_RE.match(value.strip())
        return m.group(0) if m else None
    return None


def _is_boilerplate(text: str) -> bool:
    low = text.strip().lower()
    return bool(_BOILERPLATE_RE.match(low)) or any(low.startswith(b) for b in _BOILERPLATE)


def _platform_from_stem(stem: str) -> Optional[str]:
    """``2026-03-01_claude_…`` or a trailing ``(ChatGPT)`` in the filename."""
    m = _STEM_RE.match(stem)
    if m and m.group(2).lower() in _LLM_ALIASES:
        return _LLM_ALIASES[m.group(2).lower()]
    m = _PAREN_PLATFORM_RE.search(stem)
    return _LLM_ALIASES[m.group(1).lower()] if m else None


def _title_from_stem(stem: str) -> str:
    m = _STEM_RE.match(stem)
    if m and m.group(2).lower() in _LLM_ALIASES:
        title = stem[m.end():]
    else:
        title = re.sub(r"^\d{4}-\d{2}-\d{2}[_ ]", "", stem)
    return title.replace("_", " ").strip() or stem


def normalize_frontmatter(fm: dict, stem: str) -> tuple[dict, list[str]]:
    """Return ``(normalised copy, warnings)`` for one chat note.

    Rewrites what is unambiguous (German key names, Web Clipper leftovers,
    platform aliases, missing fields derivable from URL or filename) and
    only *warns* about what needs a human (several platforms in one note,
    dates that disagree, tags copied from another note).
    """
    fm = dict(fm)
    warnings: list[str] = []
    stem_match = _STEM_RE.match(stem)

    for old, new in (("titel", "title"), ("datum", "created"), ("date", "created"),
                     ("tag", "tags"), ("art", "description")):
        if old in fm and fm.get(new) in (None, "", []):
            fm[new] = fm.pop(old)

    # Platform
    raw_llm = fm.get("source_llm")
    if isinstance(raw_llm, list):
        raw_llm = ", ".join(str(v) for v in raw_llm if v) or None
        fm["source_llm"] = raw_llm
    llm = None
    if isinstance(raw_llm, str) and raw_llm.strip():
        value = raw_llm.strip()
        if "," in value:
            warnings.append(f"source_llm names several platforms: {value!r}")
        else:
            first = value.split()[0].lower()
            llm = _LLM_ALIASES.get(value.lower()) or _LLM_ALIASES.get(first)
            if llm and value.lower() not in _LLM_ALIASES and " " in value and not fm.get("model"):
                fm["model"] = value
            if llm:
                fm["source_llm"] = llm
            else:
                warnings.append(f"unknown source_llm {value!r}")
    if raw_llm in (None, "") or (isinstance(raw_llm, str) and not raw_llm.strip()):
        llm = platform_from_url(fm.get("source")) or _platform_from_stem(stem)
        if llm:
            fm["source_llm"] = llm
        else:
            fm.pop("source_llm", None)
            warnings.append("platform not determinable")

    if fm.get("type") in (None, "", "chath"):
        fm["type"] = "chat"

    # Authors: Web Clipper writes `author`, the importers `authors`.
    authors = _as_list(fm.pop("author", None)) + _as_list(fm.get("authors"))
    authors = list(dict.fromkeys(authors))
    if not authors and llm and fm["type"] == "chat":
        authors = [DISPLAY.get(llm, llm)]
    if authors:
        fm["authors"] = authors
    else:
        fm.pop("authors", None)

    if llm and "source_platform" in fm:
        fm.pop("source_platform")
    if not fm.get("published"):
        fm.pop("published", None)
    desc = fm.get("description")
    if desc in (None, "") or (isinstance(desc, str) and _is_boilerplate(desc)):
        fm.pop("description", None)
    if not fm.get("source"):
        fm.pop("source", None)

    # Dates
    created = _iso_date(fm.get("created"))
    if not created and stem_match:
        created = stem_match.group(1)
    if created:
        fm["created"] = created
    else:
        warnings.append("no created date")
    if "modified" in fm:
        modified = _iso_date(fm["modified"])
        if modified:
            fm["modified"] = modified
    if created and stem_match and stem_match.group(1) != created:
        warnings.append(f"filename date {stem_match.group(1)} differs from created {created}")

    if not fm.get("title"):
        fm["title"] = _title_from_stem(stem)

    # Tags
    tags = [tag.lstrip("#") for tag in _as_list(fm.get("tags"))]
    tags = [tag for tag in dict.fromkeys(tags) if tag and tag.lower() not in _DROP_TAGS]
    fm["tags"] = tags
    foreign = sorted({tag.lower() for tag in tags} & (set(DISPLAY) - {llm}))
    if llm and foreign:
        warnings.append(f"tags name other platforms ({', '.join(foreign)}) — copied from another note?")

    return fm, warnings


@dataclass
class NormResult:
    path: Path
    changed: bool
    changes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _diff(before: dict, after: dict) -> list[str]:
    changes = []
    for key in after:
        if key not in before:
            changes.append(f"+{key}")
        elif before[key] != after[key] and _scalar(before[key]) != _scalar(after[key]):
            changes.append(f"~{key}")
    changes += [f"-{key}" for key in before if key not in after]
    return changes


def normalize_file(path: Path, *, write: bool) -> NormResult:
    note = read_note(path)
    fm, warnings = normalize_frontmatter(note.fm, path.stem)
    if note.repaired:
        warnings.insert(0, "invalid YAML, parsed leniently")
    if path.parent.name and _MONTH_DIR_RE.match(path.parent.name) and fm.get("created"):
        if not str(fm["created"]).startswith(path.parent.name):
            warnings.append(f"lies in folder {path.parent.name}, created {fm['created']}")
    original = note.fm
    note.fm = fm
    after = render_note(note)
    changed = after != note.raw
    changes = _diff(original, fm)
    if not note.had_frontmatter:
        changes.insert(0, "frontmatter added")
    elif changed and not changes:
        changes = ["format"]
    if changed and write:
        path.write_bytes(after.encode("utf-8"))
    return NormResult(path, changed, changes if changed else [], warnings)


# ── Vault index (what is already there) ───────────────────────────────────────

def _walk_md(root: Path, skip: set[Path] = frozenset()):
    for path in sorted(root.rglob("*.md")):
        rel_parts = path.relative_to(root).parts
        if any(part in SKIP_DIRS for part in rel_parts):
            continue
        if any(path.is_relative_to(s) for s in skip):
            continue
        yield path


@dataclass
class VaultIndex:
    stems: set = field(default_factory=set)
    sources: set = field(default_factory=set)
    date_titles: set = field(default_factory=set)

    @classmethod
    def build(cls, vault: Path) -> "VaultIndex":
        idx = cls()
        for path in _walk_md(vault):
            idx.stems.add(path.stem.lower())
            try:
                fm = read_note(path).fm
            except (OSError, UnicodeDecodeError):
                continue
            if isinstance(fm.get("source"), str):
                idx.sources.add(fm["source"].strip())
            created = _iso_date(fm.get("created") or fm.get("datum"))
            title = fm.get("title") or fm.get("titel")
            if created and isinstance(title, str):
                idx.date_titles.add((created, slugify(title)))
        return idx

    def knows(self, filename: str, source: str, created: str, title: str) -> bool:
        if source in self.sources:
            return True
        if slugify(title) == "untitled":    # an untitled stem says nothing
            return False
        return (Path(filename).stem.lower() in self.stems
                or (created, slugify(title)) in self.date_titles)


def load_ledger(vault: Path) -> dict:
    path = vault / LEDGER
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    return {"seen": {}}


def save_ledger(vault: Path, ledger: dict) -> None:
    path = vault / LEDGER
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(ledger, ensure_ascii=False, indent=1), encoding="utf-8")


# ── Export import ─────────────────────────────────────────────────────────────

def _load_export(path: Path) -> Optional[list]:
    """Return the conversation list from a ``conversations.json`` or export ZIP."""
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as zf:
            names = [n for n in zf.namelist() if n.rsplit("/", 1)[-1] == "conversations.json"]
            if not names:
                return None
            data = json.loads(zf.read(names[0]).decode("utf-8"))
    else:
        data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else None


def _export_platform(conversations: list) -> Optional[str]:
    sample = next((c for c in conversations if isinstance(c, dict)), {})
    if "chat_messages" in sample:
        return "claude"
    if "mapping" in sample:
        return "chatgpt"
    return None


def _conversation_url(platform: str, conv: dict) -> str:
    if platform == "claude":
        return f"https://claude.ai/chat/{conv.get('uuid', '')}"
    return f"https://chatgpt.com/c/{conv.get('conversation_id') or conv.get('id', '')}"


def _export_files(inbox: Path) -> list[Path]:
    """Export ZIPs and bare ``conversations.json`` files waiting in the inbox."""
    return sorted(p for p in inbox.iterdir() if p.is_file() and (
        p.suffix.lower() == ".zip" or p.name.lower() == "conversations.json"))


def import_exports(vault: Path, inbox: Path, ledger: dict, index: VaultIndex,
                   min_messages: int = 2, log=print) -> int:
    """Turn every export file in the inbox into notes; returns notes written."""
    written = 0
    for export in _export_files(inbox):
        try:
            conversations = _load_export(export)
        except (OSError, json.JSONDecodeError, zipfile.BadZipFile) as e:
            log(f"  ! {export.name}: unreadable ({e})")
            continue
        platform = _export_platform(conversations or [])
        if not platform:
            log(f"  ! {export.name}: not a Claude or ChatGPT export, left in place")
            continue
        module = import_claude_to_vault if platform == "claude" else import_chatgpt_to_vault
        new = known = short = 0
        for conv in conversations:
            if len(module.extract_messages(conv)) < min_messages:
                short += 1
                continue
            url = _conversation_url(platform, conv)
            filename, markdown, _month = module.conversation_to_markdown(conv)
            note_fm = read_note_text(markdown).fm
            created = _iso_date(note_fm.get("created")) or ""
            title = str(note_fm.get("title") or "")
            if url in ledger["seen"] or index.knows(filename, url, created, title):
                known += 1
                continue
            target = _free_path(inbox / filename)
            note = read_note_text(markdown)
            note.fm["source"] = url
            write_note(target, note)
            index.sources.add(url)
            ledger["seen"][url] = {"decision": "inbox", "date": date.today().isoformat()}
            index.stems.add(target.stem.lower())
            new += 1
        archive = vault / EXPORT_ARCHIVE
        archive.mkdir(parents=True, exist_ok=True)
        shutil.move(str(export), str(_free_path(archive / f"{date.today().isoformat()}_{export.name}")))
        log(f"  {export.name}: {platform}, {new} new, {known} already known, {short} too short")
        written += new
    return written


def _free_path(path: Path) -> Path:
    if not path.exists():
        return path
    for i in range(2, 1000):
        alt = path.with_name(f"{path.stem}-{i}{path.suffix}")
        if not alt.exists():
            return alt
    raise FileExistsError(path)


# ── Review note ───────────────────────────────────────────────────────────────

@dataclass
class Item:
    stem: str
    title: str
    platform: str = ""
    created: str = ""
    words: int = 0
    description: str = ""
    tags: list = field(default_factory=list)
    keep: bool = True
    trivial: bool = False
    triaged: bool = True


_ITEM_RE = re.compile(r"^- \[([ xX])\] \*\*(.*?)\*\*(.*?)%%id:(.+?)%%\s*$")
_DONE_RE = re.compile(r"^- \[([ xX])\] .*%%chat-inbox:done%%\s*$")
_DETAIL_RE = re.compile(r"^\s+[^:]+:\s?(.*)$")
_WORDS_RE = re.compile(r"^(\d+)\s")
_SECTIONS = ("chat_inbox.section_keep", "chat_inbox.section_untriaged", "chat_inbox.section_trivial")


def parse_review(text: str, lang: str) -> tuple[bool, list[Item]]:
    """Return ``(done, items)``; user edits to box, title, summary, tags survive.

    Items are found by their hidden ``%%id:<stem>%%`` marker; the two indented
    lines below an item are its summary and its comma-separated tags.
    """
    done = False
    items: list[Item] = []
    details: list[str] = []
    section = _SECTIONS[0]
    headings = {t(key, lang): key for key in _SECTIONS}

    def flush():
        if items and details:
            items[-1].description = details[0].strip()
            if len(details) > 1:
                items[-1].tags = [x.lstrip("#") for x in _as_list(details[1])]
        details.clear()

    for line in text.splitlines():
        if line.startswith("## "):
            flush()
            heading = re.sub(r"\s*\(\d+\)\s*$", "", line[3:]).strip()
            section = headings.get(heading, section)
            continue
        done_match = _DONE_RE.match(line)
        if done_match:
            flush()
            done = done_match.group(1).lower() == "x"
            continue
        m = _ITEM_RE.match(line)
        if m:
            flush()
            item = Item(stem=m.group(4).strip(), title=m.group(2).strip(),
                        keep=m.group(1).lower() == "x",
                        trivial=section == "chat_inbox.section_trivial",
                        triaged=section != "chat_inbox.section_untriaged")
            for part in (p.strip() for p in m.group(3).split("·")):
                if _DATE_RE.fullmatch(part):
                    item.created = part
                elif part in DISPLAY:
                    item.platform = part
                elif _WORDS_RE.match(part):
                    item.words = int(_WORDS_RE.match(part).group(1))
            items.append(item)
            continue
        d = _DETAIL_RE.match(line)
        if d and items and len(details) < 2:
            details.append(d.group(1))
        elif line.strip():
            flush()
    flush()
    return done, items


def _one_line(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("**", "")).strip()


def render_review(items: list[Item], lang: str, rejected_rel: str, done: bool = False) -> str:
    lines = [f"# {t('chat_inbox.review_title', lang)}", ""]
    if not items:
        lines.append(t("chat_inbox.empty", lang))
        return "\n".join(lines) + "\n"
    lines += [t("chat_inbox.instructions", lang).format(rejected=rejected_rel), ""]
    lines += [f"- [{'x' if done else ' '}] **{t('chat_inbox.done', lang)}** %%chat-inbox:done%%", ""]
    groups = {
        "chat_inbox.section_keep": [i for i in items if i.triaged and not i.trivial],
        "chat_inbox.section_untriaged": [i for i in items if not i.triaged],
        "chat_inbox.section_trivial": [i for i in items if i.triaged and i.trivial],
    }
    for key in _SECTIONS:
        group = groups[key]
        if not group:
            continue
        lines += [f"## {t(key, lang)} ({len(group)})", ""]
        for item in group:
            parts = [item.platform, item.created,
                     t("chat_inbox.words", lang).format(n=item.words) if item.words else ""]
            meta = "".join(f" · {p}" for p in parts if p)
            lines.append(
                f"- [{'x' if item.keep else ' '}] **{_one_line(item.title)}**{meta} · "
                f"[[{item.stem}|{t('chat_inbox.open', lang)}]] %%id:{item.stem}%%"
            )
            lines.append(f"  {t('chat_inbox.summary', lang)}: {_one_line(item.description)}")
            lines.append(f"  {t('chat_inbox.tags', lang)}: {', '.join(_one_line(x) for x in item.tags)}")
        lines.append("")
    return "\n".join(lines)


# ── Triage ────────────────────────────────────────────────────────────────────

TRIAGE_SCHEMA = {
    "type": "object",
    "properties": {"items": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "keep": {"type": "boolean"},
            "title": {"type": "string"},
            "description": {"type": "string"},
            "tags": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["id", "keep", "title", "description", "tags"],
    }}},
    "required": ["items"],
}

TRIAGE_PROMPT = """You sort a researcher's AI chat transcripts before they enter a personal research archive (an Obsidian vault feeding a retrieval system). The researcher is a historian and author; the archive should hold conversations worth finding again.

For each conversation decide:
- keep: true if it develops an idea, a research or writing question, an argument, a source question, a design decision, or material worth retrieving later. false for throwaway exchanges: quick factual lookups, everyday how-to and tech support, shopping, one-off code fixes, translating a sentence, small talk.
- title: a short, specific title (max. 80 characters), written in {language}.
- description: one or two sentences, written in {language}, saying what it is about and where it lands.
- tags: 2 to 6 topic tags. Prefer tags from the existing vocabulary below, spelled exactly as listed. Coin a new tag only if nothing fits. No platform names, no generic tags like "chat" or "KI".

Existing tag vocabulary: {vocabulary}

Return one entry per conversation, using its id unchanged.

Conversations:
{conversations}"""


def _excerpt(body: str, head: int = 1500, tail: int = 400) -> str:
    text = re.sub(r"\n{3,}", "\n\n", body.strip())
    if len(text) <= head + tail + 50:
        return text
    return text[:head] + "\n[…]\n" + text[-tail:]


_GENERIC_TAGS = set(DISPLAY) | _DROP_TAGS | {
    "chat", "chat-protokoll", "ki-generiert", "ki", "ai", "source", "note", "notes",
    "notiz", "mindmap", "moc", "hub", "exclude", "session-notiz", "claude-code",
    "prompt", "prompts", "meta",
}


def tag_vocabulary(vault: Path, min_count: int = 2, limit: int = 200) -> list[str]:
    """The vault's topic tags, most frequent first.

    Spelling variants that differ only in case count together under their most
    frequent spelling; platform and housekeeping tags are left out.
    """
    counts: dict[str, dict[str, int]] = {}
    for path in _walk_md(vault):
        try:
            tags = _as_list(read_note(path).fm.get("tags"))
        except (OSError, UnicodeDecodeError):
            continue
        for tag in tags:
            tag = tag.lstrip("#")
            if tag and tag.lower() not in _GENERIC_TAGS:
                spellings = counts.setdefault(tag.lower(), {})
                spellings[tag] = spellings.get(tag, 0) + 1
    ranked = sorted(
        ((max(s, key=s.get), sum(s.values())) for s in counts.values()),
        key=lambda kv: (-kv[1], kv[0].lower()),
    )
    return [tag for tag, n in ranked if n >= min_count][:limit]


def claude_runner(model: str) -> Callable[[str], Optional[list]]:
    """Run one triage prompt through headless Claude Code; None on failure."""
    exe = shutil.which("claude")

    def run(prompt: str) -> Optional[list]:
        if not exe:
            return None
        cmd = [
            exe, "-p", "--model", model, "--tools", "", "--strict-mcp-config",
            "--no-session-persistence", "--disable-slash-commands",
            "--setting-sources", "", "--output-format", "json",
            "--json-schema", json.dumps(TRIAGE_SCHEMA),
        ]
        try:
            proc = subprocess.run(
                cmd, input=prompt, capture_output=True, text=True,
                encoding="utf-8", timeout=600, cwd=tempfile.gettempdir(),
            )
            data = json.loads(proc.stdout)
        except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
            return None
        if data.get("is_error"):
            return None
        return (data.get("structured_output") or {}).get("items")

    return run


LANGUAGE_NAMES = {"de": "German", "en": "English"}


def triage(notes: list[tuple[Path, Note]], vocabulary: list[str],
           runner: Callable[[str], Optional[list]], batch_size: int = 12,
           lang: str = "en", log=print) -> dict[str, dict]:
    """Return ``{stem: verdict}``; stems whose batch failed are absent."""
    verdicts: dict[str, dict] = {}
    for start in range(0, len(notes), batch_size):
        batch = notes[start:start + batch_size]
        ids = {f"c{start + i}": path.stem for i, (path, _) in enumerate(batch)}
        blocks = []
        for cid, (path, note) in zip(ids, batch):
            blocks.append(
                f"<conversation id=\"{cid}\" platform=\"{note.fm.get('source_llm', '')}\" "
                f"date=\"{note.fm.get('created', '')}\" title=\"{note.fm.get('title', '')}\">\n"
                f"{_excerpt(note.body)}\n</conversation>"
            )
        prompt = TRIAGE_PROMPT.format(vocabulary=", ".join(vocabulary) or "(none yet)",
                                      language=LANGUAGE_NAMES.get(lang, "the language of the conversation"),
                                      conversations="\n\n".join(blocks))
        result = runner(prompt)
        if not result:
            log(f"  ! triage failed for {len(batch)} notes — listed unsorted")
            continue
        for entry in result:
            stem = ids.get(entry.get("id", ""))
            if stem:
                verdicts[stem] = entry
        log(f"  triage {min(start + batch_size, len(notes))}/{len(notes)}")
    return verdicts


# ── Commands ──────────────────────────────────────────────────────────────────

@dataclass
class Layout:
    vault: Path
    chats: Path
    inbox: Path
    rejected: Path
    review: Path

    @classmethod
    def from_args(cls, args) -> "Layout":
        vault = args.vault.resolve()
        chats = vault / args.chats_folder
        return cls(vault, chats, chats / args.inbox_folder,
                   chats / args.rejected_folder, vault / args.review_note)


def _word_count(body: str) -> int:
    return len(re.findall(r"\w+", body))


def cmd_scan(layout: Layout, lang: str, runner, no_triage: bool, log=print) -> int:
    layout.inbox.mkdir(parents=True, exist_ok=True)
    if _export_files(layout.inbox):
        log("Exports:")
        ledger = load_ledger(layout.vault)
        index = VaultIndex.build(layout.vault)
        import_exports(layout.vault, layout.inbox, ledger, index, log=log)
        save_ledger(layout.vault, ledger)

    done, items = (parse_review(layout.review.read_text(encoding="utf-8"), lang)
                   if layout.review.exists() else (False, []))
    present = {p.stem: p for p in layout.inbox.glob("*.md")}
    kept = [i for i in items if i.stem in present]
    listed = {i.stem for i in kept}
    # A batch whose triage failed is retried on the next run.
    retry = [i for i in kept if not i.triaged]
    kept = [i for i in kept if i.triaged]
    retry_stems = {i.stem for i in retry}

    fresh: list[tuple[Path, Note]] = []
    for stem, path in sorted(present.items()):
        result = normalize_file(path, write=True)
        for w in result.warnings:
            log(f"  ? {path.name}: {w}")
        if stem not in listed or stem in retry_stems:
            fresh.append((path, read_note(path)))
    if not fresh:
        log("No new chats in the inbox.")
        if len(kept) != len(items):    # notes moved away by hand
            _write_review(layout, kept, lang, done)
        return 0

    log(f"{len(fresh)} new chats" + ("" if no_triage else ", triage with Claude …"))
    verdicts = {} if no_triage else triage(
        fresh, tag_vocabulary(layout.vault), runner, lang=lang, log=log)

    items = kept
    for path, note in fresh:
        verdict = verdicts.get(path.stem)
        fm = note.fm
        item = Item(stem=path.stem, title=str(fm.get("title") or path.stem),
                    platform=str(fm.get("source_llm") or ""), created=str(fm.get("created") or ""),
                    words=_word_count(note.body), description=str(fm.get("description") or ""),
                    tags=_as_list(fm.get("tags")))
        if verdict:
            item.title = verdict["title"].strip() or item.title
            item.description = verdict["description"].strip() or item.description
            item.tags = list(dict.fromkeys(item.tags + [x.lstrip("#") for x in verdict["tags"]]))
            item.keep = bool(verdict["keep"])
            item.trivial = not item.keep
        else:
            item.triaged = False
        items.append(item)
    _write_review(layout, items, lang)
    log(f"Review note: {layout.review.relative_to(layout.vault)}")
    return len(fresh)


def _write_review(layout: Layout, items: list[Item], lang: str, done: bool = False) -> None:
    if not items and not layout.review.exists():
        return
    layout.review.parent.mkdir(parents=True, exist_ok=True)
    rejected_rel = layout.rejected.relative_to(layout.vault).as_posix()
    layout.review.write_text(render_review(items, lang, rejected_rel, done), encoding="utf-8")


def cmd_apply(layout: Layout, lang: str, log=print) -> int:
    if not layout.review.exists():
        return 0
    done, items = parse_review(layout.review.read_text(encoding="utf-8"), lang)
    if not done:
        if items:
            log(f"Review not marked done yet ({len(items)} chats waiting).")
        return 0
    ledger = load_ledger(layout.vault)
    filed = rejected = 0
    for item in items:
        path = layout.inbox / f"{item.stem}.md"
        if not path.exists():
            continue
        note = read_note(path)
        key = str(note.fm.get("source") or item.stem)
        if item.keep:
            note.fm["title"] = item.title or note.fm.get("title")
            if item.description:
                note.fm["description"] = item.description
            else:
                note.fm.pop("description", None)
            note.fm["tags"] = item.tags
            created = str(note.fm.get("created") or date.today().isoformat())
            platform = str(note.fm.get("source_llm") or "chat")
            target_dir = layout.chats / created[:7]
            target_dir.mkdir(parents=True, exist_ok=True)
            target = _free_path(target_dir / make_filename(created, platform, note.fm["title"]))
            write_note(path, note)
            shutil.move(str(path), str(target))
            ledger["seen"][key] = {"decision": "kept", "date": date.today().isoformat(),
                                   "path": target.relative_to(layout.vault).as_posix()}
            filed += 1
        else:
            layout.rejected.mkdir(parents=True, exist_ok=True)
            shutil.move(str(path), str(_free_path(layout.rejected / path.name)))
            ledger["seen"][key] = {"decision": "rejected", "date": date.today().isoformat()}
            rejected += 1
    save_ledger(layout.vault, ledger)
    _write_review(layout, [], lang)
    log(f"Filed {filed}, rejected {rejected}.")
    return filed


def cmd_normalize(layout: Layout, write: bool, log=print) -> list[NormResult]:
    skip = {layout.inbox, layout.rejected}
    results = [normalize_file(p, write=write) for p in _walk_md(layout.chats, skip)]
    changed = [r for r in results if r.changed]
    warned = [r for r in results if r.warnings]
    for r in results:
        if not (r.changed or r.warnings):
            continue
        rel = r.path.relative_to(layout.vault).as_posix()
        log(f"{rel}")
        if r.changed:
            log(f"    changes: {' '.join(r.changes)}")
        for w in r.warnings:
            log(f"    ? {w}")
    tally: dict[str, int] = {}
    for r in changed:
        for c in r.changes:
            tally[c] = tally.get(c, 0) + 1
    log("")
    log(f"{len(results)} notes, {len(changed)} {'changed' if write else 'would change'}, "
        f"{len(warned)} with warnings")
    for change, n in sorted(tally.items(), key=lambda kv: -kv[1]):
        log(f"    {change:24} {n}")
    return results


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Collect, triage and file AI chats in an Obsidian vault")
    parser.add_argument("command", choices=["run", "scan", "apply", "normalize"])
    parser.add_argument("vault", type=Path, help="Path to the Obsidian vault")
    parser.add_argument("--chats-folder", default=DEFAULT_CHATS)
    parser.add_argument("--inbox-folder", default=DEFAULT_INBOX, help="Inbox, relative to the chats folder")
    parser.add_argument("--rejected-folder", default=DEFAULT_REJECTED, help="Relative to the chats folder")
    parser.add_argument("--review-note", default=DEFAULT_REVIEW_NOTE, help="Relative to the vault")
    parser.add_argument("--lang", default="en", help="Language of the review note (en, de)")
    parser.add_argument("--model", default="haiku", help="Claude model for the triage")
    parser.add_argument("--no-triage", action="store_true", help="List new chats without asking Claude")
    parser.add_argument("--apply", action="store_true", help="normalize: write the changes")
    args = parser.parse_args(argv)

    if not args.vault.is_dir():
        print(f"Error: vault {args.vault} not found")
        return 1
    layout = Layout.from_args(args)
    if args.command == "normalize":
        cmd_normalize(layout, write=args.apply)
        return 0
    if args.command in ("run", "apply"):
        cmd_apply(layout, args.lang)
    if args.command in ("run", "scan"):
        cmd_scan(layout, args.lang, claude_runner(args.model), args.no_triage)
    return 0


if __name__ == "__main__":
    sys.exit(main())
