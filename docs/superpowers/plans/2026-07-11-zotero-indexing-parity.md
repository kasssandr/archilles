# Zotero Indexing Parity — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Zotero routine actually index new items (today it never does), with Calibre-equivalent priority ergonomics using Zotero-native concepts (tags, collections).

**Architecture:** Wire `--index-new` into the Zotero routine command; extend `ZoteroWatchdogScanner.scan()` with a `max_new` cap and priority sorting; generalize the existing Calibre `_index_priority_key` matcher so both scanners share it; surface Zotero collections in the scan metadata for collection-based prioritization.

**Tech Stack:** Python 3.12, SQLite (`zotero.sqlite`, read-only via `connect_readonly`), pytest, existing `ArchillesRAG.index_book()` pipeline.

## Global Constraints

- **Code language: English only** (comments, docstrings, identifiers, log/error messages, test prose). German only in docs/data. (Repo CLAUDE.md)
- **Calibre core is read-only.** This work touches only the Zotero scanner, the shared priority helper, the CLI, the routine wrapper, and config parsing — no writes to any library.
- **Recency proxy = `-item_id`.** Zotero `itemID` is the SQLite rowid, monotonic with add order — the exact analog of Calibre's `-calibre_id`. This deviates from the spec's literal "dateAdded" for a reason: it needs no date parsing, has no malformed-date failure mode, and matches the Calibre mechanism byte-for-byte. No `dateAdded` column is added.
- **Tag/collection priority = exact set membership** (case-insensitive); author/title = substring. This preserves the *existing* Calibre `_index_priority_key` behavior exactly.
- **`compute_zotero_metadata_hash` is NOT changed.** It hashes only title/authors/tags/abstract/date, so adding `collections` to the scan metadata dict cannot trigger false `metadata_changed` events. Verified before planning.

---

### Task 1: Wire `--index-new` + `max_new` cap into the Zotero routine (runs today)

Smallest change that makes `new_indexed > 0` for Zotero. Sort is recency-only here (`-item_id`); the priority *group* is layered on in Task 4 (this recency logic is not reworked, only wrapped).

**Files:**
- Modify: `scripts/run_routine.py` (`_build_command`, ~lines 76–98)
- Modify: `scripts/watchdog.py` (`scan_kwargs` assembly, ~lines 280–289)
- Modify: `src/archilles/watchdog.py` (`ZoteroWatchdogScanner.scan`, ~lines 1142–1147 and Phase 3 block ~lines 1276–1317)
- Test: `tests/test_run_routine_command.py`, `tests/test_zotero_watchdog.py`

**Interfaces:**
- Produces: `ZoteroWatchdogScanner.scan(..., max_new: int | None = None)` — caps the number of new items indexed per run; when `index_new` is set, new items are indexed newest-first (`-item_id`).
- Produces: `_build_command("zotero", ...)` returns a command containing `--index-new` (and `--max-new N` when `max_new` is not None).

- [ ] **Step 1: Write the failing test — routine command carries `--index-new` for Zotero**

In `tests/test_run_routine_command.py`:

```python
def test_build_command_zotero_indexes_new():
    from scripts.run_routine import _build_command
    cmd = _build_command("zotero", max_new=None)
    assert "--index-new" in cmd
    assert "--index-metadata-only" not in cmd  # Zotero has no stub phase
    assert "--index-fulltext-pending" not in cmd


def test_build_command_zotero_passes_max_new():
    from scripts.run_routine import _build_command
    cmd = _build_command("zotero", max_new=25)
    assert "--max-new" in cmd
    assert "25" in cmd
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_run_routine_command.py::test_build_command_zotero_indexes_new tests/test_run_routine_command.py::test_build_command_zotero_passes_max_new -v`
Expected: FAIL — `--index-new` not present for Zotero.

- [ ] **Step 3: Add the Zotero branch in `_build_command`**

In `scripts/run_routine.py`, inside `_build_command`, replace the Calibre-only block so Zotero also gets an indexing instruction. The existing structure is:

```python
        if adapter == "calibre":
            if phase == "A":
                cmd += ["--index-metadata-only"]
            else:
                cmd += ["--index-fulltext-pending"]
                if max_new is not None:
                    cmd += ["--max-new", str(max_new)]
                if rating is not None:
                    cmd += ["--rating", str(rating)]
        return cmd
```

Add an `elif` branch:

```python
        if adapter == "calibre":
            if phase == "A":
                cmd += ["--index-metadata-only"]
            else:
                cmd += ["--index-fulltext-pending"]
                if max_new is not None:
                    cmd += ["--max-new", str(max_new)]
                if rating is not None:
                    cmd += ["--rating", str(rating)]
        elif adapter == "zotero":
            # Zotero has no A/B stub phase — a new item is either fully indexed
            # or "new". Index new items immediately; --max-new bounds a run so a
            # large first backlog (e.g. 500+ items) drains over several runs,
            # newest-first, instead of one marathon.
            cmd += ["--index-new"]
            if max_new is not None:
                cmd += ["--max-new", str(max_new)]
        return cmd
```

- [ ] **Step 4: Run the routine-command tests to verify they pass**

Run: `python -m pytest tests/test_run_routine_command.py -v`
Expected: PASS.

- [ ] **Step 5: Pass `index_new` + `max_new` to the Zotero scanner in the CLI**

In `scripts/watchdog.py`, the `scan_kwargs` currently forwards `max_new` only for Calibre. The base dict already carries `index_new`. Add `max_new` for Zotero:

```python
    scan_kwargs: dict = {
        'dry_run': args.dry_run,
        'queue_new': args.queue_new,
        'index_new': args.index_new,
    }
    if scanner_type == "calibre":
        scan_kwargs['index_metadata_only'] = getattr(args, 'index_metadata_only', False)
        scan_kwargs['index_fulltext_pending'] = getattr(args, 'index_fulltext_pending', False)
        scan_kwargs['max_new'] = args.max_new
        scan_kwargs['rating_filter'] = args.rating
        scan_kwargs['first_authors'] = args.first_authors
        scan_kwargs['first_tags'] = args.first_tags
        scan_kwargs['first_titles'] = args.first_titles
    elif scanner_type == "zotero":
        scan_kwargs['max_new'] = args.max_new
```

- [ ] **Step 6: Write the failing test — scanner caps and orders new items**

In `tests/test_zotero_watchdog.py`, add a test that drives `scan(index_new=True, max_new=2)` and asserts only 2 items are indexed, newest-first. Follow the existing fixture/mocking pattern in that file (a fake `zotero.sqlite` builder and a stub RAG whose `index_book` records calls). If the file already has a helper to build a scanner with N new items, reuse it; otherwise mirror the nearest existing test's setup. Concretely, the assertion core:

```python
def test_scan_index_new_caps_and_orders_newest_first(zotero_scanner_with_new_items):
    # Fixture provides 3 new items with item_ids 10, 20, 30 (30 = newest)
    scanner, indexed_calls = zotero_scanner_with_new_items
    results = scanner.scan(index_new=True, max_new=2)
    assert results['new_indexed'] == 2
    # Newest two by item_id (30, 20) indexed; oldest (10) skipped this run
    indexed_keys = [c['key'] for c in indexed_calls]
    assert indexed_keys == ["key30", "key20"]
```

If no reusable fixture exists, build `zotero_scanner_with_new_items` in the test module: construct a temp `zotero.sqlite` with three items (attachments present, no indexed hashes so all are "new"), monkeypatch `ZoteroWatchdogScanner._load_rag` to return a stub whose `index_book(path, key, force=False)` appends `{'key': key}` to a list and returns `{}` (fresh index), and `_resolve_plan().embed_local = True` (local path, no pending-external marking).

- [ ] **Step 7: Run the scanner test to verify it fails**

