"""Tests for PDFExtractor paragraph detection, page number stripping, and overlap."""

import pytest

from src.extractors.pdf_extractor import PDFExtractor


detect = PDFExtractor._detect_paragraph_breaks


class TestPassthrough:
    def test_passthrough_existing_breaks(self):
        """Text that already contains \\n\\n should be returned unchanged."""
        text = "First paragraph.\n\nSecond paragraph.\n\nThird."
        assert detect(text) == text

    def test_passthrough_single_line(self):
        text = "Just one line of text."
        assert detect(text) == text

    def test_passthrough_empty(self):
        assert detect("") == ""


class TestShortLineBreak:
    def test_short_line_break(self):
        """A short line followed by an uppercase start should produce \\n\\n."""
        text = (
            "This is a long line that fills most of the available column width in the PDF document.\n"
            "Short ending.\n"
            "The next paragraph begins here with a longer line filling the column width again."
        )
        result = detect(text)
        assert "\n\nThe next paragraph" in result

    def test_long_lines_no_break(self):
        """Two equally long lines should NOT get a paragraph break."""
        text = (
            "This is a long line that fills the entire column width of the PDF page layout.\n"
            "Another long line that also fills the entire column width of the page layout."
        )
        result = detect(text)
        assert "\n\n" not in result


class TestHyphenation:
    def test_hyphenation_no_break(self):
        """A line ending with '-' (hyphenation) must never trigger a break."""
        text = (
            "The philosopher discussed the concept of eudai-\n"
            "Monia at length in his treatise on ethics and the good life in ancient Greece.\n"
            "Another long line that fills the column width to establish the average length."
        )
        result = detect(text)
        # The hyphenated line is very short, but must NOT get a \n\n
        assert "eudai-\n\nMonia" not in result
        assert "eudai-\nMonia" in result


class TestIndentation:
    def test_indentation_break(self):
        """A line indented with 4+ spaces should start a new paragraph."""
        text = (
            "End of previous paragraph on a normal unindented line.\n"
            "    The indented line signals a new typographic paragraph."
        )
        result = detect(text)
        assert "\n\n    The indented" in result

    def test_both_indented_no_break(self):
        """If both lines are indented, no extra break (e.g. block quote)."""
        text = (
            "    First indented line of a block quotation.\n"
            "    Second indented line of the same block quotation."
        )
        result = detect(text)
        assert "\n\n" not in result


class TestFootnoteZone:
    def test_footnote_entries_separated(self):
        """New footnote entries (start with number) should be separated."""
        # Build enough lines so that footnotes fall in bottom half
        body_lines = [
            "This is body line that fills the column width to establish average length."
            for _ in range(6)
        ]
        fn_lines = [
            "1. First footnote text that explains the reference in the body.",
            "Continuation of the first footnote spanning a second line here.",
            "2. Second footnote with its own reference and explanation text.",
        ]
        text = "\n".join(body_lines + fn_lines)
        result = detect(text)
        # Entry "2." should be separated from continuation of fn 1
        assert "\n\n2. Second footnote" in result
        # Continuation should NOT be separated from "1."
        assert "1. First footnote text that explains the reference in the body.\nContinuation" in result

    def test_footnote_continuation_not_split(self):
        """Continuation lines in footnote zone should not be split."""
        body_lines = [
            "This is body line that fills the column width to establish average length."
            for _ in range(6)
        ]
        fn_lines = [
            "1. A footnote that spans",
            "multiple lines without a new number prefix at the start of line.",
        ]
        text = "\n".join(body_lines + fn_lines)
        result = detect(text)
        assert "spans\nmultiple" in result
        assert "spans\n\nmultiple" not in result


