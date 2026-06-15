"""Shared helpers for the ``import_<platform>_to_vault.py`` scripts (finding 8.12).

Platform-specific parsing (ChatGPT's tree mapping, Claude's chat_messages,
Gemini's HTML, Grok's JSON) stays in each script. This module holds the parts
that were copy-pasted across all four:

* :func:`slugify`               — filesystem-safe slug (German umlaut folding)
* :func:`format_date` /
  :func:`get_month_folder`      — datetime → ``YYYY-MM-DD`` / ``YYYY-MM`` strings
* :func:`make_filename`         — ``<date>_<platform>_<slug>.md``
* :func:`parse_selection`       — ``"0,3,5-10"`` / ``"all"`` → list of indices
* :func:`select_conversations`  — interactive preview table + selection prompt
* :func:`render_markdown`       — frontmatter + body skeleton

These scripts are run directly (``python scripts/import_X_to_vault.py``), so the
sibling import ``from vault_import import ...`` resolves against ``scripts/``.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Callable, Optional

_UMLAUTS = {
    "ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss",
    "Ä": "Ae", "Ö": "Oe", "Ü": "Ue",
}


def slugify(text: str, max_length: int = 50) -> str:
    """Convert text to a filesystem-safe slug (folds German umlauts)."""
    text = text.lower().strip()
    for k, v in _UMLAUTS.items():
        text = text.replace(k, v)
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    if len(text) > max_length:
        text = text[:max_length].rstrip("-")
    return text or "untitled"


def format_date(dt: Optional[datetime]) -> str:
    """Format a datetime as ``YYYY-MM-DD`` (``"unknown"`` if None)."""
    return dt.strftime("%Y-%m-%d") if dt else "unknown"


def get_month_folder(dt: Optional[datetime]) -> str:
    """Month folder name ``YYYY-MM`` from a datetime (``"undated"`` if None)."""
    return dt.strftime("%Y-%m") if dt else "undated"


def make_filename(date_str: str, platform: str, title: str) -> str:
    """Build the vault note filename ``<date>_<platform>_<slug>.md``."""
    return f"{date_str}_{platform}_{slugify(title)}.md"


def parse_selection(selection: str, count: int) -> list[int]:
    """Parse a selection string into sorted, in-range indices.

    Accepts ``"all"`` (case-insensitive), comma-separated indices and
    ``start-end`` ranges, e.g. ``"0,3,5-10,15"``. Out-of-range and empty
    parts are ignored.
    """
    if selection.strip().lower() == "all":
        return list(range(count))
    indices: set[int] = set()
    for part in selection.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            start, end = part.split("-", 1)
            indices.update(range(int(start), int(end) + 1))
        else:
            indices.add(int(part))
    return [i for i in sorted(indices) if 0 <= i < count]


def select_conversations(
    conversations: list,
    describe: Callable[[object], tuple[str, int, str]],
) -> list:
    """Print a numbered preview table and let the user pick interactively.

    ``describe(conv)`` must return ``(date_str, message_count, title)`` for one
    conversation; this is the only platform-specific bit.
    """
    print(f"\n{'#':>4}  {'Date':10}  {'Msgs':>5}  Title")
    print("-" * 70)
    for i, conv in enumerate(conversations):
        date_str, msg_count, title = describe(conv)
        print(f"{i:4d}  {date_str:10}  {msg_count:5d}  {title[:45]}")

    print(f"\nTotal: {len(conversations)} conversations")
    print("Enter numbers to import (comma-separated), ranges (3-7), or 'all':")
    print("Example: 0,3,5-10,15")

    selection = input("> ").strip()
    indices = parse_selection(selection, len(conversations))
    return [conversations[i] for i in indices]


def render_markdown(
    frontmatter_lines: list[str],
    title: str,
    messages: list[dict],
    assistant_label: str,
    *,
    summary: str = "",
) -> str:
    """Assemble the shared note: frontmatter block + ``# title`` + message log.

    ``messages`` are dicts with ``role`` (``"user"``/``"assistant"``) and
    ``text``. ``assistant_label`` is e.g. ``"**Claude:**"``. An optional
    ``summary`` is rendered as a leading blockquote.
    """
    body = [f"# {title}", ""]
    if summary:
        body += [f"> {summary[:500]}", "", "---", ""]
    for msg in messages:
        label = "**User:**" if msg["role"] == "user" else assistant_label
        body += [label, "", msg["text"], "", "---", ""]
    return "\n".join(frontmatter_lines) + "\n\n" + "\n".join(body)
