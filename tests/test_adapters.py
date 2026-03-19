"""
Tests for the SourceAdapter interface, factory, and CalibreAdapter.

These tests use a temporary SQLite database that mimics Calibre's schema,
so they run without a real Calibre library.
"""

import json
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

    def test_obsidian_detected(self, empty_folder):
        (empty_folder / ".obsidian").mkdir()
        assert detect_adapter_type(empty_folder) == "obsidian"


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


# ── FolderAdapter ───────────────────────────────────────────────


@pytest.fixture
def folder_library(tmp_path):
    """Create a temporary folder library with test files and sidecar metadata."""
    # Plain text file (no sidecar)
    (tmp_path / "notes").mkdir()
    (tmp_path / "notes" / "my-hypothesis.txt").write_text("Some notes", encoding="utf-8")

    # PDF with sidecar metadata
    (tmp_path / "papers").mkdir()
    (tmp_path / "papers" / "important-paper.pdf").write_bytes(b"dummy pdf")
    sidecar_dir = tmp_path / ".archilles" / "metadata" / "papers"
    sidecar_dir.mkdir(parents=True)
    (sidecar_dir / "important-paper.pdf.json").write_text(
        json.dumps({
            "title": "An Important Paper",
            "authors": ["Jane Doe", "John Smith"],
            "tags": ["History", "Antiquity"],
            "comments": "Groundbreaking research on ancient trade.",
            "language": "eng",
            "year": 2023,
            "publisher": "Academic Press",
            "timestamps": {
                "created_at": "2023-06-15T10:00:00",
                "modified_at": "2024-01-20T14:30:00",
            },
        }),
        encoding="utf-8",
    )

    # Chat-import style filename
    (tmp_path / "chats").mkdir()
    (tmp_path / "chats" / "2026-03-01_claude_josephus-context.md").write_text(
        "Chat content", encoding="utf-8"
    )

    # Excerpt-style filename
    (tmp_path / "7570_goodman_rome-and-jerusalem.md").write_text(
        "Excerpt content", encoding="utf-8"
    )

    # Unsupported file (should be ignored)
    (tmp_path / "image.png").write_bytes(b"\x89PNG")

    # Ignored directory
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config.txt").write_text("git stuff")

    return tmp_path