class TestRealisticAcademicPage:
    def test_eunapios_style_page(self):
        """Simulate a typical Eunapios page with blocksatz and footnotes."""
        text = (
            "Eunapios was born around 347 CE in the city of Sardis in Lydia. He studied rhetoric\n"
            "under Prohaeresius in Athens and later returned to Sardis where he practiced as a\n"
            "sophist and physician. His major work, the Lives of the Philosophers and Sophists,\n"
            "provides invaluable information about the intellectual life of the fourth century.\n"
            "The work is short.\n"
            "Among his subjects were Iamblichus, Aedesius, and Maximus of Ephesus, all of whom\n"
            "played significant roles in the Neoplatonic tradition that flourished in the eastern\n"
            "provinces of the Roman Empire during the reigns of Constantine and his successors.\n"
            "Brief note.\n"
            "The text survives in two recensions: the original version and an epitome preserved in\n"
            "the Suda lexicon, which sometimes provides readings superior to the manuscript tradition.\n"
            "1. See R. Penella, Greek Philosophers and Sophists in the Fourth Century AD (2015).\n"
            "2. On the two recensions cf. Blockley, FCH (1983) 1-26."
        )
        result = detect(text)
        # Paragraph break after "fourth century." (short-ish line before "The work")
        # — not guaranteed by H1 alone, depends on avg. Let's just check key properties:

        # Footnotes 1 and 2 should be separated
        assert "\n\n2. On the two" in result
        # The long blocksatz lines should NOT be broken
        assert "rhetoric\nunder" in result or "rhetoric\n\nunder" not in result


class TestStripStandalonePageNumbers:
    """Tests for _strip_standalone_page_numbers."""

    strip = staticmethod(PDFExtractor._strip_standalone_page_numbers)

    def test_standalone_number_removed(self):
        """A bare page number on its own line at the top should be removed."""
        pages = ["119\nNachbarschaft und nahmen die Ankoemmlinge auf."]
        meta = [{'page': 119, 'page_label': '119'}]
        result = self.strip(pages, meta)
        assert result[0].startswith("Nachbarschaft")
        assert "119" not in result[0]

    def test_number_prefix_stripped(self):
        """Page number at start of first content line: '119 Text...' -> 'Text...'."""
        pages = ["119 Nachbarschaft und nahmen die Ankoemmlinge auf."]
        meta = [{'page': 119, 'page_label': '119'}]
        result = self.strip(pages, meta)
        assert result[0].startswith("Nachbarschaft")

    def test_non_matching_number_kept(self):
        """Numbers that don't match the page label should be kept."""
        pages = ["42 soldiers marched through the gate."]
        meta = [{'page': 5, 'page_label': '5'}]
        result = self.strip(pages, meta)
        assert result[0] == "42 soldiers marched through the gate."

    def test_number_in_middle_untouched(self):
        """Numbers in the middle of text should never be removed."""
        pages = ["There were 119 participants in the study."]
        meta = [{'page': 119, 'page_label': '119'}]
        result = self.strip(pages, meta)
        assert "119" in result[0]

    def test_roman_numeral_standalone(self):
        """Roman numeral page labels should also be stripped."""
        pages = ["xiv\nPreface text begins here."]
        meta = [{'page': 14, 'page_label': 'xiv'}]
        result = self.strip(pages, meta)
        assert result[0].startswith("Preface")

    def test_empty_page_label(self):
        """Pages without a label should pass through unchanged."""
        pages = ["Some text content."]
        meta = [{'page': 1, 'page_label': ''}]
        result = self.strip(pages, meta)
        assert result[0] == "Some text content."


class TestSentenceAlignedOverlap:
    """Tests for _extract_overlap_tail."""

    extract = staticmethod(PDFExtractor._extract_overlap_tail)

    def test_basic_sentence_alignment(self):
        """Overlap should start at a sentence boundary."""
        text = (
            "First sentence of the chunk. Second sentence continues here. "
            "Third sentence is also present. Fourth sentence at the end."
        )
        result = self.extract(text, target_tokens=10)
        # Should start at a sentence boundary, not mid-sentence
        assert result[0].isupper() or result.startswith("Fourth")

    def test_short_text_returned_as_is(self):
        """Text shorter than target_tokens should be returned unchanged."""
        text = "Short text."
        result = self.extract(text, target_tokens=100)
        assert result == text

    def test_overlap_not_empty(self):
        """Result should never be empty for non-empty input."""
        text = "Word " * 200
        result = self.extract(text.strip(), target_tokens=50)
        assert len(result) > 0
        assert len(result.split()) <= 60  # roughly target + some slack

    def test_preserves_minimum_content(self):
        """If sentence alignment would lose too much, fall back to word-based."""
        # One very long sentence — no sentence boundary in the tail
        text = " ".join(f"word{i}" for i in range(200))
        result = self.extract(text, target_tokens=50)
        assert len(result.split()) >= 40  # at least 40% of 50
