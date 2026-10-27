"""Sync AI chat exports into an Obsidian vault without duplicates.

The ``import_<platform>_to_vault.py`` scripts parse their platform's export
into :class:`ChatConversation` objects and hand them to
:func:`run_sync`. This module decides, per conversation, whether a
note already exists and what may be done to it.

Identity
    A chat is identified by ``(provider, chat_id)``. The importer writes both
    into the note's frontmatter. A web clip carries the id in its source URL
    (``claude.ai/chat/<id>``, ``chatgpt.com/c/<id>``, ...), so a clip and a
    later export of the same chat meet on the id, however either was edited.

What the sync may change
    The generated chat sits between ``<!-- archilles:chat:start -->`` and
    ``<!-- archilles:chat:end -->``, and the frontmatter records the hash of
    that region and the id of the last message written (``chat_last_message``).

    * Region unchanged since the last sync: it is regenerated.
    * Region edited in Obsidian (additions, restructuring, deletions, any mix):
      nothing in it is touched. Messages after ``chat_last_message`` are
      appended before the end marker. Deleted messages stay deleted, because
      the position comes from the id, not from the text.
    * Only the frontmatter keys in :data:`OWNED_KEYS` are rewritten; every
      other line (title, tags, the user's own fields) stays as it is.

Notes without sync state (old imports, web clips)
    Fingerprints of the conversation's messages locate how much of the chat a
    note already holds. A note holding a prefix of the chat is adopted and the
    rest appended. A fragmentary clip is rebuilt from the export; paragraphs
    of the clip that the export does not contain are kept as the user's own
    additions. A note without an id is matched by fingerprint alone. When
    several conversations claim it, the one whose opening it holds furthest
    gets it; a tie is reported and none of the tied chats is created.

Every note that is changed is first copied to
``<vault>/.archilles/chat-sync-backup/<timestamp>/``. Nothing is deleted:
duplicates and conflicts are reported, not resolved.
"""

from __future__ import annotations

import hashlib
import re
import shutil
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

import yaml

try:  # run as a script from scripts/, or imported as scripts.chat_sync
    from vault_import import get_month_folder, make_filename
except ImportError:  # pragma: no cover - depends on how the module is loaded
    from scripts.vault_import import get_month_folder, make_filename

START_MARKER = "<!-- archilles:chat:start -->"
END_MARKER = "<!-- archilles:chat:end -->"
CONTINUED_MARKER = "<!-- archilles:chat:continued {date} -->"
ADDITIONS_HEADING = "## Eigene Ergänzungen (aus dem Clip)"

# Frontmatter keys the sync rewrites on every write. All other keys belong to
# the user once the note exists.
OWNED_KEYS = (
    "modified",
    "message_count",
    "chat_id",
    "chat_url",
    "chat_last_message",
    "chat_body_hash",
    "chat_synced",
)

# Frontmatter keys a web clip may keep its source URL in.
URL_KEYS = ("chat_url", "source", "url", "link")

# Directories never scanned (same set the Folder/Obsidian adapters skip).
SKIP_DIRS = {".archilles", ".git", ".obsidian", ".trash", "__pycache__", "node_modules"}

# Chat ids in the source URL, per provider.
URL_PATTERNS = {
    "claude": re.compile(r"claude\.ai/chat/([0-9a-f-]{36})", re.I),
    "chatgpt": re.compile(r"(?:chatgpt\.com|chat\.openai\.com)/(?:g/[^/]+/)?c/([0-9a-z-]+)", re.I),
    "grok": re.compile(r"grok\.com/(?:chat|c)/([0-9a-z-]+)", re.I),
    "gemini": re.compile(r"gemini\.google\.com/app/([0-9a-z]+)", re.I),
    "perplexity": re.compile(r"perplexity\.ai/search/([^/?#\s]+)", re.I),
}

URL_TEMPLATES = {
    "claude": "https://claude.ai/chat/{id}",
    "chatgpt": "https://chatgpt.com/c/{id}",
    "grok": "https://grok.com/chat/{id}",
}

