"""
ARCHILLES Watchdog — Automatic Calibre→LanceDB sync scanner.

Detects three change types and dispatches accordingly:
  new_books          Calibre IDs present in metadata.db but absent from LanceDB
  metadata_changed   title / author / tags / comments / publisher changed
  annotations_changed  highlights or notes changed

The scan itself is fast: SQLite read + LanceDB hash lookup, no book files opened.
Delta updates delegate to archillesRAG.index_book(), which already handles
smart partial re-indexing (metadata-only, annotations-only, or both).

Called from:
  scripts/watchdog.py  — standalone CLI (cron / Task Scheduler / direct)
  calibre_mcp/server.py — MCP tool `watchdog_scan` (Claude Routines)
"""

import hashlib
import json
import logging
import re
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


def _discover_formats(book_path: Path) -> list[dict[str, str]]:
    return [
        {'format': ext[1:].upper(), 'path': str(f)}
        for ext in _PREFERRED_FORMATS
        for f in book_path.glob(f'*{ext}')
    ]


def _clean_html(html_text: str) -> str:
    """Strip HTML tags from Calibre comments, mirroring CalibreDB.clean_html()."""
    if not html_text:
        return ""
    text = re.sub(r'<[^>]+>', '', html_text)
    text = text.replace('&nbsp;', ' ')
    text = text.replace('&amp;', '&')
    text = text.replace('&lt;', '<')
    text = text.replace('&gt;', '>')
    text = text.replace('&quot;', '"')
    text = text.replace('&#39;', "'")
    return re.sub(r'\s+', ' ', text).strip()


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

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
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
                GROUP_CONCAT(DISTINCT tags.name)    AS tags,
                publishers.name                     AS publisher
            FROM books
            LEFT JOIN comments              ON books.id = comments.book
            LEFT JOIN books_tags_link       ON books.id = books_tags_link.book
            LEFT JOIN tags                  ON books_tags_link.tag = tags.id
            LEFT JOIN books_publishers_link ON books.id = books_publishers_link.book
            LEFT JOIN publishers            ON books_publishers_link.publisher = publishers.id
            GROUP BY books.id
        """).fetchall()
    finally:
        conn.close()

    result = {}
    for row in rows:
        cid = int(row['id'])
        raw_tags = row['tags'] or ''
        tags_list = sorted(t.strip() for t in raw_tags.split(',') if t.strip())
        result[cid] = {
            'title':     row['title'] or '',
            'author':    row['author'] or '',
            'comments':  _clean_html(row['comments'] or ''),
            'tags':      tags_list,
            'publisher': row['publisher'] or '',
            'path':      str(library_path / row['path']),
        }
    return result


def _compute_metadata_hash(meta: dict[str, Any]) -> str:
    """Replicate ``archillesRAG._compute_metadata_hash`` without importing rag_demo.

    Tags are sorted regardless of input type (list or comma-string) so the
    hash is independent of Calibre's internal tag ordering — otherwise every
    tag-reorder in Calibre would mis-classify the book as metadata_changed.
    """
    tags = meta.get('tags', [])
    if isinstance(tags, str):
        tags = sorted(t.strip() for t in tags.split(',') if t.strip())
    elif isinstance(tags, list):
        tags = sorted(tags)
    relevant = {
        'comments':  meta.get('comments', ''),
        'tags':      tags,
        'title':     meta.get('title', ''),
        'author':    meta.get('author', ''),
        'publisher': meta.get('publisher', ''),
    }
    return hashlib.md5(
        json.dumps(relevant, sort_keys=True, ensure_ascii=False).encode('utf-8')
    ).hexdigest()


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
        self.excluded_tags_lower: set[str] = {
            t.lower() for t in (excluded_tags if excluded_tags is not None else DEFAULT_EXCLUDED_TAGS)
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def scan(
        self,
        dry_run: bool = False,
        queue_new: bool = True,
        index_new: bool = False,
    ) -> dict[str, Any]:
        """
        Run a full scan and return a results dict.

        Parameters
        ----------
        dry_run   Report changes only; do not modify LanceDB or the queue.
        queue_new Write new Calibre IDs to index_queue.json (default True).
        index_new Index new books immediately via archillesRAG (slow, ~90s/book).
        """
        t0 = time.time()
        results: dict[str, Any] = {
            'new_books':            [],
            'metadata_changed':    [],
            'annotations_changed': [],
            'unchanged':           [],
            'errors':              [],
            'delta_updates':       0,    # count of Phase-2 updates (metadata / annotations)
            'delta_time':          0.0,
            'new_indexed':         0,    # count of Phase-3 immediate new-book indexes
            'new_indexed_time':    0.0,
            'scanned':             0,
        }

        # ── Phase 1: fast scan — no book files opened ──────────────────
        calibre_books = _calibre_metadata_for_hash(self.library_path)
        results['scanned'] = len(calibre_books)

        indexed_hashes = self._load_indexed_hashes()

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
            if not meta_changed and not annot_changed:
                results['unchanged'].append(cid)

        # ── Phase 2: apply delta updates ──────────────────────────────
        books_to_update = (
            set(results['metadata_changed']) | set(results['annotations_changed'])
        )
        if books_to_update and not dry_run:
            rag = self._load_rag()
            dt0 = time.time()
            books_to_update_list = sorted(books_to_update)
            total_p2 = len(books_to_update_list)
            for i, cid in enumerate(books_to_update_list, 1):
                meta = calibre_books.get(cid)
                if not meta:
                    continue
                formats = _discover_formats(Path(meta['path']))
                if not formats:
                    continue
                file_path = formats[0]['path']
                book_id = str(cid)
                print(f"\n[{i}/{total_p2}] {meta['title']}")
                try:
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
            if index_new:
                rag = self._load_rag()
                ni0 = time.time()
                saved_total, done_ids = self._load_checkpoint()
                pending = [e for e in results['new_books'] if e['calibre_id'] not in done_ids]
                already_done = len(done_ids)
                total_p3 = max(saved_total, already_done + len(pending))
                if already_done:
                    print(f"  (Fortsetzung: {already_done} bereits fertig, {len(pending)} ausstehend)")
                self._save_checkpoint(total_p3, done_ids)
                for j, entry in enumerate(pending, 1):
                    cid = entry['calibre_id']
                    meta = calibre_books.get(cid)
                    if not meta:
                        continue
                    formats = _discover_formats(Path(meta['path']))
                    if not formats:
                        continue
                    print(f"\n[{already_done + j}/{total_p3}] {entry['title']}")
                    try:
                        rag.index_book(formats[0]['path'], str(cid), force=False)
                        results['new_indexed'] += 1
                        done_ids.add(cid)
                        self._save_checkpoint(total_p3, done_ids)
                    except Exception as exc:
                        logger.error(f"New-book indexing failed for calibre_id={cid}: {exc}")
                        results['errors'].append({'calibre_id': cid, 'error': str(exc)})
                if self.checkpoint_file.exists():
                    self.checkpoint_file.unlink()
                results['new_indexed_time'] = round(time.time() - ni0, 1)

        results['total_time'] = round(time.time() - t0, 1)

        if not dry_run:
            self._write_log(results)

        return results

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_indexed_hashes(self) -> dict[int, dict[str, str]]:
        """Load stored hashes from LanceDB without loading the embedding model."""
        try:
            # Import lazily so the watchdog can be imported without heavy deps
            from scripts.rag_demo import archillesRAG
            rag = archillesRAG(db_path=self.db_path, skip_model=True)
            return rag.store.get_hashes_for_indexed_books()
        except Exception as exc:
            logger.warning(f"Could not load indexed hashes: {exc}")
            return {}

    def _load_rag(self):
        """Load a full archillesRAG instance (with embedding model)."""
        from scripts.rag_demo import archillesRAG
        return archillesRAG(db_path=self.db_path)

    def _annotation_changed(self, file_path: Path, stored_hash: str) -> bool:
        """Return True if the annotation hash for this book differs from what is stored.

        Compares bidirectionally: ``_compute_annotation_hash`` returns ``''``
        for an empty annotation list, so the comparison naturally detects both
        ``stored='' → current='abc'`` (first-time annotations) and
        ``stored='abc' → current=''`` (annotations cleared).

        PDF-native annotations (Adobe/Foxit) are included via ``include_pdf=True``
        to match the indexer (``scripts/rag_demo.py``), which stores annotation
        hashes computed over the combined Calibre-Viewer + PDF set. Using
        ``include_pdf=False`` here would make every PDF with embedded
        highlights look "changed" on every scan. Failures are logged and
        treated as "unchanged" so a transient error cannot spam the index
        with false-positive updates.
        """
        try:
            from src.calibre_mcp.annotations import get_combined_annotations
            from scripts.rag_demo import archillesRAG
            result = get_combined_annotations(
                book_path=str(file_path),
                include_pdf=True,
                exclude_toc_markers=True,
                min_length=20,
            )
            current_hash = archillesRAG._compute_annotation_hash(
                result.get('annotations', [])
            )
            return current_hash != stored_hash
        except Exception as exc:
            logger.warning(
                "Annotation check failed for %s: %s (assuming unchanged)",
                file_path, exc,
            )
            return False

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

    def _load_checkpoint(self) -> tuple[int, set[int]]:
        """Return (total_at_start, done_ids) from a previous interrupted --index-new run."""
        if not self.checkpoint_file.exists():
            return 0, set()
        try:
            data = json.loads(self.checkpoint_file.read_text(encoding='utf-8'))
            return data.get('total', 0), set(data.get('done', []))
        except Exception:
            return 0, set()

    def _save_checkpoint(self, total: int, done: set[int]) -> None:
        self.archilles_dir.mkdir(parents=True, exist_ok=True)
        self.checkpoint_file.write_text(
            json.dumps({'total': total, 'done': sorted(done)}, indent=2),
            encoding='utf-8',
        )

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
