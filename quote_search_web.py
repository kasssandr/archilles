#!/usr/bin/env python3
"""
Calibre Quote Tracker - Web UI
Interactive web interface for searching quotes in your Calibre library
"""

import streamlit as st
from pathlib import Path
import sys
from calibre_analyzer import CalibreAnalyzer
from text_extractor import CalibreTextExtractor
from search_engine import SearchEngine
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Page configuration
st.set_page_config(
    page_title="Calibre Quote Tracker",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded"
)


def initialize_session_state():
    """Initialize session state variables"""
    if 'library_path' not in st.session_state:
        st.session_state.library_path = None
    if 'search_results' not in st.session_state:
        st.session_state.search_results = []
    if 'last_query' not in st.session_state:
        st.session_state.last_query = ""
    if 'index_path' not in st.session_state:
        st.session_state.index_path = "quote_search_index.db"
    if 'collection_name' not in st.session_state:
        st.session_state.collection_name = "quote_tracker"
    if 'chroma_db_path' not in st.session_state:
        st.session_state.chroma_db_path = "./chroma_db"


def get_available_collections():
    """Get list of available ChromaDB collections"""
    try:
        import chromadb
        from chromadb.config import Settings

        client = chromadb.PersistentClient(
            path=st.session_state.chroma_db_path,
            settings=Settings(anonymized_telemetry=False)
        )
        collections = client.list_collections()
        return [col.name for col in collections]
    except Exception as e:
        logger.warning(f"Could not list collections: {e}")
        return []


def sidebar_config():
    """Sidebar configuration"""
    st.sidebar.title("⚙️ Konfiguration")

    # Library path input
    library_path = st.sidebar.text_input(
        "Calibre Bibliothek Pfad",
        value=st.session_state.get('library_path', ''),
        placeholder="/pfad/zu/Calibre-Library"
    )

    if library_path:
        st.session_state.library_path = library_path

        # Check if path exists
        path = Path(library_path)
        if path.exists():
            st.sidebar.success("✓ Bibliothek gefunden")

            # Show metadata.db status
            metadata_db = path / "metadata.db"
            if metadata_db.exists():
                st.sidebar.success("✓ metadata.db gefunden")
            else:
                st.sidebar.error("✗ metadata.db nicht gefunden")
        else:
            st.sidebar.error("✗ Pfad nicht gefunden")

    st.sidebar.divider()

    # Index path
    index_path = st.sidebar.text_input(
        "Such-Index Pfad",
        value=st.session_state.index_path,
        help="SQLite-Datenbank für den Volltext-Index"
    )
    st.session_state.index_path = index_path

    # Show index stats if exists
    if Path(index_path).exists():
        try:
            with SearchEngine(index_path) as engine:
                stats = engine.get_stats()
                st.sidebar.info(f"📊 {stats['total_books']} Bücher indiziert")
        except Exception as e:
            st.sidebar.warning(f"Index-Fehler: {e}")

    st.sidebar.divider()

    # ChromaDB Collection Selection
    st.sidebar.subheader("🗂️ Semantic Collection")

    available_collections = get_available_collections()

    if available_collections:
        # Show collection dropdown
        selected_collection = st.sidebar.selectbox(
            "Collection wählen",
            options=available_collections,
            index=available_collections.index(st.session_state.collection_name)
                  if st.session_state.collection_name in available_collections else 0,
            help="Wähle die ChromaDB Collection für semantische Suche"
        )
        st.session_state.collection_name = selected_collection

        # Show collection stats (with error handling for large collections)
        try:
            from semantic_search import SemanticSearchEngine
            engine = SemanticSearchEngine(
                chroma_db_path=st.session_state.chroma_db_path,
                collection_name=selected_collection
            )
            # Use small sample for stats to avoid RAM overload on large collections
            stats = engine.get_stats(sample_size=500)
            st.sidebar.success(
                f"✓ Collection: **{selected_collection}**\n\n"
                f"📚 {stats['unique_books']} Bücher\n\n"
                f"🧩 {stats['total_chunks']:,} Chunks"
            )
        except Exception as e:
            st.sidebar.warning(f"Collection-Info nicht verfügbar: {e}")
            logger.exception("Collection stats error")
    else:
        st.sidebar.info("ℹ️ Keine Collections gefunden. Bitte erst indizieren!")
        # Allow manual input
        manual_collection = st.sidebar.text_input(
            "Collection-Name (manuell)",
            value=st.session_state.collection_name,
            help="Gib den Namen einer existierenden Collection ein"
        )
        st.session_state.collection_name = manual_collection

    st.sidebar.divider()

    # Actions
    st.sidebar.subheader("Aktionen")

    return library_path


