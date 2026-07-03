"""
ARCHILLES Watchdog — Automatic Calibre→LanceDB sync scanner.

Detects three change types and dispatches accordingly:
  new_books          Calibre IDs present in metadata.db but absent from LanceDB
  metadata_changed   title / author / tags / comments / publisher changed
  annotations_changed  highlights or notes changed

Scan performance:
  * Metadata changes: SQLite read + LanceDB hash lookup, no book files opened.
  * Annotation changes: a (mtime_ns, size) signature for the book file and
    the Calibre-Viewer JSON sidecar is cached at
    ``<archilles_dir>/watchdog_annotation_cache.json``. On the *first* scan
    every PDF with native highlights is opened once via PyMuPDF to seed the
    cache; subsequent scans only reopen books whose signature changed, so
    repeat scans on a stable library finish in seconds.

Delta updates delegate to ArchillesRAG.index_book(), which already handles
smart partial re-indexing (metadata-only, annotations-only, or both).

Called from:
  scripts/watchdog.py  — standalone CLI (cron / Task Scheduler / direct)
  calibre_mcp/server.py — MCP tool `watchdog_scan` (Claude Routines)
"""

import json
import logging
import sqlite3
import time
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Book formats in order of preference (mirrors batch_index.py)
_PREFERRED_FORMATS = ['.pdf', '.epub', '.mobi', '.azw3', '.txt', '.md', '.txtz']

# Tags that exclude a book from indexing. The canonical list lives in
# ``src.archilles.config`` so every consumer (watchdog, batch_index, MCP
# tool, CLI) agrees; re-exported here for backward compatibility with
# existing imports.
from src.archilles.config import DEFAULT_EXCLUDED_TAGS  # noqa: E402, F401
from src.archilles.indexer import IndexingCheckpoint  # noqa: E402
from src.archilles.sqlite_ro import connect_readonly  # noqa: E402


def _discover_formats(book_path: Path) -> list[dict[str, str]]:
    return [
        {'format': ext[1:].upper(), 'path': str(f)}
        for ext in _PREFERRED_FORMATS
        for f in book_path.glob(f'*{ext}')
    ]


def _clean_html(html_text: str) -> str:
    """Strip HTML from Calibre comments -- delegiert an CalibreDB.clean_html (7.15)."""
    from src.calibre_db import CalibreDB
    return CalibreDB.clean_html(html_text)


def _calibre_metadata_for_hash(library_path: Path) -> dict[int, dict[str, Any]]:
    """
    Read the fields used by _compute_metadata_hash directly from Calibre's SQLite.

    Returns {calibre_id: {title, author, tags, comments, publisher}} for every
    book in the library.  No book files are opened — pure SQLite I/O.

    Author format matches CalibreAdapter: names joined with ' & ' in link-insertion
    order.  Comments are HTML-stripped to match CalibreDB.clean_html().
    """
    db_path = library_path / "metadata.db"
    if not db_path.exists():
        raise FileNotFoundError(f"Calibre metadata.db not found: {db_path}")

    conn = connect_readonly(db_path, row_factory=sqlite3.Row)
    try:
        rows = conn.execute("""
            SELECT
                books.id,
                books.title,
                books.path,
                (
                    SELECT GROUP_CONCAT(a2.name, ' & ')
                    FROM (
                        SELECT a2.name
                        FROM authors a2
                        INNER JOIN books_authors_link bal2
                            ON a2.id = bal2.author
                        WHERE bal2.book = books.id
                        ORDER BY bal2.id
                    ) a2
                ) AS author,
                comments.text                       AS comments,
                (
                    -- CHAR(31) (unit separator) instead of ',' so tags that
                    -- contain commas ("Blut, Bund, Buch") survive the split;
                    -- a comma split made the hash diverge permanently (7.3).
                    SELECT GROUP_CONCAT(t2.name, CHAR(31))
                    FROM tags t2
                    INNER JOIN books_tags_link btl2 ON t2.id = btl2.tag
                    WHERE btl2.book = books.id
                )                                   AS tags,
                publishers.name                     AS publisher,
                ratings.rating                      AS rating
            FROM books
            LEFT JOIN comments              ON books.id = comments.book
            LEFT JOIN books_publishers_link ON books.id = books_publishers_link.book
            LEFT JOIN publishers            ON books_publishers_link.publisher = publishers.id
            LEFT JOIN books_ratings_link    ON books.id = books_ratings_link.book
            LEFT JOIN ratings               ON books_ratings_link.rating = ratings.id
            GROUP BY books.id
        """).fetchall()
    finally:
        conn.close()

    result = {}
    for row in rows:
        cid = int(row['id'])
        raw_tags = row['tags'] or ''
        tags_list = sorted(t.strip() for t in raw_tags.split('\x1f') if t.strip())
        result[cid] = {
            'title':     row['title'] or '',
            'author':    row['author'] or '',
            'comments':  _clean_html(row['comments'] or ''),
            'tags':      tags_list,
            'publisher': row['publisher'] or '',
            'path':      str(library_path / row['path']),
            'rating':    row['rating'] or 0,
        }
    return result


def _compute_metadata_hash(meta: dict[str, Any]) -> str:
    """Delegiert an src.archilles.hashing (Befund 7.15).

    Bleibt als Modulfunktion erhalten: backfill_metadata_hash und die Tests
    importieren ``from src.archilles.watchdog import _compute_metadata_hash``.
    """
    from src.archilles.hashing import compute_metadata_hash
    return compute_metadata_hash(meta)


