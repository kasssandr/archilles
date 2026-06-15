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
        # Generic metadata labels (CLI + export + web UI)
        "label.author": "Author",
        "label.year": "Year",
        "label.page": "Page",
        "label.chapter": "Chapter",
        "label.section": "Section",
        "label.calibre_id": "Calibre ID",
        "label.score": "Score",
        "label.tags": "Tags",
        "label.filter": "Filter",
        # Web UI (scripts/web_ui.py)
        "webui.error_no_library": "ARCHILLES_LIBRARY_PATH is not set!",
        "webui.hint_set_library": 'PowerShell: `$env:ARCHILLES_LIBRARY_PATH = "C:\\path\\to\\Library"`',
        "webui.error_db_not_found": "Database not found: {path}",
        "webui.hint_run_index": "Run batch_index.py first to index your books.",
        "webui.show_fulltext": "Show full text",
        "webui.expanded_context": "Expanded context",
        "webui.surrounding_text": "Surrounding text (window_text):",
        "webui.parent_chunk": "Parent chunk ({id}):",
        "webui.section_front_matter": "📄 Front matter",
        "webui.section_back_matter": "📑 Back matter",
        "webui.chunk_child": "🧩 Sub-chunk",
        "webui.chunk_parent": "📦 Parent chunk",
        "webui.chunk_comment": "💬 Calibre comment",
        "webui.chunk_metadata": "📋 Metadata",
        "webui.export_title": "ARCHILLES Search Results",
        "webui.export_footer": "*Exported from ARCHILLES*",
        "webui.index_status": "Index Status",
        "webui.no_books": "No books indexed yet.",
        "webui.books_indexed_summary": "**{n} books** indexed · **{chunks}** chunks",
        "webui.filter_books": "Filter books",
        "webui.filter_books_placeholder": "Enter title or author...",
        "webui.books_count": "{shown} of {total} books",
        "webui.unknown": "Unknown",
        "webui.chunks_count": "{n} chunks",
        "webui.tab_search": "🔍 Search",
        "webui.tab_books": "📚 Books",
        "webui.sidebar_database": "Database",
        "webui.metric_indexed_books": "Indexed books",
        "webui.metric_chunks": "Chunks",
        "webui.search_settings": "Search settings",
        "webui.search_mode": "Search mode",
        "webui.mode_hybrid": "🔀 Hybrid (recommended)",
        "webui.mode_semantic": "🧠 Semantic",
        "webui.mode_keyword": "🔤 Keyword",
        "webui.slider_results": "Results",
        "webui.slider_max_per_book": "Max. per book",
        "webui.slider_min_similarity": "Min. similarity",
        "webui.help_min_similarity": "Filters results below this threshold (cosine similarity). Higher = stricter.",
        "webui.filter_header": "Filter",
        "webui.filter_all": "All",
        "webui.filter_language": "Language",
        "webui.section_main_only": "📖 Main text only",
        "webui.section_back_only": "📑 Back matter only",
        "webui.section_front_only": "📄 Front matter only",
        "webui.section_all": "All sections",
        "webui.filter_section": "Section",
        "webui.chunk_book_text": "📖 Book text",
        "webui.chunk_calibre_comments": "💬 Calibre comments",
        "webui.chunk_all": "📋 All",
        "webui.filter_content_type": "Content type",
        "webui.filter_all_tags": "All tags",
        "webui.help_tags": "Only search in books with these tags",
        "webui.filter_all_books": "All books",
        "webui.search_in_book": "📖 Search in book",
        "webui.advanced": "⚙️ Advanced",
        "webui.exact_phrase": "Exact phrase",
        "webui.help_exact_phrase": "Finds only exact matches (good for quotes, Latin)",
        "webui.help_expanded_context": "Shows surrounding text (window_text) or parent chunk",
        "webui.database_details": "Database details",
        "webui.json_books": "Books",
        "webui.json_chunks": "Chunks",
        "webui.json_avg_chunks": "Avg chunks/book",
        "webui.json_formats": "Formats",
        "webui.json_languages": "Languages",
        "webui.search_input": "Enter search term or question",
        "webui.search_placeholder": "e.g. 'Arendt totalitarianism' or 'What is the essence of freedom?'",
        "webui.button_search": "🔍 Search",
        "webui.button_clear": "🗑️ Clear",
        "webui.filter_book": "Book",
        "webui.spinner_searching": "Searching {n} chunks{filter}...",
        "webui.error_fts_missing": "FTS index missing! Keyword search unavailable.",
        "webui.hint_fts_solution": "Solution: `python scripts/rag_demo.py create-index --fts-only`",
        "webui.hint_fts_alternative": "Alternatively: use hybrid or semantic search.",
        "webui.error_search": "Search error: {error}",
        "webui.results_found": "**{n}** results for: *{query}*",
        "webui.button_export": "📥 Export",
        "webui.help_export": "Export results as Markdown",
        "webui.hint_try_other": "Try other search terms or disable filters.",
        "webui.hint_press_search": "Press 'Search' or Enter to search.",
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
        "label.author": "Autor",
        "label.year": "Jahr",
        "label.page": "Seite",
        "label.chapter": "Kapitel",
        "label.section": "Abschnitt",
        "label.calibre_id": "Calibre-ID",
        "label.score": "Score",
        "label.tags": "Tags",
        "label.filter": "Filter",
        "webui.error_no_library": "ARCHILLES_LIBRARY_PATH nicht gesetzt!",
        "webui.hint_set_library": 'PowerShell: `$env:ARCHILLES_LIBRARY_PATH = "C:\\Pfad\\zur\\Library"`',
        "webui.error_db_not_found": "Datenbank nicht gefunden: {path}",
        "webui.hint_run_index": "Zuerst batch_index.py ausführen, um Bücher zu indexieren.",
        "webui.show_fulltext": "Volltext anzeigen",
        "webui.expanded_context": "Erweiterter Kontext",
        "webui.surrounding_text": "Umgebender Text (window_text):",
        "webui.parent_chunk": "Eltern-Chunk ({id}):",
        "webui.section_front_matter": "📄 Vorwort/Einleitung",
        "webui.section_back_matter": "📑 Anhang/Register",
        "webui.chunk_child": "🧩 Teil-Chunk",
        "webui.chunk_parent": "📦 Eltern-Chunk",
        "webui.chunk_comment": "💬 Calibre-Kommentar",
        "webui.chunk_metadata": "📋 Metadaten",
        "webui.export_title": "ARCHILLES Suchergebnisse",
        "webui.export_footer": "*Exportiert von ARCHILLES*",
        "webui.index_status": "Index-Status",
        "webui.no_books": "Noch keine Bücher indexiert.",
        "webui.books_indexed_summary": "**{n} Bücher** indexiert · **{chunks}** Chunks",
        "webui.filter_books": "Bücher filtern",
        "webui.filter_books_placeholder": "Titel oder Autor eingeben...",
        "webui.books_count": "{shown} von {total} Büchern",
        "webui.unknown": "Unbekannt",
        "webui.chunks_count": "{n} Chunks",
        "webui.tab_search": "🔍 Suche",
        "webui.tab_books": "📚 Bücher",
        "webui.sidebar_database": "Datenbank",
        "webui.metric_indexed_books": "Indexierte Bücher",
        "webui.metric_chunks": "Chunks",
        "webui.search_settings": "Sucheinstellungen",
        "webui.search_mode": "Suchmodus",
        "webui.mode_hybrid": "🔀 Hybrid (Empfohlen)",
        "webui.mode_semantic": "🧠 Semantisch",
        "webui.mode_keyword": "🔤 Keyword",
        "webui.slider_results": "Ergebnisse",
        "webui.slider_max_per_book": "Max. pro Buch",
        "webui.slider_min_similarity": "Min. Ähnlichkeit",
        "webui.help_min_similarity": "Filtert Ergebnisse unter diesem Schwellenwert (Cosine-Ähnlichkeit). Höher = strenger.",
        "webui.filter_header": "Filter",
        "webui.filter_all": "Alle",
        "webui.filter_language": "Sprache",
        "webui.section_main_only": "📖 Nur Haupttext",
        "webui.section_back_only": "📑 Nur Anhang",
        "webui.section_front_only": "📄 Nur Vorwort",
        "webui.section_all": "Alle Abschnitte",
        "webui.filter_section": "Abschnitt",
        "webui.chunk_book_text": "📖 Buchtext",
        "webui.chunk_calibre_comments": "💬 Calibre-Kommentare",
        "webui.chunk_all": "📋 Alle",
        "webui.filter_content_type": "Inhaltstyp",
        "webui.filter_all_tags": "Alle Tags",
        "webui.help_tags": "Nur in Büchern mit diesen Tags suchen",
        "webui.filter_all_books": "Alle Bücher",
        "webui.search_in_book": "📖 In Buch suchen",
        "webui.advanced": "⚙️ Erweitert",
        "webui.exact_phrase": "Exakte Phrase",
        "webui.help_exact_phrase": "Findet nur exakte Übereinstimmungen (gut für Zitate, Latein)",
        "webui.help_expanded_context": "Zeigt umgebenden Text (window_text) oder Eltern-Chunk an",
        "webui.database_details": "Datenbankdetails",
        "webui.json_books": "Bücher",
        "webui.json_chunks": "Chunks",
        "webui.json_avg_chunks": "Ø Chunks/Buch",
        "webui.json_formats": "Formate",
        "webui.json_languages": "Sprachen",
        "webui.search_input": "Suchbegriff oder Frage eingeben",
        "webui.search_placeholder": "z.B. 'Arendt Totalitarismus' oder 'Was ist das Wesen der Freiheit?'",
        "webui.button_search": "🔍 Suchen",
        "webui.button_clear": "🗑️ Löschen",
        "webui.filter_book": "Buch",
        "webui.spinner_searching": "Suche in {n} Chunks{filter}...",
        "webui.error_fts_missing": "FTS-Index fehlt! Keyword-Suche nicht verfügbar.",
        "webui.hint_fts_solution": "Lösung: `python scripts/rag_demo.py create-index --fts-only`",
        "webui.hint_fts_alternative": "Alternativ: Hybrid- oder Semantische Suche verwenden.",
        "webui.error_search": "Suchfehler: {error}",
        "webui.results_found": "**{n}** Ergebnisse für: *{query}*",
        "webui.button_export": "📥 Export",
        "webui.help_export": "Ergebnisse als Markdown exportieren",
        "webui.hint_try_other": "Versuche andere Suchbegriffe oder deaktiviere Filter.",
        "webui.hint_press_search": "Drücke 'Suchen' oder Enter um zu suchen.",
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


