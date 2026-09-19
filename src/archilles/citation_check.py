"""Does the quotation still stand where the citation says it does?

A citation into a volume is an address (prepared-format spec §4.7): the
volume, the printed page, which occurrence of that page where a label repeats,
and a short run of the passage's own wording. The wording is the check, not
the pointer -- where the page no longer carries it, the address is *stale* and
is reported as such. It is never repaired by searching the rest of the volume;
at most the neighbouring pages are offered as a **proposal**, marked as one.

``verify_citation`` answers that question against the strongest witness it can
reach:

- the **bundle**, where the volume has one. Its master is the text Scriptor
  produced, with the page markers the address speaks about, and its pagination
  sidecar says who placed each label (printed, computed, catalogue, §6.3). The
  resolution itself is Scriptor's ``Bundle.locate``: one implementation of the
  match, not a second copy of the grammar.
- the **index**, where it has none. The chunks of the volume carry a page
  label each; the wording is looked for in the chunk's text, then in its
  window. This is the weaker witness -- a chunk boundary can cut a wording in
  half -- and it is named as such in the answer.

Nothing here is a silent repair. ``relocated`` is an answer, not a correction:
the address that was asked about travels back unchanged, and where the passage
was actually found stands beside it as ``proposal``.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from scriptor.document import MIN_WORDING_WORDS, blind, find_snippet, load_bundle

from src.archilles.book_files import bundle_master

logger = logging.getLogger(__name__)

# How many chunks of a volume the index branch reads. It is the fallback for
# volumes without a bundle, and it loads text and window_text, so it is capped:
# a volume with more chunks than this is one whose bundle should exist.
_INDEX_CHUNK_LIMIT = 10_000


def _answer(address: dict[str, Any], status: str, **fields: Any) -> dict[str, Any]:
    """One shape for every answer, so a client can read them all the same way."""
    out: dict[str, Any] = {
        "status": status,
        "address": address,
        "checked_against": None,   # 'bundle' | 'index' -- which witness answered
        "label_source": None,      # the witness behind the page label (§6.3)
        "proposal": None,          # where the wording does stand, if elsewhere
        "ambiguous": False,        # the page carries the wording more than once
        "page_found": None,        # does the volume have that page at all
        "chunk_id": None,          # a cache, never an anchor
        "chunk_stale": None,       # the chunk_id given no longer holds the quote
        "note_checked": False,     # the note branch waits for the notes sidecar
    }
    out.update(fields)
    return out


def _too_short(quote: str) -> int | None:
    """How many words the quote has, where that is under the minimum."""
    words = len(blind(quote)[0].split())
    return words if words < MIN_WORDING_WORDS else None


def _from_bundle(bundle, address: dict[str, Any], page: str, quote: str,
                 occurrence: int, **fields: Any) -> dict[str, Any]:
    """The bundle's answer: found on that page, found near it, or stale."""
    common = dict(fields, checked_against="bundle",
                  page_found=bundle.page_text(page, occurrence) is not None)
    found = bundle.locate(quote, page=page, occurrence=occurrence)
    if found is not None:
        return _answer(address, "confirmed", label_source=found.label_source,
                       ambiguous=found.ambiguous, **common)
    near = bundle.nearest(quote, page, occurrence)
    if near is not None:
        return _answer(address, "relocated", label_source=near.label_source,
                       ambiguous=near.ambiguous,
                       proposal={"page": near.page, "occurrence": near.occurrence},
                       **common)
    return _answer(address, "stale", **common)


def _in_chunk(chunk: dict[str, Any], quote: str) -> bool:
    """Is the quote in this chunk's text, or in the window around it?

    The window is read too because a chunk boundary can fall inside a sentence
    -- that is the index branch's weakness, not the address's.
    """
    return any(find_snippet(chunk.get(field) or "", quote) is not None
               for field in ("text", "window_text"))


def _page_of(chunk: dict[str, Any]) -> str:
    return str(chunk.get("page_label") or chunk.get("page_number") or "")