def _index_priority_key(
    entry: dict,
    calibre_books: dict,
    first_authors: list[str],
    first_tags: list[str],
    first_titles: list[str],
) -> tuple[int, int, int]:
    """Sort key for new-book / fulltext-backlog indexing order.

    Returns (group, rating_order, recency) where:
      group 0 = explicit priority match (first_authors / first_tags / first_titles)
      group 1 = normal queue

    Within each group, rating order favours only the top two tiers:
      5★ = 0, 4★ = 1, everything else (3★, unrated, 1–2★) = 2.
    Calibre stores ratings as 2/4/6/8/10; NULL → 0 (unrated).

    Final tiebreaker is recency: most recently added book first. Calibre IDs
    increase monotonically with add order, so -calibre_id puts the newest book
    ahead. This is what lets freshly added titles overtake the old backlog
    instead of sinking to the bottom by ID.
    """
    meta = calibre_books.get(entry['calibre_id'], {})
    rating = meta.get('rating') or 0

    is_priority = False
    if first_authors:
        author_lc = meta.get('author', '').lower()
        is_priority = any(a.lower() in author_lc for a in first_authors)
    if not is_priority and first_tags:
        tags_lc = {t.lower() for t in meta.get('tags', [])}
        is_priority = any(t.lower() in tags_lc for t in first_tags)
    if not is_priority and first_titles:
        title_lc = meta.get('title', '').lower()
        is_priority = any(t.lower() in title_lc for t in first_titles)

    if rating >= 10:   rating_order = 0  # 5★
    elif rating >= 8:  rating_order = 1  # 4★
    else:              rating_order = 2  # 3★, unrated, 1–2★ — all equal

    return (0 if is_priority else 1, rating_order, -entry['calibre_id'])


def _resolve_execution_plan(library_path: Path):
    """Resolve the ExecutionPlan for a library (Hardware-Tiers-V2 §10.4).

    Same path as ``scripts/batch_index.resolve_indexing_plan``: ``get_mode()``
    over ``config.json``, ``detect_hardware()``, and the canonical
    ``IndexRecipe`` fed to the pure ``plan()``. Centralising it here lets the
    watchdog index new titles with the same chunk schema as the bulk indexer
    instead of the old flat default ("neue Titel werden flach indexiert").
    """
    from src.archilles.config import get_mode
    from src.archilles.execution import plan
    from src.archilles.hardware import detect_hardware
    from src.archilles.recipe import default_recipe

    mode = get_mode(Path(library_path))
    return plan(detect_hardware(), default_recipe(), mode)