# Providers whose export ids are the ids in their URLs. A note carrying such
# an id is never matched to a different conversation by fingerprint.
URL_ID_PROVIDERS = {"claude", "chatgpt", "grok"}

SHINGLE_SIZE = 5
MESSAGE_FOUND = 0.5      # share of a message's shingles that must be in the note
PREFIX_COVERAGE = 0.75   # share of messages up to the last one found
MATCH_SCORE = 0.6        # share of an id-less note's shingles found in the chat
MIN_SHARED = 8           # shingles an id-less match must share at least
COMMON_SHINGLE = 25      # shingles in more notes than this are boilerplate
MIN_ADDITION_WORDS = 4   # shorter paragraphs are clip debris, not additions


# ── Data ───────────────────────────────────────────────────────────────────

@dataclass
class ChatMessage:
    id: str
    role: str                       # "user" | "assistant"
    text: str
    timestamp: Optional[datetime] = None


@dataclass
class ChatConversation:
    provider: str                   # "claude", "chatgpt", "grok", "gemini"
    chat_id: str
    title: str
    messages: list[ChatMessage]
    assistant_label: str            # e.g. "**Claude:**"
    authors: str                    # e.g. "Claude"
    source_platform: str            # e.g. "claude.ai"
    created: Optional[datetime] = None
    updated: Optional[datetime] = None
    summary: str = ""
    model: str = ""
    # Texts of the export's other branches (regenerated answers, edited
    # prompts). Never written; they let the fingerprint find a note an older
    # importer wrote from a different branch.
    match_texts: list[str] = field(default_factory=list)

    @property
    def url(self) -> str:
        template = URL_TEMPLATES.get(self.provider)
        return template.format(id=self.chat_id) if template else ""


@dataclass
class Note:
    path: Path
    frontmatter: dict
    fm_lines: Optional[list[str]]   # raw lines between the --- fences, or None
    body: str
    newline: str = "\n"

    @property
    def provider(self) -> str:
        url_provider = provider_from_url(self.url)
        if url_provider:
            return url_provider
        return str(self.frontmatter.get("source_llm") or "").lower()

    @property
    def url(self) -> str:
        for key in URL_KEYS:
            value = self.frontmatter.get(key)
            if isinstance(value, str) and value.startswith("http"):
                return value
        return ""

    @property
    def chat_id(self) -> str:
        value = self.frontmatter.get("chat_id")
        if value:
            return str(value)
        return chat_id_from_url(self.url)

    @property
    def managed(self) -> bool:
        """Written by this sync before (knows its last message)."""
        return bool(self.frontmatter.get("chat_last_message"))

    @property
    def is_clip(self) -> bool:
        """A web clip: a source URL, but not written by an importer."""
        return bool(self.url) and "message_count" not in self.frontmatter


@dataclass
class Action:
    kind: str           # created|updated|appended|adopted|rebuilt|unchanged|conflict|duplicate|ambiguous
    conversation: Optional[ChatConversation]
    path: Optional[Path]
    detail: str = ""


@dataclass
class SyncResult:
    actions: list[Action] = field(default_factory=list)

    def count(self, kind: str) -> int:
        return sum(1 for a in self.actions if a.kind == kind)


# ── Ids ────────────────────────────────────────────────────────────────────

def provider_from_url(url: str) -> str:
    for provider, pattern in URL_PATTERNS.items():
        if url and pattern.search(url):
            return provider
    return ""


def chat_id_from_url(url: str) -> str:
    for pattern in URL_PATTERNS.values():
        match = pattern.search(url or "")
        if match:
            return match.group(1)
    return ""


def content_id(*parts: object) -> str:
    """Stable id for platforms whose export carries none (Gemini)."""
    raw = "\x1f".join("" if p is None else str(p) for p in parts)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


# ── Fingerprints ───────────────────────────────────────────────────────────