def indexing_tab():
    """Indexing interface"""
    st.header("📇 Bibliothek Indizieren")

    if not st.session_state.library_path:
        st.warning("⚠️ Bitte zuerst Bibliothekspfad in der Sidebar eingeben!")
        return

    col1, col2 = st.columns(2)

    with col1:
        # Tag filter
        tag_filter = st.text_input(
            "Tag-Filter (optional)",
            placeholder="z.B. Leit-Literatur",
            help="Nur Bücher mit diesem Tag indizieren"
        )

    with col2:
        # Limit
        limit = st.number_input(
            "Maximale Anzahl Bücher",
            min_value=1,
            max_value=10000,
            value=100,
            help="Für Tests: Nur die ersten N Bücher indizieren"
        )

    # Semantic indexing option
    enable_semantic = st.checkbox(
        "🧠 Semantische Indizierung aktivieren",
        value=True,
        help="Erstellt zusätzlich einen semantischen Index für intelligente Suche. Dauert länger, ermöglicht aber konzeptionelle Suche."
    )

    # Start indexing button
    if st.button("🚀 Indizierung starten", type="primary"):
        start_indexing(tag_filter if tag_filter else None, limit, enable_semantic)


def start_indexing(tag_filter, limit, enable_semantic=True):
    """Start the indexing process"""
    progress_container = st.container()

    with progress_container:
        mode_text = "Keyword + Semantic" if enable_semantic else "Nur Keyword"
        st.info(f"⏳ Indizierung läuft... ({mode_text})")
        progress_bar = st.progress(0)
        status_text = st.empty()

        try:
            library_path = Path(st.session_state.library_path)
            metadata_db = library_path / "metadata.db"

            # Get books to index
            with CalibreAnalyzer(str(metadata_db)) as analyzer:
                if tag_filter:
                    query = """
                        SELECT DISTINCT books.id, books.title, authors.name as author
                        FROM books
                        JOIN books_authors_link ON books.id = books_authors_link.book
                        JOIN authors ON books_authors_link.author = authors.id
                        JOIN books_tags_link ON books.id = books_tags_link.book
                        JOIN tags ON books_tags_link.tag = tags.id
                        WHERE tags.name = ?
                        LIMIT ?
                    """
                    cursor = analyzer.conn.execute(query, (tag_filter, limit))
                else:
                    query = """
                        SELECT DISTINCT books.id, books.title, authors.name as author
                        FROM books
                        JOIN books_authors_link ON books.id = books_authors_link.book
                        JOIN authors ON books_authors_link.author = authors.id
                        LIMIT ?
                    """
                    cursor = analyzer.conn.execute(query, (limit,))

                books = cursor.fetchall()

            if not books:
                st.error("❌ Keine Bücher gefunden!")
                return

            status_text.text(f"Gefunden: {len(books)} Bücher")

            # Initialize engines
            keyword_engine = SearchEngine(st.session_state.index_path)

            if enable_semantic:
                try:
                    from semantic_search import SemanticSearchEngine, chunk_text
                    semantic_engine = SemanticSearchEngine(
                        chroma_db_path=st.session_state.chroma_db_path,
                        collection_name=st.session_state.collection_name
                    )
                    status_text.text(f"✓ Semantische Suchmaschine initialisiert (Collection: {st.session_state.collection_name})")
                except Exception as e:
                    st.warning(f"⚠ Semantische Suche nicht verfügbar: {e}")
                    st.info("Fallback auf nur Keyword-Indizierung")
                    semantic_engine = None
                    enable_semantic = False
            else:
                semantic_engine = None

            # Index books
            text_extractor = CalibreTextExtractor(st.session_state.library_path)
            indexed_count = 0
            failed_count = 0
            processed_book_ids = set()  # Track processed book IDs to avoid duplicates

            try:
                for idx, book in enumerate(books):
                    progress = (idx + 1) / len(books)
                    progress_bar.progress(progress)

                    book_id = book['id']
                    title = book['title']
                    author = book['author']

                    # Skip if we've already processed this book ID (multi-author books)
                    if book_id in processed_book_ids:
                        continue
                    processed_book_ids.add(book_id)

                    status_text.text(f"[{idx + 1}/{len(books)}] {title[:40]}...")

                    # Extract text
                    text, format_used = text_extractor.extract_book_text(book_id, author, title)

                    if text:
                        # Index in keyword engine
                        keyword_engine.index_book(book_id, author, title, format_used, text)

                        # Index in semantic engine
                        if enable_semantic and semantic_engine:
                            chunks = chunk_text(text, chunk_size=1000, overlap=200)
                            semantic_engine.index_text_chunks(book_id, author, title, chunks)

                        indexed_count += 1
                    else:
                        failed_count += 1

            finally:
                keyword_engine.close()

            # Show results
            progress_bar.progress(1.0)
            st.success(f"✅ Indizierung abgeschlossen!")

            col1, col2 = st.columns(2)
            with col1:
                st.metric("Erfolgreich", indexed_count)
            with col2:
                st.metric("Fehlgeschlagen", failed_count)

            # Show stats
            if enable_semantic and semantic_engine:
                sem_stats = semantic_engine.get_stats(sample_size=500)
                st.info(f"📊 Semantischer Index: {sem_stats['total_chunks']} Chunks aus {sem_stats['unique_books']} Büchern")

        except Exception as e:
            st.error(f"❌ Fehler bei der Indizierung: {e}")
            logger.exception("Indexing error")