class WatchdogScanner:
    """
    Idempotent scanner: safe to run multiple times; hash comparison skips
    books that have not changed.

    Parameters
    ----------
    library_path  Path to the Calibre library folder (contains metadata.db)
    db_path       Path to the LanceDB RAG database
    archilles_dir Path to the .archilles working directory (logs, queue, config)
    """

    def __init__(
        self,
        library_path: Path,
        db_path: str,
        archilles_dir: Path,
        excluded_tags: list[str] | None = None,
    ):
        self.library_path = library_path
        self.db_path = db_path
        self.archilles_dir = archilles_dir
        self.queue_file = archilles_dir / "index_queue.json"
        self.log_file = archilles_dir / "watchdog.log"
        self.checkpoint_file = archilles_dir / "index_new_checkpoint.json"
        self.fulltext_checkpoint_file = archilles_dir / "index_fulltext_checkpoint.json"
        self.annotation_cache_file = archilles_dir / "watchdog_annotation_cache.json"
        self.excluded_tags_lower: set[str] = {
            t.lower() for t in (excluded_tags if excluded_tags is not None else DEFAULT_EXCLUDED_TAGS)
        }
        self._annotation_cache: dict[str, dict[str, Any]] | None = None
        self._annotation_cache_dirty = False
        self._shutdown_requested = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def shutdown_requested(self) -> bool:
        """True once a graceful shutdown has been requested via :meth:`request_shutdown`."""
        return self._shutdown_requested

    def request_shutdown(self) -> None:
        """Signal that the current scan should stop after the currently-indexing book finishes.

        Mirrors :class:`scripts.safe_indexer.SafeIndexer` semantics so a user CTRL+C
        does not abort mid-write — the flag is consulted between books in both the
        Phase-2 (delta updates) and Phase-3 (new-book indexing) loops.
        """
        self._shutdown_requested = True

    def scan(
        self,
        dry_run: bool = False,
        queue_new: bool = True,
        index_new: bool = False,
        index_metadata_only: bool = False,
        index_fulltext_pending: bool = False,
        max_new: int | None = None,
        first_authors: list[str] | None = None,
        first_tags: list[str] | None = None,
        first_titles: list[str] | None = None,
        rating_filter: int | None = None,
    ) -> dict[str, Any]:
        """
        Run a full scan and return a results dict.

        Parameters
        ----------
        dry_run                Report changes only; do not modify LanceDB or queue.
        queue_new              Write new Calibre IDs to index_queue.json (default True).
        index_new              Index new books immediately via ArchillesRAG (full content).
        index_metadata_only    For new books: create a fast PHASE1_METADATA stub instead
                               of full content indexing.  Mutually exclusive with index_new.
        index_fulltext_pending Find books that have only PHASE1_METADATA stubs (no content
                               chunks) and index their full text.  This drains the backlog
                               of books that were previously stub-indexed.
        max_new                Cap on new books indexed via index_new or index_metadata_only.
                               Applies independently to index_fulltext_pending.
                               None = no limit (run until done or CTRL+C).
        first_authors          Substring list — books whose author matches come first.
        first_tags             Substring list — books carrying a matching tag come first.
        first_titles           Substring list — books whose title matches come first.
        rating_filter          Restrict the fulltext-pending backlog (Phase 4) to books
                               with exactly this star rating. 0 = unrated, 1–5 = N stars.
                               None = no restriction. Has no effect on other phases.

        Within each priority group, books are ordered by rating (5★, then 4★, then
        everything else) and then by recency (most recently added Calibre ID first).
        """
        t0 = time.time()
        results: dict[str, Any] = {
            'new_books':            [],
            'fulltext_pending':     [],  # phase1-stub books that need full content indexing
            'metadata_changed':    [],
            'annotations_changed': [],
            'unchanged':           [],
            'errors':              [],
            'delta_updates':       0,    # count of Phase-2 updates (metadata / annotations)
            'delta_time':          0.0,
            'new_indexed':         0,    # count of Phase-3 immediate new-book indexes
            'new_indexed_time':    0.0,
            'fulltext_indexed':    0,    # count of Phase-4 fulltext-pending indexes
            'fulltext_indexed_time': 0.0,
            'scanned':             0,
            'interrupted':         False,
        }

        # ── Phase 1: fast scan ─────────────────────────────────────────
        # Metadata path opens no files. Annotation path is cached by
        # (mtime_ns, size) signature; only books whose signature changed
        # since the last scan are reopened (see _annotation_changed).
        calibre_books = _calibre_metadata_for_hash(self.library_path)
        results['scanned'] = len(calibre_books)

        indexed_hashes = self._load_indexed_hashes()
        # Books in LanceDB that have only non-content chunks (phase1 stubs, annotations)
        phase1_only_ids: set[int] = {
            cid for cid, h in indexed_hashes.items()
            if not h.get('has_content', True)
        }

        for cid, meta in calibre_books.items():
            # Skip books carrying excluded tags (see config.get_excluded_tags)
            if self.excluded_tags_lower and any(
                t.lower() in self.excluded_tags_lower for t in meta.get('tags', [])
            ):
                continue

            book_path = Path(meta['path'])
            formats = _discover_formats(book_path)
            if not formats:
                continue  # no supported file on disk

            if cid not in indexed_hashes:
                results['new_books'].append({
                    'calibre_id': cid,
                    'title':      meta['title'],
                    'book_id':    str(cid),
                })
                continue

            stored = indexed_hashes[cid]
            stored_meta_hash = stored.get('metadata_hash', '')
            current_meta_hash = _compute_metadata_hash(meta)
            # Skip the comparison when no stored hash exists — we would produce
            # false positives for books indexed before hash tracking was added.
            # Use scripts/backfill_metadata_hash.py to populate missing hashes.
            meta_changed = bool(stored_meta_hash) and current_meta_hash != stored_meta_hash

            # Bidirectional annotation check: empty→nonempty (new annotations on
            # a previously unannotated book) AND nonempty→empty (annotations
            # cleared) both count as changes.
            stored_annot_hash = stored.get('annotation_hash', '')
            annot_changed = self._annotation_changed(
                file_path=Path(formats[0]['path']),
                stored_hash=stored_annot_hash,
            )

            if meta_changed:
                results['metadata_changed'].append(cid)
            if annot_changed:
                results['annotations_changed'].append(cid)

            if cid in phase1_only_ids:
                # Track for fulltext backlog; metadata/annotation changes handled in Phase 2
                results['fulltext_pending'].append({
                    'calibre_id': cid,
                    'title':      meta['title'],
                    'book_id':    str(cid),
                })
            elif not meta_changed and not annot_changed:
                results['unchanged'].append(cid)

        # ── Phase 2: apply delta updates ──────────────────────────────
        # When Phase 4 will drain the full backlog (index_fulltext_pending=True
        # without a max_new cap), phase1-only books will be re-indexed with
        # full content anyway — a Phase 2 stub refresh would just waste
        # embedding work that Phase 4 immediately overwrites.
        phase4_will_process_all_stubs = index_fulltext_pending and max_new is None
        books_to_update = (
            set(results['metadata_changed']) | set(results['annotations_changed'])
        )
        if phase4_will_process_all_stubs:
            books_to_update -= phase1_only_ids
        if books_to_update and not dry_run:
            rag = self._load_rag()
            dt0 = time.time()
            books_to_update_list = sorted(books_to_update)
            total_p2 = len(books_to_update_list)
            for i, cid in enumerate(books_to_update_list, 1):
                if self._shutdown_requested:
                    print(f"\n⏸️  Shutdown requested — phase 2 stopped after {i-1}/{total_p2} books.")
                    break
                meta = calibre_books.get(cid)
                if not meta:
                    continue
                formats = _discover_formats(Path(meta['path']))
                if not formats:
                    continue
                file_path = formats[0]['path']
                book_id = str(cid)
                print(f"\n[{i}/{total_p2}] {meta.get('author', '')}: {meta['title']}")
                try:
                    if cid in phase1_only_ids:
                        # Refresh phase1 stub with updated metadata — no full indexing
                        rag.index_book(file_path, book_id, phase='phase1')
                    else:
                        rag.index_book(file_path, book_id, force=False)
                    results['delta_updates'] += 1
                except Exception as exc:
                    logger.error(f"Delta update failed for calibre_id={cid}: {exc}")
                    results['errors'].append({'calibre_id': cid, 'error': str(exc)})
            results['delta_time'] = round(time.time() - dt0, 1)

        # ── Phase 3: handle new books ─────────────────────────────────
        new_ids = [b['calibre_id'] for b in results['new_books']]
        if new_ids and not dry_run:
            if queue_new:
                self._queue_new_books(new_ids)
            if index_new or index_metadata_only:
                rag = self._load_rag()
                # Hardware-Tiers-V2 §12: full-external has no local hierarchical
                # path here, so a new title is indexed *provisionally light* (flat,
                # local — _load_rag forced hierarchical off) and marked
                # pending_external; a later --prepare-pending-external run upgrades
                # it via external embedding. Only full-content indexing is marked —
                # phase1 metadata stubs are left to the fulltext path.
                mark_pending = not self._resolve_plan().embed_local
                ni0 = time.time()
                cp_new = IndexingCheckpoint.load(self.checkpoint_file)
                done_ids = {int(b) for b in cp_new.completed_books} if cp_new else set()
                pending = [e for e in results['new_books'] if e['calibre_id'] not in done_ids]
                pending.sort(key=lambda e: _index_priority_key(
                    e, calibre_books,
                    first_authors or [], first_tags or [], first_titles or [],
                ))
                already_done = len(done_ids)
                saved_total = cp_new.total_books if cp_new else 0
                total_p3 = max(saved_total, already_done + len(pending))
                if cp_new is None:
                    cp_new = IndexingCheckpoint.create_new(
                        self.checkpoint_file,
                        profile="",
                        book_ids=[str(e['calibre_id']) for e in pending],
                        phase="phase1" if index_metadata_only else "phase2",
                    )
                if max_new is not None:
                    pending = pending[:max_new]
                if already_done:
                    print(f"  (Resuming: {already_done} already done, {len(pending)} pending)")
                phase_label = "metadata stub" if index_metadata_only else "fulltext"
                for j, entry in enumerate(pending, 1):
                    if self._shutdown_requested:
                        print(
                            f"\n⏸️  Shutdown requested — phase 3 ({phase_label}) stopped after "
                            f"{already_done + j - 1}/{total_p3} books. "
                            f"Checkpoint preserved."
                        )
                        break
                    cid = entry['calibre_id']
                    meta = calibre_books.get(cid)
                    if not meta:
                        continue
                    formats = _discover_formats(Path(meta['path']))
                    if not formats:
                        continue
                    print(f"\n[{already_done + j}/{total_p3}] {meta.get('author', '')}: {entry['title']}")
                    try:
                        if index_metadata_only:
                            rag.index_book(formats[0]['path'], str(cid), phase='phase1')
                        else:
                            rag.index_book(formats[0]['path'], str(cid), force=False)
                            if mark_pending:
                                rag.store.mark_pending_external(str(cid))
                        results['new_indexed'] += 1
                        cp_new.complete_book(cid)
                    except Exception as exc:
                        logger.error(f"New-book indexing failed for calibre_id={cid}: {exc}")
                        results['errors'].append({'calibre_id': cid, 'error': str(exc)})
                        cp_new.fail_book(str(cid), str(exc))
                # Only clear the checkpoint when the run finished cleanly. On a
                # graceful shutdown we keep it so the next watchdog run resumes
                # exactly where this one stopped.
                if not self._shutdown_requested:
                    cp_new.delete()
                results['new_indexed_time'] = round(time.time() - ni0, 1)

        # ── Phase 4: fulltext-pending backlog ─────────────────────────
        # Index books that were previously stub-indexed (PHASE1_METADATA only)
        # but have no content chunks yet.  Runs when --index-fulltext-pending
        # is set; no max_new cap by default so the user can drain the full
        # backlog in one session (CTRL+C for graceful stop, checkpoint resumes).
        if index_fulltext_pending and results['fulltext_pending'] and not dry_run:
            rag = self._load_rag()
            # Hardware-Tiers-V2 §12: under full-external the drained stub becomes
            # flat (provisional light — _load_rag forced hierarchical off), so mark
            # it pending_external just like a Phase-3 new title.
            mark_pending = not self._resolve_plan().embed_local
            ft0 = time.time()
            cp_fulltext = IndexingCheckpoint.load(self.fulltext_checkpoint_file)
            done_ids = {int(b) for b in cp_fulltext.completed_books} if cp_fulltext else set()
            pending = [
                e for e in results['fulltext_pending']
                if e['calibre_id'] not in done_ids
            ]
            if rating_filter is not None:
                # Calibre stores stars on a 0–10 scale (N★ = N*2); unrated → 0.
                target = rating_filter * 2
                pending = [
                    e for e in pending
                    if (calibre_books.get(e['calibre_id'], {}).get('rating') or 0) == target
                ]
            pending.sort(key=lambda e: _index_priority_key(
                e, calibre_books,
                first_authors or [], first_tags or [], first_titles or [],
            ))
            already_done = len(done_ids)
            saved_total = cp_fulltext.total_books if cp_fulltext else 0
            total_p4 = max(saved_total, already_done + len(pending))
            if cp_fulltext is None:
                cp_fulltext = IndexingCheckpoint.create_new(
                    self.fulltext_checkpoint_file,
                    profile="",
                    book_ids=[str(e['calibre_id']) for e in pending],
                    phase="phase2",
                )
            if max_new is not None:
                pending = pending[:max_new]
            if already_done:
                print(f"  (Resuming fulltext: {already_done} already done, {len(pending)} pending)")
            for j, entry in enumerate(pending, 1):
                if self._shutdown_requested:
                    print(
                        f"\n⏸️  Shutdown requested — phase 4 (fulltext) stopped after "
                        f"{already_done + j - 1}/{total_p4} books. "
                        f"Checkpoint preserved."
                    )
                    break
                cid = entry['calibre_id']
                meta = calibre_books.get(cid)
                if not meta:
                    continue
                formats = _discover_formats(Path(meta['path']))
                if not formats:
                    continue
                print(f"\n[{already_done + j}/{total_p4}] {meta.get('author', '')}: {entry['title']}")
                try:
                    rag.index_book(formats[0]['path'], str(cid), force=False)
                    if mark_pending:
                        rag.store.mark_pending_external(str(cid))
                    results['fulltext_indexed'] += 1
                    cp_fulltext.complete_book(cid)
                except Exception as exc:
                    logger.error(f"Fulltext indexing failed for calibre_id={cid}: {exc}")
                    results['errors'].append({'calibre_id': cid, 'error': str(exc)})
                    cp_fulltext.fail_book(str(cid), str(exc))
            if not self._shutdown_requested:
                cp_fulltext.delete()
            results['fulltext_indexed_time'] = round(time.time() - ft0, 1)

        results['total_time'] = round(time.time() - t0, 1)
        results['interrupted'] = self._shutdown_requested

        if not dry_run:
            # Persist the annotation cache and write the log even on graceful
            # shutdown so the partial run is recorded and the next scan benefits
            # from the cached signatures.
            self._save_annotation_cache()
            self._write_log(results)

        return results

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_indexed_hashes(self) -> dict[int, dict[str, str]]:
        """Load stored hashes from LanceDB without loading the embedding model."""
        try:
            # Import lazily so the watchdog can be imported without heavy deps
            from src.archilles.engine import ArchillesRAG
            rag = ArchillesRAG(db_path=self.db_path, skip_model=True)
            return rag.store.get_hashes_for_indexed_books()
        except Exception as exc:
            logger.warning(f"Could not load indexed hashes: {exc}")
            return {}

    def _resolve_plan(self):
        """Resolve this library's ExecutionPlan (mode + detected hardware)."""
        return _resolve_execution_plan(Path(self.library_path))

    def _load_rag(self):
        """Load a full ArchillesRAG instance, wired to the Hardware-Tiers-V2 plan.

        The resolved ExecutionPlan drives batch size + device, and new titles use
        the plan's chunk schema. ``full-external`` has no local hierarchical path
        on the watchdog — its new titles are indexed *provisionally light* (flat,
        local) and marked ``pending_external`` for a later external batch embed
        (§12), so hierarchical is forced off whenever embedding is not local.
        """
        from src.archilles.engine import ArchillesRAG
        from src.archilles.config import get_languages
        ep = self._resolve_plan()
        hierarchical = ep.hierarchical and ep.embed_local
        return ArchillesRAG(
            db_path=self.db_path,
            languages=get_languages(Path(self.library_path)),
            execution_plan=ep,
            hierarchical=hierarchical,
        )

    def _annotation_files_signature(self, file_path: Path) -> list[int]:
        """Return a (book_mtime_ns, book_size, viewer_mtime_ns, viewer_size) tuple.

        The signature covers both annotation sources used by
        ``get_combined_annotations``: PDF-native annotations live inside the
        book file itself, while Calibre-Viewer highlights live in a sidecar
        JSON named after ``sha256(file_path)`` under
        ``get_annotations_dir()``. Missing files contribute zeros.

        Stored as a list (not tuple) so it round-trips through JSON.
        """
        from src.calibre_mcp.annotations import compute_book_hash, get_annotations_dir

        try:
            s = file_path.stat()
            book_sig = (s.st_mtime_ns, s.st_size)
        except OSError:
            book_sig = (0, 0)

        viewer_path = get_annotations_dir() / f"{compute_book_hash(str(file_path))}.json"
        try:
            s = viewer_path.stat()
            viewer_sig = (s.st_mtime_ns, s.st_size)
        except OSError:
            viewer_sig = (0, 0)

        return [book_sig[0], book_sig[1], viewer_sig[0], viewer_sig[1]]

    def _load_annotation_cache(self) -> dict[str, dict[str, Any]]:
        """Lazy-load the on-disk annotation cache (file → signature + computed hash)."""
        if self._annotation_cache is not None:
            return self._annotation_cache
        if self.annotation_cache_file.exists():
            try:
                self._annotation_cache = json.loads(
                    self.annotation_cache_file.read_text(encoding='utf-8')
                )
            except Exception as exc:
                logger.warning(f"Could not read annotation cache (resetting): {exc}")
                self._annotation_cache = {}
        else:
            self._annotation_cache = {}
        return self._annotation_cache

    def _save_annotation_cache(self) -> None:
        """Persist the annotation cache when it has been mutated this run."""
        if self._annotation_cache is None or not self._annotation_cache_dirty:
            return
        try:
            self.archilles_dir.mkdir(parents=True, exist_ok=True)
            self.annotation_cache_file.write_text(
                json.dumps(self._annotation_cache, indent=2),
                encoding='utf-8',
            )
            self._annotation_cache_dirty = False
        except Exception as exc:
            logger.warning(f"Could not save annotation cache: {exc}")

    def _annotation_changed(self, file_path: Path, stored_hash: str) -> bool:
        """Return True if the annotation hash for this book differs from what is stored.

        Compares bidirectionally: ``_compute_annotation_hash`` returns ``''``
        for an empty annotation list, so the comparison naturally detects both
        ``stored='' → current='abc'`` (first-time annotations) and
        ``stored='abc' → current=''`` (annotations cleared).

        Fast path: a (mtime_ns, size) signature for both the book file and the
        Calibre-Viewer JSON sidecar is cached on disk. When the signature
        matches the previous scan, the cached annotation hash is reused
        without opening the book. Cold path opens the book via
        ``get_combined_annotations(..., include_pdf=True)``, which matches the
        indexer's hash computation. Failures are logged and treated as
        "unchanged" so a transient error cannot spam the index with
        false-positive updates.
        """
        cache = self._load_annotation_cache()
        cache_key = str(file_path)
        sig = self._annotation_files_signature(file_path)

        cached = cache.get(cache_key)
        if cached and cached.get('sig') == sig:
            current_hash = cached.get('annotation_hash', '')
            return current_hash != stored_hash

        try:
            from src.calibre_mcp.annotations import get_combined_annotations
            from src.archilles.engine import ArchillesRAG
            result = get_combined_annotations(
                book_path=str(file_path),
                include_pdf=True,
                exclude_toc_markers=True,
                min_length=20,
            )
            current_hash = ArchillesRAG._compute_annotation_hash(
                result.get('annotations', [])
            )
        except Exception as exc:
            logger.warning(
                "Annotation check failed for %s: %s (assuming unchanged)",
                file_path, exc,
            )
            return False

        cache[cache_key] = {'sig': sig, 'annotation_hash': current_hash}
        self._annotation_cache_dirty = True
        return current_hash != stored_hash

    def _queue_new_books(self, calibre_ids: list[int]) -> None:
        existing: list[int] = []
        if self.queue_file.exists():
            try:
                existing = json.loads(self.queue_file.read_text(encoding='utf-8'))
            except Exception:
                pass
        merged = sorted(set(existing) | set(calibre_ids))
        self.archilles_dir.mkdir(parents=True, exist_ok=True)
        self.queue_file.write_text(json.dumps(merged, indent=2), encoding='utf-8')

    def _write_log(self, results: dict[str, Any]) -> None:
        ts = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
        n_new  = len(results['new_books'])
        n_meta = len(results['metadata_changed'])
        n_anno = len(results['annotations_changed'])
        n_unch = len(results['unchanged'])
        new_ids = [b['calibre_id'] for b in results['new_books']]
        lines = [
            f"{ts} SCAN completed in {results['total_time']}s",
            f"  new_books: {n_new}" + (f" {new_ids}" if new_ids else ""),
            f"  fulltext_pending: {len(results.get('fulltext_pending', []))}",
            f"  metadata_changed: {n_meta}"
            + (f" {results['metadata_changed']}" if n_meta else ""),
            f"  annotations_changed: {n_anno}"
            + (f" {results['annotations_changed']}" if n_anno else ""),
            f"  unchanged: {n_unch}",
            f"  errors: {len(results['errors'])}",
            f"  delta_updates: {results['delta_updates']}"
            + (f" completed in {results['delta_time']}s" if results['delta_updates'] else ""),
            f"  new_indexed: {results.get('new_indexed', 0)}"
            + (f" completed in {results.get('new_indexed_time', 0)}s" if results.get('new_indexed') else ""),
            f"  fulltext_indexed: {results.get('fulltext_indexed', 0)}"
            + (f" completed in {results.get('fulltext_indexed_time', 0)}s" if results.get('fulltext_indexed') else ""),
            "",
        ]
        self.archilles_dir.mkdir(parents=True, exist_ok=True)
        with open(self.log_file, 'a', encoding='utf-8') as fh:
            fh.write('\n'.join(lines) + '\n')