def _hits(chunks: list[dict[str, Any]], quote: str) -> tuple[list, list]:
    """(chunks whose own text holds the quote, chunks whose window does).

    Kept apart because the windows overlap: a passage stands in the window of
    the chunks on either side of it as well, so counting those as separate
    places would call almost every citation ambiguous.
    """
    own = [c for c in chunks if find_snippet(c.get("text") or "", quote) is not None]
    seen = {id(c) for c in own}      # by identity: a chunk row holds numpy values
    near = [c for c in chunks
            if id(c) not in seen
            and find_snippet(c.get("window_text") or "", quote) is not None]
    return own, near


def _from_index(store, address: dict[str, Any], book_id: str, page: str,
                quote: str, **fields: Any) -> dict[str, Any]:
    """The index's answer, for a volume without a bundle.

    The index knows no occurrence: a chunk carries one page label, and where a
    volume repeats a label its chunks are indistinguishable. The answer names
    the chunk the wording was found in, as a cache.
    """
    chunks = store.get_by_book_id(book_id, limit=_INDEX_CHUNK_LIMIT)
    on_page: list[dict[str, Any]] = []
    elsewhere: list[dict[str, Any]] = []
    for chunk in chunks:
        (on_page if _page_of(chunk) == page else elsewhere).append(chunk)
    common = dict(fields, checked_against="index", page_found=bool(on_page))

    own, near = _hits(on_page, quote)
    if own or near:
        return _answer(address, "confirmed", chunk_id=(own or near)[0].get("id"),
                       label_source=(own or near)[0].get("label_source") or None,
                       ambiguous=len(own) > 1, **common)

    own, near = _hits(elsewhere, quote)
    if own or near:
        first = (own or near)[0]
        return _answer(address, "relocated", chunk_id=first.get("id"),
                       label_source=first.get("label_source") or None,
                       ambiguous=len(own) > 1,
                       proposal={"page": _page_of(first) or None, "occurrence": 1},
                       **common)
    return _answer(address, "stale", **common)


def verify_citation(store, archilles_dir: str | Path | None, book_id: str,
                    page: str, quote: str, occurrence: int = 1,
                    note: int | None = None,
                    chunk_id: str | None = None) -> dict[str, Any]:
    """Check one citation against the volume it names. See the module docstring.

    ``store`` is the chunk store (existence of the volume, and the index
    branch); ``archilles_dir`` the library's extension zone, where bundles lie.
    ``note`` is accepted and not yet checked -- the notes sidecar (§6.6) is not
    built, and answering ``note_checked: False`` is the honest form of that.
    """
    page = str(page)
    address = {"book_id": book_id, "page": page, "occurrence": occurrence,
               "quote": quote, "note": note}

    short = _too_short(quote)
    if short is not None:
        return _answer(address, "quote_too_short",
                       error=f"a quotation carries at least {MIN_WORDING_WORDS} "
                             f"words to address a passage, this one {short}")

    if not store.get_by_book_id(book_id, limit=1):
        return _answer(address, "unknown_volume")

    stale_cache: bool | None = None
    if chunk_id:
        # An id that still exists proves nothing: 80 to 97 per cent of chunk
        # ids point at other text after a re-chunking (P-M2). So the chunk is
        # asked whether it holds the quotation, not whether it exists.
        chunk = store.get_by_id(chunk_id)
        stale_cache = chunk is None or not _in_chunk(chunk, quote)

    master = bundle_master(Path(archilles_dir), book_id) if archilles_dir else None
    bundle = None
    if master is not None:
        try:
            bundle = load_bundle(master)
        except ValueError as e:      # a sidecar version this reader cannot read
            logger.warning("verify_citation: bundle of %s unreadable (%s)", book_id, e)
    if bundle is not None:
        return _from_bundle(bundle, address, page, quote, occurrence,
                            chunk_stale=stale_cache)
    return _from_index(store, address, book_id, page, quote,
                       chunk_stale=stale_cache)
