"""EPUB text extractor."""

import logging
import re
import zipfile
from pathlib import Path
from typing import List, Dict, Any, Optional

try:
    import ebooklib
    from ebooklib import epub
    from bs4 import BeautifulSoup
    EBOOKLIB_AVAILABLE = True
except ImportError:
    EBOOKLIB_AVAILABLE = False

from collections import defaultdict

from scriptor.reflow.regions import APPARATUS, region_of_heading
from scriptor.structure import Tree, region_for_epub_type

from src.archilles.constants import SectionType
from src.archilles.text_match import contains_keyword
from .base import BaseExtractor
from .models import ExtractedText, ChunkMetadata
from .exceptions import EPUBExtractionError
from .scriptor_extractor import region_of_title, region_to_section_type

logger = logging.getLogger(__name__)

# Compiled patterns for section number extraction
_SECTION_NUM_START = re.compile(r'^(\d+(?:\.\d+)*)\s+')
_SECTION_NUM_LABEL = re.compile(r'(?:Chapter|Section)\s+(\d+(?:\.\d+)*)', re.IGNORECASE)
# Marks the place of a nav anchor in the stream of strings (_split_html_by_anchors).
_SENTINEL_OPEN, _SENTINEL_CLOSE = chr(0xE000), chr(0xE001)  # private use, never in a book
_SENTINEL_RE = re.compile(re.escape(_SENTINEL_OPEN) + r"(\d+)" + re.escape(_SENTINEL_CLOSE))

# A title is classified by Scriptor's region vocabulary (region_of_title), the
# same on every path (outline B7, absorbing seam step S7): the whole title
# must name the region, so "Literatur und Mehrsprachigkeit" stays a chapter.
#
# Filename conventions for sections that carry no heading and no TOC entry.
# Deliberately narrow and English-only: these are EPUB packaging conventions
# produced by conversion tools, not prose titles, so the multilingual TOC
# vocabulary above does not apply. Only closed compounds are listed —
# 'title page' as two words would swallow 'chapter-title-page-3.html'.
# 'index' is deliberately absent: in EPUB filenames it means the book's
# index about as often as it means the converter's source document, and a
# sampled check found `index_split_*.html` files carrying ordinary prose.
# Hiding main content is worse than leaving an index visible, and real
# indexes are usually caught by their TOC title anyway. 'appendix' is absent
# for the reason an appendix is not apparatus (user decision, 2026-09-23).
_FILENAME_BACK_MATTER = frozenset({
    'note', 'notes', 'footnote', 'footnotes',
    'endnote', 'endnotes', 'bibliography', 'biblio', 'references',
    'glossary', 'colophon',
})
_FILENAME_FRONT_MATTER = frozenset({
    'cover', 'titlepage', 'halftitle', 'frontmatter',
    'toc', 'copyright', 'imprint', 'dedication',
})
_FILENAME_PARATEXT = _FILENAME_BACK_MATTER | _FILENAME_FRONT_MATTER


# Elements that end a paragraph. Everything else -- span, i, em, a, small caps,
# a drop cap -- is inline: its text belongs to the words around it. Joining
# every string of the tree with a paragraph break instead cut "T<span>HERE"
# into "T" and "HERE" and made each italic phrase a paragraph of its own
# (Berlinski, Human Nature [3084]).
_BLOCK_TAGS = frozenset({
    'address', 'article', 'aside', 'blockquote', 'body', 'br', 'caption', 'dd',
    'details', 'div', 'dl', 'dt', 'figcaption', 'figure', 'footer', 'h1', 'h2',
    'h3', 'h4', 'h5', 'h6', 'header', 'hgroup', 'hr', 'html', 'li', 'main', 'nav',
    'ol', 'p', 'pre', 'section', 'summary', 'table', 'tbody', 'td', 'tfoot', 'th',
    'thead', 'tr', 'ul',
})


def _block_of(string) -> Any:
    """The nearest block element around a string of the tree."""
    el = string.parent
    while el is not None and getattr(el, 'name', None) not in _BLOCK_TAGS:
        el = el.parent
    return el


