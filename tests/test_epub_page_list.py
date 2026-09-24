"""The print edition's pages from an EPUB page list (Gliederung B7).

A package that declares a page list states which printed page each stretch
of text stood on. That is a statement, not a sighting: ``label_source`` is
``catalogue``, ``page`` stays 0 (an EPUB has no physical page), and a
chunk carries the page of its first paragraph.
"""

import pytest

epub = pytest.importorskip("ebooklib.epub")
bs4 = pytest.importorskip("bs4")

from src.extractors.epub_extractor import EPUBExtractor, _page_label, _paragraph_pages


@pytest.mark.parametrize("text, label", [
    ("5", "5"), ("[S. 5]", "5"), ("p. xiv", "xiv"), ("Seite 12", "12"),
    ("XIV", "XIV"), ("12a", "12a"), ("Kapitel 3", None), ("", None),
])
def test_a_label_is_read_not_guessed(text, label):
    assert _page_label(text) == label


def _soup(body: str):
    return bs4.BeautifulSoup(f"<html><body>{body}</body></html>", "html.parser")


def test_a_paragraph_takes_the_last_break_before_its_first_word():
    soup = _soup('<p><span id="p5"></span>Eins beginnt auf fünf.</p>'
                 '<p>Zwei läuft über <span id="p6"></span>die Grenze.</p>'
                 '<p>Drei steht auf sechs.</p>')
    pages, carry = _paragraph_pages(soup, [("p5", "5"), ("p6", "6")], None)
    assert [start for start, _ in pages] == ["5", "5", "6"]
    # the break inside the second paragraph, after "Zwei läuft über "
    assert pages[1][1] == [(len("Zwei läuft über"), "6")]
    assert carry == "6"
    assert "" not in soup.get_text()          # the marks are gone again


def test_the_page_runs_on_into_the_next_file():
    pages, _ = _paragraph_pages(_soup("<p>Fortsetzung.</p>"), [], "7")
    assert pages == [("7", [])]


def test_a_notes_file_at_the_end_is_not_a_continuation():
    soup = _soup('<p>Note ohne Seite.</p><p><span id="n"></span>Note auf 1021.</p>')
    pages, _ = _paragraph_pages(soup, [("n", "1021")], "1625")
    assert [start for start, _ in pages] == [None, "1021"]


def test_chunks_of_a_book_with_a_page_list(tmp_path):
    book = epub.EpubBook()
    book.set_identifier("page-list-fixture")
    book.set_title("Fixture")
    book.set_language("de")
    book.add_author("Anonymus")
    one = epub.EpubHtml(title="Eins", file_name="one.xhtml", lang="de")
    one.content = ('<html><body><h1 id="c1">Erstes Kapitel</h1>'
                   '<p><span id="pg17"></span>W1 auf siebzehn.</p>'
                   '<p><span id="pg18"></span>W2 auf achtzehn.</p></body></html>')
    two = epub.EpubHtml(title="Zwei", file_name="two.xhtml", lang="de")
    two.content = ('<html><body><h1 id="c2">Zweites Kapitel</h1>'
                   '<p>W3 noch auf achtzehn.</p></body></html>')
    pages = epub.EpubHtml(title="Seiten", file_name="pages.xhtml", lang="de")
    pages.content = ('<html><body><nav epub:type="page-list"><ol>'
                     '<li><a href="one.xhtml#pg17">17</a></li>'
                     '<li><a href="one.xhtml#pg18">[S. 18]</a></li>'
                     '</ol></nav></body></html>')
    for item in (one, two, pages):
        book.add_item(item)
    book.toc = [epub.Link("one.xhtml#c1", "Erstes Kapitel", "c1"),
                epub.Link("two.xhtml#c2", "Zweites Kapitel", "c2")]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = [one, two]
    path = tmp_path / "pages.epub"
    epub.write_epub(str(path), book)

    extractor = EPUBExtractor()
    extractor.chunk_size = 4          # one paragraph a chunk
    extractor.overlap = 0
    result = extractor.extract(path)
    by_word = {}
    for chunk in result.chunks:
        for word in ("W1", "W2", "W3"):
            if chunk["text"].split("\n\n")[0].find(word) >= 0:
                by_word[word] = chunk["metadata"]
    assert by_word["W1"]["page_label"] == "17"
    assert by_word["W2"]["page_label"] == "18"
    assert by_word["W3"]["page_label"] == "18"
    assert {m["label_source"] for m in by_word.values()} == {"catalogue"}
    assert {m["page"] for m in by_word.values()} == {0}
    assert any("Page list: 2 targets" in w for w in result.metadata.warnings)