class TestFolderAdapter:
    def test_adapter_type(self, folder_library):
        adapter = create_adapter(folder_library, "folder")
        assert adapter.adapter_type == "folder"

    def test_library_path(self, folder_library):
        adapter = create_adapter(folder_library, "folder")
        assert adapter.library_path == folder_library

    def test_list_documents_finds_supported_files(self, folder_library):
        adapter = create_adapter(folder_library, "folder")
        docs = adapter.list_documents()
        formats = {d.file_format for d in docs}
        assert "txt" in formats
        assert "pdf" in formats
        assert "md" in formats
        assert "png" not in formats

    def test_list_documents_ignores_dotdirs(self, folder_library):
        adapter = create_adapter(folder_library, "folder")
        docs = adapter.list_documents()
        paths = [str(d.file_path) for d in docs]
        assert not any(".git" in p for p in paths)

    def test_list_documents_count(self, folder_library):
        adapter = create_adapter(folder_library, "folder")
        docs = adapter.list_documents()
        # notes/my-hypothesis.txt, papers/important-paper.pdf,
        # chats/2026-03-01_claude_josephus-context.md, 7570_goodman_rome-and-jerusalem.md
        assert len(docs) == 4

    def test_sidecar_metadata_applied(self, folder_library):
        adapter = create_adapter(folder_library, "folder")
        docs = adapter.list_documents()
        paper = [d for d in docs if d.file_format == "pdf"][0]
        assert paper.title == "An Important Paper"
        assert paper.authors == ["Jane Doe", "John Smith"]
        assert "History" in paper.tags
        assert paper.language == "eng"
        assert paper.year == 2023
        assert paper.publisher == "Academic Press"
        assert paper.comments == "Groundbreaking research on ancient trade."
        assert paper.timestamps.created_at == "2023-06-15T10:00:00"
        assert paper.timestamps.modified_at == "2024-01-20T14:30:00"

    def test_filename_parsing_chat(self, folder_library):
        adapter = create_adapter(folder_library, "folder")
        docs = adapter.list_documents()
        chat = [d for d in docs if "josephus" in d.title.lower()][0]
        assert chat.title == "josephus context"
        assert chat.custom_fields.get("source_platform") == "claude"

    def test_filename_parsing_excerpt(self, folder_library):
        adapter = create_adapter(folder_library, "folder")
        docs = adapter.list_documents()
        excerpt = [d for d in docs if "goodman" in str(d.file_path)][0]
        assert "goodman" in excerpt.authors[0].lower() or "rome" in excerpt.title.lower()
        assert excerpt.custom_fields.get("ref_id") == "7570"

    def test_filename_fallback_title(self, folder_library):
        adapter = create_adapter(folder_library, "folder")
        docs = adapter.list_documents()
        note = [d for d in docs if d.file_path.name == "my-hypothesis.txt"][0]
        assert note.title == "my hypothesis"

    def test_tag_filter(self, folder_library):
        adapter = create_adapter(folder_library, "folder")
        docs = adapter.list_documents(tag_filter="History")
        assert len(docs) == 1
        assert docs[0].title == "An Important Paper"

    def test_exclude_tag(self, folder_library):
        adapter = create_adapter(folder_library, "folder")
        docs = adapter.list_documents(exclude_tag="History")
        titles = {d.title for d in docs}
        assert "An Important Paper" not in titles

    def test_get_metadata_by_id(self, folder_library):
        adapter = create_adapter(folder_library, "folder")
        docs = adapter.list_documents()
        doc_id = docs[0].doc_id
        meta = adapter.get_metadata(doc_id)
        assert meta is not None
        assert meta.doc_id == doc_id

    def test_get_metadata_not_found(self, folder_library):
        adapter = create_adapter(folder_library, "folder")
        assert adapter.get_metadata("folder:nonexistent") is None

    def test_get_file_path(self, folder_library):
        adapter = create_adapter(folder_library, "folder")
        docs = adapter.list_documents()
        fp = adapter.get_file_path(docs[0].doc_id)
        assert fp is not None
        assert fp.exists()

    def test_get_metadata_by_path(self, folder_library):
        adapter = create_adapter(folder_library, "folder")
        paper_path = folder_library / "papers" / "important-paper.pdf"
        meta = adapter.get_metadata_by_path(paper_path)
        assert meta is not None
        assert meta.title == "An Important Paper"

    def test_get_metadata_by_path_not_found(self, folder_library):
        adapter = create_adapter(folder_library, "folder")
        assert adapter.get_metadata_by_path(Path("/nonexistent/file.pdf")) is None

    def test_annotations_empty(self, folder_library):
        adapter = create_adapter(folder_library, "folder")
        docs = adapter.list_documents()
        assert adapter.get_annotations(docs[0].doc_id) == []

    def test_get_comments_from_sidecar(self, folder_library):
        adapter = create_adapter(folder_library, "folder")
        docs = adapter.list_documents()
        paper = [d for d in docs if d.file_format == "pdf"][0]
        assert "Groundbreaking" in adapter.get_comments(paper.doc_id)

    def test_get_comments_no_sidecar(self, folder_library):
        adapter = create_adapter(folder_library, "folder")
        docs = adapter.list_documents()
        note = [d for d in docs if d.file_path.name == "my-hypothesis.txt"][0]
        assert adapter.get_comments(note.doc_id) == ""

    def test_doc_id_stable(self, folder_library):
        """Same file always gets the same doc_id."""
        adapter = create_adapter(folder_library, "folder")
        docs1 = {d.file_path.name: d.doc_id for d in adapter.list_documents()}
        adapter.invalidate_cache()
        docs2 = {d.file_path.name: d.doc_id for d in adapter.list_documents()}
        assert docs1 == docs2

    def test_doc_id_starts_with_folder(self, folder_library):
        adapter = create_adapter(folder_library, "folder")
        for doc in adapter.list_documents():
            assert doc.doc_id.startswith("folder:")

    def test_filesystem_timestamps_fallback(self, folder_library):
        """Files without sidecar timestamps get filesystem timestamps."""
        adapter = create_adapter(folder_library, "folder")
        docs = adapter.list_documents()
        note = [d for d in docs if d.file_path.name == "my-hypothesis.txt"][0]
        assert note.timestamps.created_at is not None
        assert note.timestamps.modified_at is not None
        assert note.timestamps.imported_at is None

    def test_invalidate_cache(self, folder_library):
        adapter = create_adapter(folder_library, "folder")
        docs1 = adapter.list_documents()
        # Add a new file
        (folder_library / "new-note.txt").write_text("new", encoding="utf-8")
        # Cache should still return old results
        docs2 = adapter.list_documents()
        assert len(docs2) == len(docs1)
        # After invalidation, new file appears
        adapter.invalidate_cache()
        docs3 = adapter.list_documents()
        assert len(docs3) == len(docs1) + 1

    def test_get_changed_files(self, folder_library):
        adapter = create_adapter(folder_library, "folder")
        # All files should be "changed" since before they were created
        changed = adapter.get_changed_files("2000-01-01T00:00:00+00:00")
        assert len(changed) == 4
        # No files should be "changed" since far future
        changed_future = adapter.get_changed_files("2099-01-01T00:00:00+00:00")
        # The sidecar file has explicit modified_at in 2024, so only non-sidecar
        # files with filesystem timestamps (which are "now") should show up
        # Actually the sidecar file has 2024-01-20 which is < 2099, so it won't be included
        # But files without sidecar have current filesystem mtime which is also < 2099
        assert len(changed_future) == 0

    def test_empty_folder(self, empty_folder):
        adapter = create_adapter(empty_folder, "folder")
        assert adapter.list_documents() == []
        assert adapter.get_metadata("any") is None
        assert adapter.get_file_path("any") is None


