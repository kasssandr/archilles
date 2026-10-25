"""Befund 1.22: read-only-SQLite-Verbindungen auf Treiberebene.

ARCHILLES verspricht, nie in Calibres ``metadata.db`` oder Zoteros
``zotero.sqlite`` zu schreiben. Bisher war das nur Konvention -- alle
Verbindungen wurden read-write geoeffnet. ``connect_readonly`` erzwingt die
Grenze ueber einen ``mode=ro``-URI: ein versehentliches INSERT/UPDATE/DELETE
schlaegt dann mit ``sqlite3.OperationalError`` fehl statt die Quell-DB zu
veraendern.

Verwendung:
    conn = connect_readonly(library / "metadata.db", row_factory=sqlite3.Row)

``immutable=True`` setzt zusaetzlich ``immutable=1`` -- nur fuer DBs sinnvoll,
die sich waehrend der Verbindung garantiert nicht aendern (z. B. eine kopierte
Snapshot-DB). Bei Live-DBs (Calibre/Zotero laufen evtl. parallel) ``immutable``
weglassen, damit SQLite Aenderungen anderer Prozesse weiterhin sieht.
"""
import sqlite3
from pathlib import Path
from typing import Callable, Optional, Union

# 60 s, not 5 (finding 1.16): 5 s was tuned for "a brief writer lock", but a
# Zotero sync holds longer. On 2026-09-04 a routine run died of exactly that,
# 21 minutes into *one* book (1160 s of embedding on the T1000), so a long
# exposure to a database the user works in at the same time. Waiting costs
# such a caller nothing; it runs for minutes anyway, while an abort loses the
# whole run.
DEFAULT_BUSY_TIMEOUT_MS = 60_000

# What a process answering a person sets instead: an MCP client gives up on a
# tool call after 60 s, and an open Zotero app holds zotero.sqlite locked for
# as long as it runs, so waiting gains nothing there. 60 s became ~85 s on
# Windows and turned every list_tags into a timeout (2026-10-23).
INTERACTIVE_BUSY_TIMEOUT_MS = 3_000

_default_busy_timeout_ms = DEFAULT_BUSY_TIMEOUT_MS


def set_default_busy_timeout(ms: int) -> None:
    """Set the lock wait for every later connection that names none.

    Process-wide on purpose: the MCP server calls it once at startup, which
    reaches every adapter and analyzer it builds without threading a
    parameter through each of them. Explicit ``busy_timeout_ms`` still wins.
    """
    global _default_busy_timeout_ms
    _default_busy_timeout_ms = int(ms)


def connect_readonly(
    db_path: Union[str, Path],
    *,
    immutable: bool = False,
    busy_timeout_ms: Optional[int] = None,
    row_factory: Optional[Callable] = None,
) -> sqlite3.Connection:
    """Open ``db_path`` read-only (``mode=ro``).

    Args:
        db_path: path to the SQLite file.
        immutable: add ``immutable=1`` (only for databases that cannot change;
            leave it off for live ones, or SQLite ignores the WAL and reads
            stale or half-written pages, finding 4.4).
        busy_timeout_ms: how long to wait on a lock before ``SQLITE_BUSY``;
            0 disables waiting. ``None`` takes the process default
            (:data:`DEFAULT_BUSY_TIMEOUT_MS` unless
            :func:`set_default_busy_timeout` changed it).
        row_factory: optional ``row_factory`` (e.g. ``sqlite3.Row``).

    Returns:
        A read-only ``sqlite3.Connection``; write attempts raise
        ``sqlite3.OperationalError``.
    """
    if busy_timeout_ms is None:
        busy_timeout_ms = _default_busy_timeout_ms
    # as_posix() gives forward slashes, drive letter included (D:/...), which
    # parse reliably as a file: URI.
    uri = f"file:{Path(db_path).as_posix()}?mode=ro"
    if immutable:
        uri += "&immutable=1"
    conn = sqlite3.connect(uri, uri=True)
    # Set explicitly (even 0) — Python's sqlite3.connect already defaults
    # timeout=5.0s, so 0 must override that to genuinely disable waiting.
    conn.execute(f"PRAGMA busy_timeout = {int(busy_timeout_ms)}")
    if row_factory is not None:
        conn.row_factory = row_factory
    return conn
