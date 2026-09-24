"""The nav as a tree (Gliederung B7): chapter, section_title and section.

Every nav entry is a node of Scriptor's outline model; the chapter level is
declared by its rule, not taken to be the top; ``section`` is the chain of
designators below the chapter.
"""

import pytest

epub = pytest.importorskip("ebooklib.epub")

from src.archilles.constants import SectionType
from src.extractors.epub_extractor import EPUBExtractor


def _doc(name: str, body: str) -> "epub.EpubHtml":
    item = epub.EpubHtml(title=name, file_name=name, lang="de")
    item.content = f"<html><body>{body}</body></html>"
    return item


def _extract(path, docs, toc) -> dict[str, dict]:
    book = epub.EpubBook()
    book.set_identifier("outline-fixture")
    book.set_title("Fixture")
    book.set_language("de")
    book.add_author("Anonymus")
    for d in docs:
        book.add_item(d)
    book.toc = toc
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = docs
    epub.write_epub(str(path), book)
    out = {}
    for chunk in EPUBExtractor().extract(path).chunks:
        for word in chunk["text"].split():
            if word.startswith("W") and word[1:].isdigit():
                out[word] = chunk["metadata"]
    return out


@pytest.fixture(scope="module")
def germanen(tmp_path_factory):
    """Steuer, "Germanen" (De Gruyter): part > chapter > decimal section."""
    part = _doc("p1.xhtml",
                '<h1 id="p1">I Methodisches</h1><p>W1 Einführung in den Teil.</p>'
                '<h2 id="c1">1 Zur Ausgangslage</h2><p>W2 Ausgangslage.</p>'
                '<h2 id="c2">2 Germanien aus der Sicht der Germanen</h2><p>W3 Germanien.</p>'
                '<h3 id="s21">2.1 Die Themen dieses Buches</h3><p>W4 Themen.</p>'
                '<h3 id="s22">2.2 Die Thesen dieses Buches</h3><p>W5 Thesen.</p>')
    part2 = _doc("p2.xhtml",
                 '<h1 id="p2">II Überblick</h1><p>W6 Zweiter Teil.</p>'
                 '<h2 id="c3">3 Kulturen</h2><p>W7 Kulturen.</p>')
    notes = _doc("n.xhtml", '<h1 id="n">Anmerkungen</h1><p>W8 Note.</p>'
                            '<h2 id="n1">Kapitel 1</h2><p>W9 Note zu Kapitel 1.</p>')
    toc = [
        (epub.Link("p1.xhtml#p1", "I Methodisches", "p1"), [
            epub.Link("p1.xhtml#c1", "1 Zur Ausgangslage", "c1"),
            (epub.Link("p1.xhtml#c2", "2 Germanien aus der Sicht der Germanen", "c2"), [
                epub.Link("p1.xhtml#s21", "2.1 Die Themen dieses Buches", "s21"),
                epub.Link("p1.xhtml#s22", "2.2 Die Thesen dieses Buches", "s22"),
            ]),
        ]),
        (epub.Link("p2.xhtml#p2", "II Überblick", "p2"), [
            epub.Link("p2.xhtml#c3", "3 Kulturen", "c3"),
        ]),
        (epub.Link("n.xhtml#n", "Anmerkungen", "n"), [
            epub.Link("n.xhtml#n1", "Kapitel 1", "n1"),
        ]),
    ]
    return _extract(tmp_path_factory.mktemp("outline") / "germanen.epub",
                    [part, part2, notes], toc)


def test_the_chain_of_a_decimal_section(germanen):
    meta = germanen["W4"]
    assert meta["chapter"] == "I Methodisches"
    assert meta["section_title"] == "2.1 Die Themen dieses Buches"
    assert meta["section"] == "2.1"


def test_a_chapter_node_below_the_top(germanen):
    meta = germanen["W3"]
    assert (meta["section_title"], meta["section"]) == (
        "2 Germanien aus der Sicht der Germanen", "2")