def _blocks(root, sentinel_re: Optional['re.Pattern'] = None) -> List[tuple]:
    """The paragraphs of an element: ``[(text, [(sentinel id, offset)]), ...]``.

    Consecutive strings under the same block element are one paragraph,
    joined without a separator (the markup between them carries its own
    spaces) and with runs of whitespace collapsed. A ``<br>`` ends the
    paragraph it stands in. Strings matching ``sentinel_re`` are taken out of
    the text and reported with the paragraph they stood in, so that a split
    can fall on its beginning; ``offset`` is how much of the paragraph's
    text came before the sentinel (0 at its start; more for a page break
    mid-paragraph).
    """
    from bs4 import (Comment, Declaration, Doctype, NavigableString,
                     ProcessingInstruction, Tag)
    skipped = (Comment, Declaration, Doctype, ProcessingInstruction)

    out: List[tuple] = []
    parts: List[str] = []
    marks: List[int] = []
    current = None

    def flush() -> None:
        text = ' '.join(''.join(parts).split())
        if text or marks:
            out.append((text, list(marks)))
        parts.clear()
        marks.clear()

    for node in root.descendants:
        if isinstance(node, Tag):
            if node.name == 'br':
                flush()
                current = None
            continue
        if not isinstance(node, NavigableString) or isinstance(node, skipped):
            continue
        block = _block_of(node)
        if block is not current:
            flush()
            current = block
        hit = sentinel_re.fullmatch(str(node)) if sentinel_re else None
        if hit:
            marks.append((int(hit.group(1)), len(' '.join(''.join(parts).split()))))
        else:
            parts.append(str(node))
    flush()
    return out


# Marks the place of a page-list target (private use, apart from the nav ones).
_PAGE_OPEN, _PAGE_CLOSE = chr(0xE002), chr(0xE003)
_PAGE_SENTINEL_RE = re.compile(re.escape(_PAGE_OPEN) + r"(\d+)" + re.escape(_PAGE_CLOSE))

# A page-list label as the reader sees it: "[S. 5]", "p. xiv", "Seite 12".
# The prefix is the reader's language, not the page (Befund Gliederung §6.1).
_LABEL_PREFIX = re.compile(
    r"^\[?\s*(?:s\.|seite|p\.|pp\.|page|pag\.|pág\.|bl\.)?\s*", re.IGNORECASE)
# What is read as a label at all; anything else is not guessed.
_LABEL_OK = re.compile(r"^(?:\d{1,4}[a-z]?|[ivxlcdm]{1,8})$", re.IGNORECASE)


def _page_label(text: str) -> Optional[str]:
    """The printed page a page-list entry names, or None if it names none."""
    label = _LABEL_PREFIX.sub('', ' '.join((text or '').split())).rstrip('] ').strip()
    return label if _LABEL_OK.match(label) else None


def _page_targets(book) -> Dict[str, List[tuple]]:
    """``file -> [(anchor or None, label), ...]`` from the package's page list.

    EPUB 3 declares it as ``<nav epub:type="page-list">``, EPUB 2 as the
    NCX ``pageList``; hrefs are resolved against the document that holds
    them, so the keys are item names. Entries whose label is not a page are
    dropped rather than guessed.
    """
    import posixpath

    targets: Dict[str, List[tuple]] = defaultdict(list)
    for item in book.get_items():
        name = item.get_name() or ''
        try:
            content = item.get_content()
        except Exception:  # noqa: BLE001
            continue
        if not content or (b'page-list' not in content and b'pageList' not in content
                           and b'pagelist' not in content.lower()):
            continue
        soup = BeautifulSoup(content, 'html.parser')
        pairs = []
        for nav in soup.find_all('nav'):
            if 'page-list' in (nav.get('epub:type') or '').split():
                pairs += [(a.get_text(), a.get('href')) for a in nav.find_all('a')]
        for target in soup.find_all('pagetarget'):
            text = target.find('text')
            content_el = target.find('content')
            pairs.append((text.get_text() if text else target.get('value', ''),
                          content_el.get('src') if content_el else None))
        base = posixpath.dirname(name)
        for text, href in pairs:
            label = _page_label(text)
            if not href or label is None:
                continue
            file, _, anchor = href.partition('#')
            path = posixpath.normpath(posixpath.join(base, file)) if file else name
            targets[path].append((anchor or None, label))
        if targets:
            break
    return targets


