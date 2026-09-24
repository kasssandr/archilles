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

        def cs(p):
            return m[p]['chapter'], m[p]['section_title']

        assert cs(5) == ('Preface', '')
        assert cs(9) == ('Preface', '')
        assert cs(10) == ('Chapter I', '')
        assert cs(15) == ('Chapter I', '')
        assert cs(20) == ('Chapter II', '')
        assert cs(50) == ('Index', '')
        assert m[50]['region'] == 'index'

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
        m = PDFExtractor._build_page_toc_map(toc, last_page=500)

        assert m[100]['chapter'] == 'Index'
        assert m[500]['chapter'] == 'Index'
        assert 501 not in m

    # --- outline B8: the tree, not "level 1 is the chapter" ---

    def test_parts_lie_above_the_chapters(self):
        toc = [
            {'level': 1, 'title': 'Part I – Origins', 'page': 5},
            {'level': 2, 'title': '1. The Temple', 'page': 7},
            {'level': 3, 'title': 'The Priests', 'page': 12},
            {'level': 2, 'title': '2. The City', 'page': 30},
            {'level': 1, 'title': 'Part II – Networks', 'page': 50},
            {'level': 2, 'title': '3. The Roads', 'page': 52},
        ]
        m = PDFExtractor._build_page_toc_map(toc, last_page=80)

        assert m[5]['chapter'] == 'Part I – Origins'      # the part page is its own
        assert m[8]['chapter'] == '1. The Temple'
        assert m[8]['section_title'] == ''
        assert m[12]['chapter'] == '1. The Temple'
        assert m[12]['section_title'] == 'The Priests'
        assert m[52]['chapter'] == '3. The Roads'

    def test_a_cover_beside_the_chapters_leaves_them_chapters(self):
        """G1: 32 of 93 outlines carry 'Cover' on level 1 beside the chapters."""
        toc = [
            {'level': 1, 'title': 'Cover', 'page': 1},
            {'level': 1, 'title': 'Title Page', 'page': 3},
            {'level': 1, 'title': '1. Genesis', 'page': 9},
            {'level': 2, 'title': 'Abraham', 'page': 11},
            {'level': 1, 'title': '2. Exodus', 'page': 40},
        ]
        m = PDFExtractor._build_page_toc_map(toc, last_page=60)

        assert m[1]['region'] == 'front-matter'
        assert m[11]['chapter'] == '1. Genesis'
        assert m[11]['section_title'] == 'Abraham'
        assert m[11]['region'] is None
        assert m[45]['chapter'] == '2. Exodus'

    def test_page_bookmarks_map_nothing(self):
        """JSTOR's outline of every page is no outline (Briefing §7.6)."""
        toc = [{'level': 1, 'title': f'p. {n}', 'page': n - 298} for n in range(299, 320)]
        assert PDFExtractor._build_page_toc_map(toc) == {}

    def test_section_is_the_designator_chain(self):
        toc = [
            {'level': 1, 'title': 'Erstes Kapitel: Die bildliche Aneignung', 'page': 20},
            {'level': 2, 'title': 'A. Begriff', 'page': 21},
            {'level': 3, 'title': 'II. Aneignung', 'page': 25},
            {'level': 4, 'title': '1. Aneignung als allgemeinsprachlicher Begriff', 'page': 26},
            {'level': 1, 'title': 'Zweites Kapitel: Die Rede', 'page': 90},
        ]
        m = PDFExtractor._build_page_toc_map(toc, last_page=100)

        assert m[26]['chapter'] == 'Erstes Kapitel: Die bildliche Aneignung'
        assert m[26]['section_title'] == '1. Aneignung als allgemeinsprachlicher Begriff'
        assert m[26]['section'] == 'A.II.1'
        assert m[90]['section'] == ''

    def test_a_section_under_the_notes_stays_notes(self):
        toc = [
            {'level': 1, 'title': '1. Anfang', 'page': 5},
            {'level': 1, 'title': '2. Ende', 'page': 20},
            {'level': 1, 'title': 'Anmerkungen', 'page': 40},
            {'level': 2, 'title': 'Vorwort', 'page': 40},
            {'level': 2, 'title': 'Kapitel 1', 'page': 41},
        ]
        m = PDFExtractor._build_page_toc_map(toc, last_page=50)

        assert m[40]['region'] == 'notes'
        assert m[45]['region'] == 'notes'
        assert m[45]['chapter'] == 'Anmerkungen'


# ---------------------------------------------------------------------------
# _section_type_from_toc_title
# ---------------------------------------------------------------------------

class TestSectionTypeFromTocTitle:
    """Tests for PDFExtractor._section_type_from_toc_title()."""

    @pytest.mark.parametrize("title", [
        'Table of Contents', 'INHALTSVERZEICHNIS', 'Inhalt', 'Title Page', 'Impressum',
    ])
    def test_front_matter(self, title):
        assert PDFExtractor._section_type_from_toc_title(title) == 'front_matter'

    @pytest.mark.parametrize("title", [
        'Preface', 'VORWORT', 'Geleitwort', 'Acknowledgments', 'Danksagung',
        'Appendix', 'Anhang', 'Appendix C. Dream Transcripts',
    ])
    def test_prefaces_and_appendices_stay_searchable(self, title):
        """User decisions of 2026-09-10 (preface) and 2026-09-23 (appendix):
        both are named, neither is apparatus."""
        assert PDFExtractor._section_type_from_toc_title(title) == 'main_content'

    @pytest.mark.parametrize("title", [
        'Index', 'REGISTER', 'Sachregister', 'Personenregister',
        'Bibliography', 'BIBLIOGRAPHIE', 'Literaturverzeichnis',
        'Glossary', 'Glossar', 'List of Illustrations',
        'Notes', 'Endnotes', 'Anmerkungen',
        'Abbreviations', 'Abkürzungsverzeichnis', 'Index of Modern Authors',
    ])
    def test_back_matter(self, title):
        assert PDFExtractor._section_type_from_toc_title(title) == 'back_matter'

    @pytest.mark.parametrize("title", [
        'Chapter I: The Temple', 'A. Einleitung', 'Introduction',
        '3. The Roman Empire', 'Part II: Networks',
        'Einleitung', 'Einführung',
        # Named nothing by Scriptor's vocabulary, so running text (M2: an
        # epilogue is argument; a dedication or copyright page is too short
        # to matter either way).
        'Nachwort', 'Afterword', 'Prologue', 'Foreword', 'Dedication', 'Widmung',
        'Copyright',
    ])
    def test_main_content(self, title):
        """Titles that name no region return None (→ main_content fallback)."""
        assert PDFExtractor._section_type_from_toc_title(title) is None

    def test_case_insensitive(self):
        assert PDFExtractor._section_type_from_toc_title('BIBLIOGRAPHY') == 'back_matter'
        assert PDFExtractor._section_type_from_toc_title('inhaltsverzeichnis') == 'front_matter'

    def test_the_whole_title_must_name_the_region(self):
        assert PDFExtractor._section_type_from_toc_title(
            'D. BIBLIOGRAPHIE UND QUELLEN'
        ) == 'back_matter'
        assert PDFExtractor._section_type_from_toc_title(
            'Literatur und Mehrsprachigkeit'
        ) is None
        assert PDFExtractor._section_type_from_toc_title(
            'Preface to the Second Edition'
        ) is None