def search_tab():
    """Search interface"""
    st.header("🔍 Zitat-Suche")

    # Search input
    query = st.text_input(
        "Suchbegriff",
        value=st.session_state.last_query,
        placeholder="z.B. Josephus, ancient Rome, Testimonium Flavianum...",
        help="Gib einen Suchbegriff ein"
    )

    # Search mode selector
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        search_mode = st.selectbox(
            "🔎 Suchmodus",
            options=['keyword', 'semantic', 'hybrid'],
            format_func=lambda x: {
                'keyword': '🔤 Keyword (exakt)',
                'semantic': '🧠 Semantisch (intelligent)',
                'hybrid': '🔀 Hybrid (beides)'
            }[x],
            help="Keyword: Findet exakte Begriffe | Semantisch: Findet konzeptionell Verwandtes | Hybrid: Kombiniert beide"
        )

    with col2:
        context_type = st.selectbox(
            "Kontext-Typ",
            options=['sentences', 'words'],
            format_func=lambda x: "Sätze" if x == 'sentences' else "Wörter"
        )

    with col3:
        context_size = st.number_input(
            "Kontext-Größe",
            min_value=1,
            max_value=500,
            value=3 if context_type == 'sentences' else 200,
            help="Anzahl Sätze/Wörter vor und nach dem Treffer"
        )

    with col4:
        max_results = st.number_input(
            "Max. Ergebnisse",
            min_value=1,
            max_value=100,
            value=20
        )

    # Advanced options (collapsible)
    with st.expander("🎛️ Erweiterte Optionen", expanded=False):
        col_adv1, col_adv2 = st.columns(2)

        with col_adv1:
            enable_diversity = st.checkbox(
                "Ergebnis-Diversität aktivieren",
                value=True,
                help="Begrenzt Treffer pro Buch für vielfältigere Ergebnisse"
            )

        with col_adv2:
            max_per_book = st.number_input(
                "Max. Treffer pro Buch",
                min_value=1,
                max_value=10,
                value=3,
                disabled=not enable_diversity,
                help="Maximale Anzahl Treffer aus demselben Buch (vermeidet Dominanz einzelner Bücher)"
            )

        st.divider()

        # Semantic confidence threshold
        show_semantic_options = search_mode in ['semantic', 'hybrid']

        if show_semantic_options:
            st.markdown("**🎯 Semantische Suche - Konfidenz**")

            min_similarity = st.slider(
                "Minimale Ähnlichkeit (Confidence Threshold)",
                min_value=0.0,
                max_value=1.0,
                value=0.5,
                step=0.05,
                help="Filtert semantische Treffer unter diesem Schwellenwert. "
                     "Höher = nur sehr relevante Treffer | Niedriger = mehr Treffer, aber evtl. weniger relevant. "
                     "Empfohlen: 0.5-0.7 für gute Balance"
            )

            # Show interpretation
            if min_similarity >= 0.7:
                st.caption("🎯 Streng: Nur sehr relevante Treffer")
            elif min_similarity >= 0.5:
                st.caption("⚖️ Ausgewogen: Gute Balance zwischen Relevanz und Anzahl")
            else:
                st.caption("🔓 Tolerant: Viele Treffer, auch weniger relevante")
        else:
            min_similarity = 0.5  # Default for keyword-only

    # Search button
    if st.button("🔎 Suchen", type="primary") or (query and query != st.session_state.last_query):
        if not query:
            st.warning("⚠️ Bitte Suchbegriff eingeben!")
        else:
            diversity_limit = max_per_book if enable_diversity else None
            perform_search(query, search_mode, context_type, context_size, max_results, diversity_limit, min_similarity)
            st.session_state.last_query = query

    # Display results
    if st.session_state.search_results:
        st.divider()
        display_search_results(context_type, context_size)


