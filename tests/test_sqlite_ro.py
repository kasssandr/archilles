"""Befund 1.22: read-only-SQLite-Helper erzwingt die Calibre/Zotero-Grenze.

Die Read-only-Grenze ("ARCHILLES schreibt nie in Calibre/Zotero") war bisher
nur Konvention. ``connect_readonly`` erzwingt sie auf Treiberebene via
``mode=ro``-URI, sodass jeder Schreibversuch hart fehlschlaegt.
"""
import sqlite3

import pytest

from src.archilles.sqlite_ro import connect_readonly


@pytest.fixture
def db(tmp_path):
    """Eine kleine echte SQLite-DB mit einer Zeile."""
    path = tmp_path / "metadata.db"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE books (id INTEGER PRIMARY KEY, title TEXT)")
    con.execute("INSERT INTO books (id, title) VALUES (1, 'Sein und Zeit')")
    con.commit()
    con.close()
    return path


class TestConnectReadonly:
    def test_select_works(self, db):
        conn = connect_readonly(db)
        try:
            row = conn.execute("SELECT title FROM books WHERE id = 1").fetchone()
            assert row[0] == "Sein und Zeit"
        finally:
            conn.close()

    def test_write_is_rejected(self, db):
        conn = connect_readonly(db)
        try:
            with pytest.raises(sqlite3.OperationalError, match="readonly"):
                conn.execute("UPDATE books SET title = 'x' WHERE id = 1")
        finally:
            conn.close()

    def test_insert_is_rejected(self, db):
        conn = connect_readonly(db)
        try:
            with pytest.raises(sqlite3.OperationalError, match="readonly"):
                conn.execute("INSERT INTO books (id, title) VALUES (2, 'y')")
        finally:
            conn.close()

    def test_row_factory_applied(self, db):
        conn = connect_readonly(db, row_factory=sqlite3.Row)
        try:
            row = conn.execute("SELECT title FROM books WHERE id = 1").fetchone()
            assert row["title"] == "Sein und Zeit"
        finally:
            conn.close()

    def test_accepts_path_and_str(self, db):
        # Sowohl pathlib.Path als auch str muessen funktionieren.
        for arg in (db, str(db)):
            conn = connect_readonly(arg)
            try:
                assert conn.execute("SELECT COUNT(*) FROM books").fetchone()[0] == 1
            finally:
                conn.close()

    def test_immutable_still_reads(self, db):
        # immutable=1 ist fuer statische DBs gedacht; SELECT muss weiter klappen.
        conn = connect_readonly(db, immutable=True)
        try:
            assert conn.execute("SELECT COUNT(*) FROM books").fetchone()[0] == 1
        finally:
            conn.close()
