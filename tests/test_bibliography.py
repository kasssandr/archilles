"""Tests for the shared bibliography formatters (finding 5.11).

These encode the *canonical* behaviour on normalized book dicts, which both
the Calibre metadata.db path (calibre_analyzer) and the SourceAdapter path
(server) must produce. Previously each path had its own divergent copy.
"""

import csv
import json
import sqlite3
import textwrap
from io import StringIO

import pytest

from src.archilles.bibliography import (
    BIB_FORMATTERS,
    format_bibtex,
    format_ris,
    format_endnote,
    format_csv,
)
from src.calibre_mcp.calibre_analyzer import CalibreAnalyzer, _year_from_pubdate


@pytest.fixture
def book():
    """A fully-populated normalized book dict."""
    return {
        'id': 42,
        'title': 'The Origins of Totalitarianism',
        'authors': ['Hannah Arendt', 'Co Author'],
        'year': 1951,
        'publisher': 'Schocken Books',
        'identifiers': {'isbn': '9780805242256'},
        'tags': ['History', 'Politics'],
        'formats': ['EPUB', 'PDF'],
    }


@pytest.fixture
def sparse_book():
    """Minimal book: no authors, no year, no publisher, no isbn, no tags."""
    return {
        'id': 7,
        'title': 'Untitled',
        'authors': [],
        'year': None,
        'publisher': '',
        'identifiers': {},
        'tags': [],
        'formats': [],
    }


# ── BibTeX ──────────────────────────────────────────────────────────────

def test_bibtex_full(book):
    out = format_bibtex([book])
    # cite key: <lastname><year><alnum title[:20]>
    assert out.startswith('@book{Arendt1951TheOriginsofTotal,')
    assert 'title = {The Origins of Totalitarianism},' in out
    assert 'author = {Hannah Arendt and Co Author},' in out
    assert 'year = {1951},' in out  # int rendered without quotes/decimals
    assert 'publisher = {Schocken Books},' in out
    assert 'isbn = {9780805242256},' in out
    assert 'keywords = {History, Politics},' in out
    assert out.rstrip().endswith('}')


def test_bibtex_sparse_uses_fallbacks(sparse_book):
    out = format_bibtex([sparse_book])
    assert '@book{UnknownNODATEUntitled,' in out
    assert 'author' not in out
    assert 'year' not in out
    assert 'publisher' not in out
    assert 'isbn' not in out
    assert 'keywords' not in out


def test_bibtex_multiple_books_separated_by_blank_line(book, sparse_book):
    out = format_bibtex([book, sparse_book])
    assert '\n\n' in out
    assert out.count('@book{') == 2


# ── RIS ─────────────────────────────────────────────────────────────────

def test_ris_full(book):
    out = format_ris([book])
    assert 'TY  - BOOK' in out
    assert 'TI  - The Origins of Totalitarianism' in out
    assert 'AU  - Hannah Arendt' in out
    assert 'AU  - Co Author' in out  # one AU line per author
    assert 'PY  - 1951' in out
    assert 'PB  - Schocken Books' in out
    assert 'SN  - 9780805242256' in out
    assert 'KW  - History' in out
    assert out.rstrip().endswith('ER  -')


def test_ris_sparse(sparse_book):
    out = format_ris([sparse_book])
    assert 'TY  - BOOK' in out
    assert 'AU  -' not in out
    assert 'PY  -' not in out
    assert 'PB  -' not in out
    assert 'SN  -' not in out


# ── EndNote ─────────────────────────────────────────────────────────────

def test_endnote_full(book):
    out = format_endnote([book])
    assert '%0 Book' in out
    assert '%T The Origins of Totalitarianism' in out
    assert '%A Hannah Arendt' in out
    assert '%A Co Author' in out
    assert '%D 1951' in out
    assert '%I Schocken Books' in out
    assert '%@ 9780805242256' in out
    assert '%K History' in out


# ── CSV ─────────────────────────────────────────────────────────────────

def test_csv_full(book):
    out = format_csv([book])
    rows = list(csv.reader(StringIO(out)))
    assert rows[0] == ['ID', 'Title', 'Authors', 'Year', 'Publisher',
                       'ISBN', 'Tags', 'Formats']
    assert rows[1] == [
        '42',
        'The Origins of Totalitarianism',
        'Hannah Arendt; Co Author',
        '1951',
        'Schocken Books',
        '9780805242256',
        'History; Politics',
        'EPUB; PDF',
    ]


