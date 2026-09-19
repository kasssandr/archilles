"""The context head: where a chunk stands, prepended to what it says.

A chunk of a book carries a sentence and no idea which chapter it belongs to.
The embedding therefore sees "Vielmehr ging es um die Aneignung der Form" with
nothing around it, and a question phrased in the vocabulary of the chapter --
which is how people ask -- has only the sentence to match against.

The head is that context, written in front of the text *for the embedding
only*: ``Chapter › Section\\n\\ntext``. It never enters the stored ``text``,
and that is the whole point of keeping it separate:

- the stored text is what a reader is shown and what a citation is checked
  against; a head in it would be words the book does not print on that page;
- BM25 counts terms, so a chapter title repeated in front of every chunk of
  that chapter would skew keyword search towards long chapters;
- the retrieved passage goes into a prompt, where the heading would appear a
  second time beside the citation metadata.

Whether it is written at all is an index-wide decision (``IndexRecipe.
context_head``), because it changes the vector and thus what the index *is*:
two books embedded under different settings cannot be compared. It is off
until the measurement decides (P-M1, four arms: chapter boundaries alone, with
the head, and with a deliberately wrong head as the control -- an arm that
wins with the wrong head has measured length, not context).
"""
from __future__ import annotations

from typing import Any, Mapping

__all__ = ["context_head", "embed_text_for"]

SEPARATOR = " › "


def context_head(meta: Mapping[str, Any]) -> str:
    """``Chapter › Section`` from a chunk's metadata, or "" where neither is set.

    Empty parts fall away rather than leaving a dangling separator; the book's
    title and author are deliberately not part of it -- they are the same for
    every chunk of a volume and would tell the vector nothing.
    """
    parts = [str(meta.get(key)).strip() for key in ("chapter", "section_title")
             if meta.get(key)]
    return SEPARATOR.join(p for p in parts if p)


def embed_text_for(chunk: Mapping[str, Any], enabled: bool) -> str | None:
    """The text to embed for ``chunk``, or None to embed its text unchanged.

    None rather than the text itself, so that a caller can tell "no head" from
    "a head that happens to be empty" and store the field only where there is
    something to store.
    """
    if not enabled:
        return None
    head = context_head(chunk.get("metadata") or chunk)
    text = chunk.get("text") or ""
    return f"{head}\n\n{text}" if head and text else None
