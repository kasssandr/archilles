"""Word-boundary keyword matching.

Shared helper for the substring-matching finding family of the 2026-06-10
code review (2.2, 4.5, 6.2): naive ``keyword in text`` checks matched inside
words — 'notes' in 'banknotes', 'toc' in 'protocol', 'teil' in 'Vorteil',
'Kant' in 'Kantine' — misclassifying sections, dropping highlights and
boosting unrelated results.

Keywords may be single words or phrases ("table of contents"). Matching is
case-insensitive and requires non-word characters (or string edges) around
the keyword. Lookarounds are used instead of ``\\b`` so keywords that start
or end with non-word characters stay matchable.
"""

import re
from functools import lru_cache
from typing import Iterable

__all__ = ["contains_keyword", "count_keyword_matches"]


@lru_cache(maxsize=1024)
def _keyword_pattern(keyword: str) -> re.Pattern:
    return re.compile(r"(?<!\w)" + re.escape(keyword.lower()) + r"(?!\w)")


def contains_keyword(text: str, keywords: Iterable[str]) -> bool:
    """Return True if any keyword occurs in text as a whole word/phrase."""
    if not text:
        return False
    lowered = text.lower()
    return any(_keyword_pattern(kw).search(lowered) for kw in keywords)


def count_keyword_matches(text: str, keywords: Iterable[str]) -> int:
    """Count how many distinct keywords occur in text as whole words/phrases."""
    if not text:
        return 0
    lowered = text.lower()
    return sum(1 for kw in keywords if _keyword_pattern(kw).search(lowered))
