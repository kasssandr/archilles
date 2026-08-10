"""Tests for EPUB sub-section detection via heading splitting."""

import pytest

from src.archilles.constants import SectionType
from src.extractors.epub_extractor import EPUBExtractor


class TestSplitTextByHeadings:
    split = staticmethod(EPUBExtractor._split_text_by_headings)

    def test_no_headings_returns_single_section(self):
        text = "Paragraph one.\n\nParagraph two.\n\nParagraph three."
        result = self.split(text, [])
        assert len(result) == 1
        assert result[0]['heading'] is None
        assert result[0]['text'] == text

    def test_single_heading_splits_into_two(self):
        text = "Intro text here.\n\nSECTION ONE\n\nSection content follows."
        result = self.split(text, ["SECTION ONE"])
        assert len(result) == 2
        assert result[0]['heading'] is None
        assert "Intro text" in result[0]['text']
        assert result[1]['heading'] == "SECTION ONE"
        assert "Section content" in result[1]['text']

    def test_heading_included_in_section_text(self):
        text = "Intro.\n\nMY HEADING\n\nContent after heading."
        result = self.split(text, ["MY HEADING"])
        assert result[1]['text'].startswith("MY HEADING")

    def test_multiple_headings(self):
        text = (
            "Intro paragraph.\n\n"
            "FIRST SECTION\n\nFirst content.\n\n"
            "SECOND SECTION\n\nSecond content."
        )
        result = self.split(text, ["FIRST SECTION", "SECOND SECTION"])
        assert len(result) == 3
        assert result[0]['heading'] is None
        assert result[1]['heading'] == "FIRST SECTION"
        assert result[2]['heading'] == "SECOND SECTION"
        assert "First content" in result[1]['text']
        assert "Second content" in result[2]['text']

    def test_no_intro_before_first_heading(self):
        text = "THE HEADING\n\nContent after heading."
        result = self.split(text, ["THE HEADING"])
        assert len(result) == 1
        assert result[0]['heading'] == "THE HEADING"

    def test_whitespace_normalization(self):
        """Heading with extra whitespace in text should still match."""
        text = "Intro.\n\nTHE   KNIGHTS   HOSPITALLER\n\nKnight content."
        result = self.split(text, ["THE KNIGHTS HOSPITALLER"])
        assert len(result) == 2
        assert result[1]['heading'] == "THE   KNIGHTS   HOSPITALLER"

    def test_unmatched_heading_ignored(self):
        """Headings not found in text should not cause splits."""
        text = "Paragraph one.\n\nParagraph two."
        result = self.split(text, ["NONEXISTENT HEADING"])
        assert len(result) == 1
        assert result[0]['heading'] is None

    def test_churton_style_chapter(self):
        """Simulate a Churton-style chapter with sub-sections."""
        text = (
            "Chapter Two\n\n"
            "ST. JOHN'S MEN AND THE PASSION OF THE CORN\n\n"
            "There were three men called John.\n\n"
            "Some more text about Masonry and history.\n\n"
            "ST. JOHN THE BAPTIST AS LORD OF THE FEAST\n\n"
            "We have established that St. John the Baptist was important.\n\n"
            "THE KNIGHTS HOSPITALLER\n\n"
            "In 1023, eighteen years after destruction.\n\n"
            "HERALD OF THE HARVEST\n\n"
            "Why had John the Baptist been chosen by the church."
        )
        headings = [
            "ST. JOHN'S MEN AND THE PASSION OF THE CORN",
            "ST. JOHN THE BAPTIST AS LORD OF THE FEAST",
            "THE KNIGHTS HOSPITALLER",
            "HERALD OF THE HARVEST",
        ]
        result = self.split(text, headings)
        assert len(result) == 5  # intro + 4 sections
        assert result[0]['heading'] is None
        assert "Chapter Two" in result[0]['text']
        assert result[1]['heading'] == "ST. JOHN'S MEN AND THE PASSION OF THE CORN"
        assert "three men called John" in result[1]['text']
        assert result[4]['heading'] == "HERALD OF THE HARVEST"
        assert "chosen by the church" in result[4]['text']


class TestBuildTocMap:
    build = staticmethod(EPUBExtractor._build_toc_map)

    def test_first_entry_per_file_wins(self):
        """When multiple TOC entries point to the same file, keep the first."""
        toc = [
            {'title': 'Chapter 2', 'level': 1, 'href': 'text00007.html'},
            {'title': 'Sub-Section A', 'level': 2, 'href': 'text00007.html#sub_a'},
            {'title': 'Sub-Section B', 'level': 2, 'href': 'text00007.html#sub_b'},
        ]
        result = self.build(toc)
        assert result['text00007.html']['title'] == 'Chapter 2'
        assert result['text00007.html']['level'] == 1

    def test_different_files_kept(self):
        toc = [
            {'title': 'Chapter 1', 'level': 1, 'href': 'ch01.html'},
            {'title': 'Chapter 2', 'level': 1, 'href': 'ch02.html'},
        ]
        result = self.build(toc)
        assert 'ch01.html' in result
        assert 'ch02.html' in result


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
        "Text/081_appendix-m.html",
    ])
    def test_untitled_back_matter_detected_from_filename(self, filename):
        assert self.detect("", filename) == SectionType.BACK_MATTER

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
        assert self.detect("Preface") == SectionType.FRONT_MATTER

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