_COMMENT = re.compile(r"<!--.*?-->", re.S)
_MD_LINK = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_NON_WORD = re.compile(r"[^\w]+")


def words(text: str) -> list[str]:
    """Words of a text with Markdown, punctuation and case removed."""
    text = unicodedata.normalize("NFKC", text).lower()
    text = _COMMENT.sub(" ", text)
    text = _MD_LINK.sub(r"\1", text)
    return _NON_WORD.sub(" ", text).split()


def shingles(text: str) -> set[str]:
    """Overlapping word n-grams; a short text is one shingle."""
    w = words(text)
    if not w:
        return set()
    if len(w) < SHINGLE_SIZE:
        return {" ".join(w)}
    return {" ".join(w[i:i + SHINGLE_SIZE]) for i in range(len(w) - SHINGLE_SIZE + 1)}


class TextFingerprint:
    """Containment test against a note's (or a chat's) text."""

    def __init__(self, text: str):
        self.shingles = shingles(text)
        self.flat = " " + " ".join(words(text)) + " "

    def contains(self, text: str, threshold: float = MESSAGE_FOUND) -> bool:
        w = words(text)
        if not w:
            return False
        if len(w) < SHINGLE_SIZE:
            return (" " + " ".join(w) + " ") in self.flat
        own = shingles(text)
        return len(own & self.shingles) / len(own) >= threshold


def locate_messages(note_text: str, messages: list[ChatMessage]) -> list[bool]:
    """Which of the conversation's messages the note still holds."""
    fp = TextFingerprint(note_text)
    return [fp.contains(m.text) for m in messages]


def prefix_end(found: list[bool]) -> Optional[int]:
    """Index of the last message held, if the note holds a prefix of the chat.

    Deleted or shortened messages are tolerated as long as most messages up to
    the last one found are still there. Returns ``None`` for a fragment.
    """
    if not any(found):
        return None
    last = max(i for i, f in enumerate(found) if f)
    coverage = sum(found[: last + 1]) / (last + 1)
    return last if coverage >= PREFIX_COVERAGE else None


def paragraphs(text: str) -> list[str]:
    text = _COMMENT.sub("", text)
    return [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]


def own_paragraphs(note_body: str, conversation: ChatConversation) -> list[str]:
    """Paragraphs of a note that the conversation does not contain."""
    chat_fp = TextFingerprint("\n\n".join(
        [conversation.summary] + [m.text for m in conversation.messages]))
    title_words = words(conversation.title)
    result = []
    for para in paragraphs(note_body):
        w = words(para)
        if len(w) < MIN_ADDITION_WORDS or w == title_words:
            continue
        if para.lstrip().startswith(ADDITIONS_HEADING):
            continue
        if not chat_fp.contains(para):
            result.append(para)
    return result


# ── Note files ─────────────────────────────────────────────────────────────

_FENCE = re.compile(r"\A---[ \t]*\n(.*?\n)?---[ \t]*(?:\n|\Z)", re.S)


def parse_note(path: Path, text: str) -> Note:
    newline = "\r\n" if "\r\n" in text else "\n"
    text = text.replace("\r\n", "\n")
    match = _FENCE.match(text)
    if not match:
        return Note(path, {}, None, text, newline)
    raw = match.group(1) or ""
    try:
        frontmatter = yaml.safe_load(raw) or {}
        if not isinstance(frontmatter, dict):
            frontmatter = {}
    except yaml.YAMLError:
        frontmatter = {}
    return Note(path, frontmatter, raw.splitlines(), text[match.end():], newline)


def read_note(path: Path) -> Note:
    return parse_note(path, path.read_text(encoding="utf-8-sig"))


def _yaml_scalar(value: object) -> str:
    text = str(value)
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/+-]*", text) and not text.endswith(":"):
        return text
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def set_keys(fm_lines: list[str], values: dict) -> list[str]:
    """Rewrite the given top-level keys in place; append the missing ones.

    Lines of other keys are kept verbatim, so the user's formatting survives.
    """
    lines = list(fm_lines)
    for key, value in values.items():
        if value is None:
            continue
        new_line = f"{key}: {_yaml_scalar(value)}"
        pattern = re.compile(rf"^{re.escape(key)}\s*:")
        for i, line in enumerate(lines):
            if pattern.match(line):
                lines[i] = new_line
                break
        else:
            lines.append(new_line)
    return lines