# ── ObsidianAdapter ─────────────────────────────────────────────


@pytest.fixture
def obsidian_vault(tmp_path):
    """Create a minimal Obsidian vault for testing."""
    # .obsidian config dir (enables auto-detection)
    (tmp_path / ".obsidian").mkdir()

    # .trash — should NOT be indexed
    (tmp_path / ".trash").mkdir()
    (tmp_path / ".trash" / "deleted_note.md").write_text(
        "---\ntitle: Deleted\n---\nThis should not be indexed.",
        encoding="utf-8",
    )

    # Note with full frontmatter
    (tmp_path / "Notizen").mkdir()
    (tmp_path / "Notizen" / "josephus-hypothese.md").write_text(
        textwrap.dedent("""\
        ---
        title: Die Josephus-Hypothese
        authors:
          - Max Mustermann
          - Anna Beispiel
        tags:
          - Judentum
          - Antike
        created: "2025-11-01"
        language: de
        type: research-note
        source_llm: claude-3-5-sonnet
        aliases:
          - Josephus
        ---

        Ein erster Absatz über die Hypothese.

        Mehr Details folgen hier. Verweis auf [[Flavius Josephus]] und [[Römisches Reich]].
        Ein Inline-Tag: #Historiographie und #Antike/Judentum.
        """),
        encoding="utf-8",
    )

    # Note without any frontmatter
    (tmp_path / "Notizen" / "ohne-frontmatter.md").write_text(
        "Kein Frontmatter hier. Nur Text. #lesezeichen",
        encoding="utf-8",
    )

    # Chat-import style filename (Obsidian should still parse filename)
    (tmp_path / "KI-Chats").mkdir()
    (tmp_path / "KI-Chats" / "2026-03-01_claude_thema.md").write_text(
        "---\ntitle: KI-Chat Thema\n---\nInhalt des Chats.",
        encoding="utf-8",
    )

    # Non-markdown file (FolderAdapter logic should handle it)
    (tmp_path / "papers").mkdir()
    (tmp_path / "papers" / "wichtig.pdf").write_bytes(b"dummy pdf")

    return tmp_path


