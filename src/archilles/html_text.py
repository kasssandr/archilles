"""HTML-to-plain-text stripping.

Shared helper for Zotero notes/abstracts, which arrive as HTML fragments.
Uses the stdlib HTMLParser (handles entities and malformed markup) and
collapses all whitespace to single spaces.
"""

import re
from html.parser import HTMLParser

__all__ = ["strip_html"]


class _HTMLStripper(HTMLParser):
    """Minimal HTML-to-text converter."""

    def __init__(self):
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self._parts.append(data)

    def get_text(self) -> str:
        return " ".join(self._parts).strip()


def strip_html(html: str) -> str:
    """Strip HTML tags and return whitespace-collapsed plain text."""
    if not html:
        return ""
    stripper = _HTMLStripper()
    stripper.feed(html)
    return re.sub(r"\s+", " ", stripper.get_text()).strip()