def assemble(fm_lines: list[str], body: str, newline: str = "\n") -> str:
    text = "---\n" + "\n".join(fm_lines) + "\n---\n" + body
    if not text.endswith("\n"):
        text += "\n"
    return text.replace("\n", newline) if newline != "\n" else text


# ── Rendering ──────────────────────────────────────────────────────────────

def render_messages(messages: Iterable[ChatMessage], assistant_label: str) -> str:
    out: list[str] = []
    for msg in messages:
        label = "**User:**" if msg.role == "user" else assistant_label
        out += [label, "", msg.text, "", "---", ""]
    return "\n".join(out)


def render_region(conversation: ChatConversation) -> str:
    inner = ""
    if conversation.summary:
        inner += f"> {conversation.summary[:500]}\n\n---\n\n"
    inner += render_messages(conversation.messages, conversation.assistant_label)
    return f"{START_MARKER}\n{inner.rstrip()}\n{END_MARKER}"


def region_hash(region: str) -> str:
    normalized = "\n".join(line.rstrip() for line in region.replace("\r\n", "\n").split("\n"))
    return hashlib.sha256(normalized.strip().encode("utf-8")).hexdigest()[:16]


def find_region(body: str) -> Optional[tuple[int, int]]:
    """Span of the generated region including both markers, if intact."""
    start = body.find(START_MARKER)
    end = body.rfind(END_MARKER)
    if start == -1 or end == -1 or end < start:
        return None
    return start, end + len(END_MARKER)


def region_untouched(note: Note) -> bool:
    stored = note.frontmatter.get("chat_body_hash")
    span = find_region(note.body)
    if not stored or span is None:
        return False
    return region_hash(note.body[span[0]:span[1]]) == str(stored)


def owned_values(conversation: ChatConversation, body_hash: Optional[str], today: str) -> dict:
    return {
        "modified": conversation.updated.strftime("%Y-%m-%d") if conversation.updated else None,
        "message_count": len(conversation.messages),
        "chat_id": conversation.chat_id,
        "chat_url": conversation.url or None,
        "chat_last_message": conversation.messages[-1].id if conversation.messages else None,
        # An empty hash marks the region as the user's: later syncs only append.
        "chat_body_hash": body_hash or "",
        "chat_synced": today,
    }


def new_note_text(conversation: ChatConversation, today: str) -> str:
    title = conversation.title.replace('"', "'")
    fm = [
        f'title: "{title}"',
        f"authors: [{conversation.authors}]",
        "tags: [chat-protokoll, KI-generiert]",
        "type: chat",
        f"source_llm: {conversation.provider}",
        f"source_platform: {conversation.source_platform}",
    ]
    if conversation.model:
        fm.append(f"model: {conversation.model}")
    created = conversation.created.strftime("%Y-%m-%d") if conversation.created else "unknown"
    fm.append(f"created: {created}")
    region = render_region(conversation)
    fm = set_keys(fm, owned_values(conversation, region_hash(region), today))
    return assemble(fm, f"\n# {conversation.title}\n\n{region}\n")


def _with_frontmatter(note: Note, conversation: ChatConversation,
                      body_hash: Optional[str], today: str) -> list[str]:
    fm = note.fm_lines if note.fm_lines is not None else []
    values = owned_values(conversation, body_hash, today)
    # Keys a clip may lack; never overwrite the user's own values.
    for key, value in (("type", "chat"), ("source_llm", conversation.provider)):
        if key not in note.frontmatter:
            values[key] = value
    return set_keys(fm, values)