def test_csv_sparse_year_empty(sparse_book):
    out = format_csv([sparse_book])
    rows = list(csv.reader(StringIO(out)))
    assert rows[1][3] == ''  # year None -> empty string, not "None"


# ── Registry dict ───────────────────────────────────────────────────────

def test_bib_formatters_dict():
    assert set(BIB_FORMATTERS) == {'bibtex', 'ris', 'endnote', 'csv'}
    assert BIB_FORMATTERS['bibtex'] is format_bibtex
    assert BIB_FORMATTERS['ris'] is format_ris
    assert BIB_FORMATTERS['endnote'] is format_endnote
    assert BIB_FORMATTERS['csv'] is format_csv


# ── pubdate -> year helper ──────────────────────────────────────────────

@pytest.mark.parametrize("pubdate,expected", [
    ("1951-03-02T00:00:00", 1951),
    ("2020-01-15", 2020),
    (None, None),
    ("", None),
    ("not-a-date", None),
])
def test_year_from_pubdate(pubdate, expected):
    assert _year_from_pubdate(pubdate) == expected


# ── Calibre analyzer path delegates to the shared formatters (5.11) ──────

def _minimal_calibre_db(path):
    """Build the subset of Calibre's schema that _get_books_batch reads."""
    conn = sqlite3.connect(path / "metadata.db")
    conn.executescript(textwrap.dedent("""\
        CREATE TABLE books (id INTEGER PRIMARY KEY, title TEXT, pubdate TEXT,
                            path TEXT, isbn TEXT, has_cover INTEGER DEFAULT 0);
        CREATE TABLE authors (id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE books_authors_link (id INTEGER PRIMARY KEY, book INT, author INT);
        CREATE TABLE publishers (id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE books_publishers_link (id INTEGER PRIMARY KEY, book INT, publisher INT);
        CREATE TABLE tags (id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE books_tags_link (id INTEGER PRIMARY KEY, book INT, tag INT);
        CREATE TABLE identifiers (id INTEGER PRIMARY KEY, book INT, type TEXT, val TEXT);
        CREATE TABLE data (id INTEGER PRIMARY KEY, book INT, format TEXT);
    """))
    conn.execute("INSERT INTO books (id, title, pubdate, path) VALUES "
                 "(1, 'The Origins of Totalitarianism', '1951-03-02T00:00:00', 'p')")
    conn.execute("INSERT INTO authors (id, name) VALUES (10, 'Hannah Arendt')")
    conn.execute("INSERT INTO books_authors_link (book, author) VALUES (1, 10)")
    conn.execute("INSERT INTO publishers (id, name) VALUES (10, 'Schocken Books')")
    conn.execute("INSERT INTO books_publishers_link (book, publisher) VALUES (1, 10)")
    conn.execute("INSERT INTO tags (id, name) VALUES (10, 'History')")
    conn.execute("INSERT INTO books_tags_link (book, tag) VALUES (1, 10)")
    conn.execute("INSERT INTO identifiers (book, type, val) VALUES (1, 'isbn', '9780805242256')")
    conn.execute("INSERT INTO data (book, format) VALUES (1, 'EPUB')")
    conn.commit()
    conn.close()


def test_analyzer_export_delegates_to_shared_bibtex(tmp_path):
    _minimal_calibre_db(tmp_path)
    with CalibreAnalyzer(tmp_path / "metadata.db") as a:
        result = a.export_bibliography(format='bibtex')
    data = result['data']
    assert result['book_count'] == 1
    # Canonical shared format: year as int, entry ends with '}' (not legacy '}\n')
    assert 'year = {1951},' in data
    assert 'author = {Hannah Arendt},' in data
    assert 'publisher = {Schocken Books},' in data
    assert data.rstrip().endswith('}')


def test_analyzer_export_json_has_int_year_and_inline_publisher(tmp_path):
    _minimal_calibre_db(tmp_path)
    with CalibreAnalyzer(tmp_path / "metadata.db") as a:
        result = a.export_bibliography(format='json')
    book = json.loads(result['data'])[0]
    assert book['year'] == 1951           # int, normalized from pubdate
    assert book['publisher'] == 'Schocken Books'  # inline, not a separate dict
    assert 'pubdate' not in book          # raw Calibre keys dropped


def test_analyzer_export_unsupported_format(tmp_path):
    _minimal_calibre_db(tmp_path)
    with CalibreAnalyzer(tmp_path / "metadata.db") as a:
        result = a.export_bibliography(format='xml')
    assert 'error' in result