# ───────────────────────────────────────────────────────────────────
# Corpus-language data (Strang 3)
# ───────────────────────────────────────────────────────────────────
# Unlike the UI message catalogue above, these are *corpus* data derived from
# the whole ``languages`` list (not just languages[0]). Language-specific data
# lives here per ISO-639-1 code so new languages can be added in one place.
# Helpers return either the union of the *active* languages (OCR codes, stop
# words — finding 8.3) or, where cross-language mixing is harmless thanks to
# the P1 word-boundary matching, the union of *all* known languages (TOC
# keywords — findings 2.2/6.15).

# ISO-639-1 → Tesseract OCR language code (finding 2.33).
OCR_CODES: dict[str, str] = {
    "en": "eng", "de": "deu", "fr": "fra", "es": "spa", "it": "ita",
    "pt": "por", "nl": "nld", "la": "lat", "ru": "rus", "el": "ell",
    "he": "heb", "ar": "ara", "zh": "chi_sim", "ja": "jpn", "ko": "kor",
}


def get_ocr_language(languages: list[str] | None) -> str:
    """Tesseract ``+``-joined OCR codes for the active languages.

    Unknown ISO codes are skipped, duplicates removed (order preserved);
    falls back to ``"eng"`` when nothing maps.
    """
    codes: list[str] = []
    for lng in (languages or []):
        code = OCR_CODES.get(lng)
        if code and code not in codes:
            codes.append(code)
    return "+".join(codes) or "eng"