def _paragraph_pages(soup, targets: List[tuple], carry: Optional[str]) -> tuple:
    """The printed page at the start of each paragraph of a file.

    Returns ``(pages, carry)``: per paragraph of ``_block_text`` a pair
    ``(start, breaks)`` -- the page its first word stands on, and the page
    breaks inside it as ``(offset, label)`` -- and the label the file ends
    on. A chunk carries the page of its first character, and a chunk the
    chunker cut out of a long paragraph finds it among the breaks.
    """
    from bs4 import NavigableString

    # A file whose first page lies before the page the reading is on is not
    # its continuation -- a notes file gathered at the end of the book
    # (Steuer [7237]: after the index on 1625, notes on 1021). What precedes
    # its first break has no page anyone stated, and none is guessed.
    first = targets[0][1] if targets else None
    if (first and carry and first.isdigit() and carry.isdigit()
            and int(first) < int(carry)):
        carry = None

    sentinels, labels = [], []
    for anchor, label in targets:
        if anchor is None:
            carry = label           # the target is the file itself
            continue
        el = soup.find(id=anchor)
        if el is None:
            continue
        sentinel = NavigableString(f"{_PAGE_OPEN}{len(labels)}{_PAGE_CLOSE}")
        el.insert(0, sentinel)
        sentinels.append(sentinel)
        labels.append(label)
    pages: List[tuple] = []
    pending: Optional[str] = None   # a break standing in an empty block
    for text, marks in _blocks(soup, _PAGE_SENTINEL_RE):
        at_start = [labels[k] for k, offset in marks if offset == 0]
        inside = [(offset, labels[k]) for k, offset in marks if offset > 0]
        if not text:
            if marks:
                pending = labels[marks[-1][0]]
            continue
        start = at_start[-1] if at_start else (pending or carry)
        pending = None
        pages.append((start, inside))
        carry = inside[-1][1] if inside else start
    for sentinel in sentinels:
        sentinel.extract()
    if pending:
        carry = pending
    return pages, carry


def _block_text(root) -> str:
    """The text of an element, a paragraph per block element."""
    return '\n\n'.join(text for text, _ in _blocks(root) if text)


def _normalize_item_name(filename: str) -> str:
    """Reduce an EPUB item name to bare words for keyword matching.

    ``Text/index_split_033.html`` becomes ``index split``. Digits and
    separators go because they carry the sequence, not the meaning, and
    word-boundary matching would otherwise fail on ``index_split``.
    """
    if not filename:
        return ""
    stem = filename.rsplit('/', 1)[-1].rsplit('\\', 1)[-1]
    stem = re.sub(r'\.(x?html?|ncx|xml)$', '', stem, flags=re.IGNORECASE)
    return re.sub(r'[\d_\-.]+', ' ', stem).strip().lower()