def append_block(body: str, messages: list[ChatMessage], label: str, today: str) -> str:
    block = CONTINUED_MARKER.format(date=today) + "\n" + render_messages(messages, label).rstrip()
    end = body.rfind(END_MARKER)
    if end != -1:
        return body[:end].rstrip() + "\n\n" + block + "\n" + body[end:]
    return body.rstrip() + "\n\n" + block + "\n" + END_MARKER + "\n"


# ── Vault index ────────────────────────────────────────────────────────────

class VaultIndex:
    """Chat notes of a vault, by id and by fingerprint."""

    def __init__(self, vault: Path):
        self.vault = vault
        self.notes: list[Note] = []
        self.by_id: dict[tuple[str, str], list[Note]] = defaultdict(list)
        for path in sorted(self._markdown_files(vault)):
            try:
                note = read_note(path)
            except (OSError, UnicodeDecodeError):
                continue
            if not (note.chat_id or note.frontmatter.get("type") == "chat"
                    or note.frontmatter.get("source_llm")):
                continue
            self.notes.append(note)
            if note.chat_id and note.provider:
                self.by_id[(note.provider, note.chat_id)].append(note)
        self._fingerprints: dict[Path, set[str]] = {}

    @staticmethod
    def _markdown_files(vault: Path) -> Iterable[Path]:
        for path in vault.rglob("*.md"):
            rel = path.relative_to(vault).parts[:-1]
            if any(part in SKIP_DIRS or part.startswith(".") for part in rel):
                continue
            yield path

    def fingerprint(self, note: Note) -> set[str]:
        if note.path not in self._fingerprints:
            self._fingerprints[note.path] = shingles(note.body)
        return self._fingerprints[note.path]

    def fuzzy_pool(self, provider: str, exclude: set[Path]) -> list[Note]:
        """Unmanaged notes of a provider that no id ties to another chat."""
        pool = []
        for note in self.notes:
            if note.path in exclude or note.managed:
                continue
            if note.provider and note.provider != provider:
                continue
            if note.chat_id and note.provider in URL_ID_PROVIDERS:
                continue
            pool.append(note)
        return pool


def _held_prefix(note: Note, conv: ChatConversation) -> int:
    """Number of the conversation's opening messages the note holds."""
    end = prefix_end(locate_messages(note.body, conv.messages))
    return 0 if end is None else end + 1


def fuzzy_matches(conversations: list[ChatConversation], pool: list[Note], index: VaultIndex
                  ) -> tuple[dict[str, list[tuple[Note, float]]], list[Action], set[str]]:
    """Match id-less notes to conversations by shared shingles.

    A note claimed by several conversations (a prompt sent twice, a chat that
    quotes another) goes to the one whose opening it holds furthest. On a tie
    it is reported as ambiguous and left alone, and the ids of the tied
    conversations are returned so that none of them is created as a new note.
    """
    postings: dict[str, list[int]] = defaultdict(list)
    for i, note in enumerate(pool):
        for sh in index.fingerprint(note):
            postings[sh].append(i)

    candidates: dict[str, list[tuple[Note, float]]] = defaultdict(list)
    claimed: dict[Path, list[ChatConversation]] = defaultdict(list)
    for conv in conversations:
        shared: dict[int, int] = defaultdict(int)
        conv_shingles = set()
        for text in [m.text for m in conv.messages] + conv.match_texts:
            conv_shingles |= shingles(text)
        for sh in conv_shingles:
            hits = postings.get(sh, ())
            if len(hits) > COMMON_SHINGLE:
                continue
            for i in hits:
                shared[i] += 1
        for i, n in shared.items():
            size = len(index.fingerprint(pool[i])) or 1
            score = n / size
            if n >= MIN_SHARED and score >= MATCH_SCORE:
                candidates[conv.chat_id].append((pool[i], score))
                claimed[pool[i].path].append(conv)

    actions = []
    blocked: set[str] = set()
    notes = {note.path: note for note in pool}
    for path, convs in claimed.items():
        if len(convs) < 2:
            continue
        held = {c.chat_id: _held_prefix(notes[path], c) for c in convs}
        ranked = sorted(convs, key=lambda c: -held[c.chat_id])
        if held[ranked[0].chat_id] > held[ranked[1].chat_id]:
            losers = ranked[1:]
        else:
            losers = convs
            blocked.update(c.chat_id for c in convs)
            listed = ", ".join(f"„{c.title}“ {c.url or c.chat_id}" for c in convs)
            actions.append(Action(
                "ambiguous", None, path,
                f"matches {len(convs)} chats equally: {listed}; none created. "
                f"Put the right chat's URL into the note's source: to settle it"))
        for conv in losers:
            candidates[conv.chat_id] = [(n, s) for n, s in candidates[conv.chat_id] if n.path != path]
    return candidates, actions, blocked