# ══════════════════════════════════════════════════════════════════
# Zotero Watchdog
# ══════════════════════════════════════════════════════════════════

_ZOTERO_EXCLUDED_TYPE_IDS = (1, 3, 27)  # annotation, attachment, note
_ZOTERO_INDEXABLE_CONTENT_TYPES = (
    "application/pdf",
    "application/epub+zip",
    "text/html",
    "text/plain",
)


def _zotero_metadata_for_scan(library_path: Path) -> dict[str, dict[str, Any]]:
    """Batch-read all Zotero items in one pass for watchdog scanning.

    Returns {item_key: {title, authors, tags, abstract, date, modified_at,
                         attachment_modified_at, has_attachment}}.
    Authors and tags are pre-sorted for stable hash computation.
    """
    db_path = library_path / "zotero.sqlite"
    if not db_path.exists():
        raise FileNotFoundError(f"zotero.sqlite not found in {library_path}")

    excluded = ",".join(str(t) for t in _ZOTERO_EXCLUDED_TYPE_IDS)
    conn = connect_readonly(db_path, immutable=True, row_factory=sqlite3.Row)
    try:
        items = conn.execute(f"""
            SELECT itemID, key, dateModified
            FROM items
            WHERE itemTypeID NOT IN ({excluded})
            AND itemID NOT IN (SELECT itemID FROM deletedItems)
        """).fetchall()

        if not items:
            return {}

        valid_ids = {r["itemID"] for r in items}
        id_to_key = {r["itemID"]: r["key"] for r in items}

        result: dict[str, dict[str, Any]] = {
            r["key"]: {
                "item_id": r["itemID"],
                "modified_at": r["dateModified"] or "",
                "title": "",
                "authors": [],
                "tags": [],
                "abstract": "",
                "date": "",
                "attachment_modified_at": None,
                "has_attachment": False,
            }
            for r in items
        }

        # EAV fields (title, abstract, date) — one query for all items
        field_rows = conn.execute("""
            SELECT id.itemID, f.fieldName, idv.value
            FROM itemData id
            JOIN itemDataValues idv ON id.valueID = idv.valueID
            JOIN fields f ON id.fieldID = f.fieldID
            WHERE f.fieldName IN ('title', 'shortTitle', 'abstractNote', 'date')
        """).fetchall()

        for row in field_rows:
            key = id_to_key.get(row["itemID"])
            if not key:
                continue
            fn, val = row["fieldName"], row["value"]
            d = result[key]
            if fn == "title":
                d["title"] = val
            elif fn == "shortTitle" and not d["title"]:
                d["title"] = val
            elif fn == "abstractNote":
                d["abstract"] = val
            elif fn == "date":
                d["date"] = val

        # Creators — one query for all items
        creator_rows = conn.execute("""
            SELECT ic.itemID, c.firstName, c.lastName, ct.creatorType
            FROM itemCreators ic
            JOIN creators c ON ic.creatorID = c.creatorID
            JOIN creatorTypes ct ON ic.creatorTypeID = ct.creatorTypeID
            ORDER BY ic.itemID, ic.orderIndex
        """).fetchall()

        author_map: dict[int, list[str]] = {}
        editor_map: dict[int, list[str]] = {}
        for row in creator_rows:
            if row["itemID"] not in valid_ids:
                continue
            first, last = row["firstName"] or "", row["lastName"] or ""
            name = f"{first} {last}".strip() if first else last
            if not name:
                continue
            if row["creatorType"] == "author":
                author_map.setdefault(row["itemID"], []).append(name)
            elif row["creatorType"] == "editor":
                editor_map.setdefault(row["itemID"], []).append(name)

        for iid, key in id_to_key.items():
            result[key]["authors"] = sorted(author_map.get(iid) or editor_map.get(iid, []))

        # Tags — one query for all items
        tag_rows = conn.execute("""
            SELECT it.itemID, t.name
            FROM itemTags it
            JOIN tags t ON it.tagID = t.tagID
        """).fetchall()

        for row in tag_rows:
            key = id_to_key.get(row["itemID"])
            if key:
                result[key]["tags"].append(row["name"])
        for data in result.values():
            data["tags"].sort()

        # Attachments: has_attachment + max dateModified (signals annotation changes)
        ct_ph = ",".join("?" * len(_ZOTERO_INDEXABLE_CONTENT_TYPES))
        att_rows = conn.execute(f"""
            SELECT ia.parentItemID, MAX(i.dateModified) AS att_modified
            FROM itemAttachments ia
            JOIN items i ON ia.itemID = i.itemID
            WHERE ia.linkMode IN (0, 1, 2)
            AND ia.contentType IN ({ct_ph})
            AND ia.itemID NOT IN (SELECT itemID FROM deletedItems)
            GROUP BY ia.parentItemID
        """, _ZOTERO_INDEXABLE_CONTENT_TYPES).fetchall()

        for row in att_rows:
            key = id_to_key.get(row["parentItemID"])
            if key:
                result[key]["has_attachment"] = True
                result[key]["attachment_modified_at"] = row["att_modified"]

        return result
    finally:
        conn.close()