def test_text_on_the_chapter_level_has_no_section(germanen):
    meta = germanen["W1"]
    assert meta["chapter"] == "I Methodisches"
    assert not meta["section_title"] and not meta["section"]


def test_two_top_entries_in_one_file_are_two_nodes(tmp_path):
    """Before B7 only the first entry of a file became a chapter; a second
    level-1 entry into the same file was dropped."""
    doc = _doc("both.xhtml",
               '<h1 id="a">Erstes Kapitel</h1><p>W1 eins.</p>'
               '<h1 id="b">Zweites Kapitel</h1><p>W2 zwei.</p>')
    out = _extract(tmp_path / "both.epub", [doc], [
        epub.Link("both.xhtml#a", "Erstes Kapitel", "a"),
        epub.Link("both.xhtml#b", "Zweites Kapitel", "b"),
    ])
    assert out["W1"]["chapter"] == "Erstes Kapitel"
    assert out["W2"]["chapter"] == "Zweites Kapitel"


def test_a_heading_the_nav_leaves_out_takes_the_depth_its_tag_has_elsewhere(tmp_path):
    """The nav lists chapter 1's sections, not chapter 2's. What the nav
    shows of h2 in chapter 1 -- depth 2 -- holds for the h2 of chapter 2."""
    one = _doc("one.xhtml",
               '<h1 id="c1">1 Erstes Kapitel</h1><p>W1 eins.</p>'
               '<h2 id="s11">1.1 Erster Abschnitt</h2><p>W2 eins eins.</p>')
    two = _doc("two.xhtml",
               '<h1 id="c2">2 Zweites Kapitel</h1><p>W3 zwei.</p>'
               '<h2>2.1 Nicht verzeichnet</h2><p>W4 zwei eins.</p>'
               '<h4>Kein Abschnitt</h4><p>W5 unter h4.</p>')
    out = _extract(tmp_path / "learnt.epub", [one, two], [
        (epub.Link("one.xhtml#c1", "1 Erstes Kapitel", "c1"),
         [epub.Link("one.xhtml#s11", "1.1 Erster Abschnitt", "s11")]),
        epub.Link("two.xhtml#c2", "2 Zweites Kapitel", "c2"),
    ])
    assert (out["W2"]["section_title"], out["W2"]["section"]) == ("1.1 Erster Abschnitt", "1.1")
    assert out["W4"]["chapter"] == "2 Zweites Kapitel"
    assert (out["W4"]["section_title"], out["W4"]["section"]) == ("2.1 Nicht verzeichnet", "2.1")
    # h4 has no depth in this book: it cuts the text, it is no node
    assert out["W5"]["section_title"] == "Kein Abschnitt"
    assert out["W5"]["section"] == "2.1"


def test_without_a_nav_the_heading_tag_is_the_depth(tmp_path):
    doc = _doc("only.xhtml",
               '<h1>1 Erstes Kapitel</h1><p>W1 eins.</p>'
               '<h2>1.1 Abschnitt</h2><p>W2 eins eins.</p>'
               '<h1>2 Zweites Kapitel</h1><p>W3 zwei.</p>')
    out = _extract(tmp_path / "bare.epub", [doc], [])
    assert out["W1"]["chapter"] == "1 Erstes Kapitel"
    assert (out["W2"]["section_title"], out["W2"]["section"]) == ("1.1 Abschnitt", "1.1")
    assert out["W3"]["chapter"] == "2 Zweites Kapitel"


def test_a_node_inside_an_apparatus_keeps_its_region(germanen):
    assert (germanen["W8"]["section_type"], germanen["W8"]["region"]) == (
        SectionType.BACK_MATTER, "notes")
    assert (germanen["W9"]["section_type"], germanen["W9"]["region"]) == (
        SectionType.BACK_MATTER, "notes")
    assert germanen["W7"]["section_type"] == SectionType.MAIN_CONTENT