# ── Sync ───────────────────────────────────────────────────────────────────

class Syncer:
    def __init__(self, vault: Path, output_folder: str = "KI-Chats", *,
                 dry_run: bool = False, now: Optional[datetime] = None):
        self.vault = vault
        self.output_base = vault / output_folder
        self.dry_run = dry_run
        now = now or datetime.now()
        self.today = now.strftime("%Y-%m-%d")
        self.backup_dir = vault / ".archilles" / "chat-sync-backup" / now.strftime("%Y%m%d-%H%M%S")

    # ── writing ──

    def _write(self, path: Path, text: str, *, backup: bool) -> None:
        if self.dry_run:
            return
        if backup and path.exists():
            target = self.backup_dir / path.relative_to(self.vault)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="")

    def _new_path(self, conv: ChatConversation) -> Path:
        date_str = conv.created.strftime("%Y-%m-%d") if conv.created else "unknown"
        folder = self.output_base / get_month_folder(conv.created)
        path = folder / make_filename(date_str, conv.provider, conv.title)
        stem = path.stem
        i = 2
        while path.exists():
            path = folder / f"{stem}-{i}.md"
            i += 1
        return path

    # ── decisions ──

    def create(self, conv: ChatConversation) -> Action:
        path = self._new_path(conv)
        self._write(path, new_note_text(conv, self.today), backup=False)
        return Action("created", conv, path, f"{len(conv.messages)} messages")

    def update(self, note: Note, conv: ChatConversation) -> Action:
        """A note this sync wrote before."""
        ids = [m.id for m in conv.messages]
        last = str(note.frontmatter.get("chat_last_message"))
        untouched = region_untouched(note)

        if last in ids:
            new = conv.messages[ids.index(last) + 1:]
            if not new:
                return Action("unchanged", conv, note.path)
            if untouched:
                return self._regenerate(note, conv, f"+{len(new)} messages")
            return self._append(note, conv, new, "appended")

        # The chat's history changed upstream (edited prompt, other branch).
        if untouched:
            return self._regenerate(note, conv, "history changed upstream, regenerated")
        end = prefix_end(locate_messages(note.body, conv.messages))
        if end is None:
            return Action("conflict", conv, note.path,
                          "history changed upstream and the note was edited; left as is")
        new = conv.messages[end + 1:]
        if not new:
            return Action("unchanged", conv, note.path)
        return self._append(note, conv, new, "appended")

    def adopt(self, note: Note, conv: ChatConversation, how: str) -> Action:
        """A note without sync state: an old import or a web clip."""
        end = prefix_end(locate_messages(note.body, conv.messages))
        if end is not None:
            new = conv.messages[end + 1:]
            body = append_block(note.body, new, conv.assistant_label, self.today) if new else note.body
            fm = _with_frontmatter(note, conv, None, self.today)
            self._write(note.path, assemble(fm, body, note.newline), backup=True)
            return Action("adopted", conv, note.path,
                          f"matched by {how}; held {end + 1}/{len(conv.messages)} messages, +{len(new)}")
        if note.is_clip:
            return self._rebuild(note, conv, how)
        return Action("conflict", conv, note.path,
                      f"matched by {how}, but the note holds only scattered parts of the chat; left as is")

    def _regenerate(self, note: Note, conv: ChatConversation, detail: str) -> Action:
        region = render_region(conv)
        start, end = find_region(note.body)
        body = note.body[:start] + region + note.body[end:]
        fm = _with_frontmatter(note, conv, region_hash(region), self.today)
        self._write(note.path, assemble(fm, body, note.newline), backup=True)
        return Action("updated", conv, note.path, detail)

    def _append(self, note: Note, conv: ChatConversation, new: list[ChatMessage], kind: str) -> Action:
        body = append_block(note.body, new, conv.assistant_label, self.today)
        fm = _with_frontmatter(note, conv, None, self.today)
        self._write(note.path, assemble(fm, body, note.newline), backup=True)
        own = own_paragraphs(note.body, conv)
        edits = f"edited, {len(own)} own paragraphs kept" if own else "edited (form only)"
        return Action(kind, conv, note.path, f"+{len(new)} messages; {edits}")

    def _rebuild(self, note: Note, conv: ChatConversation, how: str) -> Action:
        own = own_paragraphs(note.body, conv)
        heading = re.search(r"^# .+$", note.body, re.M)
        parts = [heading.group(0) if heading else f"# {conv.title}"]
        if own:
            parts.append(ADDITIONS_HEADING + "\n\n" + "\n\n".join(own))
        region = render_region(conv)
        parts.append(region)
        body = "\n" + "\n\n".join(parts) + "\n"
        fm = _with_frontmatter(note, conv, region_hash(region), self.today)
        self._write(note.path, assemble(fm, body, note.newline), backup=True)
        return Action("rebuilt", conv, note.path,
                      f"fragmentary clip matched by {how}; {len(own)} own paragraphs kept, "
                      f"original in {self.backup_dir.relative_to(self.vault).as_posix()}")

    # ── driver ──

    def sync(self, conversations: list[ChatConversation], index: Optional[VaultIndex] = None) -> SyncResult:
        index = index or VaultIndex(self.vault)
        result = SyncResult()

        groups: dict[str, list[tuple[Note, str]]] = {}
        matched: set[Path] = set()
        for conv in conversations:
            notes = index.by_id.get((conv.provider, conv.chat_id), [])
            groups[conv.chat_id] = [(n, "id") for n in notes]
            matched.update(n.path for n in notes)

        by_provider: dict[str, list[ChatConversation]] = defaultdict(list)
        for conv in conversations:
            if not groups[conv.chat_id]:
                by_provider[conv.provider].append(conv)
        blocked: set[str] = set()
        for provider, convs in by_provider.items():
            candidates, actions, tied = fuzzy_matches(convs, index.fuzzy_pool(provider, matched), index)
            result.actions += actions
            blocked |= tied
            for conv in convs:
                ranked = sorted(candidates.get(conv.chat_id, []), key=lambda ns: -ns[1])
                groups[conv.chat_id] = [(n, "fingerprint") for n, _ in ranked]

        for conv in conversations:
            group = groups[conv.chat_id]
            if not group:
                if conv.chat_id not in blocked:   # a tie is reported, not guessed
                    result.actions.append(self.create(conv))
                continue
            primary, how = self._primary(group, conv)
            if primary.managed:
                result.actions.append(self.update(primary, conv))
            else:
                result.actions.append(self.adopt(primary, conv, how))
            for note, _ in group:
                if note.path != primary.path:
                    own = own_paragraphs(note.body, conv)
                    rel = primary.path.relative_to(self.vault).as_posix()
                    result.actions.append(Action(
                        "duplicate", conv, note.path,
                        f"same chat as {rel}; {len(own)} own paragraphs not in the export"))
        return result

    @staticmethod
    def _primary(group: list[tuple[Note, str]], conv: ChatConversation) -> tuple[Note, str]:
        """The note that carries the chat on: a managed one, else the fullest."""
        managed = [(n, h) for n, h in group if n.managed]
        if managed:
            return managed[0]

        def held(item: tuple[Note, str]) -> int:
            return sum(locate_messages(item[0].body, conv.messages))
        return max(group, key=held)


