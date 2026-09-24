"""The region of an EPUB section (Gliederung B7, absorbing seam step S7).

A title is classified by Scriptor's region vocabulary, the same one the
prepared master and the PDF contents use; the publisher's ``epub:type`` goes
before the title; a sub-section may name a region of its own, but inside an
apparatus only another apparatus.
"""

import pytest

epub = pytest.importorskip("ebooklib.epub")

from src.archilles.constants import SectionType
from src.extractors.epub_extractor import EPUBExtractor


def _book(path, chapters) -> None:
    """chapters: (file, nav title, body html, [(anchor, sub title), ...])."""
    book = epub.EpubBook()
    book.set_identifier("region-fixture")
    book.set_title("Fixture")
    book.set_language("de")
    book.add_author("Anonymus")
    items, toc = [], []
    for name, title, body, subs in chapters:
        item = epub.EpubHtml(title=title, file_name=name, lang="de")
        item.content = f"<html><body>{body}</body></html>"
        book.add_item(item)
        items.append(item)
        link = epub.Link(name, title, name)
        toc.append((link, [epub.Link(f"{name}#{a}", t, a) for a, t in subs]) if subs else link)
    book.toc = toc
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = items
    epub.write_epub(str(path), book)


def _by_word(path) -> dict[str, tuple[str, str]]:
    """(section_type, region) of the chunk holding each 'Absatz <word>'."""
    out = {}
    for chunk in EPUBExtractor().extract(path).chunks:
        meta = chunk["metadata"]
        for word in chunk["text"].split():
            if word.startswith("W") and word[1:].isdigit():
                out[word] = (meta["section_type"], meta.get("region"))
    return out


@pytest.fixture(scope="module")
def regions(tmp_path_factory):
    path = tmp_path_factory.mktemp("regions") / "regions.epub"
    _book(path, [
        ("ch1.xhtml", "Kapitel 1",
         "<h1>Kapitel 1</h1><p>W1 Text.</p>"
         '<aside epub:type="footnote"><p>W2 Fußnote.</p></aside>', []),
        ("works.xhtml", "Works",
         '<section epub:type="bibliography"><h1>Works</h1><p>W3 Eintrag.</p></section>', []),
        ("front.xhtml", "Einführung",
         '<section epub:type="frontmatter"><h1>Einführung</h1><p>W4 Text.</p></section>', []),
        ("app.xhtml", "Appendix C. Dream Transcripts",
         "<h1>Appendix C. Dream Transcripts</h1><p>W5 Protokoll.</p>", []),
        ("notes.xhtml", "Anmerkungen",
         "<h1>Anmerkungen</h1><p>W6 Vorspann.</p>"
         '<h2 id="n1">Vorwort</h2><p>W7 Note zum Vorwort.</p>'
         '<h2 id="n2">Literatur</h2><p>W8 Titel.</p>',
         [("n1", "Vorwort"), ("n2", "Literatur")]),
        ("ch2.xhtml", "Kapitel 2",
         "<h1>Kapitel 2</h1><p>W9 Text.</p>"
         '<h2 id="k1">Notes</h2><p>W10 Note.</p>',
         [("k1", "Notes")]),
        ("gloss.xhtml", "Glossary",
         "<h1>Glossary</h1><p>W11 Begriff.</p>", []),
    ])
    return _by_word(path)


def test_running_text_carries_no_region(regions):
    assert regions["W1"] == (SectionType.MAIN_CONTENT, None)


def test_a_footnote_element_names_no_region(regions):
    assert regions["W2"] == (SectionType.MAIN_CONTENT, None)


def test_epub_type_outranks_a_title_that_names_nothing(regions):
    assert regions["W3"] == (SectionType.BACK_MATTER, "bibliography")


def test_the_frontmatter_partition_alone_names_no_region(regions):
    assert regions["W4"] == (SectionType.MAIN_CONTENT, None)


def test_an_appendix_with_a_title_is_named_and_searchable(regions):
    assert regions["W5"] == (SectionType.MAIN_CONTENT, "appendix")


def test_inside_an_apparatus_a_sub_section_names_only_another_apparatus(regions):
    assert regions["W6"] == (SectionType.BACK_MATTER, "notes")
    assert regions["W7"] == (SectionType.BACK_MATTER, "notes")        # not preface
    assert regions["W8"] == (SectionType.BACK_MATTER, "bibliography")


def test_a_chapter_s_notes_leave_the_search(regions):
    assert regions["W9"] == (SectionType.MAIN_CONTENT, None)
    assert regions["W10"] == (SectionType.BACK_MATTER, "notes")


def test_a_glossary_is_a_list(regions):
    assert regions["W11"] == (SectionType.BACK_MATTER, "lists")


@pytest.mark.parametrize("title, expected", [
    ("Indice", (SectionType.FRONT_MATTER, "contents")),     # not `index`
    ("Indice dei nomi", (SectionType.BACK_MATTER, "index")),
    ("Literatur und Mehrsprachigkeit", (SectionType.MAIN_CONTENT, None)),
    ("Title Page", (SectionType.FRONT_MATTER, "front-matter")),
])
def test_titles_are_read_by_scriptor_s_vocabulary(title, expected):
    assert EPUBExtractor._classify(title) == expected
