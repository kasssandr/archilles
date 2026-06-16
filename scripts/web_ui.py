#!/usr/bin/env python3
"""
ARCHILLES Web UI - Streamlit interface for semantic book search.

Usage:
    streamlit run scripts/web_ui.py

Environment:
    ARCHILLES_LIBRARY_PATH: Path to library (required; legacy: CALIBRE_LIBRARY_PATH)
"""

import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.archilles.config import get_languages, get_library_path
from src.archilles.constants import ChunkType, SectionType
from src.archilles.i18n import t

import streamlit as st

# Page config must be first Streamlit command
st.set_page_config(
    page_title="ARCHILLES",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded"
)


def _ui_lang() -> str:
    """Operator/interface language (``get_languages(...)[0]``, default 'en')."""
    return get_languages(get_library_path(required=False))[0]


def _safe_str(value: Any) -> str:
    """Coerce a possibly int/None/NaN metadata value to a clean string.

    Aggregating the store's book list (groupby/first) can yield non-string
    values — numeric tags, or NaN for sparse author/title — which break the
    downstream .split()/.lower()/slicing assumptions and crash the page.
    """
    if value is None:
        return ''
    if isinstance(value, float) and value != value:  # NaN
        return ''
    return str(value)


@st.cache_resource
def load_service():
    """Load ARCHILLES service (cached for performance)."""
    from src.service import ArchillesService

    lang = _ui_lang()
    library_path = get_library_path(required=False)
    if not library_path:
        st.error(t("webui.error_no_library", lang))
        st.info(t("webui.hint_set_library", lang))
        st.stop()

    db_path = str(library_path / ".archilles" / "rag_db")

    if not Path(db_path).exists():
        st.error(t("webui.error_db_not_found", lang).format(path=db_path))
        st.info(t("webui.hint_run_index", lang))
        st.stop()

    return ArchillesService(db_path=db_path)


@st.cache_data(ttl=300)  # Cache for 5 minutes
def get_available_tags(_service) -> List[str]:
    """Get all unique tags from indexed books."""
    try:
        books = _service.get_book_list()
    except Exception:
        return []
    all_tags = set()
    for book in books:
        tags_str = _safe_str(book.get('tags'))
        if tags_str:
            for tag in tags_str.split(', '):
                tag = tag.strip()
                if tag:
                    all_tags.add(tag)
    return sorted(all_tags)


@st.cache_data(ttl=300)  # Cache for 5 minutes
def get_indexed_books_list(_service) -> List[Dict[str, Any]]:
    """Get list of indexed books for dropdown."""
    try:
        books = _service.get_book_list()
    except Exception:
        return []
    # Normalize string-ish fields up front; aggregation can yield int/NaN, which
    # would break sorting, slicing and .lower() in the books tab and book filter.
    for book in books:
        for key in ('title', 'author', 'tags'):
            book[key] = _safe_str(book.get(key))
    return sorted(books, key=lambda x: x.get('title', ''))


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


def _get_result_field(result: Dict[str, Any], key: str, default: Any = '') -> Any:
    """Extract a field from result metadata with fallback to top-level result dict."""
    metadata = result.get('metadata', {})
    value = metadata.get(key, default)
    if not value:
        value = result.get(key, default)
    return value


