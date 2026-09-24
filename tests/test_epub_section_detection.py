"""Tests for EPUB sub-section detection via heading splitting."""

import pytest

from src.archilles.constants import SectionType
from src.extractors.epub_extractor import EPUBExtractor


class TestSplitHtmlAt:
    """Sections begin where their element stands (Gliederung B7): a heading
    or a nav anchor, found by its place in the tree, never by its words."""

    @staticmethod
    def _split(html):
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(f"<html><body>{html}</body></html>", "html.parser")
        markers = [(h, ' '.join(h.get_text().split()), None)
                   for h in soup.find_all(['h2', 'h3'])]
        return EPUBExtractor()._split_html_at(soup, markers)

    def test_no_markers_returns_single_section(self):
        result = self._split("<p>Paragraph one.</p><p>Paragraph two.</p>")
        assert len(result) == 1
        assert result[0]['heading'] is None
        assert result[0]['text'] == "Paragraph one.\n\nParagraph two."

    def test_heading_opens_its_section_and_stays_in_its_text(self):
        result = self._split("<p>Intro text here.</p><h2>SECTION ONE</h2><p>Content follows.</p>")
        assert [r['heading'] for r in result] == [None, "SECTION ONE"]
        assert result[1]['text'].startswith("SECTION ONE")

    def test_no_intro_before_first_heading(self):
        result = self._split("<h2>THE HEADING</h2><p>Content after heading.</p>")
        assert [r['heading'] for r in result] == ["THE HEADING"]

    def test_a_heading_s_words_earlier_in_the_prose_do_not_split(self):
        result = self._split("<p>Of THE KNIGHTS HOSPITALLER more below.</p>"
                             "<h2>THE KNIGHTS HOSPITALLER</h2><p>Knight content.</p>")
        assert "more below" in result[0]['text']
        assert result[1]['text'].startswith("THE KNIGHTS HOSPITALLER\n\nKnight")

    def test_churton_style_chapter(self):
        """A Churton-style chapter with sub-sections."""
        result = self._split(
            "<p>Chapter Two</p>"
            "<h2>ST. JOHN'S MEN AND THE PASSION OF THE CORN</h2>"
            "<p>There were three men called John.</p>"
            "<p>Some more text about Masonry and history.</p>"
            "<h2>ST. JOHN THE BAPTIST AS LORD OF THE FEAST</h2>"
            "<p>We have established that St. John the Baptist was important.</p>"
            "<h2>THE KNIGHTS HOSPITALLER</h2><p>In 1023, eighteen years after destruction.</p>"
            "<h2>HERALD OF THE HARVEST</h2><p>Why had John the Baptist been chosen by the church.</p>")
        assert len(result) == 5  # intro + 4 sections
        assert result[0]['heading'] is None
        assert "Chapter Two" in result[0]['text']
        assert result[1]['heading'] == "ST. JOHN'S MEN AND THE PASSION OF THE CORN"
        assert "three men called John" in result[1]['text']
        assert result[4]['heading'] == "HERALD OF THE HARVEST"
        assert "chosen by the church" in result[4]['text']



class TestSectionTypeFromFilename:
    """Paratext must be recognised when the EPUB gives it no readable title.

    Many EPUBs carry no <h1> and no TOC entry for their index, notes or
    front matter. Those sections used to fall through to `main_content`,
    which put index entries and footnote apparatus into search results as
    if they were prose. The filename is the only identifier left, and it
    usually carries the convention (`index_split_033.html`,
    `Footnote_570.xhtml`).
    """

    detect = staticmethod(EPUBExtractor._detect_section_type)

    @pytest.mark.parametrize("filename", [
        "Footnote_570.xhtml",
        "part0012_footnote.html",
        "notes.xhtml",
        "OEBPS/endnotes.html",
        "bibliography.xhtml",
        "glossary.html",
    ])
    def test_untitled_back_matter_detected_from_filename(self, filename):
        assert self.detect("", filename) == SectionType.BACK_MATTER

    def test_an_appendix_file_stays_searchable(self):
        # An appendix is not apparatus (user decision, 2026-09-23).
        assert self.detect("", "Text/081_appendix-m.html") == SectionType.MAIN_CONTENT

    @pytest.mark.parametrize("filename", [
        "index_split_033.html",
        "Text/index_split_007.xhtml",
        "xhtml/index.html",
    ])
    def test_index_filenames_are_not_trusted(self, filename):
        """'index' names the converter's source as often as a real index.

        A sample of the live library found `index_split_*.html` files holding
        ordinary prose, so trusting the name hid main content. Real indexes
        still get caught by their TOC title.
        """
        assert self.detect("", filename) == SectionType.MAIN_CONTENT
        assert self.detect("Index", filename) == SectionType.BACK_MATTER

    @pytest.mark.parametrize("filename", [
        "cover.xhtml",
        "titlepage.xhtml",
        "OEBPS/toc.ncx.html",
        "copyright.html",
    ])
    def test_untitled_front_matter_detected_from_filename(self, filename):
        assert self.detect("", filename) == SectionType.FRONT_MATTER

    @pytest.mark.parametrize("filename", [
        "chapter_005.html",
        "part0003_split_012.html",
        "Text/84A8F77B79B542889A3D37D0A416DF59.xhtml",
        "ch12.xhtml",
        "content_0021.html",
        "text00007.html",
        "chapter-title-page-3.html",
    ])
    def test_ordinary_chapters_stay_main_content(self, filename):
        assert self.detect("", filename) == SectionType.MAIN_CONTENT

    def test_readable_title_wins_over_filename(self):
        # A real heading is stronger evidence than a filename convention:
        # a chapter that merely lives in index_split_*.html is still a chapter.
        assert (self.detect("Chapter 7: The Origin of Species", "index_split_033.html")
                == SectionType.MAIN_CONTENT)

    def test_title_still_detected_without_filename(self):
        assert self.detect("Bibliography") == SectionType.BACK_MATTER
        assert self.detect("Contents") == SectionType.FRONT_MATTER
        # A preface is named but searchable (user decision, 2026-09-10).
        assert self.detect("Preface") == SectionType.MAIN_CONTENT

    def test_no_title_and_no_filename_is_main_content(self):
        assert self.detect("", "") == SectionType.MAIN_CONTENT


class TestFilenameSignalsUsable:
    """A filename marker means nothing when every file carries it.

    Conversion tools routinely name every document after the source file
    (`index_split_000.html` … `index_split_412.html`). Taking that literally
    filed whole books under back matter — one lost 1088 of its 1090 chunks.
    """

    usable = staticmethod(EPUBExtractor._filename_signals_usable)

    def test_mixed_names_keep_the_signal(self):
        assert self.usable([
            "part0001_split_000.html",
            "part0002_split_000.html",
            "index_split_033.html",
        ]) is True

    def test_uniform_paratext_names_discard_the_signal(self):
        # Every file carries the same marker: it describes the converter's
        # naming scheme, not a section boundary.
        assert self.usable(
            [f"notes_{i:03d}.html" for i in range(50)]
        ) is False

    def test_footnote_heavy_book_keeps_the_signal(self):
        # 570 footnote files alongside real chapters is a legitimate book,
        # not a naming convention — the chapters are what save it.
        names = [f"part0012_footnote_{i}.xhtml" for i in range(570)]
        names += ["chapter_001.xhtml", "chapter_002.xhtml"]
        assert self.usable(names) is True

    def test_empty_book_has_no_signal(self):
        assert self.usable([]) is False
