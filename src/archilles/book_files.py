"""The files a book consists of in a library: its formats, and its Scriptor bundle.

``discover_formats`` is the one place that lists a Calibre book folder; the
watchdog and batch_index each kept a copy of it.

``bundle_master`` finds a book's prepared text. A Scriptor bundle lies in the
library's extension zone (ADR-005), ``<library>/.archilles/scriptor/<key>/``
(see ``bundle_key``). It is not another format of the book: the
book file stays the book's identity -- Calibre metadata, viewer annotations
(keyed by the file's path) and links follow it -- and only the text is read
from the bundle, where indexing extracts (Naht S4).
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
from pathlib import Path

from scriptor.reflow.regions import read_metadata_block

from src.archilles.constants import PREFERRED_FORMATS

logger = logging.getLogger(__name__)

_PREFERRED_FORMAT_SET = frozenset(PREFERRED_FORMATS)

# Characters that are invalid in Windows filenames (superset of POSIX).
_UNSAFE_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

BUNDLE_FOLDER = 'scriptor'
# A numeric book id is padded to this width so the bundle folders sort in id
# order in any file listing. Five digits carry every id below 100.000.
BUNDLE_KEY_DIGITS = 5
_NUMERIC_ID = re.compile(r'^[0-9]+$')
_MASTER_SUFFIXES = frozenset({'.md', '.markdown'})
_REVIEW_SUFFIX = '.review.md'
# Enough for the metadata block, which opens a master (spec §4.1).
_SNIFF_BYTES = 4096


def prepared_jsonl_name(book_id: str) -> str:
    """Filename for a book's prepared-chunks JSONL (one file per book).

    Keyed by the adapter-unique ``book_id``, not ``calibre_id`` — non-Calibre
    sources (Zotero keys, folder ids) have no Calibre id, so every item used
    to collide on ``0.jsonl`` and only one book per library ever got prepared
    (review 2026-07-03, finding 5.1). For Calibre books ``book_id`` is the
    numeric id as a string, so existing ``{calibre_id}.jsonl`` corpora keep
    matching.

    Filesystem-unsafe characters are replaced; whenever sanitisation changes
    the name (or empties it), a short hash of the original id is appended so
    distinct ids ("a/b" vs "a_b") cannot map to the same file.
    """
    original = str(book_id)
    safe = _UNSAFE_FILENAME_CHARS.sub('_', original).strip(' .')
    if not safe or safe != original:
        digest = hashlib.md5(original.encode('utf-8')).hexdigest()[:8]
        safe = f"{safe or 'book'}-{digest}"
    return f"{safe}.jsonl"


# An EPUB's page list names the printed pages; fewer than this many do not
# carry a book's citations.
MIN_PAGE_LIST_LABELS = 10
_GUTENBERG = re.compile(rb'gutenberg\.org|Project Gutenberg', re.IGNORECASE)
_NCX_LABEL = re.compile(r'<pageTarget\b.*?<text>(.*?)</text>', re.S | re.I)
_NAV_PAGE_LIST = re.compile(r'<nav\b[^>]*page-list.*?</nav>', re.S | re.I)
_NAV_LABEL = re.compile(r'<a\b[^>]*>(.*?)</a>', re.S | re.I)
_TAG = re.compile(r'<[^>]+>')
_epub_verdicts: dict[tuple, bool] = {}


def epub_outranks_pdf(epub_path) -> bool:
    """Whether a book's EPUB is indexed before its PDF.

    It is when it states the printed pages -- a page list with readable labels,
    read by the extractor's own rule -- or when it is a Project Gutenberg text,
    proofread against the page images. Either way the EPUB gives the text
    a PDF has to be read for, and its structure besides. Cached per file
    state: this runs on every watchdog scan.
    """
    try:
        st = os.stat(epub_path)
    except OSError:
        return False
    key = (str(epub_path), st.st_mtime_ns, st.st_size)
    if key not in _epub_verdicts:
        _epub_verdicts[key] = _read_epub_verdict(epub_path)
    return _epub_verdicts[key]


def _read_epub_verdict(epub_path) -> bool:
    import zipfile

    from src.extractors.epub_extractor import _page_label

    try:
        with zipfile.ZipFile(epub_path) as z:
            names = [n for n in z.namelist() if n.lower().endswith(('.opf', '.ncx', '.xhtml', '.html', '.htm'))]
            package = b''.join(z.read(n) for n in names if n.lower().endswith('.opf'))
            if _GUTENBERG.search(package):
                return True
            labels = 0
            for name in names:
                data = z.read(name)
                if b'pageTarget' not in data and b'page-list' not in data:
                    continue
                text = data.decode('utf-8', errors='replace')
                found = _NCX_LABEL.findall(text)
                for nav in _NAV_PAGE_LIST.findall(text):
                    found += _NAV_LABEL.findall(nav)
                labels += sum(1 for t in found if _page_label(_TAG.sub('', t)))
                if labels >= MIN_PAGE_LIST_LABELS:
                    return True
    except (OSError, zipfile.BadZipFile, KeyError):
        return False
    return False


def discover_formats(book_dir: Path) -> list[dict[str, str]]:
    """The book files in ``book_dir``, in PREFERRED_FORMATS order.

    The one exception: an EPUB that outranks the PDF (``epub_outranks_pdf``)
    comes first.

    One directory scan instead of one glob per extension -- this runs for
    every library book on every watchdog scan.
    """
    by_ext: dict[str, list[str]] = {}
    try:
        with os.scandir(book_dir) as it:
            for entry in it:
                if not entry.is_file():
                    continue
                suffix = os.path.splitext(entry.name)[1].lower()
                if suffix in _PREFERRED_FORMAT_SET:
                    by_ext.setdefault(suffix, []).append(entry.path)
    except OSError:
        return []
    order = list(PREFERRED_FORMATS)
    epubs = by_ext.get('.epub', ())
    if '.pdf' in by_ext and any(epub_outranks_pdf(p) for p in epubs):
        order.remove('.epub')
        order.insert(order.index('.pdf'), '.epub')
    return [
        {'format': ext[1:].upper(), 'path': path}
        for ext in order
        for path in sorted(by_ext.get(ext, ()))
    ]


def is_scriptor_master(file_path: Path) -> bool:
    """A Markdown file whose metadata block names a ``format_version``.

    The detected format cannot tell: python-magic calls a master text/plain,
    like any note. The block can, and it opens the file (spec §4.1).
    """
    file_path = Path(file_path)
    if file_path.suffix.lower() not in _MASTER_SUFFIXES:
        return False
    try:
        with open(file_path, 'rb') as f:
            head = f.read(_SNIFF_BYTES)
    except OSError:
        return False
    block = read_metadata_block(head.decode('utf-8', errors='replace').replace('\r\n', '\n'))
    return bool(block and block.get('format_version'))


def bundle_key(book_id: str) -> str:
    """The folder name a book's bundle lies under.

    A numeric id is zero-padded to five digits, so a listing of the bundle
    folder sorts the way the library does: book 150 is ``00150``, not ``150``
    sitting between ``1499`` and ``1500``. An id that is not a number (a Zotero
    key, a folder id) keeps the filesystem-safe form the prepared JSONL uses --
    there is no order to preserve there.
    """
    text = str(book_id)
    if _NUMERIC_ID.match(text):
        return text.zfill(BUNDLE_KEY_DIGITS)
    return prepared_jsonl_name(text)[:-len('.jsonl')]


def bundle_dir(archilles_dir: Path, book_id: str) -> Path:
    """Where the bundle of ``book_id`` lies, whether or not it exists."""
    return Path(archilles_dir) / BUNDLE_FOLDER / bundle_key(book_id)


def bundle_master(archilles_dir: Path, book_id: str) -> Path | None:
    """The master of the book's bundle, or None.

    A master is a Markdown file there that declares a format_version and is
    not the review copy (which declares one too). Two of them are refused and
    named rather than chosen between: which of them was meant is not this
    function's to guess.
    """
    folder = bundle_dir(archilles_dir, book_id)
    if not folder.is_dir():
        return None
    masters = [
        p for p in sorted(folder.iterdir())
        if p.is_file() and not p.name.lower().endswith(_REVIEW_SUFFIX) and is_scriptor_master(p)
    ]
    if len(masters) > 1:
        logger.warning("Scriptor bundle %s holds %d masters (%s) -- none is used",
                       folder, len(masters), ", ".join(p.name for p in masters))
        return None
    return masters[0] if masters else None