def perform_search(query, search_mode, context_type, context_size, max_results, max_per_book=None, min_similarity=0.5):
    """Perform search and store results"""
    import random

    # Witty academic thinking messages (inspired by Claude's thinking states)
    thinking_messages = [
        "🧠 Cerebrating through ancient texts...",
        "📚 Mulling over manuscripts...",
        "🔍 Frolicking through footnotes...",
        "⚡ Pondering papyri...",
        "🎯 Cogitating through codices...",
        "✨ Ruminating over references...",
        "🤔 Deliberating on documents...",
        "💭 Meditating on metadata...",
        "🧩 Puzzling through passages...",
        "🔬 Scrutinizing sources...",
        "📖 Perusing parchments...",
        "🎓 Contemplating corpus...",
        "⚙️ Processing profound passages...",
        "🌟 Excavating erudite excerpts...",
        "🏛️ Rummaging through rabbinic writings...",
        "📜 Sifting through scrolls...",
        "🕵️ Investigating inscriptions...",
        "💡 Illuminating intellectual insights...",
        "🗝️ Unlocking textual treasures...",
        "⚗️ Distilling doctrinal discourse...",
        "🎭 Deciphering dramatic dialogues...",
        "🌍 Traversing theological treatises...",
        "🔭 Exploring exegetical evidence...",
        "📐 Analyzing argumentative apparatus...",
    ]

    spinner_text = random.choice(thinking_messages)

    try:
        from search_engine import HybridSearchEngine

        with st.spinner(spinner_text):
            with HybridSearchEngine(
                fts_db_path=st.session_state.index_path,
                chroma_db_path=st.session_state.chroma_db_path,
                collection_name=st.session_state.collection_name
            ) as engine:
                # Execute search based on mode
                if search_mode == 'keyword':
                    results = engine.search_keyword(query, limit=max_results)
                elif search_mode == 'semantic':
                    results = engine.search_semantic(query, limit=max_results, max_per_book=max_per_book, min_similarity=min_similarity)
                else:  # hybrid
                    results = engine.search_hybrid(query, limit=max_results, keyword_weight=0.5, max_per_book=max_per_book, min_similarity=min_similarity)

            st.session_state.search_results = results

            if not results:
                st.info("ℹ️ Keine Ergebnisse gefunden.")
            else:
                # Show search mode info
                if search_mode == 'semantic' and not engine._semantic_available:
                    st.warning("⚠️ Semantische Suche nicht verfügbar, Keyword-Suche verwendet")

    except Exception as e:
        st.error(f"❌ Suchfehler: {e}")
        logger.exception("Search error")