class TestObsidianAdapter:
    def test_adapter_type(self, obsidian_vault):
        from src.adapters.obsidian_adapter import ObsidianAdapter
        adapter = ObsidianAdapter(obsidian_vault)
        assert adapter.adapter_type == "obsidian"

    def test_autodetect(self, obsidian_vault):
        from src.adapters.obsidian_adapter import ObsidianAdapter
        adapter = create_adapter(obsidian_vault)
        assert isinstance(adapter, ObsidianAdapter)
        assert adapter.adapter_type == "obsidian"

    def test_folder_override(self, obsidian_vault):
        from src.adapters.folder_adapter import FolderAdapter
        adapter = create_adapter(obsidian_vault, "folder")
        assert isinstance(adapter, FolderAdapter)
        assert adapter.adapter_type == "folder"

    def test_frontmatter_title_tags_authors(self, obsidian_vault):
        adapter = create_adapter(obsidian_vault)
        docs = adapter.list_documents()
        note = next(d for d in docs if "josephus" in d.file_path.name)
        assert note.title == "Die Josephus-Hypothese"
        assert note.authors == ["Max Mustermann", "Anna Beispiel"]
        assert "Judentum" in note.tags
        assert "Antike" in note.tags
        assert note.language == "de"
        assert note.year == 2025

    def test_frontmatter_missing_fields_no_crash(self, obsidian_vault):
        adapter = create_adapter(obsidian_vault)
        docs = adapter.list_documents()
        note = next(d for d in docs if d.file_path.name == "ohne-frontmatter.md")
        assert note.title == "ohne-frontmatter"  # falls back to stem
        assert isinstance(note.tags, list)
        assert isinstance(note.authors, list)

    def test_wikilinks_extracted(self, obsidian_vault):
        adapter = create_adapter(obsidian_vault)
        docs = adapter.list_documents()
        note = next(d for d in docs if "josephus" in d.file_path.name)
        wikilinks = note.custom_fields.get("wikilinks", [])
        assert "Flavius Josephus" in wikilinks
        assert "Römisches Reich" in wikilinks

    def test_inline_tags_merged(self, obsidian_vault):
        adapter = create_adapter(obsidian_vault)
        docs = adapter.list_documents()
        note = next(d for d in docs if "josephus" in d.file_path.name)
        # frontmatter tags + inline tags combined
        assert "Historiographie" in note.tags
        assert "Antike/Judentum" in note.tags

    def test_trash_excluded(self, obsidian_vault):
        adapter = create_adapter(obsidian_vault)
        docs = adapter.list_documents()
        paths = [str(d.file_path) for d in docs]
        assert not any(".trash" in p for p in paths)

    def test_obsidian_dir_excluded(self, obsidian_vault):
        adapter = create_adapter(obsidian_vault)
        docs = adapter.list_documents()
        paths = [str(d.file_path) for d in docs]
        assert not any(".obsidian" in p for p in paths)

    def test_non_md_file_indexed(self, obsidian_vault):
        adapter = create_adapter(obsidian_vault)
        docs = adapter.list_documents()
        formats = {d.file_format for d in docs}
        assert "pdf" in formats

    def test_existing_folder_adapter_tests_pass(self, obsidian_vault):
        """Obsidian adapter inherits FolderAdapter — basic contract holds."""
        adapter = create_adapter(obsidian_vault)
        docs = adapter.list_documents()
        assert len(docs) > 0
        for doc in docs:
            assert doc.doc_id.startswith("folder:")
            assert isinstance(doc.tags, list)
            assert doc.file_path.exists()

    def test_custom_fields_type_and_source_llm(self, obsidian_vault):
        adapter = create_adapter(obsidian_vault)
        docs = adapter.list_documents()
        note = next(d for d in docs if "josephus" in d.file_path.name)
        assert note.custom_fields.get("type") == "research-note"
        assert note.custom_fields.get("source_llm") == "claude-3-5-sonnet"
        assert note.custom_fields.get("aliases") == ["Josephus"]

    def test_first_paragraph_as_comment(self, obsidian_vault):
        adapter = create_adapter(obsidian_vault)
        docs = adapter.list_documents()
        note = next(d for d in docs if "josephus" in d.file_path.name)
        assert "Hypothese" in adapter.get_comments(note.doc_id)
