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
        # Markdown export (PromptBuilder.export_to_markdown)
        "export.title": "ARCHILLES RAG - Search Results",
        "export.query": "Query",
        "export.date": "Date",
        "export.results": "Results",
        "export.location": "Location",
        "export.relevance": "Relevance",
        "export.source": "Source",
        "export.page_pdf": "PDF p.",
        "export.page": "p.",
        "export.open_in_calibre": "Open in Calibre",
        "export.language": "Language",
        "export.subject": "Subject",
        "export.publisher": "Publisher",
        "export.tag_search": "#search",
        "export.tag_latin": "#latin",
        "export.tag_german": "#german",
    },
    "de": {
        "export.title": "ARCHILLES RAG - Suchergebnisse",
        "export.query": "Query",
        "export.date": "Datum",
        "export.results": "Ergebnisse",
        "export.location": "Ort",
        "export.relevance": "Relevanz",
        "export.source": "Quelle",
        "export.page_pdf": "PDF S.",
        "export.page": "S.",
        "export.open_in_calibre": "In Calibre öffnen",
        "export.language": "Sprache",
        "export.subject": "Thema",
        "export.publisher": "Verlag",
        "export.tag_search": "#suche",
        "export.tag_latin": "#latein",
        "export.tag_german": "#deutsch",
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
