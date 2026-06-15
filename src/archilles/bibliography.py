"""Shared bibliography formatters (BibTeX / RIS / EndNote / CSV).

A single implementation that operates on *normalized* book dicts, so the same
code serves both the Calibre ``metadata.db`` path (``calibre_analyzer``) and
the ``SourceAdapter`` path (``server``). Previously each path carried its own
divergent copy (finding 5.11; the ``str`` vs ``int`` year drift was 5.2).

Normalized book dict keys:
    id          int | str
    title       str
    authors     list[str]
    year        int | None
    publisher   str            (optional, "" if absent)
    identifiers dict           (optional; ISBN read from ``identifiers['isbn']``)
    tags        list[str]      (optional)
    formats     list[str]      (optional; used by CSV only)
"""

from __future__ import annotations

import csv
from io import StringIO


def format_bibtex(books: list[dict]) -> str:
    entries = []
    for b in books:
        last = b['authors'][0].split()[-1] if b['authors'] else 'Unknown'
        yr = str(b['year']) if b['year'] else 'NODATE'
        key = ''.join(c for c in b['title'][:20] if c.isalnum())
        cite = f"{last}{yr}{key}"
        e = f"@book{{{cite},\n  title = {{{b['title']}}},\n"
        if b['authors']:
            e += f"  author = {{{' and '.join(b['authors'])}}},\n"
        if b['year']:
            e += f"  year = {{{b['year']}}},\n"
        if b.get('publisher'):
            e += f"  publisher = {{{b['publisher']}}},\n"
        if b.get('identifiers', {}).get('isbn'):
            e += f"  isbn = {{{b['identifiers']['isbn']}}},\n"
        if b.get('tags'):
            e += f"  keywords = {{{', '.join(b['tags'])}}},\n"
        e += "}"
        entries.append(e)
    return '\n\n'.join(entries)


def format_ris(books: list[dict]) -> str:
    entries = []
    for b in books:
        e = "TY  - BOOK\n"
        e += f"TI  - {b['title']}\n"
        for a in b['authors']:
            e += f"AU  - {a}\n"
        if b['year']:
            e += f"PY  - {b['year']}\n"
        if b.get('publisher'):
            e += f"PB  - {b['publisher']}\n"
        if b.get('identifiers', {}).get('isbn'):
            e += f"SN  - {b['identifiers']['isbn']}\n"
        for t in b.get('tags', []):
            e += f"KW  - {t}\n"
        e += "ER  - "
        entries.append(e)
    return '\n\n'.join(entries)


def format_endnote(books: list[dict]) -> str:
    entries = []
    for b in books:
        e = "%0 Book\n"
        e += f"%T {b['title']}\n"
        for a in b['authors']:
            e += f"%A {a}\n"
        if b['year']:
            e += f"%D {b['year']}\n"
        if b.get('publisher'):
            e += f"%I {b['publisher']}\n"
        if b.get('identifiers', {}).get('isbn'):
            e += f"%@ {b['identifiers']['isbn']}\n"
        for t in b.get('tags', []):
            e += f"%K {t}\n"
        entries.append(e)
    return '\n\n'.join(entries)


def format_csv(books: list[dict]) -> str:
    out = StringIO()
    w = csv.writer(out)
    w.writerow(['ID', 'Title', 'Authors', 'Year', 'Publisher', 'ISBN', 'Tags', 'Formats'])
    for b in books:
        w.writerow([
            b['id'],
            b['title'],
            '; '.join(b['authors']),
            b['year'] or '',
            b.get('publisher', ''),
            b.get('identifiers', {}).get('isbn', ''),
            '; '.join(b.get('tags', [])),
            '; '.join(b.get('formats', [])),
        ])
    return out.getvalue()


BIB_FORMATTERS = {
    'bibtex':  format_bibtex,
    'ris':     format_ris,
    'endnote': format_endnote,
    'csv':     format_csv,
}