def render_result(result: Dict[str, Any], index: int, query_terms: List[str],
                  show_expanded_context: bool = False, service=None, lang: str = "en"):
    """Render a single search result."""
    score = result.get('score', 0)
    text = result.get('text', '')

    # Extract metadata (nested in 'metadata' dict from query results)
    book_title = _get_result_field(result, 'book_title', 'Unknown')
    author = _get_result_field(result, 'author')
    year = _get_result_field(result, 'year', 0)
    language = _get_result_field(result, 'language')
    page = _get_result_field(result, 'page_number', 0)
    page_label = _get_result_field(result, 'page_label')
    section_type = _get_result_field(result, 'section_type')
    tags = _get_result_field(result, 'tags')
    calibre_id = _get_result_field(result, 'calibre_id', 0)
    chapter = _get_result_field(result, 'chapter')
    section_title = _get_result_field(result, 'section_title')
    chunk_type = _get_result_field(result, 'chunk_type')
    window_text = _get_result_field(result, 'window_text')
    parent_id = _get_result_field(result, 'parent_id')

    # Fallback for title
    if not book_title or book_title == 'Unknown':
        book_title = result.get('metadata', {}).get('title', '') or 'Unknown'

    # Score color -- adapt to score range (RRF scores are much smaller than cosine)
    if score > 0.8:
        score_color = "green"      # High cosine similarity (semantic mode)
    elif score > 0.5:
        score_color = "orange"     # Moderate cosine similarity
    elif score > 0.03:
        score_color = "green"      # High RRF score (hybrid mode)
    elif score > 0:
        score_color = "orange"     # Low RRF score
    else:
        score_color = "gray"

    with st.container():
        # Header row
        col1, col2 = st.columns([5, 1])
        with col1:
            st.markdown(f"### {index}. {book_title}")
        with col2:
            st.markdown(f":{score_color}[{t('label.score', lang)}: {score:.2f}]")

        # Metadata row
        meta_parts = []
        if author:
            meta_parts.append(f"**{t('label.author', lang)}:** {author}")
        if year and year > 0:
            meta_parts.append(f"**{t('label.year', lang)}:** {year}")
        if language:
            meta_parts.append(f"**{t('label.language', lang)}:** {language}")
        # Page: prefer page_label (printed page), show PDF page if different
        if page_label and page_label != str(page):
            meta_parts.append(f"**{t('label.page', lang)}:** {page_label} (PDF: {page})")
        elif page and page > 0:
            meta_parts.append(f"**{t('label.page', lang)}:** {page}")
        if calibre_id and calibre_id > 0:
            meta_parts.append(f"**{t('label.calibre_id', lang)}:** {calibre_id}")

        if meta_parts:
            st.markdown(" | ".join(meta_parts))

        # Chapter / Section
        location_parts = []
        if chapter:
            location_parts.append(f"**{t('label.chapter', lang)}:** {chapter}")
        if section_title:
            location_parts.append(f"**{t('label.section', lang)}:** {section_title}")
        if location_parts:
            st.markdown(" | ".join(location_parts))

        # Tags and badges
        badge_row = []
        if tags:
            badge_row.append(f"🏷️ {tags}")

        # Section type badge
        if section_type and section_type != SectionType.MAIN_CONTENT:
            section_labels = {
                SectionType.FRONT_MATTER: t('webui.section_front_matter', lang),
                SectionType.BACK_MATTER: t('webui.section_back_matter', lang)
            }
            label = section_labels.get(section_type, section_type)
            badge_row.append(label)

        # Chunk type badge (only for hierarchical chunks)
        if chunk_type and chunk_type not in (ChunkType.CONTENT, ''):
            chunk_labels = {
                ChunkType.CHILD: t('webui.chunk_child', lang),
                ChunkType.PARENT: t('webui.chunk_parent', lang),
                ChunkType.CALIBRE_COMMENT: t('webui.chunk_comment', lang),
                ChunkType.PHASE1_METADATA: t('webui.chunk_metadata', lang)
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
        with st.expander(t('webui.show_fulltext', lang)):
            st.text(text)

        # Context expansion (window_text or parent chunk)
        if show_expanded_context and (window_text or parent_id):
            with st.expander(t('webui.expanded_context', lang)):
                if window_text and len(window_text) > len(text):
                    st.caption(t('webui.surrounding_text', lang))
                    st.text(window_text)
                elif parent_id and service:
                    parent = service.get_chunk_by_id(parent_id)
                    if parent and parent.get('text'):
                        st.caption(t('webui.parent_chunk', lang).format(id=parent_id))
                        st.text(parent['text'])

        st.divider()


def generate_markdown_export(results: List[Dict[str, Any]], query: str,
                             filters: List[str], lang: str = "en") -> str:
    """Generate Markdown export of search results."""
    from datetime import datetime

    lines = [
        f"# {t('webui.export_title', lang)}",
        f"",
        f"**{t('export.query', lang)}:** {query}",
        f"**{t('export.date', lang)}:** {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        f"**{t('export.results', lang)}:** {len(results)}",
    ]

    if filters:
        lines.append(f"**{t('label.filter', lang)}:** {', '.join(filters)}")

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
            meta_parts.append(f"**{t('label.author', lang)}:** {author}")
        if year and year > 0:
            meta_parts.append(f"**{t('label.year', lang)}:** {year}")
        if chapter:
            meta_parts.append(f"**{t('label.chapter', lang)}:** {chapter}")
        if section_title:
            meta_parts.append(f"**{t('label.section', lang)}:** {section_title}")
        if page_label:
            meta_parts.append(f"**{t('label.page', lang)}:** {page_label}")
        elif page and page > 0:
            meta_parts.append(f"**{t('label.page', lang)}:** {page}")
        if calibre_id and calibre_id > 0:
            meta_parts.append(f"**{t('label.calibre_id', lang)}:** {calibre_id}")
        meta_parts.append(f"**{t('label.score', lang)}:** {score:.2f}")

        lines.append(" | ".join(meta_parts))
        lines.append("")
        lines.append(f"> {text[:500]}{'...' if len(text) > 500 else ''}")
        lines.append("")
        lines.append("---")
        lines.append("")

    lines.append(t('webui.export_footer', lang))

    return "\n".join(lines)


def render_books_tab(service, stats, lang: str = "en"):
    """Render index status overview — what's indexed, what's not."""
    st.header(t('webui.index_status', lang))

    books = get_indexed_books_list(service)

    if not books:
        st.info(t('webui.no_books', lang))
        return

    total_chunks = stats.get('total_chunks', 0)
    st.markdown(t('webui.books_indexed_summary', lang).format(
        n=len(books), chunks=f"{total_chunks:,}"))

    # Search/filter within indexed books
    filter_text = st.text_input(
        t('webui.filter_books', lang),
        placeholder=t('webui.filter_books_placeholder', lang),
        key="book_filter"
    )

    filtered = books
    if filter_text:
        q = filter_text.lower()
        filtered = [b for b in books if
                    q in (b.get('title', '') or '').lower() or
                    q in (b.get('author', '') or '').lower()]
        st.caption(t('webui.books_count', lang).format(shown=len(filtered), total=len(books)))

    st.divider()

    # Compact table-like display
    for book in filtered:
        title = book.get('title') or t('webui.unknown', lang)
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
            st.caption(t('webui.chunks_count', lang).format(n=chunks))


def main():
    lang = _ui_lang()

    # Header in Courier Prime
    st.markdown(
        '<link href="https://fonts.googleapis.com/css2?family=Courier+Prime&display=swap" rel="stylesheet">'
        '<h1 style="font-family: \'Courier Prime\', monospace;">📚 ARCHILLES</h1>',
        unsafe_allow_html=True
    )
    st.caption("Semantic Search for Your Book Collection")

    # Load ARCHILLES service
    service = load_service()

    # Get stats (with fallback for empty/new databases)
    try:
        stats = service.get_index_status()
    except Exception:
        stats = {'total_books': 0, 'total_chunks': 0, 'languages': {}, 'file_types': {}}

    # Tabs
    tab_search, tab_books = st.tabs([t('webui.tab_search', lang), t('webui.tab_books', lang)])

    # Sidebar
    with st.sidebar:
        st.header(t('webui.sidebar_database', lang))
        st.metric(t('webui.metric_indexed_books', lang), stats.get('total_books', 0))
        st.metric(t('webui.metric_chunks', lang), f"{stats.get('total_chunks', 0):,}")

        st.divider()

        # Search settings
        st.header(t('webui.search_settings', lang))

        mode = st.selectbox(
            t('webui.search_mode', lang),
            options=['hybrid', 'semantic', 'keyword'],
            format_func=lambda x: {
                'hybrid': t('webui.mode_hybrid', lang),
                'semantic': t('webui.mode_semantic', lang),
                'keyword': t('webui.mode_keyword', lang)
            }.get(x, x),
            index=0
        )

        top_k = st.slider(t('webui.slider_results', lang), min_value=5, max_value=50, value=10, step=5)

        max_per_book = st.slider(t('webui.slider_max_per_book', lang), min_value=1, max_value=10, value=2)

        # Confidence threshold (only meaningful for semantic mode)
        if mode == 'semantic':
            min_similarity = st.slider(
                t('webui.slider_min_similarity', lang),
                min_value=0.0,
                max_value=1.0,
                value=0.0,
                step=0.05,
                help=t('webui.help_min_similarity', lang)
            )
        else:
            min_similarity = 0.0  # RRF/keyword scores are not on 0-1 scale

        st.divider()

        # Filters
        st.header(t('webui.filter_header', lang))

        # Language filter
        languages = stats.get('languages', {})
        if languages:
            all_label = t('webui.filter_all', lang)
            lang_options = [all_label] + list(languages.keys())
            selected_lang = st.selectbox(t('webui.filter_language', lang), options=lang_options)
            language_filter = None if selected_lang == all_label else selected_lang
        else:
            language_filter = None

        # Section filter — default to 'main' (exclude bibliography/index)
        section_options = {
            t('webui.section_main_only', lang): SectionType.MAIN,
            t('webui.section_back_only', lang): SectionType.BACK_MATTER,
            t('webui.section_front_only', lang): SectionType.FRONT_MATTER,
            t('webui.section_all', lang): None,
        }
        selected_section = st.selectbox(t('webui.filter_section', lang), options=list(section_options.keys()))
        section_filter = section_options[selected_section]

        # Chunk type filter
        chunk_options = {
            t('webui.chunk_book_text', lang): ChunkType.CONTENT,
            t('webui.chunk_calibre_comments', lang): ChunkType.CALIBRE_COMMENT,
            t('webui.chunk_all', lang): None
        }
        selected_chunk = st.selectbox(t('webui.filter_content_type', lang), options=list(chunk_options.keys()))
        chunk_type_filter = chunk_options[selected_chunk]

        # Tag filter
        available_tags = get_available_tags(service)
        if available_tags:
            selected_tags = st.multiselect(
                f"🏷️ {t('label.tags', lang)}",
                options=available_tags,
                default=[],
                help=t('webui.help_tags', lang)
            )
            tag_filter = selected_tags if selected_tags else None
        else:
            tag_filter = None

        # Book filter
        indexed_books = get_indexed_books_list(service)
        if indexed_books:
            book_options = [{'label': t('webui.filter_all_books', lang), 'id': None}]
            for book in indexed_books:
                title = (book.get('title') or t('webui.unknown', lang))[:50]
                author = book.get('author', '')[:20]
                book_id = book.get('book_id', '')
                label = f"{title}" + (f" ({author})" if author else "")
                book_options.append({'label': label, 'id': book_id})

            selected_book_idx = st.selectbox(
                t('webui.search_in_book', lang),
                options=range(len(book_options)),
                format_func=lambda i: book_options[i]['label'],
                index=0
            )
            book_id_filter = book_options[selected_book_idx]['id']
        else:
            book_id_filter = None

        st.divider()

        # Advanced options
        with st.expander(t('webui.advanced', lang)):
            exact_phrase = st.checkbox(
                t('webui.exact_phrase', lang),
                value=False,
                help=t('webui.help_exact_phrase', lang)
            )
            show_expanded_context = st.checkbox(
                t('webui.expanded_context', lang),
                value=False,
                help=t('webui.help_expanded_context', lang)
            )

        st.divider()

        # Database info
        with st.expander(t('webui.database_details', lang)):
            st.json({
                t('webui.json_books', lang): stats.get('total_books', 0),
                t('webui.json_chunks', lang): stats.get('total_chunks', 0),
                t('webui.json_avg_chunks', lang): round(stats.get('avg_chunks_per_book', 0), 1),
                t('webui.json_formats', lang): stats.get('file_types', {}),
                t('webui.json_languages', lang): stats.get('languages', {})
            })

    # Search tab (rendered first to ensure it's always available)
    with tab_search:
        # Search input
        query = st.text_input(
            t('webui.search_input', lang),
            placeholder=t('webui.search_placeholder', lang),
            key="search_query"
        )

        # Search button
        col1, col2, col3 = st.columns([1, 1, 4])
        with col1:
            search_clicked = st.button(t('webui.button_search', lang), type="primary", use_container_width=True)
        with col2:
            if st.button(t('webui.button_clear', lang), use_container_width=True):
                st.session_state.search_query = ""
                st.rerun()

        # Execute search
        if query and search_clicked:
            query_terms = query.split()

            # Build filter description for display
            active_filters = []
            if tag_filter:
                active_filters.append(f"{t('label.tags', lang)}: {', '.join(tag_filter)}")
            if book_id_filter:
                active_filters.append(f"{t('webui.filter_book', lang)}: {book_options[selected_book_idx]['label']}")
            if language_filter:
                active_filters.append(f"{t('label.language', lang)}: {language_filter}")
            if exact_phrase:
                active_filters.append(t('webui.exact_phrase', lang))

            filter_msg = (f" ({t('label.filter', lang)}: {'; '.join(active_filters)})"
                          if active_filters else "")

            spinner_msg = t('webui.spinner_searching', lang).format(
                n=f"{stats.get('total_chunks', 0):,}", filter=filter_msg)
            with st.spinner(spinner_msg):
                try:
                    results = service.search(
                        query=query,
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
                        st.error(t('webui.error_fts_missing', lang))
                        st.info(t('webui.hint_fts_solution', lang))
                        st.info(t('webui.hint_fts_alternative', lang))
                    else:
                        st.error(t('webui.error_search', lang).format(error=e))
                    results = []

            # Results header
            if results:
                st.success(t('webui.results_found', lang).format(n=len(results), query=query))

                # Show active filters
                if active_filters:
                    st.caption(f"{t('label.filter', lang)}: {' | '.join(active_filters)}")

                # Export button
                col_export, col_spacer = st.columns([1, 5])
                with col_export:
                    export_md = generate_markdown_export(results, query, active_filters, lang=lang)
                    st.download_button(
                        label=t('webui.button_export', lang),
                        data=export_md,
                        file_name=f"archilles_search_{query[:20].replace(' ', '_')}.md",
                        mime="text/markdown",
                        help=t('webui.help_export', lang)
                    )

                st.divider()

                # Results
                for i, result in enumerate(results, 1):
                    render_result(result, i, query_terms,
                                  show_expanded_context=show_expanded_context,
                                  service=service, lang=lang)
            else:
                st.warning(t('results.no_results', lang))
                st.info(t('webui.hint_try_other', lang))

        elif query and not search_clicked:
            st.info(t('webui.hint_press_search', lang))

    # Books tab
    with tab_books:
        render_books_tab(service, stats, lang=lang)

    # Footer
    st.divider()
    st.caption("ARCHILLES - Advanced Research & Citation Helper for Intelligent Literature & Library Exploration System")


if __name__ == "__main__":
    main()