Run: `python -m pytest tests/test_zotero_watchdog.py::test_scan_index_new_caps_and_orders_newest_first -v`
Expected: FAIL — `scan()` has no `max_new` parameter (TypeError).

- [ ] **Step 8: Add `max_new` + recency cap to `ZoteroWatchdogScanner.scan`**

In `src/archilles/watchdog.py`, extend the signature:

```python
    def scan(
        self,
        dry_run: bool = False,
        queue_new: bool = True,
        index_new: bool = False,
        max_new: int | None = None,
    ) -> dict[str, Any]:
```

In the Phase 3 block (`if index_new:`), replace the direct iteration over `results['new_books']` with a sorted+capped `pending` list. The current loop is:

```python
                total_p3 = len(new_keys)
                for j, entry in enumerate(results['new_books'], 1):
```

Replace with:

```python
                # Recency-first: Zotero itemID is the rowid, monotonic with add
                # order, so -item_id puts the newest item first (exact analog of
                # Calibre's -calibre_id). max_new bounds a run so a large first
                # backlog drains over several runs, newest-first.
                pending = sorted(
                    results['new_books'],
                    key=lambda e: -zotero_items.get(e['doc_id'], {}).get('item_id', 0),
                )
                if max_new is not None:
                    pending = pending[:max_new]
                total_p3 = len(pending)
                for j, entry in enumerate(pending, 1):
```

(The loop body below — `key = entry['doc_id']`, `file_path = adapter.get_file_path(key)`, etc. — is unchanged.)

- [ ] **Step 9: Run the scanner test to verify it passes**

Run: `python -m pytest tests/test_zotero_watchdog.py::test_scan_index_new_caps_and_orders_newest_first -v`
Expected: PASS.

- [ ] **Step 10: Run the full Zotero + routine suites (regression)**

Run: `python -m pytest tests/test_zotero_watchdog.py tests/test_run_routine_command.py -v`
Expected: PASS (no regressions).

- [ ] **Step 11: Commit**

```bash
git add scripts/run_routine.py scripts/watchdog.py src/archilles/watchdog.py tests/test_run_routine_command.py tests/test_zotero_watchdog.py
git commit -m "feat(zotero): index new items in the routine with a max_new cap

Wire --index-new into the Zotero routine command and add a max_new cap +
recency (newest-first, -item_id) ordering to ZoteroWatchdogScanner.scan.
Fixes new_indexed always 0 for Zotero.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Generalize the priority matcher (`_priority_match`)

Pure refactor: extract the author/tag/title matching out of `_index_priority_key` into a shared, data-model-agnostic helper that also supports collections. Calibre behavior is unchanged.

**Files:**
- Modify: `src/archilles/watchdog.py` (`_index_priority_key`, ~lines 164–204; add `_priority_match` above it)
- Test: `tests/test_watchdog.py`

**Interfaces:**
- Produces: `_priority_match(author: str, tags: list[str], title: str, collections: list[str], first_authors: list[str], first_tags: list[str], first_titles: list[str], first_collections: list[str]) -> bool` — True if the item matches any explicit priority filter. Author/title = substring; tags/collections = exact set membership; all case-insensitive.
- `_index_priority_key(entry, calibre_books, first_authors, first_tags, first_titles)` keeps its exact signature and return value.

- [ ] **Step 1: Write the failing test for `_priority_match`**

In `tests/test_watchdog.py`:

```python
def test_priority_match_author_substring():
    from src.archilles.watchdog import _priority_match
    assert _priority_match("Hannah Arendt", [], "", [], ["arendt"], [], [], []) is True
    assert _priority_match("Hannah Arendt", [], "", [], ["kant"], [], [], []) is False


def test_priority_match_tag_exact_membership():
    from src.archilles.watchdog import _priority_match
    # exact (case-insensitive) membership, NOT substring
    assert _priority_match("", ["Prio"], "", [], [], ["prio"], [], []) is True
    assert _priority_match("", ["Priority"], "", [], [], ["prio"], [], []) is False