def duplicate_groups(index: VaultIndex) -> list[list[Note]]:
    """Notes of the vault that share a chat id (e.g. one chat clipped twice)."""
    return [notes for notes in index.by_id.values() if len(notes) > 1]


# ── Reporting ──────────────────────────────────────────────────────────────

_ORDER = ["created", "updated", "appended", "adopted", "rebuilt", "unchanged",
          "duplicate", "conflict", "ambiguous"]


def summary_line(result: SyncResult) -> str:
    parts = [f"{kind}: {result.count(kind)}" for kind in _ORDER if result.count(kind)]
    return ", ".join(parts) or "nothing to do"


def print_actions(result: SyncResult, vault: Path, dry_run: bool, *, verbose: bool = False) -> None:
    prefix = "[DRY RUN] " if dry_run else ""
    for action in sorted(result.actions, key=lambda a: _ORDER.index(a.kind)):
        if action.kind == "unchanged" and not verbose:
            continue
        rel = action.path.relative_to(vault).as_posix() if action.path else "-"
        detail = f"  ({action.detail})" if action.detail else ""
        print(f"  {prefix}{action.kind:9} {rel}{detail}")
    print(f"\n{prefix}{summary_line(result)}")


def write_report(result: SyncResult, vault: Path, report_path: Path, source: str) -> None:
    lines = [f"# Chat sync {datetime.now():%Y-%m-%d %H:%M}", "", f"Source: `{source}`", "",
             summary_line(result), ""]
    for kind in _ORDER:
        actions = [a for a in result.actions if a.kind == kind]
        if not actions or kind == "unchanged":
            continue
        lines += [f"## {kind} ({len(actions)})", ""]
        for a in actions:
            link = f"[[{a.path.relative_to(vault).with_suffix('').as_posix()}]]" if a.path else "-"
            lines.append(f"- {link}" + (f" — {a.detail}" if a.detail else ""))
        lines.append("")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8")


