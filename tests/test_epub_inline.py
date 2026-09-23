"""EPUB text keeps inline markup inside its words (Berlinski, Human Nature [3084]).

The extractor joined every string of the HTML tree with a paragraph break,
so "T<span>HERE</span>" became "T" and "HERE", and every italic phrase a
paragraph of its own. Sixty books of the library, all affected. A paragraph
ends at a block element now, nowhere else.
"""

import pytest

bs4 = pytest.importorskip("bs4")

from src.extractors.epub_extractor import _block_text


def _text(html: str) -> str:
    return _block_text(bs4.BeautifulSoup(f"<html><body>{html}</body></html>", "html.parser"))


def test_small_caps_and_a_drop_cap_stay_in_their_words():
    html = ('<h1>5. T<span class="sc">HE</span> D<span class="sc">ANGEROUS</span> '
            'D<span class="sc">ISCIPLINE</span></h1>'
            '<p><span class="dc">T</span><span class="sc">HERE WAS A CERTAIN</span> '
            '<span class="sc">RABBI IN THE TOWN OF</span> Y<span class="sc">EHUPETZ</span>.</p>')
    assert _text(html) == ("5. THE DANGEROUS DISCIPLINE\n\n"
                           "THERE WAS A CERTAIN RABBI IN THE TOWN OF YEHUPETZ.")


def test_italics_and_superscripts_are_not_paragraphs():
    html = "<p>called him <i>Zogn Gornisht</i>, on the 178<sup>th</sup> day.</p>"
    assert _text(html) == "called him Zogn Gornisht, on the 178th day."


def test_block_elements_and_breaks_still_separate():
    html = "<p>eins</p><div>zwei<p>drei</p>vier</div><p>fünf<br/>sechs</p><ul><li>a</li><li>b</li></ul>"
    assert _text(html).split("\n\n") == ["eins", "zwei", "drei", "vier", "fünf", "sechs", "a", "b"]
