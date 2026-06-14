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


def connect_readonly(
    db_path: Union[str, Path],
    *,
    immutable: bool = False,
    row_factory: Optional[Callable] = None,
) -> sqlite3.Connection:
    """Oeffnet ``db_path`` schreibgeschuetzt (``mode=ro``).

    Args:
        db_path: Pfad zur SQLite-Datei.
        immutable: zusaetzlich ``immutable=1`` (nur fuer unveraenderliche DBs).
        row_factory: optionale ``row_factory`` (z. B. ``sqlite3.Row``).

    Returns:
        Eine read-only ``sqlite3.Connection``. Schreibversuche werfen
        ``sqlite3.OperationalError``.
    """
    # as_posix() liefert Forward-Slashes inkl. Windows-Laufwerksbuchstaben
    # (D:/...), die als file:-URI verlaesslich parsen.
    uri = f"file:{Path(db_path).as_posix()}?mode=ro"
    if immutable:
        uri += "&immutable=1"
    conn = sqlite3.connect(uri, uri=True)
    if row_factory is not None:
        conn.row_factory = row_factory
    return conn
