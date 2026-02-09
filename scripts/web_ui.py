#!/usr/bin/env python3
"""
ARCHILLES Web UI - Streamlit interface for semantic book search.

Usage:
    streamlit run scripts/web_ui.py

Environment:
    CALIBRE_LIBRARY_PATH: Path to Calibre library (required)
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import os
import streamlit as st
from typing import List, Dict, Any
import re

# Page config must be first Streamlit command
st.set_page_config(
    page_title="ARCHILLES",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded"
)


@st.cache_resource
def load_rag():
    """Load RAG system (cached for performance)."""
    from scripts.rag_demo import archillesRAG

    library_path = os.getenv('CALIBRE_LIBRARY_PATH') or os.getenv('CALIBRE_LIBRARY')
    if not library_path:
        st.error("CALIBRE_LIBRARY_PATH nicht gesetzt!")
        st.info('PowerShell: `$env:CALIBRE_LIBRARY_PATH = "C:\\Pfad\\zur\\Calibre-Library"`')
        st.stop()

    db_path = str(Path(library_path) / ".archilles" / "rag_db")

    if not Path(db_path).exists():
        st.error(f"Database not found: {db_path}")
        st.info("Run batch_index.py first to index your books.")
        st.stop()

    return archillesRAG(db_path=db_path)


@st.cache_data(ttl=300)  # Cache for 5 minutes
def get_available_tags(_rag) -> List[str]:
    """Get all unique tags from indexed books."""
    try:
        books = _rag.store.get_indexed_books()
    except Exception:
        return []
    all_tags = set()
    for book in books:
        tags_str = book.get('tags', '')
        if tags_str:
            for tag in tags_str.split(', '):
                tag = tag.strip()
                if tag:
                    all_tags.add(tag)
    return sorted(all_tags)


@st.cache_data(ttl=300)  # Cache for 5 minutes
def get_indexed_books_list(_rag) -> List[Dict[str, Any]]:
    """Get list of indexed books for dropdown."""
    try:
        books = _rag.store.get_indexed_books()
    except Exception:
        return []
    return sorted(books, key=lambda x: x.get('title', '') or '')


def highlight_text(text: str, query_terms: List[str]) -> str:
    """Highlight query terms in text with HTML markup."""
    if not query_terms:
        return text

    result = text
    for term in sorted(query_terms, key=len, reverse=True):
        pattern = re.compile(re.escape(term), re.IGNORECASE)
        result = pattern.sub(lambda m: f"**{m.group()}**", result)

    return result


def extract_snippet(text: str, query_terms: List[str], context_chars: int = 200) -> str:
    """Extract relevant snippet around query terms."""
    if not query_terms:
        return text[:context_chars * 2] + "..." if len(text) > context_chars * 2 else text

    text_lower = text.lower()
    best_pos = -1

    for term in query_terms:
        pos = text_lower.find(term.lower())
        if pos != -1 and (best_pos == -1 or pos < best_pos):
            best_pos = pos

    if best_pos == -1:
        return text[:context_chars * 2] + "..." if len(text) > context_chars * 2 else text

    start = max(0, best_pos - context_chars)
    end = min(len(text), best_pos + context_chars)

    snippet = text[start:end]
    if start > 0:
        snippet = "..." + snippet
    if end < len(text):
        snippet = snippet + "..."

    return snippet


def render_result(result: Dict[str, Any], index: int, query_terms: List[str],
                  show_expanded_context: bool = False, rag=None):
    """Render a single search result."""
    score = result.get('score', 0)
    text = result.get('text', '')

    # Extract metadata (nested in 'metadata' dict from query results)
    metadata = result.get('metadata', {})
    book_title = metadata.get('book_title', '') or result.get('book_title', 'Unknown')
    author = metadata.get('author', '') or result.get('author', '')
    year = metadata.get('year', 0) or result.get('year', 0)
    language = metadata.get('language', '') or result.get('language', '')
    page = metadata.get('page_number', 0) or result.get('page_number', 0)
    page_label = metadata.get('page_label', '') or result.get('page_label', '')
    section_type = metadata.get('section_type', '') or result.get('section_type', '')
    tags = metadata.get('tags', '') or result.get('tags', '')
    calibre_id = metadata.get('calibre_id', 0) or result.get('calibre_id', 0)
    chapter = metadata.get('chapter', '') or result.get('chapter', '')
    section_title = metadata.get('section_title', '') or result.get('section_title', '')
    chunk_type = metadata.get('chunk_type', '') or result.get('chunk_type', '')
    window_text = metadata.get('window_text', '') or ''
    parent_id = metadata.get('parent_id', '') or ''

    # Fallback for title
    if not book_title or book_title == 'Unknown':
        book_title = metadata.get('title', '') or 'Unknown'

    # Score color — adapt to score range (RRF scores are much smaller than cosine)
    if score > 0.5:
        # Cosine similarity range (semantic mode)
        score_color = "green" if score > 0.8 else "orange"
    elif score > 0:
        # RRF range (hybrid mode) — rank-based, typically 0.01-0.05
        score_color = "green" if score > 0.03 else "orange"
    else:
        score_color = "gray"

    with st.container():
        # Header row
        col1, col2 = st.columns([5, 1])
        with col1:
            st.markdown(f"### {index}. {book_title}")
        with col2:
            st.markdown(f":{score_color}[Score: {score:.2f}]")

        # Metadata row
        meta_parts = []
        if author:
            meta_parts.append(f"**Autor:** {author}")
        if year and year > 0:
            meta_parts.append(f"**Jahr:** {year}")
        if language:
            meta_parts.append(f"**Sprache:** {language}")
        # Page: prefer page_label (printed page), show PDF page if different
        if page_label and page_label != str(page):
            meta_parts.append(f"**Seite:** {page_label} (PDF: {page})")
        elif page and page > 0:
            meta_parts.append(f"**Seite:** {page}")
        if calibre_id and calibre_id > 0:
            meta_parts.append(f"**Calibre-ID:** {calibre_id}")

        if meta_parts:
            st.markdown(" | ".join(meta_parts))

        # Chapter / Section
        location_parts = []
        if chapter:
            location_parts.append(f"**Kapitel:** {chapter}")
        if section_title:
            location_parts.append(f"**Abschnitt:** {section_title}")
        if location_parts:
            st.markdown(" | ".join(location_parts))

        # Tags and badges
        badge_row = []
        if tags:
            badge_row.append(f"🏷️ {tags}")

        # Section type badge
        if section_type and section_type != 'main_content':
            section_labels = {
                'front_matter': '📄 Vorwort/Einleitung',
                'back_matter': '📑 Anhang/Register'
            }
            label = section_labels.get(section_type, section_type)
            badge_row.append(label)

        # Chunk type badge (only for hierarchical chunks)
        if chunk_type and chunk_type not in ('content', ''):
            chunk_labels = {
                'child': '🧩 Teil-Chunk',
                'parent': '📦 Eltern-Chunk',
                'calibre_comment': '💬 Calibre-Kommentar',
                'phase1_metadata': '📋 Metadaten'
            }
            label = chunk_labels.get(chunk_type, chunk_type)
            badge_row.append(label)

        if badge_row:
            st.caption(" · ".join(badge_row))

        # Snippet with highlighting
        snippet = extract_snippet(text, query_terms)
        highlighted = highlight_text(snippet, query_terms)
        st.markdown(f"> {highlighted}")

        # Expandable sections
        with st.expander("Volltext anzeigen"):
            st.text(text)

        # Context expansion (window_text or parent chunk)
        if show_expanded_context and (window_text or parent_id):
            with st.expander("Erweiterter Kontext"):
                if window_text and len(window_text) > len(text):
                    st.caption("Umgebender Text (window_text):")
                    st.text(window_text)
                elif parent_id and rag:
                    parent = rag.store.get_by_id(parent_id)
                    if parent and parent.get('text'):
                        st.caption(f"Eltern-Chunk ({parent_id}):")
                        st.text(parent['text'])

        st.divider()


def generate_markdown_export(results: List[Dict[str, Any]], query: str, filters: List[str]) -> str:
    """Generate Markdown export of search results."""
    from datetime import datetime

    lines = [
        f"# ARCHILLES Suchergebnisse",
        f"",
        f"**Query:** {query}",
        f"**Datum:** {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"**Ergebnisse:** {len(results)}",
    ]

    if filters:
        lines.append(f"**Filter:** {', '.join(filters)}")

    lines.append("")
    lines.append("---")
    lines.append("")

    for i, result in enumerate(results, 1):
        metadata = result.get('metadata', {})
        text = result.get('text', '')
        score = result.get('score', 0)

        book_title = metadata.get('book_title', '') or metadata.get('title', 'Unknown')
        author = metadata.get('author', '')
        year = metadata.get('year', 0)
        page = metadata.get('page_number', 0)
        page_label = metadata.get('page_label', '')
        calibre_id = metadata.get('calibre_id', 0)
        chapter = metadata.get('chapter', '')
        section_title = metadata.get('section_title', '')

        lines.append(f"## {i}. {book_title}")
        lines.append("")

        meta_parts = []
        if author:
            meta_parts.append(f"**Autor:** {author}")
        if year and year > 0:
            meta_parts.append(f"**Jahr:** {year}")
        if chapter:
            meta_parts.append(f"**Kapitel:** {chapter}")
        if section_title:
            meta_parts.append(f"**Abschnitt:** {section_title}")
        if page_label:
            meta_parts.append(f"**Seite:** {page_label}")
        elif page and page > 0:
            meta_parts.append(f"**Seite:** {page}")
        if calibre_id and calibre_id > 0:
            meta_parts.append(f"**Calibre-ID:** {calibre_id}")
        meta_parts.append(f"**Score:** {score:.2f}")

        lines.append(" | ".join(meta_parts))
        lines.append("")
        lines.append(f"> {text[:500]}{'...' if len(text) > 500 else ''}")
        lines.append("")
        lines.append("---")
        lines.append("")

    lines.append(f"*Exportiert von ARCHILLES*")

    return "\n".join(lines)


def render_books_tab(rag, stats):
    """Render index status overview — what's indexed, what's not."""
    st.header("Index-Status")

    books = get_indexed_books_list(rag)

    if not books:
        st.info("Noch keine Bücher indexiert.")
        return

    total_chunks = stats.get('total_chunks', 0)
    st.markdown(f"**{len(books)} Bücher** indexiert · **{total_chunks:,}** Chunks")

    # Search/filter within indexed books
    filter_text = st.text_input(
        "Bücher filtern",
        placeholder="Titel oder Autor eingeben...",
        key="book_filter"
    )

    filtered = books
    if filter_text:
        q = filter_text.lower()
        filtered = [b for b in books if
                    q in (b.get('title', '') or '').lower() or
                    q in (b.get('author', '') or '').lower()]
        st.caption(f"{len(filtered)} von {len(books)} Büchern")

    st.divider()

    # Compact table-like display
    for book in filtered:
        title = book.get('title', 'Unbekannt')
        author = book.get('author', '')
        chunks = book.get('chunks', 0)
        calibre_id = book.get('calibre_id', 0)

        col1, col2 = st.columns([5, 1])
        with col1:
            line = f"**{title}**"
            if author:
                line += f"  \n{author}"
            st.markdown(line)
        with col2:
            st.caption(f"{chunks} Chunks")


def main():
    # Header in Courier Prime
    st.markdown(
        '<link href="https://fonts.googleapis.com/css2?family=Courier+Prime&display=swap" rel="stylesheet">'
        '<h1 style="font-family: \'Courier Prime\', monospace;">📚 ARCHILLES</h1>',
        unsafe_allow_html=True
    )
    st.caption("Semantic Search for Your Book Collection")

    # Load RAG system
    rag = load_rag()

    # Get stats (with fallback for empty/new databases)
    try:
        stats = rag.store.get_stats()
    except Exception:
        stats = {'total_books': 0, 'total_chunks': 0, 'languages': {}, 'file_types': {}}

    # Tabs
    tab_search, tab_books = st.tabs(["🔍 Suche", "📚 Bücher"])

    # Sidebar
    with st.sidebar:
        st.header("Datenbank")
        st.metric("Indexierte Bücher", stats.get('total_books', 0))
        st.metric("Chunks", f"{stats.get('total_chunks', 0):,}")

        st.divider()

        # Search settings
        st.header("Sucheinstellungen")

        mode = st.selectbox(
            "Suchmodus",
            options=['hybrid', 'semantic', 'keyword'],
            format_func=lambda x: {
                'hybrid': '🔀 Hybrid (Empfohlen)',
                'semantic': '🧠 Semantisch',
                'keyword': '🔤 Keyword'
            }.get(x, x),
            index=0
        )

        top_k = st.slider("Ergebnisse", min_value=5, max_value=50, value=10, step=5)

        max_per_book = st.slider("Max. pro Buch", min_value=1, max_value=10, value=2)

        # Confidence threshold (only meaningful for semantic mode)
        if mode == 'semantic':
            min_similarity = st.slider(
                "Min. Ähnlichkeit",
                min_value=0.0,
                max_value=1.0,
                value=0.0,
                step=0.05,
                help="Filtert Ergebnisse unter diesem Schwellenwert (Cosine-Ähnlichkeit). Höher = strenger."
            )
        else:
            min_similarity = 0.0  # RRF/keyword scores are not on 0-1 scale

        st.divider()

        # Filters
        st.header("Filter")

        # Language filter
        languages = stats.get('languages', {})
        if languages:
            lang_options = ['Alle'] + list(languages.keys())
            selected_lang = st.selectbox("Sprache", options=lang_options)
            language_filter = None if selected_lang == 'Alle' else selected_lang
        else:
            language_filter = None

        # Section filter — default to 'main' (exclude bibliography/index)
        section_options = {
            '📖 Nur Haupttext': 'main',
            '📑 Nur Anhang': 'back_matter',
            '📄 Nur Vorwort': 'front_matter',
            'Alle Abschnitte': None,
        }
        selected_section = st.selectbox("Abschnitt", options=list(section_options.keys()))
        section_filter = section_options[selected_section]

        # Chunk type filter
        chunk_options = {
            '📖 Buchtext': 'content',
            '💬 Calibre-Kommentare': 'calibre_comment',
            '📋 Alle': None
        }
        selected_chunk = st.selectbox("Inhaltstyp", options=list(chunk_options.keys()))
        chunk_type_filter = chunk_options[selected_chunk]

        # Tag filter
        available_tags = get_available_tags(rag)
        if available_tags:
            tag_options = ['Alle Tags'] + available_tags
            selected_tags = st.multiselect(
                "🏷️ Tags",
                options=available_tags,
                default=[],
                help="Nur in Büchern mit diesen Tags suchen"
            )
            tag_filter = selected_tags if selected_tags else None
        else:
            tag_filter = None

        # Book filter
        indexed_books = get_indexed_books_list(rag)
        if indexed_books:
            book_options = [{'label': 'Alle Bücher', 'id': None}]
            for book in indexed_books:
                title = book.get('title', 'Unbekannt')[:50]
                author = book.get('author', '')[:20]
                book_id = book.get('book_id', '')
                label = f"{title}" + (f" ({author})" if author else "")
                book_options.append({'label': label, 'id': book_id})

            selected_book_idx = st.selectbox(
                "📖 In Buch suchen",
                options=range(len(book_options)),
                format_func=lambda i: book_options[i]['label'],
                index=0
            )
            book_id_filter = book_options[selected_book_idx]['id']
        else:
            book_id_filter = None

        st.divider()

        # Advanced options
        with st.expander("⚙️ Erweitert"):
            exact_phrase = st.checkbox(
                "Exakte Phrase",
                value=False,
                help="Findet nur exakte Übereinstimmungen (gut für Zitate, Latein)"
            )
            show_expanded_context = st.checkbox(
                "Erweiterter Kontext",
                value=False,
                help="Zeigt umgebenden Text (window_text) oder Eltern-Chunk an"
            )

        st.divider()

        # Database info
        with st.expander("Datenbankdetails"):
            st.json({
                "Bücher": stats.get('total_books', 0),
                "Chunks": stats.get('total_chunks', 0),
                "Ø Chunks/Buch": round(stats.get('avg_chunks_per_book', 0), 1),
                "Formate": stats.get('file_types', {}),
                "Sprachen": stats.get('languages', {})
            })

    # Search tab (rendered first to ensure it's always available)
    with tab_search:
        # Search input
        query = st.text_input(
            "Suchbegriff oder Frage eingeben",
            placeholder="z.B. 'Arendt Totalitarismus' oder 'Was ist das Wesen der Freiheit?'",
            key="search_query"
        )

        # Search button
        col1, col2, col3 = st.columns([1, 1, 4])
        with col1:
            search_clicked = st.button("🔍 Suchen", type="primary", use_container_width=True)
        with col2:
            if st.button("🗑️ Löschen", use_container_width=True):
                st.session_state.search_query = ""
                st.rerun()

        # Execute search
        if query and search_clicked:
            query_terms = query.split()

            # Build filter description for display
            active_filters = []
            if tag_filter:
                active_filters.append(f"Tags: {', '.join(tag_filter)}")
            if book_id_filter:
                active_filters.append(f"Buch: {book_options[selected_book_idx]['label']}")
            if language_filter:
                active_filters.append(f"Sprache: {language_filter}")
            if exact_phrase:
                active_filters.append("Exakte Phrase")

            filter_msg = f" (Filter: {'; '.join(active_filters)})" if active_filters else ""

            with st.spinner(f"Suche in {stats.get('total_chunks', 0):,} Chunks{filter_msg}..."):
                try:
                    results = rag.query(
                        query_text=query,
                        top_k=top_k,
                        mode=mode,
                        language=language_filter,
                        book_id=book_id_filter,
                        exact_phrase=exact_phrase,
                        tag_filter=tag_filter,
                        section_filter=section_filter,
                        chunk_type_filter=chunk_type_filter,
                        max_per_book=max_per_book,
                        min_similarity=min_similarity
                    )
                except Exception as e:
                    error_msg = str(e)
                    if "INVERTED index" in error_msg or "full text search" in error_msg.lower():
                        st.error("FTS-Index fehlt! Keyword-Suche nicht verfügbar.")
                        st.info("Lösung: `python scripts/rag_demo.py create-index --fts-only`")
                        st.info("Alternativ: Hybrid- oder Semantische Suche verwenden.")
                    else:
                        st.error(f"Suchfehler: {e}")
                    results = []

            # Results header
            if results:
                st.success(f"**{len(results)}** Ergebnisse für: *{query}*")

                # Show active filters
                if active_filters:
                    st.caption(f"Filter: {' | '.join(active_filters)}")

                # Export button
                col_export, col_spacer = st.columns([1, 5])
                with col_export:
                    export_md = generate_markdown_export(results, query, active_filters)
                    st.download_button(
                        label="📥 Export",
                        data=export_md,
                        file_name=f"archilles_search_{query[:20].replace(' ', '_')}.md",
                        mime="text/markdown",
                        help="Ergebnisse als Markdown exportieren"
                    )

                st.divider()

                # Results
                for i, result in enumerate(results, 1):
                    render_result(result, i, query_terms,
                                  show_expanded_context=show_expanded_context,
                                  rag=rag)
            else:
                st.warning("Keine Ergebnisse gefunden.")
                st.info("Versuche andere Suchbegriffe oder deaktiviere Filter.")

        elif query and not search_clicked:
            st.info("Drücke 'Suchen' oder Enter um zu suchen.")

    # Books tab
    with tab_books:
        render_books_tab(rag, stats)

    # Footer
    st.divider()
    st.caption("ARCHILLES - Advanced Research & Citation Helper for Intelligent Literature & Library Exploration System")


if __name__ == "__main__":
    main()
