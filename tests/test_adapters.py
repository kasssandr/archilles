"""
Tests for the SourceAdapter interface, factory, and CalibreAdapter.

These tests use a temporary SQLite database that mimics Calibre's schema,
so they run without a real Calibre library.
"""

import sqlite3
import textwrap
from pathlib import Path

import pytest

from src.adapters.base import (
    DocumentAnnotation,
    DocumentMetadata,
    DocumentTimestamps,
    SourceAdapter,
)
from src.adapters import create_adapter, detect_adapter_type


# ── Fixtures ────────────────────────────────────────────────────


def _create_calibre_db(library_path: Path, books=None):
    """Create a minimal Calibre metadata.db for testing."""
    db_path = library_path / "metadata.db"
    conn = sqlite3.connect(db_path)

    conn.executescript(
        textwrap.dedent("""\
        CREATE TABLE books (
            id INTEGER PRIMARY KEY,
            title TEXT NOT NULL,
            path TEXT NOT NULL,
            has_cover INTEGER DEFAULT 0,
            timestamp TEXT,
            pubdate TEXT,
            last_modified TEXT
        );
        CREATE TABLE authors (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL
        );
        CREATE TABLE books_authors_link (
            id INTEGER PRIMARY KEY,
            book INTEGER NOT NULL,
            author INTEGER NOT NULL
        );
        CREATE TABLE publishers (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL
        );
        CREATE TABLE books_publishers_link (
            id INTEGER PRIMARY KEY,
            book INTEGER NOT NULL,
            publisher INTEGER NOT NULL
        );
        CREATE TABLE languages (
            id INTEGER PRIMARY KEY,
            lang_code TEXT NOT NULL
        );
        CREATE TABLE books_languages_link (
            id INTEGER PRIMARY KEY,
            book INTEGER NOT NULL,
            lang_code INTEGER NOT NULL
        );
        CREATE TABLE tags (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL
        );
        CREATE TABLE books_tags_link (
            id INTEGER PRIMARY KEY,
            book INTEGER NOT NULL,
            tag INTEGER NOT NULL
        );
        CREATE TABLE comments (
            id INTEGER PRIMARY KEY,
            book INTEGER NOT NULL,
            text TEXT
        );
        CREATE TABLE identifiers (
            id INTEGER PRIMARY KEY,
            book INTEGER NOT NULL,
            type TEXT NOT NULL,
            val TEXT NOT NULL
        );
        CREATE TABLE custom_columns (
            id INTEGER PRIMARY KEY,
            label TEXT NOT NULL,
            name TEXT NOT NULL,
            datatype TEXT NOT NULL,
            display TEXT
        );
    """)
    )

    if books is None:
        books = [
            {
                "id": 1,
                "title": "Test Book",
                "path": "Author One/Test Book (1)",
                "author": "Author One",
                "publisher": "Test Press",
                "language": "eng",
                "tags": ["History", "Science"],
                "isbn": "978-3-16-148410-0",
                "comments": "<p>A <b>great</b> book.</p>",
                "pubdate": "2020-01-15T00:00:00",
                "last_modified": "2025-06-01T12:00:00",
            },
        ]

    for book in books:
        conn.execute(
            "INSERT INTO books (id, title, path, pubdate, last_modified) VALUES (?, ?, ?, ?, ?)",
            (book["id"], book["title"], book["path"],
             book.get("pubdate"), book.get("last_modified")),
        )
        # Author
        conn.execute("INSERT OR IGNORE INTO authors (id, name) VALUES (?, ?)", (book["id"], book["author"]))
        conn.execute("INSERT INTO books_authors_link (book, author) VALUES (?, ?)", (book["id"], book["id"]))

        # Publisher
        if book.get("publisher"):
            conn.execute("INSERT OR IGNORE INTO publishers (id, name) VALUES (?, ?)", (book["id"], book["publisher"]))
            conn.execute("INSERT INTO books_publishers_link (book, publisher) VALUES (?, ?)", (book["id"], book["id"]))

        # Language
        if book.get("language"):
            conn.execute("INSERT OR IGNORE INTO languages (id, lang_code) VALUES (?, ?)", (book["id"], book["language"]))
            conn.execute("INSERT INTO books_languages_link (book, lang_code) VALUES (?, ?)", (book["id"], book["id"]))

        # Tags
        for i, tag in enumerate(book.get("tags", [])):
            tag_id = book["id"] * 100 + i
            conn.execute("INSERT OR IGNORE INTO tags (id, name) VALUES (?, ?)", (tag_id, tag))
            conn.execute("INSERT INTO books_tags_link (book, tag) VALUES (?, ?)", (book["id"], tag_id))

        # ISBN
        if book.get("isbn"):
            conn.execute(
                "INSERT INTO identifiers (book, type, val) VALUES (?, 'isbn', ?)",
                (book["id"], book["isbn"]),
            )

        # Comments
        if book.get("comments"):
            conn.execute("INSERT INTO comments (book, text) VALUES (?, ?)", (book["id"], book["comments"]))

        # Create book directory with a dummy PDF
        book_dir = library_path / book["path"]
        book_dir.mkdir(parents=True, exist_ok=True)
        dummy_file = book_dir / f"{book['title']}.pdf"
        dummy_file.write_text("dummy")

    conn.commit()
    conn.close()