def add_sync_arguments(parser) -> None:
    """CLI options shared by the importers."""
    parser.add_argument("--report", type=Path, default=None,
                        help="Write a Markdown report of every action to this file")
    parser.add_argument("--verbose", action="store_true",
                        help="Also list unchanged notes")


def run_sync(conversations: list[ChatConversation], args) -> SyncResult:
    """Sync parsed conversations as the importers' ``main()`` asks for."""
    syncer = Syncer(args.vault_path, args.output_folder, dry_run=args.dry_run)
    print(f"\nScanning {args.vault_path} for existing chat notes...")
    index = VaultIndex(args.vault_path)
    print(f"Found {len(index.notes)} chat notes")
    result = syncer.sync(conversations, index)
    print_actions(result, args.vault_path, args.dry_run, verbose=args.verbose)
    if args.report:
        write_report(result, args.vault_path, args.report, str(args.input_file))
        print(f"Report: {args.report}")
    if result.count("conflict") or result.count("duplicate") or result.count("ambiguous"):
        print("Conflicts, duplicates and ambiguous matches were left untouched.")
    return result


def main() -> None:
    """``python chat_sync.py VAULT``: list notes that share a chat id."""
    import argparse
    parser = argparse.ArgumentParser(description="Find chat notes in a vault that share a chat id")
    parser.add_argument("vault_path", type=Path)
    args = parser.parse_args()
    index = VaultIndex(args.vault_path)
    groups = duplicate_groups(index)
    print(f"{len(index.notes)} chat notes, {len(groups)} chats with more than one note")
    for notes in groups:
        print(f"\n{notes[0].provider} {notes[0].chat_id}")
        for note in notes:
            state = "managed" if note.managed else ("clip" if note.is_clip else "import")
            print(f"  [{state}] {note.path.relative_to(args.vault_path).as_posix()}")


if __name__ == "__main__":
    main()
