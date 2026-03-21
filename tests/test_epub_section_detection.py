"""Tests for EPUB sub-section detection via heading splitting."""

import pytest

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