@pytest.fixture
def calibre_library(tmp_path):
    """Create a temporary Calibre library with one test book."""
    _create_calibre_db(tmp_path)
    return tmp_path


@pytest.fixture
def calibre_library_multi(tmp_path):
    """Create a Calibre library with multiple books for filter tests."""
    books = [
        {
            "id": 1,
            "title": "Ancient History",
            "path": "Smith/Ancient History (1)",
            "author": "Smith",
            "publisher": "Academic Press",
            "language": "eng",
            "tags": ["History", "Antiquity"],
            "isbn": "111-1-11-111111-1",
            "comments": "About ancient civilizations.",
            "pubdate": "2019-05-01T00:00:00",
            "last_modified": "2025-01-01T00:00:00",
        },
        {
            "id": 2,
            "title": "Modern Physics",
            "path": "Jones/Modern Physics (2)",
            "author": "Jones",
            "publisher": "Science House",
            "language": "deu",
            "tags": ["Science", "Physics"],
            "isbn": None,
            "comments": None,
            "pubdate": "2022-03-15T00:00:00",
            "last_modified": "2025-02-01T00:00:00",
        },
        {
            "id": 3,
            "title": "Excluded Book",
            "path": "Doe/Excluded Book (3)",
            "author": "Doe",
            "publisher": None,
            "language": "eng",
            "tags": ["Doublette"],
            "isbn": None,
            "comments": None,
            "pubdate": None,
            "last_modified": None,
        },
    ]
    _create_calibre_db(tmp_path, books)
    return tmp_path


@pytest.fixture
def empty_folder(tmp_path):
    """An empty directory (no metadata.db)."""
    return tmp_path


# ── Auto-Detection ──────────────────────────────────────────────


class TestDetectAdapterType:
    def test_calibre_detected(self, calibre_library):
        assert detect_adapter_type(calibre_library) == "calibre"

    def test_folder_fallback(self, empty_folder):
        assert detect_adapter_type(empty_folder) == "folder"

    def test_obsidian_returns_folder(self, empty_folder):
        (empty_folder / ".obsidian").mkdir()
        assert detect_adapter_type(empty_folder) == "folder"


# ── Factory ─────────────────────────────────────────────────────


class TestCreateAdapter:
    def test_auto_calibre(self, calibre_library):
        adapter = create_adapter(calibre_library)
        assert adapter.adapter_type == "calibre"

    def test_auto_folder(self, empty_folder):
        adapter = create_adapter(empty_folder)
        assert adapter.adapter_type == "folder"

    def test_explicit_calibre(self, calibre_library):
        adapter = create_adapter(calibre_library, "calibre")
        assert adapter.adapter_type == "calibre"

    def test_explicit_folder(self, empty_folder):
        adapter = create_adapter(empty_folder, "folder")
        assert adapter.adapter_type == "folder"

    def test_unknown_type_raises(self, empty_folder):
        with pytest.raises(ValueError, match="Unknown adapter type"):
            create_adapter(empty_folder, "notion")

    def test_calibre_missing_db_raises(self, empty_folder):
        with pytest.raises(FileNotFoundError):
            create_adapter(empty_folder, "calibre")


# ── CalibreAdapter ──────────────────────────────────────────────


