"""Central catalogue for user-visible, language-dependent strings (P3, code
review 2026-06).

Stage 1 scope: the message catalogue plus the :func:`t` lookup. The
operator/interface language is ``get_languages(...)[0]`` (see
:mod:`src.archilles.config`); prompts to the LLM standardise on English and do
**not** use this catalogue.

English is the canonical, complete catalogue and the fallback language. German
is provided as a second built-in. A missing key in the target language falls
back to English; an unknown language falls back to English wholesale. Further
languages can be bolted on later as extra bundles (or external JSON) without
touching callers, since they only ever go through :func:`t`.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Canonical / fallback language. Every key MUST exist in this bundle.
FALLBACK_LANG = "en"

# key -> {lang: text}. The English bundle is authoritative; other-language
# bundles may be partial (missing keys fall back to English via :func:`t`).
MESSAGES: dict[str, dict[str, str]] = {
    "en": {
        # Generic, context-spanning labels (CLI + export)
        "page.pdf": "PDF p.",
        "page.plain": "p.",
        "label.relevance": "Relevance",
        "label.language": "Language",
        # Markdown export (PromptBuilder.export_to_markdown)
        "export.title": "ARCHILLES RAG - Search Results",
        "export.query": "Query",
        "export.date": "Date",
        "export.results": "Results",
        "export.location": "Location",
        "export.source": "Source",
        "export.open_in_calibre": "Open in Calibre",
        "export.subject": "Subject",
        "export.publisher": "Publisher",
        "export.tag_search": "#search",
        "export.tag_latin": "#latin",
        "export.tag_german": "#german",
        # CLI search output (Searcher.print_results)
        "results.no_results": "No results found.",
        "results.header": "TOP {n} RESULTS:",
        "results.text": "Text",
        "results.relevance_very_high": "very high",
        "results.relevance_high": "high",
        "results.relevance_medium": "medium",
    },
    "de": {
        "page.pdf": "PDF S.",
        "page.plain": "S.",
        "label.relevance": "Relevanz",
        "label.language": "Sprache",
        "export.title": "ARCHILLES RAG - Suchergebnisse",
        "export.query": "Query",
        "export.date": "Datum",
        "export.results": "Ergebnisse",
        "export.location": "Ort",
        "export.source": "Quelle",
        "export.open_in_calibre": "In Calibre öffnen",
        "export.subject": "Thema",
        "export.publisher": "Verlag",
        "export.tag_search": "#suche",
        "export.tag_latin": "#latein",
        "export.tag_german": "#deutsch",
        "results.no_results": "Keine Ergebnisse gefunden.",
        "results.header": "TOP {n} TREFFER:",
        "results.text": "Text",
        "results.relevance_very_high": "sehr hoch",
        "results.relevance_high": "hoch",
        "results.relevance_medium": "mittel",
    },
}


def t(key: str, lang: str = FALLBACK_LANG) -> str:
    """Translate ``key`` into ``lang``.

    Resolution order: requested language → English fallback → the key itself
    (with a logged warning, so a missing string degrades visibly instead of
    crashing the caller).
    """
    bundle = MESSAGES.get(lang)
    if bundle is not None and key in bundle:
        return bundle[key]

    fallback = MESSAGES[FALLBACK_LANG]
    if key in fallback:
        return fallback[key]

    logger.warning("Missing i18n key %r (lang=%r)", key, lang)
    return key
