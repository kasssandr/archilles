"""
Annotation Writer — persists matched external annotations into LanceDB.

Bridges between AnnotationProvider output (list of `Annotation` objects with
`raw_metadata['asin']` etc.) plus BookMatcher results, and the existing
`chunks` table schema (chunk_type='annotation').

Idempotent per (calibre_id, annotation_source): existing annotations of the
same source for a Calibre book are deleted before new ones are inserted.
Highlights without text are skipped (positions alone are not retrievable).
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from pathlib import Path
from typing import Iterable

from src.archilles.annotation_providers.base import Annotation
from src.archilles.sqlite_ro import connect_readonly

logger = logging.getLogger(__name__)


def _load_calibre_extras(library: Path, calibre_ids: list[int]) -> dict[int, dict]:
    """Fetch tags + language for a set of calibre_ids in one query."""
    if not calibre_ids:
        return {}
    placeholders = ",".join("?" * len(calibre_ids))
    query = f"""
        SELECT b.id,
               (SELECT GROUP_CONCAT(t.name, ', ')
                  FROM tags t
                  JOIN books_tags_link btl ON btl.tag = t.id
                 WHERE btl.book = b.id) AS tags,
               (SELECT l.lang_code
                  FROM languages l
                  JOIN books_languages_link bll ON bll.lang_code = l.id
                 WHERE bll.book = b.id LIMIT 1) AS language
          FROM books b
         WHERE b.id IN ({placeholders})
    """
    out: dict[int, dict] = {}
    with connect_readonly(library / "metadata.db") as con:
        for cid, tags, lang in con.execute(query, calibre_ids):
            out[cid] = {"tags": tags or "", "language": lang or ""}
    return out


def _id_for_annotation(source: str, asin: str | None, cid: int, idx: int) -> str:
    """Stable per-annotation primary key."""
    if asin:
        return f"{source}_{asin}_note_{idx}"
    return f"{source}_cid{cid}_note_{idx}"


def write_annotations(
    matched: list[dict],
    library: Path,
    db_path: Path,
    *,
    device: str = "cpu",
    embedder=None,
    progress=print,
) -> tuple[int, int]:
    """Embed and persist matched annotations as ``chunk_type='annotation'``.

    Args:
        matched: List of dicts as produced by ``BookMatcher.match_batch`` —
                 each dict carries ``calibre_id``, ``calibre_title``,
                 ``calibre_author`` and the original ``annotation``.
        library: Calibre library path (for tag/language enrichment).
        db_path: LanceDB directory.
        device: Embedder device when building one ('cpu' or 'cuda').
        embedder: Optional pre-loaded BGEEmbedder. If omitted, creates a
                  bge-m3 instance.
        progress: Callable for per-book progress lines (default: print).

    Returns:
        (n_books_written, n_annotations_written)
    """
    # Finding 6.1: persist EVERY annotation that carries text — highlights
    # from My Clippings.txt etc. arrive with their full highlighted text and
    # were silently dropped by the old type=='note' filter. Only textless
    # entries (bare bookmarks/positions) are skipped, as documented.
    with_text = [
        m for m in matched if (m["annotation"].text or "").strip()
    ]
    if not with_text:
        return 0, 0

    # Group by calibre_id, preserving annotation order within each book
    by_book: dict[int, list[dict]] = {}
    for item in with_text:
        by_book.setdefault(item["calibre_id"], []).append(item)

    extras = _load_calibre_extras(library, list(by_book))

    if embedder is None:
        from src.archilles.embedders.bge import BGEEmbedder
        embedder = BGEEmbedder(model_name="bge-m3", device=device, batch_size=16)
        embedder.load_model()

    from src.storage.lancedb_store import LanceDBStore
    store = LanceDBStore(str(db_path))
    if store.table is None:
        raise RuntimeError(f"LanceDB table not found at {db_path}")

    n_books = 0
    n_total = 0
    now = datetime.now().isoformat()

    for cid, items in by_book.items():
        # Drop pre-existing annotations of this source for this Calibre book.
        source = items[0]["annotation"].source
        store.table.delete(
            f"calibre_id = {cid} AND chunk_type = 'annotation' "
            f"AND annotation_source = '{source}'"
        )

        def _body(a: Annotation) -> str:
            """Highlight text plus attached user note (if any)."""
            body = (a.text or "").strip()
            if a.note and a.note.strip():
                body = f"{body} | Note: {a.note.strip()}"
            return body

        bodies = [_body(m["annotation"]) for m in items]
        emb = embedder.embed_batch(bodies)
        embeddings = emb.embeddings

        cal_meta = extras.get(cid, {})
        chunks = []
        for i, m in enumerate(items):
            a: Annotation = m["annotation"]
            asin = (a.raw_metadata or {}).get("asin")
            annot_hash = hashlib.md5(
                f"{source}:{asin or cid}:{i}:{a.text}".encode("utf-8")
            ).hexdigest()
            chunks.append({
                "id": _id_for_annotation(source, asin, cid, i),
                "text": f"[ANNOTATION] {bodies[i]}",
                "book_id": str(cid),
                "book_title": m["calibre_title"],
                "author": m["calibre_author"],
                "calibre_id": cid,
                "tags": cal_meta.get("tags", ""),
                "language": cal_meta.get("language", ""),
                "chunk_index": -1000 - i,
                "chunk_type": "annotation",
                "annotation_type": a.type,
                "annotation_source": source,
                "annotation_hash": annot_hash,
                "page_number": a.page_number or 0,
                "format": source,
                "source_file": str(asin or ""),
                "indexed_at": now,
            })

        store.add_chunks(chunks, embeddings)
        progress(
            f"  [{cid}] {m['calibre_title'][:60]}: "
            f"wrote {len(chunks)} {source} note{'s' if len(chunks) != 1 else ''}"
        )
        n_books += 1
        n_total += len(chunks)

    return n_books, n_total


def annotation_dicts_for_matching(annotations: Iterable[Annotation]) -> list[dict]:
    """Build the dicts BookMatcher.match_batch expects from Annotation objects.

    Carries ``asin`` (from raw_metadata) so the matcher's ASIN stage can fire.
    """
    out: list[dict] = []
    for a in annotations:
        out.append({
            "title": a.book_title or "",
            "author": a.book_author,
            "asin": (a.raw_metadata or {}).get("asin"),
            "annotation": a,
        })
    return out