def test_priority_match_collection_exact_membership():
    from src.archilles.watchdog import _priority_match
    assert _priority_match("", [], "", ["Current Project"], [], [], [], ["current project"]) is True
    assert _priority_match("", [], "", ["Archive"], [], [], [], ["current project"]) is False


def test_priority_match_title_substring():
    from src.archilles.watchdog import _priority_match
    assert _priority_match("", [], "The Human Condition", [], [], [], ["human"], []) is True
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_watchdog.py -k priority_match -v`
Expected: FAIL — `_priority_match` not defined (ImportError).

- [ ] **Step 3: Add `_priority_match` and refactor `_index_priority_key` to use it**

In `src/archilles/watchdog.py`, add above `_index_priority_key`:

```python
def _priority_match(
    author: str,
    tags: list[str],
    title: str,
    collections: list[str],
    first_authors: list[str],
    first_tags: list[str],
    first_titles: list[str],
    first_collections: list[str],
) -> bool:
    """True if the item matches any explicit priority filter (group 0).

    Author and title match by substring; tags and collections match by exact
    (case-insensitive) set membership. This mirrors the original Calibre
    priority rule and extends it to Zotero collections.
    """
    if first_authors and any(a.lower() in author.lower() for a in first_authors):
        return True
    if first_tags:
        tags_lc = {t.lower() for t in tags}
        if any(t.lower() in tags_lc for t in first_tags):
            return True
    if first_titles and any(t.lower() in title.lower() for t in first_titles):
        return True
    if first_collections:
        colls_lc = {c.lower() for c in collections}
        if any(c.lower() in colls_lc for c in first_collections):
            return True
    return False
```

Then replace the matching block inside `_index_priority_key` (the `is_priority = False ...` through the three `if` checks) with a single call:

```python
    meta = calibre_books.get(entry['calibre_id'], {})
    rating = meta.get('rating') or 0

    is_priority = _priority_match(
        meta.get('author', ''),
        meta.get('tags', []),
        meta.get('title', ''),
        [],  # Calibre has no collections
        first_authors,
        first_tags,
        first_titles,
        [],
    )

    if rating >= 10:   rating_order = 0  # 5★
    elif rating >= 8:  rating_order = 1  # 4★
    else:              rating_order = 2  # 3★, unrated, 1–2★ — all equal

    return (0 if is_priority else 1, rating_order, -entry['calibre_id'])
```

- [ ] **Step 4: Run the priority tests + existing Calibre watchdog tests (regression)**

Run: `python -m pytest tests/test_watchdog.py -v`
Expected: PASS — new `_priority_match` tests green AND every existing `_index_priority_key` / scan-ordering test still green (behavior unchanged).

- [ ] **Step 5: Commit**

```bash
git add src/archilles/watchdog.py tests/test_watchdog.py
git commit -m "refactor(watchdog): extract shared _priority_match helper

Generalize the Calibre priority matcher into a data-model-agnostic helper
that also supports collections. Calibre behavior unchanged.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Surface Zotero collections in scan metadata

Add each item's collection names to the scan metadata dict so collection-based prioritization has data to work with. The metadata hash is deliberately untouched.

**Files:**
- Modify: `src/archilles/watchdog.py` (`_zotero_metadata_for_scan`, ~lines 989–1086)
- Test: `tests/test_zotero_watchdog.py`

**Interfaces:**
- Produces: `_zotero_metadata_for_scan(library_path)` result dicts now include `"collections": list[str]` (sorted), alongside the existing `item_id`, `title`, `authors`, `tags`, etc.

- [ ] **Step 1: Write the failing test — collections are surfaced, hash unaffected**

