"""The ``section_title`` of an EPUB chunk when the table of contents points
into a file (Le Goff [4031], found at the acceptance of Gliederung B1).

Sub-entries of the nav often target an empty anchor, ``<a id="sec1"/>``,
rather than the heading itself. The split located each anchor by the text of
its element; an empty element has none, every split point fell on the same
offset, and the whole file went to the last sub-section. Every chunk of the
file then named a section it is not in. The anchor's place in the document is
the witness, not its text.
"""

import pytest

epub = pytest.importorskip("ebooklib.epub")

from src.extractors.epub_extractor import EPUBExtractor

SECTIONS = ("Erster Abschnitt", "Zweiter Abschnitt", "Dritter Abschnitt")


def _book(path, body: str, anchors: tuple[str, ...]) -> None:
    book = epub.EpubBook()
    book.set_identifier("anchor-fixture")
    book.set_title("Fixture")
    book.set_language("de")
    book.add_author("Anonymus")
    chapter = epub.EpubHtml(title="Kapitel", file_name="ch.xhtml", lang="de")
    chapter.content = f"<html><body>{body}</body></html>"
    book.add_item(chapter)
    # A second chapter, so that the chapters stand on the top level: with one
    # alone the outline model declares the level below it the chapter level.
    other = epub.EpubHtml(title="Kapitel 2", file_name="ch2.xhtml", lang="de")
    other.content = "<html><body><h1>Kapitel 2</h1><p>Absatz anderes.</p></body></html>"
    book.add_item(other)
    book.toc = [(epub.Link("ch.xhtml", "Kapitel", "ch"),
                 [epub.Link(f"ch.xhtml#{a}", t, a) for a, t in zip(anchors, SECTIONS)]),
                epub.Link("ch2.xhtml", "Kapitel 2", "ch2")]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = [chapter, other]
    epub.write_epub(str(path), book)


def _section_of(path) -> dict[str, str]:
    """The section a paragraph names; for text on the chapter level, where
    the outline model leaves ``section_title`` empty, the chapter."""
    chunks = EPUBExtractor().extract(path).chunks
    return {
        key: chunk["metadata"]["section_title"] or chunk["metadata"]["chapter"]
        for chunk in chunks
        for key in ("vorspann", "eins", "zwei", "drei")
        if f"Absatz {key}" in chunk["text"]
    }


@pytest.fixture(scope="module")
def empty_anchors(tmp_path_factory):
    path = tmp_path_factory.mktemp("anchors") / "empty.epub"
    _book(path,
          "<h1>Kapitel</h1><p>Absatz vorspann vor dem ersten Abschnitt.</p>"
          '<p><em><a id="sec1"></a>Erster Abschnitt</em></p><p>Absatz eins.</p>'
          '<p><em><a id="sec2"></a>Zweiter Abschnitt</em></p><p>Absatz zwei.</p>'
          '<p><em><a id="sec3"></a>Dritter Abschnitt</em></p><p>Absatz drei.</p>',
          ("sec1", "sec2", "sec3"))
    return _section_of(path)


def test_an_empty_anchor_opens_its_own_section(empty_anchors):
    assert empty_anchors["eins"] == "Erster Abschnitt"
    assert empty_anchors["zwei"] == "Zweiter Abschnitt"
    assert empty_anchors["drei"] == "Dritter Abschnitt"


def test_text_before_the_first_anchor_keeps_the_file_title(empty_anchors):
    assert empty_anchors["vorspann"] == "Kapitel"


def test_an_anchor_on_the_heading_itself_still_splits(tmp_path):
    path = tmp_path / "headed.epub"
    _book(path,
          "<h1>Kapitel</h1><p>Absatz vorspann.</p>"
          '<h2 id="h1">Erster Abschnitt</h2><p>Absatz eins.</p>'
          '<h2 id="h2">Zweiter Abschnitt</h2><p>Absatz zwei.</p>'
          '<h2 id="h3">Dritter Abschnitt</h2><p>Absatz drei.</p>',
          ("h1", "h2", "h3"))
    sections = _section_of(path)
    assert (sections["eins"], sections["zwei"], sections["drei"]) == SECTIONS


def test_an_anchor_whose_words_stand_earlier_in_the_file_splits_at_its_place(tmp_path):
    """The old search found the heading's words where the prose first used
    them and cut the file there."""
    path = tmp_path / "echo.epub"
    _book(path,
          "<h1>Kapitel</h1><p>Was im Erster Abschnitt folgt, sagt der Absatz vorspann.</p>"
          '<h2 id="h1">Erster Abschnitt</h2><p>Absatz eins.</p>'
          '<h2 id="h2">Zweiter Abschnitt</h2><p>Absatz zwei.</p>'
          '<h2 id="h3">Dritter Abschnitt</h2><p>Absatz drei.</p>',
          ("h1", "h2", "h3"))
    sections = _section_of(path)
    assert sections["vorspann"] == "Kapitel"
    assert sections["eins"] == "Erster Abschnitt"