def _compute_zotero_metadata_hash(data: dict[str, Any]) -> str:
    """Delegiert an src.archilles.hashing (Befund 7.15).

    Bleibt als Modulfunktion erhalten (Tests/Aufrufer importieren sie direkt).
    """
    from src.archilles.hashing import compute_zotero_metadata_hash
    return compute_zotero_metadata_hash(data)


class ZoteroWatchdogScanner:
    """Incremental sync scanner for Zotero libraries.

    Detects three change types and dispatches accordingly:
      new_items           Zotero keys present in zotero.sqlite but absent from LanceDB
      metadata_changed    title / authors / tags / abstract / date changed
      annotations_changed attachment dateModified changed (covers PDF + DB annotations)

    Phase 1 is pure SQLite + in-memory hash comparison — no book files are opened.
    Phase 2 re-indexes changed items via ArchillesRAG.index_book().
    Phase 3 queues or immediately indexes new items.
    """

    def __init__(
        self,
        library_path: Path,
        db_path: str,
        archilles_dir: Path,
        excluded_tags: list[str] | None = None,
    ):
        self.library_path = Path(library_path)
        self.db_path = db_path
        self.archilles_dir = archilles_dir
        self.queue_file = archilles_dir / "zotero_index_queue.json"
        self.log_file = archilles_dir / "watchdog.log"
        self.annotation_cache_file = archilles_dir / "zotero_watchdog_cache.json"
        self.excluded_tags_lower: set[str] = {
            t.lower() for t in (excluded_tags or [])
        }
        self._annotation_cache: dict[str, str] | None = None  # {key: att_modified_at}
        self._annotation_cache_dirty = False
        self._shutdown_requested = False

    @property
    def shutdown_requested(self) -> bool:
        return self._shutdown_requested

    def request_shutdown(self) -> None:
        self._shutdown_requested = True

    def scan(
        self,
        dry_run: bool = False,
        queue_new: bool = True,
        index_new: bool = False,
    ) -> dict[str, Any]:
        """Run a full scan and return a results dict."""
        t0 = time.time()
        results: dict[str, Any] = {
            'new_books':            [],
            'metadata_changed':    [],
            'annotations_changed': [],
            'unchanged':           [],
            'errors':              [],
            'delta_updates':       0,
            'delta_time':          0.0,
            'new_indexed':         0,
            'new_indexed_time':    0.0,
            'scanned':             0,
            'interrupted':         False,
        }

        # ── Phase 1: fast scan ────────────────────────────────────
        zotero_items = _zotero_metadata_for_scan(self.library_path)
        results['scanned'] = len(zotero_items)

        indexed_hashes = self._load_indexed_hashes()
        ann_cache = self._load_annotation_cache()
        # Deferred annotation-cache writes (finding 4.3): a changed att_modified
        # is committed to the cache only after Phase 2 has re-indexed the item,
        # so a failed or interrupted delta re-detects it next scan instead of
        # silently swallowing the update.
        pending_cache: dict[str, str] = {}

        for key, data in zotero_items.items():
            if self.excluded_tags_lower:
                item_tags_lower = {t.lower() for t in data.get("tags", [])}
                if item_tags_lower & self.excluded_tags_lower:
                    continue

            if not data["has_attachment"]:
                continue

            if key not in indexed_hashes:
                results['new_books'].append({'doc_id': key, 'title': data.get('title', key)})
                continue

            stored = indexed_hashes[key]

            # Metadata change
            current_meta_hash = _compute_zotero_metadata_hash(data)
            stored_meta_hash = stored.get('metadata_hash', '')
            meta_changed = bool(stored_meta_hash) and current_meta_hash != stored_meta_hash

            # Annotation change: attachment dateModified as proxy
            current_att_mod = data.get("attachment_modified_at") or ""
            cached_att_mod = ann_cache.get(key, "")
            annot_changed = bool(cached_att_mod) and current_att_mod != cached_att_mod

            # First-seen seeding is not a change signal — cache it immediately.
            # A genuine change (annot_changed) is deferred to Phase 2 (4.3).
            if annot_changed:
                pending_cache[key] = current_att_mod
            elif not cached_att_mod and current_att_mod:
                ann_cache[key] = current_att_mod
                self._annotation_cache_dirty = True

            if meta_changed:
                results['metadata_changed'].append(key)
            if annot_changed:
                results['annotations_changed'].append(key)
            if not meta_changed and not annot_changed:
                results['unchanged'].append(key)

        # ── Phase 2: apply delta updates ─────────────────────────
        books_to_update = set(results['metadata_changed']) | set(results['annotations_changed'])
        if books_to_update and not dry_run:
            from src.adapters.zotero_adapter import ZoteroAdapter
            adapter = ZoteroAdapter(self.library_path)
            rag = self._load_rag()
            dt0 = time.time()
            update_list = sorted(books_to_update)
            total_p2 = len(update_list)
            for i, key in enumerate(update_list, 1):
                if self._shutdown_requested:
                    print(f"\n⏸️  Shutdown requested — phase 2 stopped after {i-1}/{total_p2} items.")
                    break
                data = zotero_items.get(key, {})
                file_path = adapter.get_file_path(key)
                if not file_path:
                    logger.warning("No file found for Zotero key %s — skipping delta update", key)
                    continue
                print(f"\n[{i}/{total_p2}] {data.get('title', key)}")
                try:
                    rag.index_book(str(file_path), key, force=False)
                    results['delta_updates'] += 1
                    # Commit the deferred annotation-cache value now that the
                    # re-index succeeded (4.3). Metadata-only changes have no
                    # pending entry; failed/shutdown-skipped items keep their
                    # old cached value and are re-detected next scan.
                    if key in pending_cache:
                        ann_cache[key] = pending_cache[key]
                        self._annotation_cache_dirty = True
                except Exception as exc:
                    logger.error("Delta update failed for key=%s: %s", key, exc)
                    results['errors'].append({'doc_id': key, 'error': str(exc)})
            results['delta_time'] = round(time.time() - dt0, 1)

        # ── Phase 3: handle new items ─────────────────────────────
        new_keys = [b['doc_id'] for b in results['new_books']]
        if new_keys and not dry_run:
            if queue_new:
                self._queue_new_items(new_keys)
            if index_new:
                from src.adapters.zotero_adapter import ZoteroAdapter
                adapter = ZoteroAdapter(self.library_path)
                rag = self._load_rag()
                ni0 = time.time()
                total_p3 = len(new_keys)
                for j, entry in enumerate(results['new_books'], 1):
                    if self._shutdown_requested:
                        print(f"\n⏸️  Shutdown requested — phase 3 stopped after {j-1}/{total_p3} items.")
                        break
                    key = entry['doc_id']
                    file_path = adapter.get_file_path(key)
                    if not file_path:
                        continue
                    print(f"\n[{j}/{total_p3}] {entry['title']}")
                    try:
                        rag.index_book(str(file_path), key, force=False)
                        results['new_indexed'] += 1
                        # Seed annotation cache for freshly indexed items
                        att_mod = zotero_items.get(key, {}).get("attachment_modified_at") or ""
                        if att_mod:
                            ann_cache[key] = att_mod
                            self._annotation_cache_dirty = True
                    except Exception as exc:
                        logger.error("New-item indexing failed for key=%s: %s", key, exc)
                        results['errors'].append({'doc_id': key, 'error': str(exc)})
                results['new_indexed_time'] = round(time.time() - ni0, 1)

        results['total_time'] = round(time.time() - t0, 1)
        results['interrupted'] = self._shutdown_requested

        if not dry_run:
            self._save_annotation_cache()
            self._write_log(results)

        return results

    # ── Internal helpers ──────────────────────────────────────────

    def _load_indexed_hashes(self) -> dict[str, dict[str, str]]:
        """Load stored hashes from LanceDB using string book_id as key."""
        try:
            from src.archilles.engine import ArchillesRAG
            rag = ArchillesRAG(db_path=self.db_path, skip_model=True)
            return rag.store.get_hashes_by_book_id()
        except Exception as exc:
            logger.warning("Could not load indexed hashes: %s", exc)
            return {}

    def _resolve_plan(self):
        """Resolve this library's ExecutionPlan (mode + detected hardware)."""
        return _resolve_execution_plan(Path(self.library_path))

    def _load_rag(self):
        """Load a full ArchillesRAG instance, wired to the Hardware-Tiers-V2 plan.

        Mirrors :meth:`WatchdogScanner._load_rag`: the resolved ExecutionPlan
        drives batch/device, and new items use the plan's chunk schema instead of
        the old flat default. ``full-external`` is forced flat (provisional light).
        """
        from src.archilles.engine import ArchillesRAG
        from src.archilles.config import get_languages
        from src.adapters.zotero_adapter import ZoteroAdapter
        ep = self._resolve_plan()
        hierarchical = ep.hierarchical and ep.embed_local
        # Pass the adapter (finding 4.1b): without it, delta re-indexing runs
        # _extract_metadata through the Calibre path, finds no metadata.db above
        # the Zotero storage tree, extracts {} and wipes hashes / abstracts.
        return ArchillesRAG(
            db_path=self.db_path,
            languages=get_languages(Path(self.library_path)),
            execution_plan=ep,
            hierarchical=hierarchical,
            adapter=ZoteroAdapter(self.library_path),
        )

    def _load_annotation_cache(self) -> dict[str, str]:
        """Lazy-load the Zotero annotation cache ({item_key: att_modified_at})."""
        if self._annotation_cache is not None:
            return self._annotation_cache
        if self.annotation_cache_file.exists():
            try:
                self._annotation_cache = json.loads(
                    self.annotation_cache_file.read_text(encoding='utf-8')
                )
            except Exception as exc:
                logger.warning("Could not read Zotero annotation cache (resetting): %s", exc)
                self._annotation_cache = {}
        else:
            self._annotation_cache = {}
        return self._annotation_cache

    def _save_annotation_cache(self) -> None:
        if self._annotation_cache is None or not self._annotation_cache_dirty:
            return
        try:
            self.archilles_dir.mkdir(parents=True, exist_ok=True)
            self.annotation_cache_file.write_text(
                json.dumps(self._annotation_cache, indent=2),
                encoding='utf-8',
            )
            self._annotation_cache_dirty = False
        except Exception as exc:
            logger.warning("Could not save Zotero annotation cache: %s", exc)

    def _queue_new_items(self, keys: list[str]) -> None:
        existing: list[str] = []
        if self.queue_file.exists():
            try:
                existing = json.loads(self.queue_file.read_text(encoding='utf-8'))
            except Exception:
                pass
        merged = sorted(set(existing) | set(keys))
        self.archilles_dir.mkdir(parents=True, exist_ok=True)
        self.queue_file.write_text(json.dumps(merged, indent=2), encoding='utf-8')

    def _write_log(self, results: dict[str, Any]) -> None:
        ts = datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
        n_new  = len(results['new_books'])
        n_meta = len(results['metadata_changed'])
        n_anno = len(results['annotations_changed'])
        n_unch = len(results['unchanged'])
        new_ids = [b['doc_id'] for b in results['new_books']]
        lines = [
            f"{ts} ZOTERO SCAN completed in {results['total_time']}s",
            f"  new_items: {n_new}" + (f" {new_ids}" if new_ids else ""),
            f"  metadata_changed: {n_meta}"
            + (f" {results['metadata_changed']}" if n_meta else ""),
            f"  annotations_changed: {n_anno}"
            + (f" {results['annotations_changed']}" if n_anno else ""),
            f"  unchanged: {n_unch}",
            f"  errors: {len(results['errors'])}",
            f"  delta_updates: {results['delta_updates']}"
            + (f" completed in {results['delta_time']}s" if results['delta_updates'] else ""),
            f"  new_indexed: {results.get('new_indexed', 0)}"
            + (f" completed in {results.get('new_indexed_time', 0)}s" if results.get('new_indexed') else ""),
            "",
        ]
        self.archilles_dir.mkdir(parents=True, exist_ok=True)
        with open(self.log_file, 'a', encoding='utf-8') as fh:
            fh.write('\n'.join(lines) + '\n')