# BCP-47 locale for the operator language (finding 4.13: was hard-coded "de-DE").
LOCALES: dict[str, str] = {
    "en": "en-US", "de": "de-DE", "fr": "fr-FR", "es": "es-ES", "it": "it-IT",
    "pt": "pt-PT", "nl": "nl-NL", "la": "la", "ru": "ru-RU", "el": "el-GR",
    "he": "he-IL", "ar": "ar", "zh": "zh-CN", "ja": "ja-JP", "ko": "ko-KR",
}


def get_locale(languages: list[str] | None) -> str:
    """BCP-47 locale for the operator language (``languages[0]``); default en-US."""
    first = (languages or ["en"])[0]
    return LOCALES.get(first, "en-US")


# Stop words per language (was the single mixed ``ArchillesRAG.STOP_WORDS`` —
# finding 8.3: 'die' (de) dropped English "die", 'a' (en) dropped Latin "a").
STOPWORDS: dict[str, frozenset[str]] = {
    "en": frozenset({
        'a', 'an', 'and', 'are', 'as', 'at', 'be', 'by', 'for', 'from',
        'has', 'he', 'in', 'is', 'it', 'its', 'of', 'on', 'that', 'the',
        'to', 'was', 'will', 'with', 'or', 'but', 'not', 'this', 'these',
    }),
    "de": frozenset({
        'der', 'die', 'das', 'den', 'dem', 'des', 'ein', 'eine', 'einer',
        'eines', 'einem', 'einen', 'und', 'oder', 'aber', 'von', 'zu',
        'im', 'am', 'um', 'bei', 'mit', 'für', 'aus', 'auf', 'durch',
    }),
    "fr": frozenset({
        'le', 'la', 'les', 'un', 'une', 'des', 'du', 'de', 'd', 'et', 'ou',
        'mais', 'dans', 'pour', 'par', 'sur', 'avec', 'au', 'aux', 'ce',
        'cette', 'ces', 'est', 'sont', 'être', 'avoir', 'à', 'son', 'sa',
    }),
    "es": frozenset({
        'el', 'la', 'los', 'las', 'un', 'una', 'unos', 'unas', 'y', 'o',
        'pero', 'en', 'por', 'para', 'con', 'sin', 'sobre', 'del', 'al',
        'es', 'son', 'ser', 'estar', 'haber', 'ha', 'han', 'su', 'sus',
    }),
    "it": frozenset({
        'il', 'lo', 'la', 'i', 'gli', 'le', 'un', 'uno', 'una', 'e', 'o',
        'ma', 'in', 'di', 'd', 'da', 'per', 'con', 'su', 'del', 'della', 'dei',
        'degli', 'delle', 'al', 'alla', 'ai', 'agli', 'alle', 'è', 'sono',
    }),
    "pt": frozenset({
        'o', 'a', 'os', 'as', 'um', 'uma', 'uns', 'umas', 'e', 'ou',
        'mas', 'em', 'de', 'por', 'para', 'com', 'sem', 'sobre', 'do',
        'da', 'dos', 'das', 'ao', 'à', 'aos', 'às', 'é', 'são', 'seu', 'sua',
    }),
    "nl": frozenset({
        'de', 'het', 'een', 'en', 'of', 'maar', 'in', 'op', 'voor', 'van',
        'met', 'door', 'bij', 'aan', 'naar', 'om', 'over', 'is', 'zijn',
        'was', 'waren', 'heeft', 'hebben', 'had', 'hadden', 'der',
    }),
    "la": frozenset({
        'et', 'in', 'ad', 'cum', 'ex', 'ab', 'a', 'e', 'de', 'per', 'pro', 'sub',
        'atque', 'sed', 'aut', 'vel', 'ac', 'neque', 'nec', 'est', 'sunt',
    }),
    "ru": frozenset({
        'и', 'в', 'на', 'с', 'по', 'для', 'к', 'от', 'за', 'о',
        'из', 'у', 'это', 'как', 'но', 'или', 'а', 'не', 'что', 'он',
    }),
    "el": frozenset({
        'ο', 'η', 'το', 'οι', 'τα', 'και', 'ή', 'αλλά', 'σε', 'από',
        'για', 'με', 'στο', 'στη', 'στον', 'στην', 'του', 'της', 'των', 'εν',
    }),
    "he": frozenset({
        'ה', 'ו', 'ב', 'ל', 'מ', 'ש', 'של', 'את', 'על', 'אל', 'עם',
        'כי', 'אם', 'או', 'זה', 'זאת', 'אלה', 'הוא', 'היא',
    }),
    "ar": frozenset({
        'في', 'من', 'إلى', 'على', 'هذا', 'هذه', 'و', 'أو', 'لا',
        'ما', 'هو', 'هي', 'التي', 'الذي', 'مع', 'عن', 'إن', 'ال',
    }),
}


