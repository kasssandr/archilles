"""An EPUB that states the printed pages, or is a Gutenberg text, is indexed before the PDF.

Otherwise the PDF comes first, as it always did.
"""

import zipfile
from pathlib import Path

import pytest

pytest.importorskip("bs4")

from src.archilles.book_files import MIN_PAGE_LIST_LABELS, discover_formats, epub_outranks_pdf

_OPF = ('<?xml version="1.0"?><package xmlns="http://www.idpf.org/2007/opf" version="2.0">'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>T</dc:title>{meta}'
        '</metadata><manifest/><spine toc="ncx"/></package>')


def _epub(path: Path, *, meta: str = "", labels=(), words: int = 1) -> Path:
    targets = "".join(f'<pageTarget id="p{i}" value="{i}" type="normal" playOrder="{i}">'
                      f'<navLabel><text>{label}</text></navLabel><content src="t.xhtml#p{i}"/></pageTarget>'
                      for i, label in enumerate(labels, 1))
    ncx = f'<ncx><navMap/>{"<pageList>" + targets + "</pageList>" if labels else ""}</ncx>'
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("mimetype", "application/epub+zip")
        z.writestr("OEBPS/content.opf", _OPF.format(meta=meta))
        z.writestr("OEBPS/toc.ncx", ncx)
        z.writestr("OEBPS/t.xhtml", f"<html><body><p>{' '.join(['Wort'] * words)}</p></body></html>")
    return path


def _book(tmp_path: Path, **epub) -> Path:
    (tmp_path / "Buch.pdf").write_bytes(b"%PDF-1.4")
    _epub(tmp_path / "Buch.epub", **epub)
    return tmp_path


def _first(book_dir: Path) -> str:
    return discover_formats(book_dir)[0]["format"]


def test_a_gutenberg_epub_comes_first(tmp_path):
    book = _book(tmp_path, meta="<dc:source>https://www.gutenberg.org/ebooks/74500</dc:source>")
    assert _first(book) == "EPUB"


def test_a_page_list_of_printed_pages_comes_first(tmp_path):
    book = _book(tmp_path, labels=[f"{{{n}}}" for n in range(626, 626 + MIN_PAGE_LIST_LABELS)])
    assert _first(book) == "EPUB"


def test_a_few_labels_do_not_carry_the_citations(tmp_path):
    book = _book(tmp_path, labels=["1", "2", "3"])
    assert _first(book) == "PDF"


def test_a_list_of_the_front_matter_only_does_not_count(tmp_path):
    # A collected-studies volume: i..xii listed, the articles' pages not.
    labels = ["i", "ii", "iii", "iv", "v", "vi", "vii", "viii", "ix", "x", "xi", "xii"]
    book = _book(tmp_path, labels=labels, words=len(labels) * 6000)
    assert _first(book) == "PDF"


def test_a_dense_page_still_counts(tmp_path):
    labels = [str(n) for n in range(1, 13)]
    book = _book(tmp_path, labels=labels, words=len(labels) * 1300)
    assert _first(book) == "EPUB"


def test_labels_that_name_no_page_do_not_count(tmp_path):
    book = _book(tmp_path, labels=[f"Kapitel {n}" for n in range(20)])
    assert _first(book) == "PDF"


def test_an_epub_without_page_list_stays_behind_the_pdf(tmp_path):
    assert _first(_book(tmp_path)) == "PDF"


def test_a_broken_epub_stays_behind_the_pdf(tmp_path):
    (tmp_path / "Buch.pdf").write_bytes(b"%PDF-1.4")
    (tmp_path / "Buch.epub").write_bytes(b"not a zip")
    assert _first(tmp_path) == "PDF"
    assert not epub_outranks_pdf(tmp_path / "Buch.epub")


def test_the_calibre_adapter_reads_the_same_file(tmp_path):
    from src.adapters.calibre_adapter import CalibreAdapter

    adapter = CalibreAdapter.__new__(CalibreAdapter)
    adapter._library_path = tmp_path
    (tmp_path / "A").mkdir()
    _book(tmp_path / "A", meta="<dc:publisher>Project Gutenberg</dc:publisher>")
    assert adapter._find_primary_file("A").suffix == ".epub"


def test_batch_index_follows_the_library_order_unless_a_format_is_forced(tmp_path):
    from scripts.batch_index import _select_best_format as select

    formats = discover_formats(_book(tmp_path, meta="<dc:source>gutenberg.org</dc:source>"))
    assert select(formats)["format"] == "EPUB"
    assert select(formats, "pdf")["format"] == "PDF"
