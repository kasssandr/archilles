"""Result-set utilities shared by service, engine and CLI layers.

Lives below both the service facade and the RAG engine so that neither
has to import the other (breaks the service ↔ engine import cycle,
review 2026-06-10, finding 4.9 context).
"""
from typing import Any


def matches_tag_filter(result_tags: str, tag_filter: list[str]) -> bool:
    """True if a result's tag string contains ALL requested tags (AND logic).

    The MCP tool schema documents AND semantics ("Results must match ALL
    tags"); the previous implementation used OR (code review finding 8.1).
    Comparison is case-insensitive on whole tag names, not substrings.
    """
    if not result_tags:
        return False
    result_tag_set = {t.strip().lower() for t in result_tags.split(',')}
    return all(ft.strip().lower() in result_tag_set for ft in tag_filter)


def diversify_results(
    results: list[dict[str, Any]],
    max_per_book: int,
    top_k: int,
) -> list[dict[str, Any]]:
    """Limit results to *max_per_book* per book, keeping top-ranked first."""
    diversified: list[dict[str, Any]] = []
    book_counts: dict[str, int] = {}

    for r in results:
        metadata = r.get("metadata", {})
        bid = metadata.get("book_id", r.get("book_id", "unknown"))
        count = book_counts.get(bid, 0)
        if count < max_per_book:
            diversified.append(r)
            book_counts[bid] = count + 1
        if len(diversified) >= top_k:
            break

    for i, r in enumerate(diversified):
        r["rank"] = i + 1

    return diversified