In `tests/test_zotero_watchdog.py` (reuse the module's temp-`zotero.sqlite` builder; if none exists, create a minimal one that inserts an item, an attachment, a collection, and a `collectionItems` row):

```python
def test_zotero_metadata_includes_collections(tmp_zotero_library_with_collection):
    from src.archilles.watchdog import _zotero_metadata_for_scan, _compute_zotero_metadata_hash
    lib = tmp_zotero_library_with_collection  # item "key1" in collection "Current Project"
    result = _zotero_metadata_for_scan(lib)
    assert result["key1"]["collections"] == ["Current Project"]

    # Hash must ignore collections: same data minus collections → identical hash
    data = dict(result["key1"])
    h1 = _compute_zotero_metadata_hash(data)
    data_no_coll = {k: v for k, v in data.items() if k != "collections"}
    h2 = _compute_zotero_metadata_hash(data_no_coll)
    assert h1 == h2
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m pytest tests/test_zotero_watchdog.py::test_zotero_metadata_includes_collections -v`
Expected: FAIL — `KeyError: 'collections'` (field not present).

- [ ] **Step 3: Add the collections query and field**

In `src/archilles/watchdog.py`, in `_zotero_metadata_for_scan`:

First, add `"collections": []` to the per-item result initializer (the dict comprehension around line 989):

```python
        result: dict[str, dict[str, Any]] = {
            r["key"]: {
                "item_id": r["itemID"],
                "modified_at": r["dateModified"] or "",
                "title": "",
                "authors": [],
                "tags": [],
                "collections": [],
                "abstract": "",
                "date": "",
                "attachment_modified_at": None,
                "has_attachment": False,
            }
            for r in items
        }
```

Then, after the tags block (right before the "Attachments" block, ~line 1067), add a collections batch query:

```python
        # Collections — one query for all items (priority signal, NOT hashed)
        coll_rows = conn.execute("""
            SELECT ci.itemID, c.collectionName
            FROM collectionItems ci
            JOIN collections c ON ci.collectionID = c.collectionID
        """).fetchall()

        for row in coll_rows:
            key = id_to_key.get(row["itemID"])
            if key:
                result[key]["collections"].append(row["collectionName"])
        for data in result.values():
            data["collections"].sort()
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `python -m pytest tests/test_zotero_watchdog.py::test_zotero_metadata_includes_collections -v`
Expected: PASS.

- [ ] **Step 5: Run the full Zotero suite (regression)**

Run: `python -m pytest tests/test_zotero_watchdog.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/archilles/watchdog.py tests/test_zotero_watchdog.py
git commit -m "feat(zotero): surface collection names in scan metadata

Adds a collections field (sorted) per item for priority sorting. The
metadata hash is unchanged, so collection moves do not trigger re-index.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: Full Zotero priority sort (tags/authors/titles/collections + config wiring)

Replace Task 1's recency-only sort with the full priority key, add the `--first-collection` CLI flag, thread priority filters into the Zotero scan, add the Calibre-only `--rating` warning for Zotero, and add `priority_collections` to source config so the routine can pass collections.

**Files:**
- Modify: `src/archilles/watchdog.py` (`ZoteroWatchdogScanner.scan` signature + Phase 3 sort; add `_zotero_priority_key`)
- Modify: `scripts/watchdog.py` (add `--first-collection`; thread first_* into Zotero `scan_kwargs`; `--rating` warning)
- Modify: `src/archilles/config.py` (`SourceConfig.priority_collections` + parsing)
- Modify: `scripts/run_routine.py` (`_build_command` + call site: pass `--first-collection` from `src.priority_collections`)
- Test: `tests/test_zotero_watchdog.py`, `tests/test_run_routine_command.py`

**Interfaces:**
- Consumes: `_priority_match` (Task 2), `collections` scan field (Task 3), `scan(..., max_new)` (Task 1).
- Produces: `_zotero_priority_key(entry, zotero_items, first_authors, first_tags, first_titles, first_collections) -> tuple[int, int, int]`.
- Produces: `ZoteroWatchdogScanner.scan(..., max_new, first_authors, first_tags, first_titles, first_collections)`.
- Produces: `SourceConfig.priority_collections: list[str] | None`.
- Produces: `_build_command(adapter, phase, max_new, priority_tags, rating, priority_collections)`.

- [ ] **Step 1: Write the failing test — priority group beats recency (Variante A)**

In `tests/test_zotero_watchdog.py`:

```python
def test_zotero_priority_key_tag_beats_newer_untagged():
    from src.archilles.watchdog import _zotero_priority_key
    items = {
        "old_tagged":   {"item_id": 10, "authors": [], "tags": ["Prio"], "title": "", "collections": []},
        "new_untagged": {"item_id": 99, "authors": [], "tags": [],       "title": "", "collections": []},
    }
    entries = [{"doc_id": "new_untagged"}, {"doc_id": "old_tagged"}]
    ordered = sorted(entries, key=lambda e: _zotero_priority_key(
        e, items, [], ["prio"], [], []))
    # Old-but-tagged item first (group 0), then newer untagged (group 1)
    assert [e["doc_id"] for e in ordered] == ["old_tagged", "new_untagged"]


def test_zotero_priority_key_collection_match():
    from src.archilles.watchdog import _zotero_priority_key
    items = {"c": {"item_id": 5, "authors": [], "tags": [], "title": "",
                   "collections": ["Current Project"]}}
    key = _zotero_priority_key({"doc_id": "c"}, items, [], [], [], ["current project"])
    assert key[0] == 0  # group 0 = priority
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python -m pytest tests/test_zotero_watchdog.py -k zotero_priority_key -v`
Expected: FAIL — `_zotero_priority_key` not defined.

- [ ] **Step 3: Add `_zotero_priority_key` and use it in Phase 3**

In `src/archilles/watchdog.py`, add near `_index_priority_key`:

```python
def _zotero_priority_key(
    entry: dict,
    zotero_items: dict,
    first_authors: list[str],
    first_tags: list[str],
    first_titles: list[str],
    first_collections: list[str],
) -> tuple[int, int, int]:
    """Sort key for Zotero new-item indexing order.

    Returns (group, 0, recency): group 0 = explicit priority match
    (author/tag/title/collection), group 1 = normal queue. Zotero has no
    rating, so the middle slot is always 0. Recency (-item_id) puts the newest
    item first — the analog of Calibre's -calibre_id. Variante A: an explicit
    priority match beats recency (an old tagged item outranks a new untagged one).
    """
    data = zotero_items.get(entry['doc_id'], {})
    is_priority = _priority_match(
        " ".join(data.get('authors', [])),
        data.get('tags', []),
        data.get('title', ''),
        data.get('collections', []),
        first_authors,
        first_tags,
        first_titles,
        first_collections,
    )
    return (0 if is_priority else 1, 0, -data.get('item_id', 0))
```

Extend the `scan` signature (from Task 1's `max_new` version):

```python
    def scan(
        self,
        dry_run: bool = False,
        queue_new: bool = True,
        index_new: bool = False,
        max_new: int | None = None,
        first_authors: list[str] | None = None,
        first_tags: list[str] | None = None,
        first_titles: list[str] | None = None,
        first_collections: list[str] | None = None,
    ) -> dict[str, Any]:
```

Replace the Task 1 recency-only sort in Phase 3 with the priority key:

```python
                pending = sorted(
                    results['new_books'],
                    key=lambda e: _zotero_priority_key(
                        e, zotero_items,
                        first_authors or [], first_tags or [],
                        first_titles or [], first_collections or [],
                    ),
                )
                if max_new is not None:
                    pending = pending[:max_new]
                total_p3 = len(pending)
                for j, entry in enumerate(pending, 1):
```

- [ ] **Step 4: Run the priority-key tests to verify they pass**

Run: `python -m pytest tests/test_zotero_watchdog.py -k zotero_priority_key -v`
Expected: PASS.

- [ ] **Step 5: Add `--first-collection`, thread filters into Zotero scan, warn on `--rating`**

In `scripts/watchdog.py`, add the CLI flag after `--first-title` (~line 217):

```python
    parser.add_argument(
        '--first-collection', metavar='COLLECTION', dest='first_collections',
        action='append', default=[],
        help='Index items in this Zotero collection first (exact name, '
             'case-insensitive); repeatable. Zotero only.'
    )
```

Extend the Zotero `scan_kwargs` branch (from Task 1) to forward the priority filters, and warn that `--rating` is Calibre-only:

```python
    elif scanner_type == "zotero":
        scan_kwargs['max_new'] = args.max_new
        scan_kwargs['first_authors'] = args.first_authors
        scan_kwargs['first_tags'] = args.first_tags
        scan_kwargs['first_titles'] = args.first_titles
        scan_kwargs['first_collections'] = args.first_collections
        if args.rating is not None:
            print("WARNING: --rating is ignored for Zotero (Calibre-only; "
                  "Zotero has no rating field).", file=sys.stderr)
```

- [ ] **Step 6: Add `priority_collections` to source config**

In `src/archilles/config.py`, add the field to `SourceConfig` (after `priority_tags`, ~line 300):

```python
    priority_tags: list[str] | None = None
    # Zotero collection names whose items are indexed first (group 0). Exact
    # match, case-insensitive. Zotero only.
    priority_collections: list[str] | None = None
```

And in the parsing block (after the `priority` validation, ~line 395), add:

```python
        priority_coll = src.get("priority_collections")
        if priority_coll is not None and not isinstance(priority_coll, list):
            raise ValueError(
                f"Source '{src['name']}': priority_collections must be a list, "
                f"got {type(priority_coll).__name__}"
            )
```

Then add to the `SourceConfig(...)` constructor call (after `priority_tags=...`):

```python
            priority_collections=[str(c) for c in priority_coll] if priority_coll is not None else None,
```

- [ ] **Step 7: Write the failing test — routine passes `--first-collection`**

In `tests/test_run_routine_command.py`:

```python
def test_build_command_zotero_passes_collections():
    from scripts.run_routine import _build_command
    cmd = _build_command("zotero", max_new=None, priority_collections=["Current Project"])
    assert "--first-collection" in cmd
    assert "Current Project" in cmd
```

- [ ] **Step 8: Run the test to verify it fails**

Run: `python -m pytest tests/test_run_routine_command.py::test_build_command_zotero_passes_collections -v`
Expected: FAIL — `_build_command` has no `priority_collections` parameter (TypeError).

- [ ] **Step 9: Thread `priority_collections` through `_build_command` and its call site**

In `scripts/run_routine.py`, add the parameter to `_build_command`:

```python
def _build_command(
    adapter: str,
    phase: str = "A",
    max_new: int | None = None,
    priority_tags: list[str] | None = None,
    rating: int | None = None,
    priority_collections: list[str] | None = None,
) -> list[str]:
```

After the existing `--first-tag` loop (~line 82), add a collections loop (applies to Zotero; harmless for others since only Zotero honors it):

```python
        for coll in priority_collections or []:
            cmd += ["--first-collection", coll]
```

Update the call site (~line 240):

```python
    cmd = _build_command(adapter, phase=phase, max_new=args.max_new,
                         priority_tags=src.priority_tags, rating=args.rating,
                         priority_collections=src.priority_collections)
```

- [ ] **Step 10: Run the routine-command tests to verify they pass**

Run: `python -m pytest tests/test_run_routine_command.py -v`
Expected: PASS.

- [ ] **Step 11: Run the full affected suites (regression)**

Run: `python -m pytest tests/test_zotero_watchdog.py tests/test_run_routine_command.py tests/test_watchdog.py -v`
Expected: PASS.

- [ ] **Step 12: Commit**

```bash
git add src/archilles/watchdog.py scripts/watchdog.py src/archilles/config.py scripts/run_routine.py tests/test_zotero_watchdog.py tests/test_run_routine_command.py
git commit -m "feat(zotero): full priority parity (tags/authors/titles/collections)

Add _zotero_priority_key (Variante A: explicit priority beats recency),
--first-collection CLI flag, priority_collections source config, and a
Calibre-only warning for --rating under Zotero.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: End-to-end verification of the local path (OSS product quality)

Confirm a fresh, local-only (no external embedding) Zotero indexing run actually indexes new items and they become searchable. This is the product-quality gate, not a unit test.

**Files:**
- None modified. Verification only.

- [ ] **Step 1: Full test suite**

Run: `python -m pytest -q`
Expected: PASS (green suite; note the count — it should be ≥ the pre-change count).

- [ ] **Step 2: Dry-run the Zotero routine command**

Run: `python scripts/run_routine.py --source archilles-zotero --frequency daily --dry-run`
Expected: printed command contains `--index-new`. If `priority_collections` is set in `~/.archilles/config.json`, it also contains `--first-collection`.

- [ ] **Step 3: Capped real run against the live Zotero library**

Run a small, bounded indexing pass directly (bypassing the daily marker) to observe real behavior without a marathon:

Run: `python scripts/watchdog.py --json --index-new --max-new 5`
Expected: final JSON shows `"new_indexed": 5` (or the number of new items if fewer). Console shows `[1/5] … [5/5]` book headers with real extraction/embedding lines.

- [ ] **Step 4: Confirm the newly indexed items are searchable**

Run: `python scripts/rag_demo.py stats`
Expected: chunk count increased versus before Step 3.

Then a query hitting one of the just-indexed titles:

Run: `python scripts/rag_demo.py query "<a phrase from a just-indexed Zotero item>" --mode hybrid`
Expected: at least one result cites the newly indexed Zotero item.

- [ ] **Step 5: (Optional, user decision) Bound the daily Zotero run**

If the remaining backlog (~500+) should drain gradually rather than in one long run, add `--max-new N` to the Zotero scheduler wrapper `~/.archilles/scheduler/zotero.cmd` (append to the `run_routine.py` invocation is not supported — instead the routine passes it only when `args.max_new` is set; the simplest route is a dedicated capped run or adding `--max-new` handling to the wrapper). Document the chosen value. This step is an ops decision, not code.

---

## Self-Review

**Spec coverage:**
- Problem (Zotero never indexes new) → Task 1. ✓
- External-embedding integration (full-external `mark_pending`) → preserved in Task 1 (loop body unchanged). ✓
- Local path + watchdog correct for OSS → Task 5 verification. ✓
- Zotero-native priority (tags/collections) → Tasks 2, 3, 4. ✓
- `--first-collection` → Task 4 Step 5. ✓
- Generalized helper (Ansatz 1) → Task 2. ✓
- No A/B phase, no checkpoint → honored (Task 1 relies on natural re-detection). ✓
- `--rating` Calibre-only + stderr warning → Task 4 Step 5. ✓
- Recency = newest first → Tasks 1 & 4 (`-item_id`; deviation from literal "dateAdded" documented in Global Constraints). ✓
- Hash unaffected by collections → Task 3 Step 1 asserts it. ✓
- Ordering: Schritt 1 runs today → Task 1 is self-contained and delivers `new_indexed > 0`. ✓

**Placeholder scan:** No TBD/TODO. The one soft spot — `zotero_scanner_with_new_items` / `tmp_zotero_library_with_collection` fixtures — is handled by instructing reuse of the existing `tests/test_zotero_watchdog.py` fixtures and, failing that, giving the exact construction (temp sqlite with item/attachment/collection rows, stubbed `_load_rag`).

**Type consistency:** `scan(..., max_new, first_authors, first_tags, first_titles, first_collections)` consistent across Tasks 1 & 4. `_priority_match` 8-arg signature consistent between Task 2 definition and Task 4 caller. `_build_command(..., priority_collections)` consistent between Task 4 definition and call site. `_zotero_priority_key` 6-arg signature consistent between definition and test callers.
