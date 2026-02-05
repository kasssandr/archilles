#!/usr/bin/env python3
"""
ARCHILLES Web UI - Streamlit interface for semantic book search.

Usage:
    streamlit run scripts/web_ui.py

Environment:
    CALIBRE_LIBRARY: Path to Calibre library (required)
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

    library_path = os.getenv('CALIBRE_LIBRARY')
    if not library_path:
        st.error("CALIBRE_LIBRARY environment variable not set")
        st.stop()

    db_path = str(Path(library_path) / ".archilles" / "rag_db")

    if not Path(db_path).exists():
        st.error(f"Database not found: {db_path}")
        st.info("Run batch_index.py first to index your books.")
        st.stop()

    return archillesRAG(db_path=db_path)


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


def render_result(result: Dict[str, Any], index: int, query_terms: List[str]):
    """Render a single search result."""
    score = result.get('score', 0)
    text = result.get('text', '')

    # Extract metadata
    book_title = result.get('book_title', 'Unknown')
    author = result.get('author', '')
    year = result.get('year', 0)
    language = result.get('language', '')
    page = result.get('page_number', 0)
    section_type = result.get('section_type', '')
    tags = result.get('tags', '')
    calibre_id = result.get('calibre_id', 0)

    # Score color
    if score > 0.8:
        score_color = "green"
    elif score > 0.6:
        score_color = "orange"
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
        if page and page > 0:
            meta_parts.append(f"**Seite:** {page}")
        if calibre_id and calibre_id > 0:
            meta_parts.append(f"**Calibre-ID:** {calibre_id}")

        if meta_parts:
            st.markdown(" | ".join(meta_parts))

        # Tags
        if tags:
            st.markdown(f"**Tags:** {tags}")

        # Section type badge
        if section_type:
            section_labels = {
                'main_content': '📖 Haupttext',
                'front_matter': '📄 Vorwort/Einleitung',
                'back_matter': '📑 Anhang/Register'
            }
            label = section_labels.get(section_type, section_type)
            st.caption(label)

        # Snippet with highlighting
        snippet = extract_snippet(text, query_terms)
        highlighted = highlight_text(snippet, query_terms)
        st.markdown(f"> {highlighted}")

        # Expander for full text
        with st.expander("Volltext anzeigen"):
            st.text(text)

        st.divider()


def render_books_tab(rag, stats):
    """Render the indexed books browser tab."""
    st.header("Indexierte Bücher")

    # Get indexed books
    books = rag.store.get_indexed_books()

    if not books:
        st.info("Noch keine Bücher indexiert.")
        return

    # Sort options
    col1, col2 = st.columns([1, 3])
    with col1:
        sort_by = st.selectbox(
            "Sortieren nach",
            options=['title', 'author', 'year', 'chunks'],
            format_func=lambda x: {
                'title': 'Titel',
                'author': 'Autor',
                'year': 'Jahr',
                'chunks': 'Chunks'
            }.get(x, x)
        )

    # Sort books
    reverse = sort_by in ['year', 'chunks']
    books_sorted = sorted(
        books,
        key=lambda x: x.get(sort_by, '') or '',
        reverse=reverse
    )

    # Display books
    st.markdown(f"**{len(books_sorted)} Bücher** indexiert mit **{stats.get('total_chunks', 0):,}** Chunks")
    st.divider()

    for book in books_sorted:
        with st.container():
            col1, col2 = st.columns([4, 1])
            with col1:
                title = book.get('title', 'Unbekannt')
                author = book.get('author', '')
                year = book.get('year', 0)

                st.markdown(f"**{title}**")
                meta = []
                if author:
                    meta.append(author)
                if year and year > 0:
                    meta.append(str(year))
                if meta:
                    st.caption(" | ".join(meta))

            with col2:
                chunks = book.get('chunks', 0)
                calibre_id = book.get('calibre_id', 0)
                st.metric("Chunks", chunks, label_visibility="collapsed")
                if calibre_id:
                    st.caption(f"ID: {calibre_id}")

            # Tags
            tags = book.get('tags', '')
            if tags:
                st.caption(f"Tags: {tags}")

            st.divider()


def main():
    # Header
    st.title("📚 ARCHILLES")
    st.caption("Semantic Search for Your Book Collection")

    # Load RAG system
    rag = load_rag()

    # Get stats
    stats = rag.store.get_stats()

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

        # Section filter
        section_options = {
            'Alle': None,
            '📖 Nur Haupttext': 'main',
            '📄 Nur Vorwort': 'front_matter',
            '📑 Nur Anhang': 'back_matter'
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

    # Books tab
    with tab_books:
        render_books_tab(rag, stats)

    # Search tab
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

            with st.spinner(f"Suche in {stats.get('total_chunks', 0):,} Chunks..."):
                try:
                    results = rag.query(
                        query_text=query,
                        top_k=top_k,
                        mode=mode,
                        language=language_filter,
                        section_filter=section_filter,
                        chunk_type_filter=chunk_type_filter,
                        max_per_book=max_per_book
                    )
                except Exception as e:
                    st.error(f"Suchfehler: {e}")
                    results = []

            # Results header
            if results:
                st.success(f"**{len(results)}** Ergebnisse für: *{query}*")

                # Results
                for i, result in enumerate(results, 1):
                    render_result(result, i, query_terms)
            else:
                st.warning("Keine Ergebnisse gefunden.")
                st.info("Versuche andere Suchbegriffe oder deaktiviere Filter.")

        elif query and not search_clicked:
            st.info("Drücke 'Suchen' oder Enter um zu suchen.")

    # Footer
    st.divider()
    st.caption("ARCHILLES - Advanced Research & Citation Helper for Intelligent Literature & Library Exploration System")


if __name__ == "__main__":
    main()
