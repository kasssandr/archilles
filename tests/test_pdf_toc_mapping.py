"""Tests for PDF TOC-to-page mapping and section type classification."""

import pytest
from src.extractors.pdf_extractor import PDFExtractor


# ---------------------------------------------------------------------------
# _build_page_toc_map
# ---------------------------------------------------------------------------

class TestBuildPageTocMap:
    """Tests for PDFExtractor._build_page_toc_map()."""

    def test_empty_toc(self):
        assert PDFExtractor._build_page_toc_map([]) == {}

    def test_too_short_toc(self):
        toc = [{'level': 1, 'title': 'Ch1', 'page': 1}]
        assert PDFExtractor._build_page_toc_map(toc) == {}

    def test_two_entries_rejected(self):
        toc = [
            {'level': 1, 'title': 'Ch1', 'page': 1},
            {'level': 1, 'title': 'Ch2', 'page': 10},
        ]
        assert PDFExtractor._build_page_toc_map(toc) == {}

    def test_all_same_page_rejected(self):
        toc = [
            {'level': 1, 'title': 'A', 'page': 1},
            {'level': 1, 'title': 'B', 'page': 1},
            {'level': 1, 'title': 'C', 'page': 1},
        ]
        assert PDFExtractor._build_page_toc_map(toc) == {}

    def test_junk_toc_rejected(self):
        """Scanner-artifact TOCs like 'scan 1', 'z - a.d.n.001' are filtered."""
        toc = [
            {'level': 1, 'title': 'scan 1', 'page': 1},
            {'level': 1, 'title': 'scan 3', 'page': 1},
            {'level': 1, 'title': 'z - a.d.n.001', 'page': 1},
            {'level': 1, 'title': 'z - a.d.n.002', 'page': 30},
            {'level': 1, 'title': 'zcan 2', 'page': 1},
        ]
        assert PDFExtractor._build_page_toc_map(toc) == {}

    def test_flat_toc_level1_only(self):
        """All level-1 entries map to chapter, no section_title."""
        toc = [
            {'level': 1, 'title': 'Preface', 'page': 5},
            {'level': 1, 'title': 'Chapter I', 'page': 10},
            {'level': 1, 'title': 'Chapter II', 'page': 20},
            {'level': 1, 'title': 'Index', 'page': 50},
        ]
        m = PDFExtractor._build_page_toc_map(toc)

        assert m[5] == {'chapter': 'Preface', 'section_title': ''}
        assert m[9] == {'chapter': 'Preface', 'section_title': ''}
        assert m[10] == {'chapter': 'Chapter I', 'section_title': ''}
        assert m[15] == {'chapter': 'Chapter I', 'section_title': ''}
        assert m[20] == {'chapter': 'Chapter II', 'section_title': ''}
        assert m[50] == {'chapter': 'Index', 'section_title': ''}

    def test_hierarchical_toc(self):
        """Level-2+ entries populate section_title, level-1 populates chapter."""
        toc = [
            {'level': 1, 'title': 'A. Einleitung', 'page': 10},
            {'level': 2, 'title': '1. Forschung', 'page': 10},
            {'level': 3, 'title': '1.1 Wege', 'page': 10},
            {'level': 3, 'title': '1.2 Verortung', 'page': 21},
            {'level': 1, 'title': 'B. Übersetzung', 'page': 75},
        ]
        m = PDFExtractor._build_page_toc_map(toc)

        assert m[10]['chapter'] == 'A. Einleitung'
        assert m[10]['section_title'] == '1.1 Wege'
        assert m[20]['section_title'] == '1.1 Wege'
        assert m[21]['section_title'] == '1.2 Verortung'
        assert m[74]['chapter'] == 'A. Einleitung'
        assert m[75]['chapter'] == 'B. Übersetzung'
        assert m[75]['section_title'] == ''

    def test_pages_before_first_toc_entry_not_mapped(self):
        """Pages before the first TOC entry have no mapping."""
        toc = [
            {'level': 1, 'title': 'Chapter I', 'page': 10},
            {'level': 1, 'title': 'Chapter II', 'page': 20},
            {'level': 1, 'title': 'Chapter III', 'page': 30},
        ]
        m = PDFExtractor._build_page_toc_map(toc)

        assert 1 not in m
        assert 9 not in m
        assert 10 in m

    def test_last_entry_extends_to_end(self):
        """The last TOC entry covers all remaining pages."""
        toc = [
            {'level': 1, 'title': 'Ch1', 'page': 1},
            {'level': 1, 'title': 'Ch2', 'page': 10},
            {'level': 1, 'title': 'Index', 'page': 100},
        ]
        m = PDFExtractor._build_page_toc_map(toc)

        assert m[100]['chapter'] == 'Index'
        assert m[500]['chapter'] == 'Index'


# ---------------------------------------------------------------------------
# _section_type_from_toc_title
# ---------------------------------------------------------------------------

class TestSectionTypeFromTocTitle:
    """Tests for PDFExtractor._section_type_from_toc_title()."""

    @pytest.mark.parametrize("title", [
        'Preface', 'VORWORT', 'Foreword', 'Geleitwort',
        'Table of Contents', 'INHALTSVERZEICHNIS', 'Inhalt',
        'Acknowledgments', 'Danksagung', 'Dedication', 'Widmung',
        'Copyright', 'Prologue',
    ])
    def test_front_matter(self, title):
        assert PDFExtractor._section_type_from_toc_title(title) == 'front_matter'

    @pytest.mark.parametrize("title", [
        'Index', 'REGISTER', 'Sachregister', 'Personenregister',
        'Bibliography', 'BIBLIOGRAPHIE', 'Literaturverzeichnis',
        'Glossary', 'Glossar', 'Appendix', 'Anhang',
        'Notes', 'Endnotes', 'Anmerkungen', 'Nachwort', 'Afterword',
        'Abbreviations', 'Abkürzungsverzeichnis',
    ])
    def test_back_matter(self, title):
        assert PDFExtractor._section_type_from_toc_title(title) == 'back_matter'

    @pytest.mark.parametrize("title", [
        'Chapter I: The Temple', 'A. Einleitung', 'Introduction',
        '3. The Roman Empire', 'Part II: Networks',
        'Einleitung', 'Einführung',
    ])
    def test_main_content(self, title):
        """Regular chapter titles and introductions return None (→ main_content fallback)."""
        assert PDFExtractor._section_type_from_toc_title(title) is None

    def test_case_insensitive(self):
        assert PDFExtractor._section_type_from_toc_title('BIBLIOGRAPHY') == 'back_matter'
        assert PDFExtractor._section_type_from_toc_title('vorwort') == 'front_matter'

    def test_keyword_in_longer_title(self):
        assert PDFExtractor._section_type_from_toc_title(
            'D. BIBLIOGRAPHIE UND QUELLEN'
        ) == 'back_matter'
        assert PDFExtractor._section_type_from_toc_title(
            'Preface to the Second Edition'
        ) == 'front_matter'