def get_stopwords(languages: list[str] | None) -> set[str]:
    """Union of stop-word sets for the active languages.

    ``None``/empty falls back to *all* known languages (legacy behaviour), so
    callers without a language context keep working unchanged.
    """
    active = [l for l in (languages or []) if l in STOPWORDS] or list(STOPWORDS)
    out: set[str] = set()
    for l in active:
        out |= STOPWORDS[l]
    return out


# TOC / section-classification keywords (findings 2.2, 6.15). Per-language for
# maintainability; getters return the union of *all* known languages (Option B,
# not language-filtered — P1 word-boundary matching prevents cross-language
# false hits like 'notes' in 'banknotes').
TOC_FRONT_MATTER: dict[str, frozenset[str]] = {
    "en": frozenset({
        'preface', 'foreword', 'acknowledgments', 'acknowledgements',
        'table of contents', 'contents', 'toc', 'dedication',
        'about the author', 'about this book', 'prologue', 'copyright', 'isbn',
        'title page', 'half title', 'frontispiece',
        'list of illustrations', 'list of maps',
    }),
    "de": frozenset({
        'vorwort', 'geleitwort', 'danksagung', 'inhaltsverzeichnis', 'inhalt',
        'widmung', 'über den autor', 'prolog',
    }),
}
TOC_BACK_MATTER: dict[str, frozenset[str]] = {
    "en": frozenset({
        'index', 'bibliography', 'references', 'glossary', 'appendix',
        'notes', 'endnotes', 'epilogue', 'afterword', 'abbreviations',
        'about the publisher', 'colophon',
    }),
    "de": frozenset({
        'register', 'sachregister', 'personenregister', 'namenregister',
        'bibliographie', 'literaturverzeichnis', 'literatur', 'quellenverzeichnis',
        'glossar', 'anhang', 'anmerkungen', 'endnoten', 'epilog', 'nachwort',
        'abkürzungen', 'abkürzungsverzeichnis',
    }),
}
# Generic TOC markers used to filter short highlights (annotations).
TOC_GENERIC: dict[str, frozenset[str]] = {
    "en": frozenset({
        'table of contents', 'contents', 'chapter', 'part', 'section',
        'index', 'appendix', 'preface', 'introduction', 'bibliography',
    }),
    "de": frozenset({
        'inhaltsverzeichnis', 'kapitel', 'teil', 'index', 'register',
        'anhang', 'vorwort', 'einleitung', 'literaturverzeichnis',
    }),
}


