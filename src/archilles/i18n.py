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
        "webui.error_no_library": "No library is set up yet. Add one below, then start its routine.",
        "webui.hint_set_library": 'To search a library directly instead: `$env:ARCHILLES_LIBRARY_PATH = "C:\\path\\to\\Library"`',
        "webui.error_db_not_found": "Database not found: {path}",
        "webui.hint_run_index": "Nothing is indexed yet. Start the routine of this library in the setup below.",
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
        "webui.tab_setup": "⚙️ Setup",
        "setup.title": "Setup",
        "setup.intro": "Add a library, decide its settings once, choose a rhythm. From then on the routine keeps the index current. On an empty index the first run *is* the initial indexing: all titles become searchable by their metadata within minutes, the full texts follow.",
        "setup.error_master": "The master configuration cannot be read: {error}",
        "setup.source": "Library",
        "setup.new_source": "➕ Add a library",
        "setup.name": "Name",
        "setup.help_name": "Short name of the library, e.g. 'calibre' or 'zotero'. It appears in search results.",
        "setup.path": "Folder",
        "setup.help_path": "The library folder: Calibre (contains metadata.db), Zotero data directory (contains zotero.sqlite), an Obsidian vault or any folder.",
        "setup.hint_new_source": "Enter a name and the folder of the library.",
        "setup.error_name_taken": "A library named '{name}' already exists.",
        "setup.error_path_missing": "Folder not found: {path}",
        "setup.adapter": "Type",
        "setup.help_adapter": "Detected: {adapter}",
        "setup.section_tags": "1 · Tags",
        "setup.loading_tags": "Reading tags…",
        "setup.error_tags": "Tags could not be read: {error}",
        "setup.tag_overview": "All tags ({n})",
        "setup.works": "Titles",
        "setup.priority_tags": "Index first",
        "setup.help_priority_tags": "Titles with these tags get their full text first (any tag containing the word counts).",
        "setup.excluded_tags": "Never index",
        "setup.help_excluded_tags": "Titles with these tags stay out of the index entirely.",
        "setup.metadata_only_tags": "Metadata only",
        "setup.help_metadata_only_tags": "Title, Comments and annotations are indexed, the book's text is not (translations, duplicates).",
        "setup.warning_prio_excluded": "Both prioritised and excluded, exclusion wins: {tags}",
        "setup.section_mode": "2 · Indexing mode and languages",
        "setup.mode": "Mode",
        "setup.mode_auto": "Automatic (on this machine: {auto})",
        "setup.mode_light": "Light: flat chunks, local, free",
        "setup.mode_full-local": "Full, local: hierarchical chunks, needs a capable GPU",
        "setup.mode_full-external": "Full, external: prepared here, embedded on a rented GPU",
        "setup.mode_external_warning": "New titles are indexed provisionally and marked for an external run. Choose this only when an external embedding run is actually planned.",
        "setup.ui_language": "Interface language",
        "setup.corpus_languages": "Languages of the books",
        "setup.help_corpus_languages": "Used for OCR and for recognising chapters, registers and tables of contents.",
        "setup.section_schedule": "3 · Rhythm",
        "setup.schedule": "Update",
        "setup.schedule_daily": "daily",
        "setup.schedule_weekly": "weekly",
        "setup.schedule_manual": "only on request",
        "setup.help_schedule": "The routine runs after logon, at most once per day or week. 'Only on request' runs it solely via the button below.",
        "setup.save": "💾 Save settings",
        "setup.saved": "Saved: {master} and {library}",
        "setup.hint_save_first": "Save first, then the routine can be started.",
        "setup.error_generic": "Error: {error}",
        "setup.section_routines": "4 · Routine",
        "setup.last_run": "Last completed run ({label}): {when}",
        "setup.never_run": "This library's routine has not run yet.",
        "setup.last_result": "Last run {when}, exit code {code}: {stats}",
        "setup.run_now_text": "**Run now** opens a console window and runs the routine regardless of the rhythm. For Calibre: first the metadata of all titles, then the full texts. The full text can take hours to days; CTRL+C in the window stops cleanly after the current book, and the next run continues.",
        "setup.run_now": "▶️ Run now",
        "setup.run_started": "Started in a separate window.",
        "setup.scheduler_windows_only": "Automatic scheduling is set up through the Windows Task Scheduler and is available on Windows only.",
        "setup.register_text": "**Task Scheduler:** registers {tasks}, starting after each logon. The rhythm above is read on every run; changing it later needs no new registration.",
        "setup.check_tasks": "🔎 Show registered tasks",
        "setup.register": "📅 Register in Task Scheduler",
        "setup.registered": "Registered: {output}",
        "setup.no_tasks": "No ARCHILLES tasks are registered.",
        "setup.other_tasks_warning": "Further routine tasks exist: {tasks}. If one of them serves this library too, it runs twice; tasks registered with a fixed --frequency also ignore the rhythm set here. Remove duplicates in the Task Scheduler.",
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
        "webui.error_no_library": "Noch keine Bibliothek eingerichtet. Unten eine hinzufügen und ihre Routine starten.",
        "webui.hint_set_library": 'Um stattdessen direkt eine Bibliothek zu durchsuchen: `$env:ARCHILLES_LIBRARY_PATH = "C:\\Pfad\\zur\\Library"`',
        "webui.error_db_not_found": "Datenbank nicht gefunden: {path}",
        "webui.hint_run_index": "Noch nichts indexiert. Unten in der Einrichtung die Routine dieser Bibliothek starten.",
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
        "webui.tab_setup": "⚙️ Einrichtung",
        "setup.title": "Einrichtung",
        "setup.intro": "Bibliothek hinzufügen, Einstellungen einmal festlegen, Rhythmus wählen. Danach hält die Routine den Index aktuell. Auf einem leeren Index *ist* der erste Lauf die Erstindexierung: Alle Titel sind binnen Minuten über ihre Metadaten auffindbar, die Volltexte folgen.",
        "setup.error_master": "Die Master-Konfiguration ist nicht lesbar: {error}",
        "setup.source": "Bibliothek",
        "setup.new_source": "➕ Bibliothek hinzufügen",
        "setup.name": "Name",
        "setup.help_name": "Kurzname der Bibliothek, z. B. 'calibre' oder 'zotero'. Er erscheint in den Suchergebnissen.",
        "setup.path": "Ordner",
        "setup.help_path": "Der Ordner der Bibliothek: Calibre (enthält metadata.db), Zotero-Datenverzeichnis (enthält zotero.sqlite), ein Obsidian-Vault oder ein beliebiger Ordner.",
        "setup.hint_new_source": "Namen und Ordner der Bibliothek eingeben.",
        "setup.error_name_taken": "Eine Bibliothek namens '{name}' gibt es schon.",
        "setup.error_path_missing": "Ordner nicht gefunden: {path}",
        "setup.adapter": "Art",
        "setup.help_adapter": "Erkannt: {adapter}",
        "setup.section_tags": "1 · Tags",
        "setup.loading_tags": "Tags werden gelesen …",
        "setup.error_tags": "Tags konnten nicht gelesen werden: {error}",
        "setup.tag_overview": "Alle Tags ({n})",
        "setup.works": "Titel",
        "setup.priority_tags": "Zuerst indexieren",
        "setup.help_priority_tags": "Titel mit diesen Tags bekommen ihren Volltext zuerst (jeder Tag, der das Wort enthält, zählt).",
        "setup.excluded_tags": "Nie indexieren",
        "setup.help_excluded_tags": "Titel mit diesen Tags bleiben ganz aus dem Index.",
        "setup.metadata_only_tags": "Nur Metadaten",
        "setup.help_metadata_only_tags": "Titel, Kommentar und Annotationen werden indexiert, der Buchtext nicht (Übersetzungen, Dubletten).",
        "setup.warning_prio_excluded": "Zugleich priorisiert und ausgeschlossen, der Ausschluss gewinnt: {tags}",
        "setup.section_mode": "2 · Indexierungsmodus und Sprachen",
        "setup.mode": "Modus",
        "setup.mode_auto": "Automatisch (auf diesem Rechner: {auto})",
        "setup.mode_light": "Light: flache Chunks, lokal, kostenlos",
        "setup.mode_full-local": "Voll, lokal: hierarchische Chunks, braucht eine leistungsfähige GPU",
        "setup.mode_full-external": "Voll, extern: hier vorbereitet, auf gemieteter GPU eingebettet",
        "setup.mode_external_warning": "Neue Titel werden vorläufig indexiert und für einen externen Lauf vorgemerkt. Nur wählen, wenn ein externes Embedding tatsächlich ansteht.",
        "setup.ui_language": "Sprache der Oberfläche",
        "setup.corpus_languages": "Sprachen der Bücher",
        "setup.help_corpus_languages": "Für OCR und für das Erkennen von Kapiteln, Registern und Inhaltsverzeichnissen.",
        "setup.section_schedule": "3 · Rhythmus",
        "setup.schedule": "Aktualisieren",
        "setup.schedule_daily": "täglich",
        "setup.schedule_weekly": "wöchentlich",
        "setup.schedule_manual": "nur auf Anforderung",
        "setup.help_schedule": "Die Routine läuft nach der Anmeldung, höchstens einmal pro Tag bzw. Woche. Bei „nur auf Anforderung“ läuft sie nur über den Knopf unten.",
        "setup.save": "💾 Einstellungen speichern",
        "setup.saved": "Gespeichert: {master} und {library}",
        "setup.hint_save_first": "Erst speichern, dann lässt sich die Routine starten.",
        "setup.error_generic": "Fehler: {error}",
        "setup.section_routines": "4 · Routine",
        "setup.last_run": "Letzter vollständiger Lauf ({label}): {when}",
        "setup.never_run": "Die Routine dieser Bibliothek ist noch nicht gelaufen.",
        "setup.last_result": "Letzter Lauf {when}, Exit-Code {code}: {stats}",
        "setup.run_now_text": "**Jetzt starten** öffnet ein Konsolenfenster und führt die Routine unabhängig vom Rhythmus aus. Bei Calibre: erst die Metadaten aller Titel, dann die Volltexte. Der Volltext kann Stunden bis Tage dauern; STRG+C im Fenster beendet sauber nach dem laufenden Buch, der nächste Lauf macht weiter.",
        "setup.run_now": "▶️ Jetzt starten",
        "setup.run_started": "In einem eigenen Fenster gestartet.",
        "setup.scheduler_windows_only": "Die automatische Planung läuft über die Windows-Aufgabenplanung und ist nur unter Windows verfügbar.",
        "setup.register_text": "**Aufgabenplanung:** trägt {tasks} ein, Start jeweils nach der Anmeldung. Der Rhythmus oben wird bei jedem Lauf gelesen; ihn später zu ändern, braucht keine neue Eintragung.",
        "setup.check_tasks": "🔎 Eingetragene Aufgaben anzeigen",
        "setup.register": "📅 In der Aufgabenplanung eintragen",
        "setup.registered": "Eingetragen: {output}",
        "setup.no_tasks": "Keine ARCHILLES-Aufgaben eingetragen.",
        "setup.other_tasks_warning": "Es gibt weitere Routine-Aufgaben: {tasks}. Bedient eine davon ebenfalls diese Bibliothek, läuft sie doppelt; Aufgaben mit festem --frequency ignorieren zudem den hier gewählten Rhythmus. Doppelte in der Aufgabenplanung entfernen.",
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


# Classifying a section by its title is Scriptor's region vocabulary since
# outline step B7 (src/extractors/scriptor_extractor.region_of_title); the
# front- and back-matter word lists that stood here are gone with it.
#
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