class TestCalibreAdapter:
    def test_adapter_type(self, calibre_library):
        adapter = create_adapter(calibre_library)
        assert adapter.adapter_type == "calibre"

    def test_library_path(self, calibre_library):
        adapter = create_adapter(calibre_library)
        assert adapter.library_path == calibre_library

    def test_list_documents(self, calibre_library):
        adapter = create_adapter(calibre_library)
        docs = adapter.list_documents()
        assert len(docs) == 1
        doc = docs[0]
        assert isinstance(doc, DocumentMetadata)
        assert doc.doc_id == "1"
        assert doc.title == "Test Book"
        assert doc.authors == ["Author One"]
        assert doc.file_format == "pdf"
        assert "History" in doc.tags
        assert "Science" in doc.tags

    def test_list_documents_tag_filter(self, calibre_library_multi):
        adapter = create_adapter(calibre_library_multi)
        docs = adapter.list_documents(tag_filter="History")
        assert len(docs) == 1
        assert docs[0].title == "Ancient History"

    def test_list_documents_exclude_tag(self, calibre_library_multi):
        adapter = create_adapter(calibre_library_multi)
        docs = adapter.list_documents(exclude_tag="Doublette")
        titles = {d.title for d in docs}
        assert "Excluded Book" not in titles
        assert len(docs) == 2

    def test_get_metadata(self, calibre_library):
        adapter = create_adapter(calibre_library)
        meta = adapter.get_metadata("1")
        assert meta is not None
        assert meta.doc_id == "1"
        assert meta.title == "Test Book"
        assert meta.publisher == "Test Press"
        assert meta.language == "eng"
        assert meta.identifiers.get("isbn") == "978-3-16-148410-0"

    def test_get_metadata_not_found(self, calibre_library):
        adapter = create_adapter(calibre_library)
        assert adapter.get_metadata("999") is None

    def test_get_file_path(self, calibre_library):
        adapter = create_adapter(calibre_library)
        fp = adapter.get_file_path("1")
        assert fp is not None
        assert fp.suffix == ".pdf"
        assert fp.exists()

    def test_get_comments(self, calibre_library):
        adapter = create_adapter(calibre_library)
        comments = adapter.get_comments("1")
        assert "great" in comments
        assert "<b>" not in comments  # HTML stripped

    def test_get_comments_empty(self, calibre_library_multi):
        adapter = create_adapter(calibre_library_multi)
        assert adapter.get_comments("2") == ""

    def test_get_annotations_empty(self, calibre_library):
        adapter = create_adapter(calibre_library)
        annots = adapter.get_annotations("1")
        assert annots == []

    def test_timestamps(self, calibre_library):
        adapter = create_adapter(calibre_library)
        meta = adapter.get_metadata("1")
        assert meta is not None
        assert meta.timestamps.created_at is not None
        assert "2020" in meta.timestamps.created_at
        assert meta.timestamps.modified_at is not None
        assert "2025" in meta.timestamps.modified_at
        # imported_at and indexed_at are set by ARCHILLES, not the adapter
        assert meta.timestamps.imported_at is None
        assert meta.timestamps.indexed_at is None


# ── DocumentMetadata Dataclass ──────────────────────────────────


class TestDocumentMetadata:
    def test_defaults(self):
        meta = DocumentMetadata(
            doc_id="test",
            title="Test",
            authors=["A"],
            file_path=Path("/tmp/test.pdf"),
            file_format="pdf",
        )
        assert meta.tags == []
        assert meta.comments == ""
        assert meta.language == ""
        assert meta.identifiers == {}
        assert meta.custom_fields == {}
        assert isinstance(meta.timestamps, DocumentTimestamps)

    def test_timestamps_default(self):
        ts = DocumentTimestamps()
        assert ts.created_at is None
        assert ts.modified_at is None
        assert ts.imported_at is None
        assert ts.indexed_at is None


# ── FolderAdapter (stub) ────────────────────────────────────────


class TestFolderAdapterStub:
    def test_adapter_type(self, empty_folder):
        adapter = create_adapter(empty_folder, "folder")
        assert adapter.adapter_type == "folder"

    def test_list_documents_not_implemented(self, empty_folder):
        adapter = create_adapter(empty_folder, "folder")
        with pytest.raises(NotImplementedError):
            adapter.list_documents()

    def test_annotations_empty(self, empty_folder):
        adapter = create_adapter(empty_folder, "folder")
        assert adapter.get_annotations("any") == []

    def test_comments_empty(self, empty_folder):
        adapter = create_adapter(empty_folder, "folder")
        assert adapter.get_comments("any") == ""
