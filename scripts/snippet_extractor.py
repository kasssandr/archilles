#!/usr/bin/env python3
"""
Extract relevant context snippets from search results
"""

import re
from typing import List, Tuple

def extract_context_snippet(text: str, query_terms: List[str], context_chars: int = 150) -> Tuple[str, List[str]]:
    """
    Extract a snippet showing where query terms appear in the text.

    Args:
        text: The full text to search in
        query_terms: List of terms to find
        context_chars: Characters of context to show around matches

    Returns:
        (snippet, found_terms) tuple
    """
    text_lower = text.lower()

    # Find first occurrence of any query term
    best_pos = -1
    found_terms = []

    for term in query_terms:
        term_lower = term.lower()
        pos = text_lower.find(term_lower)
        if pos != -1:
            if best_pos == -1 or pos < best_pos:
                best_pos = pos
            found_terms.append(term)

    if best_pos == -1:
        # No terms found, return beginning
        return text[:context_chars * 2] + "...", []

    # Extract context window around first match
    start = max(0, best_pos - context_chars)
    end = min(len(text), best_pos + context_chars)

    snippet = text[start:end]

    # Add ellipsis if truncated
    if start > 0:
        snippet = "..." + snippet
    if end < len(text):
        snippet = snippet + "..."

    return snippet, found_terms


def highlight_terms(text: str, terms: List[str]) -> str:
    """
    Highlight query terms in text with >>> <<< markers.

    Args:
        text: Text to highlight in
        terms: Terms to highlight

    Returns:
        Text with highlighted terms
    """
    result = text

    # Sort by length (longest first) to avoid partial matches
    sorted_terms = sorted(terms, key=len, reverse=True)

    for term in sorted_terms:
        # Case-insensitive replacement
        pattern = re.compile(re.escape(term), re.IGNORECASE)
        result = pattern.sub(lambda m: f">>>{m.group()}<<<", result)

    return result