def display_search_results(context_type, context_size):
    """Display search results"""
    results = st.session_state.search_results

    st.subheader(f"📋 {len(results)} Ergebnisse gefunden")

    for idx, result in enumerate(results, 1):
        # Build title with relevance info
        # Try different score fields depending on search mode
        relevance_score = result.get('relevance_score',
                                     result.get('hybrid_score',
                                               result.get('similarity',
                                                         abs(result.get('rank', 0)))))
        source_icon = {
            'keyword': '🔤',
            'semantic': '🧠',
            'hybrid': '🔀'
        }.get(result.get('source', 'keyword'), '🔎')

        # Get title and author safely
        title = result.get('title', 'Unbekannt')
        author = result.get('author', 'Unbekannt')
        format_str = result.get('format', 'UNKNOWN')

        with st.expander(
            f"{idx}. {source_icon} **{title}** von {author} "
            f"({format_str}) - Relevanz: {relevance_score:.2f}",
            expanded=(idx <= 3)  # Auto-expand first 3 results
        ):
            # Show snippet/text
            if 'snippet' in result and result['snippet']:
                st.markdown("**Textauszug:**")
                st.markdown(result['snippet'], unsafe_allow_html=True)
            elif 'text' in result:
                st.markdown("**Textauszug:**")
                st.markdown(result['text'][:500] + "...", unsafe_allow_html=True)

            # Get detailed context for keyword search
            if result.get('source') == 'keyword' or result.get('source') is None:
                try:
                    with SearchEngine(st.session_state.index_path) as engine:
                        contexts = engine.get_context_around_match(
                            result['book_id'],
                            st.session_state.last_query,
                            context_type=context_type,
                            context_size=context_size
                        )

                        if contexts:
                            st.divider()
                            for ctx_idx, context in enumerate(contexts[:3], 1):  # Show max 3 contexts
                                st.markdown(f"**Fundstelle {ctx_idx}:**")
                                st.markdown(context['context'], unsafe_allow_html=True)
                                if ctx_idx < len(contexts[:3]):
                                    st.divider()

                except Exception as e:
                    st.warning(f"Kontext konnte nicht geladen werden: {e}")

            # Metadata
            metadata_parts = [f"Buch-ID: {result['book_id']}"]

            if 'format' in result and result['format']:
                metadata_parts.append(f"Format: {result['format']}")

            # Show scoring details for hybrid results
            if result.get('source') == 'hybrid':
                metadata_parts.append(
                    f"Keyword: {result.get('keyword_score', 0):.2f} | "
                    f"Semantisch: {result.get('semantic_score', 0):.2f}"
                )

            st.caption(" | ".join(metadata_parts))


def statistics_tab():
    """Statistics display"""
    st.header("📊 Statistiken")

    if not Path(st.session_state.index_path).exists():
        st.warning("⚠️ Noch kein Index vorhanden. Bitte zuerst Bibliothek indizieren!")
        return

    try:
        with SearchEngine(st.session_state.index_path) as engine:
            stats = engine.get_stats()

            # Display stats
            col1, col2, col3 = st.columns(3)

            with col1:
                st.metric("Indizierte Bücher", stats['total_books'])

            with col2:
                total_mb = stats['total_characters'] / (1024 * 1024)
                st.metric("Gesamt-Text", f"{total_mb:.1f} MB")

            with col3:
                avg_chars = stats['total_characters'] / max(stats['total_books'], 1)
                st.metric("Ø Zeichen/Buch", f"{avg_chars:,.0f}")

            # Format breakdown
            st.subheader("Formate")
            if stats['formats']:
                import pandas as pd
                df = pd.DataFrame(stats['formats'])
                st.bar_chart(df.set_index('format'))
            else:
                st.info("Keine Format-Daten verfügbar")

    except Exception as e:
        st.error(f"❌ Fehler beim Laden der Statistiken: {e}")
        logger.exception("Statistics error")


def main():
    """Main application"""
    initialize_session_state()

    # Header
    st.title("📚 Calibre Zitat-Tracker")
    st.markdown("*Systematische Suche nach Zitaten und Argumenten in deiner Calibre-Bibliothek*")

    # Sidebar
    sidebar_config()

    # Main tabs
    tab1, tab2, tab3 = st.tabs(["🔍 Suche", "📇 Indizierung", "📊 Statistiken"])

    with tab1:
        search_tab()

    with tab2:
        indexing_tab()

    with tab3:
        statistics_tab()

    # Footer
    st.divider()
    st.caption("Calibre Quote Tracker v1.0 - Phase 1 MVP")


if __name__ == '__main__':
    main()