class EPUBExtractor(BaseExtractor):
    """
    Extract text from EPUB files.

    Handles:
    - EPUB 2 and EPUB 3
    - Table of contents extraction
    - Chapter/section preservation
    - Metadata extraction (author, title, etc.)
    """

    SUPPORTED_EXTENSIONS = {'.epub'}

    def supports(self, file_path: Path) -> bool:
        """Check if file is EPUB."""
        return file_path.suffix.lower() in self.SUPPORTED_EXTENSIONS

    def extract(self, file_path: Path) -> ExtractedText:
        """
        Extract text from EPUB file.

        Args:
            file_path: Path to EPUB file

        Returns:
            ExtractedText object

        Raises:
            EPUBExtractionError: If extraction fails
        """
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        if not EBOOKLIB_AVAILABLE:
            return self._extract_manual(file_path)

        try:
            return self._extract_with_ebooklib(file_path)
        except Exception as e:
            try:
                return self._extract_manual(file_path)
            except Exception as e2:
                raise EPUBExtractionError(
                    f"EPUB extraction failed: {e}\nFallback also failed: {e2}"
                ) from e

    def _extract_with_ebooklib(self, file_path: Path) -> ExtractedText:
        """Extract using ebooklib library."""
        book = epub.read_epub(str(file_path))

        title = self._get_dc_metadata(book, 'title')
        author = self._get_dc_metadata(book, 'creator')
        language = self._get_dc_metadata(book, 'language')

        toc = self._extract_toc_ebooklib(book)
        # The nav as a tree (Gliederung B7): every entry a node, depth its
        # nesting, the chapter level declared by Scriptor's rule rather than
        # taken to be the top.
        tree = Tree.from_headings(
            [(e.get('level', 1), e.get('title') or '') for e in toc],
            region_of=region_of_heading) if toc else None
        level = tree.chapter_level() if tree else None
        by_file: Dict[str, List[tuple]] = defaultdict(list)  # file -> [(node, anchor)]
        for i, entry in enumerate(toc):
            href = entry.get('href')
            if href:
                base, _, anchor = href.partition('#')
                by_file[base].append((i, anchor or None))
        node_class: Dict[int, tuple] = {}   # node -> (section_type, region)
        printed: Dict[int, str] = {}        # node -> the <h1> its own file prints

        chapters_text = []
        chapters_metadata = []

        _sub_heading_re = re.compile(r'^h[2-6]$')

        doc_items = self._reading_order(book)
        use_filenames = self._filename_signals_usable(
            [i.get_name() for i in doc_items]
        )
        running: Optional[int] = None       # the node the reading is in
        # The print edition's pages, where the package declares them.
        page_targets = _page_targets(book)
        page_carry: Optional[str] = None    # the page the reading is on

        for item in doc_items:
            content = item.get_content()

            # Parse HTML once — extract text, h1, and sub-headings
            soup = BeautifulSoup(content, 'html.parser')
            for el in soup(['script', 'style']):
                el.decompose()

            h1 = soup.find('h1')
            chapter_title = (' '.join(_block_text(h1).split()) or None) if h1 else None

            item_name = item.get_name()
            file_pages: Optional[List[Optional[str]]] = None
            if page_targets:
                file_pages, page_carry = _paragraph_pages(
                    soup, page_targets.get(item_name, []), page_carry)

            text = self._clean_text(_block_text(soup))
            if not text.strip():
                continue
            file_paras = text.split('\n\n')
            para_at = 0                     # where the next section's text begins
            entries = by_file.get(item_name, [])
            anchored = [(i, a) for i, a in entries if a and soup.find(id=a) is not None]
            at_start = [i for i, a in entries if (i, a) not in anchored]

            # The file's own classification: its heading, its filename, the
            # epub:type it opens with. Untitled items fall back to the
            # filename -- index and note files routinely ship without a
            # heading or TOC entry.
            start = h1 or soup.find('section') or soup.find('body')
            start_types = self._epub_types_at(start)
            file_title = chapter_title or (toc[at_start[-1]]['title'] if at_start else '')
            file_class = self._classify(
                file_title, item_name if use_filenames else '', start_types)

            # The node the file opens in: the deepest entry pointing at the
            # file itself; else, for a file with no entry and no heading of
            # its own -- a converter's continuation of the previous file --
            # the node the reading is in. A file with a heading of its own
            # and no entry is a section the nav does not list.
            if at_start:
                head_node = at_start[-1]
            elif chapter_title is None or anchored:
                head_node = running
            else:
                head_node = None

            if anchored:
                sections = self._split_html_by_anchors(
                    soup, [{'title': toc[i]['title'], 'anchor': a, 'node': i}
                           for i, a in anchored])
            else:
                sub_headings = [
                    ' '.join(_block_text(h).split())
                    for h in soup.find_all(_sub_heading_re)
                ]
                sections = self._split_text_by_headings(text, sub_headings)

            for section in sections:
                if not section['text'].strip():
                    continue
                node = section.get('node', head_node)
                heading = section['heading'] if section.get('node') is None else None

                if node is not None and tree is not None:
                    epub_types = section.get('epub_types') or start_types
                    base_type, base_region = self._node_class(
                        node, toc, tree, node_class, epub_types)
                    names_own = (file_class[1] is not None
                                 or file_class[0] != SectionType.MAIN_CONTENT)
                    if node == head_node and names_own and (
                            not at_start or base_region is None):
                        # The file's own evidence -- its heading, epub:type
                        # or filename -- where the node's title names nothing,
                        # and always in a continuation the nav does not list.
                        base_type, base_region = file_class
                    fields = tree.fields_of(node, level)
                    if chapter_title and node in at_start:
                        printed[node] = chapter_title
                    chain = [node] + tree.ancestors(node)
                    chapter_node = next(
                        (j for j in chain if tree.nodes[j].depth <= (level or 1)), node)
                    # The printed heading of the chapter outranks its nav
                    # title (B1), in every file the chapter runs through.
                    chapter = (printed.get(chapter_node) or fields.chapter
                               or toc[node]['title'])
                    section_title = heading or fields.section_title or None
                    section_number = fields.section or None
                else:
                    base_type, base_region = file_class
                    chapter = file_title or item_name
                    section_title = heading
                    section_number = None

                # A heading inside the node may name a region of its own --
                # a chapter's "Notes"; inside an apparatus only another
                # apparatus (under "Anmerkungen" a "Vorwort" holds the notes
                # to the preface).
                section_type, region = base_type, base_region
                if heading:
                    sub_type, sub_region = self._classify(heading)
                    if sub_region is not None and (
                            base_region not in APPARATUS or sub_region in APPARATUS):
                        section_type, region = sub_type, sub_region

                # The printed page of each paragraph: the section's paragraphs
                # are the file's, in order, so they are found by walking on.
                para_pages = None
                if file_pages is not None and len(file_pages) == len(file_paras):
                    para_pages = []
                    for para in section['text'].split('\n\n'):
                        k = para_at
                        while k < len(file_paras) and file_paras[k] != para:
                            k += 1
                        if k < len(file_paras):
                            para_pages.append(file_pages[k])
                            para_at = k + 1
                        else:
                            para_pages.append(None)

                chapters_text.append(section['text'])
                chapters_metadata.append({
                    'chapter': chapter,
                    'section': section_number,
                    'section_title': section_title,
                    'section_type': section_type,
                    'region': region,
                    'file': item_name,
                    'para_pages': para_pages,
                })
                if node is not None:
                    running = node

        full_text = '\n\n---\n\n'.join(chapters_text)

        chunks = self._create_chunks_with_chapters(
            chapters_text, chapters_metadata, file_path, title, author
        )

        extraction_metadata = self._create_extraction_metadata(
            file_path=file_path,
            format_name='epub',
            extraction_time=0,
            total_chars=len(full_text),
            total_words=len(full_text.split()),
            total_chunks=len(chunks),
        )
        extraction_metadata.warnings.append("Extracted with ebooklib")
        if page_targets:
            # The edition the page list refers to, where the package names it
            # (Befund Gliederung §6.1: a log line, no column on this path).
            source = self._get_dc_metadata(book, 'source')
            extraction_metadata.warnings.append(
                f"Page list: {sum(len(v) for v in page_targets.values())} targets, "
                f"print edition {source or 'not named'} (label_source catalogue)")

        return ExtractedText(
            full_text=full_text,
            chunks=chunks,
            metadata=extraction_metadata,
            toc=toc,
        )

    def _extract_manual(self, file_path: Path) -> ExtractedText:
        """
        Fallback: Manual extraction by unzipping EPUB.

        EPUB is a ZIP file containing HTML/XHTML files.
        """
        chapters_text = []

        with zipfile.ZipFile(file_path, 'r') as zip_ref:
            html_files = [
                name for name in zip_ref.namelist()
                if name.endswith(('.html', '.xhtml', '.htm'))
                and not name.startswith('__MACOSX')
            ]

            for html_file in sorted(html_files):
                try:
                    text = self._extract_html_text(zip_ref.read(html_file))
                    if text.strip():
                        chapters_text.append(text)
                except Exception:
                    continue

        if not chapters_text:
            raise EPUBExtractionError("No readable content found in EPUB")

        full_text = '\n\n---\n\n'.join(chapters_text)

        base_metadata = ChunkMetadata(
            source_file=str(file_path),
            format='epub',
        )
        chunks = self._create_chunks(full_text, base_metadata)

        extraction_metadata = self._create_extraction_metadata(
            file_path=file_path,
            format_name='epub',
            extraction_time=0,
            total_chars=len(full_text),
            total_words=len(full_text.split()),
            total_chunks=len(chunks),
        )
        extraction_metadata.warnings.append("Extracted with manual ZIP method (fallback)")

        return ExtractedText(
            full_text=full_text,
            chunks=chunks,
            metadata=extraction_metadata,
        )

    def _extract_toc_ebooklib(self, book) -> List[Dict[str, Any]]:
        """
        Extract table of contents from EPUB.

        Returns list of TOC entries with:
        - title: Chapter/section title
        - level: Nesting level (1, 2, 3...)
        - section: Section number if present (e.g., "19.20")
        - href: Link to file in EPUB
        """
        toc = []

        def make_toc_entry(title: str, href: Optional[str], level: int) -> Dict[str, Any]:
            """Build a TOC entry dict, including section number if found."""
            entry = {'title': title, 'level': level, 'href': href}
            section_num = self._extract_section_number(title)
            if section_num:
                entry['section'] = section_num
            return entry

        def parse_toc_item(item, level=1, parent_section=''):
            if isinstance(item, tuple):
                section_obj = item[0]
                children = item[1] if len(item) > 1 else []

                title = section_obj.title if hasattr(section_obj, 'title') else str(section_obj)
                href = section_obj.href if hasattr(section_obj, 'href') else None

                entry = make_toc_entry(title, href, level)
                toc.append(entry)

                section_num = entry.get('section', parent_section)
                for child in children:
                    parse_toc_item(child, level + 1, section_num)

            elif isinstance(item, list):
                for sub_item in item:
                    parse_toc_item(sub_item, level, parent_section)

            elif hasattr(item, 'href') and hasattr(item, 'title'):
                # ebooklib Link object (child of a tuple section)
                title = item.title if item.title else str(item)
                href = item.href if item.href else None
                toc.append(make_toc_entry(title, href, level))

        try:
            toc_items = book.toc
            if not toc_items:
                return toc

            if isinstance(toc_items, list):
                for item in toc_items:
                    if hasattr(item, 'href') and hasattr(item, 'title'):
                        # Link object (most common format)
                        title = item.title if item.title else str(item)
                        href = item.href if item.href else None
                        toc.append(make_toc_entry(title, href, level=1))
                    elif isinstance(item, tuple):
                        parse_toc_item(item, 1, '')
            elif isinstance(toc_items, tuple):
                parse_toc_item(toc_items, 1, '')
        except Exception as e:
            logger.warning("TOC extraction failed: %s: %s", type(e).__name__, e)

        return toc

    @staticmethod
    def _get_dc_metadata(book, field: str) -> Optional[str]:
        """Extract a Dublin Core metadata field from an EPUB book."""
        values = book.get_metadata('DC', field)
        return values[0][0] if values else None

    @staticmethod
    def _extract_section_number(title: str) -> Optional[str]:
        """
        Extract section number from TOC title.

        Handles formats like:
        - "19.20 Land Warfare" -> "19.20"
        - "Chapter 3" -> "3"
        - "3.4.2 Tactics" -> "3.4.2"
        """
        match = _SECTION_NUM_START.match(title)
        if match:
            return match.group(1)

        match = _SECTION_NUM_LABEL.search(title)
        if match:
            return match.group(1)

        return None

    @staticmethod
    def _filename_signals_usable(item_names: List[str]) -> bool:
        """True when paratext filenames actually distinguish anything.

        Some conversion tools name every file after the source document, so a
        whole book arrives as ``index_split_000.html`` … ``index_split_412.html``.
        There the word describes the converter, not the section, and honouring
        it would file the entire book under back matter — measured against the
        live library, that was 45 books, one of them losing 1088 of 1090 chunks.

        Paratext is a demarcation: where no file lacks the marker, nothing is
        being demarcated, so the signal is discarded for that book.
        """
        if not item_names:
            return False
        return any(
            not contains_keyword(_normalize_item_name(name), _FILENAME_PARATEXT)
            for name in item_names
        )

    @staticmethod
    def _classify(title: str, filename: str = "",
                  epub_types: str = "") -> tuple[str, Optional[str]]:
        """``(section_type, region)`` of a section.

        Args:
            title: Chapter heading or TOC title.
            filename: EPUB item name, used only when there is no title and no
                ``epub:type`` — many EPUBs ship their index, notes and front
                matter without a heading or TOC entry, and the filename is
                then the only identifier left (``index_split_033.html``).
            epub_types: the ``epub:type`` of the element the section begins
                in. The publisher's own statement, so it outranks the title.

        The region is Scriptor's name (spec §4.4) and is stored beside the
        section type; a filename is no region, so it yields None there.
        """
        region = region_for_epub_type(epub_types) if epub_types else None
        if region is None:
            region = region_of_title(title)
        if region is not None:
            return region_to_section_type(region), region
        if title:
            # A readable heading outranks a packaging convention: a chapter
            # that merely lives in index_split_*.html is still a chapter.
            return SectionType.MAIN_CONTENT, None

        normalized = _normalize_item_name(filename)
        if contains_keyword(normalized, _FILENAME_FRONT_MATTER):
            return SectionType.FRONT_MATTER, None
        if contains_keyword(normalized, _FILENAME_BACK_MATTER):
            return SectionType.BACK_MATTER, None
        return SectionType.MAIN_CONTENT, None

    @classmethod
    def _node_class(cls, node: int, toc: List[Dict[str, Any]], tree: 'Tree',
                    cache: Dict[int, tuple], epub_types: str = '') -> tuple:
        """``(section_type, region)`` of a nav node.

        Its own title (and the ``epub:type`` where it begins) if they name a
        region; otherwise its parent's. Inside an apparatus a node may only
        name another apparatus -- the rule the sub-sections follow.
        """
        if node in cache:
            return cache[node]
        own = cls._classify(toc[node].get('title') or '', '', epub_types)
        ancestors = tree.ancestors(node)
        parent = cls._node_class(ancestors[0], toc, tree, cache) if ancestors else None
        if own[1] is not None and (parent is None or parent[1] not in APPARATUS
                                   or own[1] in APPARATUS):
            result = own
        elif parent is not None:
            result = parent
        else:
            result = own
        cache[node] = result
        return result

    @staticmethod
    def _reading_order(book) -> list:
        """The documents in spine order, then any the spine leaves out.

        The manifest lists files in whatever order the packager wrote them;
        a node that runs on into the next file needs the order they are read
        in. Documents outside the spine are kept, at the end, so that no
        text is lost.
        """
        docs = [i for i in book.get_items() if i.get_type() == ebooklib.ITEM_DOCUMENT]
        by_id = {i.get_id(): i for i in docs}
        ordered = []
        for entry in book.spine:
            idref = entry[0] if isinstance(entry, (tuple, list)) else entry
            item = by_id.pop(idref, None)
            if item is not None:
                ordered.append(item)
        return ordered + [i for i in docs if i.get_id() in by_id]

    @classmethod
    def _detect_section_type(cls, title: str, filename: str = "") -> str:
        """'front_matter', 'main_content' or 'back_matter' — see ``_classify``."""
        return cls._classify(title, filename)[0]

    @staticmethod
    def _epub_types_at(el) -> str:
        """The ``epub:type`` of an element or the nearest section around it.

        A publisher marks the partition on ``<body>`` or on a ``<section>``;
        the element a heading or an anchor stands on rarely carries it.
        """
        while el is not None and getattr(el, 'name', None):
            types = el.get('epub:type') if hasattr(el, 'get') else None
            if types:
                return types
            if el.name in ('body', 'html'):
                break
            el = el.parent
        return ''

    @staticmethod
    def _split_text_by_headings(
        text: str, heading_texts: List[str]
    ) -> List[Dict[str, Any]]:
        """Split extracted text into sections at sub-heading boundaries.

        Args:
            text: Full extracted text from one HTML item.
            heading_texts: Texts of h2-h6 headings found in the HTML.

        Returns:
            List of dicts with 'heading' (str or None) and 'text' (str).
            The intro before the first heading gets heading=None.
        """
        if not heading_texts:
            return [{'heading': None, 'text': text}]

        normalized_headings = {' '.join(h.split()) for h in heading_texts}
        paragraphs = text.split('\n\n')
        sections: List[Dict[str, Any]] = []
        current_heading: Optional[str] = None
        current_paras: List[str] = []

        for para in paragraphs:
            normalized = ' '.join(para.strip().split())
            if normalized in normalized_headings:
                if current_paras:
                    sections.append({
                        'heading': current_heading,
                        'text': '\n\n'.join(current_paras),
                    })
                current_heading = para.strip()
                current_paras = [para]  # include heading in section text
            else:
                current_paras.append(para)

        if current_paras:
            sections.append({
                'heading': current_heading,
                'text': '\n\n'.join(current_paras),
            })

        return sections

    def _split_html_by_anchors(
        self,
        soup: 'BeautifulSoup',
        sub_sections: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Split parsed HTML into sections using TOC anchor IDs.

        Each sub-section dict must have ``'title'`` and ``'anchor'`` keys.
        The anchor is looked up as an ``id`` attribute in the HTML tree.
        Text between consecutive anchors forms one section.

        Returns:
            List of ``{'heading': str|None, 'text': str}`` dicts.
        """
        # Collect (element, title) pairs for anchors that exist in the HTML
        markers: List[tuple] = []
        for sub in sub_sections:
            anchor = sub.get('anchor')
            if not anchor:
                continue
            el = soup.find(id=anchor)
            if el:
                markers.append((el, sub))

        if not markers:
            text = self._clean_text(_block_text(soup))
            return [{'heading': None, 'text': text}]

        # Place each anchor where it stands in the document, not by its words.
        # A nav sub-entry often targets an empty <a id="sec1"/>: its text is
        # '', which a search "finds" at every offset, so every split fell on
        # one point and the whole file went to the last sub-section (Le Goff
        # [4031]). And a heading's words may stand earlier in the prose. A
        # sentinel string put into each anchor element marks its place in the
        # stream of strings; the sentinels are taken out again afterwards.
        from bs4 import NavigableString

        sentinels = []
        for k, (el, _sub) in enumerate(markers):
            sentinel = NavigableString(f"{_SENTINEL_OPEN}{k}{_SENTINEL_CLOSE}")
            el.insert(0, sentinel)
            sentinels.append(sentinel)
        body = soup.find('body') or soup
        parts: List[str] = []
        length = 0
        split_points: List[tuple] = []  # (char_offset, title, epub:type)
        # A split falls on the beginning of the paragraph its anchor stands
        # in: an anchor sits at the head of its heading, never mid-sentence.
        for text, marks in _blocks(body, _SENTINEL_RE):
            start = length + 2 if parts and text else length
            for k, _offset in marks:
                el, sub = markers[k]
                split_points.append((start, sub, self._epub_types_at(el)))
            if not text:
                continue
            if parts:
                length += 2  # the '\n\n' that joins the paragraphs
            parts.append(text)
            length += len(text)
        for sentinel in sentinels:
            sentinel.extract()
        full_text = '\n\n'.join(parts)
        split_points.sort(key=lambda point: point[0])

        if not split_points:
            return [{'heading': None, 'text': self._clean_text(full_text)}]

        sections: List[Dict[str, Any]] = []

        # Intro text before the first marker
        intro = full_text[:split_points[0][0]].strip()
        if intro:
            sections.append({'heading': None, 'text': self._clean_text(intro)})

        # Sections between markers
        for i, (offset, sub, epub_types) in enumerate(split_points):
            end = split_points[i + 1][0] if i + 1 < len(split_points) else len(full_text)
            section_text = full_text[offset:end].strip()
            if section_text:
                section = {
                    'heading': sub['title'],
                    'text': self._clean_text(section_text),
                    'epub_types': epub_types,
                }
                if sub.get('node') is not None:
                    section['node'] = sub['node']
                sections.append(section)

        return sections

    def _extract_html_text(self, content: bytes) -> str:
        """Extract and clean text from HTML/XHTML content."""
        soup = BeautifulSoup(content, 'html.parser')
        for element in soup(['script', 'style']):
            element.decompose()
        return self._clean_text(_block_text(soup))

    def _create_chunks_with_chapters(
        self,
        chapters_text: List[str],
        chapters_metadata: List[Dict],
        file_path: Path,
        title: str,
        author: str
    ) -> List[Dict[str, Any]]:
        """Create chunks with chapter and section information."""
        chunks = []

        for chapter_text, chapter_meta in zip(chapters_text, chapters_metadata):
            base_metadata = ChunkMetadata(
                source_file=str(file_path),
                format='epub',
                title=title,
                author=author,
                chapter=chapter_meta.get('chapter'),
                section=chapter_meta.get('section'),
                section_title=chapter_meta.get('section_title'),
                section_type=chapter_meta.get('section_type', SectionType.MAIN_CONTENT),
                region=chapter_meta.get('region'),
            )

            chapter_chunks = self._create_chunks(chapter_text, base_metadata)
            para_pages = chapter_meta.get('para_pages')
            if para_pages:
                self._assign_pages(chapter_chunks, chapter_text.split('\n\n'), para_pages)
            chunks.extend(chapter_chunks)

        return chunks

    @staticmethod
    def _assign_pages(chunks: List[Dict[str, Any]], paras: List[str],
                      pages: List[Optional[str]]) -> None:
        """Give each chunk the printed page of its first paragraph.

        The page comes from the package's page list: stated, not seen on a
        page, so ``label_source`` is ``catalogue`` (spec §6.3, Befund
        Gliederung §6.1) and ``page`` stays 0 -- an EPUB has no physical
        page. The chunk's first paragraph is found by its opening words; a
        paragraph the chunker cut is found by the words of its piece.
        """
        k = 0
        for chunk in chunks:
            first = chunk['text'].split('\n\n', 1)[0].strip()[:80]
            j = k
            while j < len(paras) and first not in paras[j]:
                j += 1
            if j == len(paras) or pages[j] is None:
                continue
            k = j
            label, breaks = pages[j]
            at = paras[j].find(first)
            for offset, inside in breaks:
                if offset <= at:
                    label = inside
            if label:
                chunk['metadata']['page_label'] = label
                chunk['metadata']['label_source'] = 'catalogue'
                chunk['metadata']['page'] = 0

    @staticmethod
    def _clean_text(text: str) -> str:
        """Clean extracted text by collapsing whitespace and blank lines."""
        lines = [line.strip() for line in text.split('\n')]
        lines = [line for line in lines if line]
        return '\n\n'.join(lines)