def _union(per_lang: dict[str, frozenset[str]]) -> frozenset[str]:
    out: set[str] = set()
    for words in per_lang.values():
        out |= words
    return frozenset(out)


def get_toc_front_matter_keywords() -> frozenset[str]:
    """All known front-matter TOC keywords (not language-filtered)."""
    return _union(TOC_FRONT_MATTER)


def get_toc_back_matter_keywords() -> frozenset[str]:
    """All known back-matter TOC keywords (not language-filtered)."""
    return _union(TOC_BACK_MATTER)


def get_toc_keywords() -> frozenset[str]:
    """All known generic TOC markers (not language-filtered)."""
    return _union(TOC_GENERIC)


# Dialogue speaker markers (finding 3.19). The private author name "tom" was
# removed from the public repo. User markers are per-language; LLM/assistant
# markers are language-neutral product names.
DIALOGUE_USER_MARKERS: dict[str, frozenset[str]] = {
    "en": frozenset({"user", "human"}),
    "de": frozenset({"nutzer", "ich"}),
}
DIALOGUE_LLM_MARKERS: frozenset[str] = frozenset({
    "chatgpt", "grok", "gemini", "claude", "assistant",
    "copilot", "perplexity", "mistral", "llama", "deepseek",
    "chatbot", "ai", "bot",
})


def get_dialogue_user_markers(languages: list[str] | None = None) -> frozenset[str]:
    """User/speaker markers for dialogue chunking; union of active languages
    (all known when ``None``/empty)."""
    active = [l for l in (languages or []) if l in DIALOGUE_USER_MARKERS] or list(DIALOGUE_USER_MARKERS)
    out: set[str] = set()
    for l in active:
        out |= DIALOGUE_USER_MARKERS[l]
    return frozenset(out)
