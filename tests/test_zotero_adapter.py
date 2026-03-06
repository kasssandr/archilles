"""
Tests for the ZoteroAdapter.

Uses a temporary SQLite database that mimics Zotero's schema,
so tests run without a real Zotero installation.
"""

import sqlite3
from pathlib import Path

import pytest

from src.adapters.base import DocumentAnnotation, DocumentMetadata
from src.adapters import create_adapter, detect_adapter_type


# ── Fixtures ────────────────────────────────────────────────────


def _create_zotero_db(library_path: Path, items=None):
    """Create a minimal zotero.sqlite for testing."""
    db_path = library_path / "zotero.sqlite"
    conn = sqlite3.connect(str(db_path))

    conn.executescript("""
        CREATE TABLE itemTypes (
            itemTypeID INTEGER PRIMARY KEY,
            typeName TEXT NOT NULL
        );
        INSERT INTO itemTypes VALUES (1, 'annotation');
        INSERT INTO itemTypes VALUES (3, 'attachment');
        INSERT INTO itemTypes VALUES (7, 'book');
        INSERT INTO itemTypes VALUES (8, 'bookSection');
        INSERT INTO itemTypes VALUES (12, 'journalArticle');
        INSERT INTO itemTypes VALUES (27, 'note');

        CREATE TABLE items (
            itemID INTEGER PRIMARY KEY,
            itemTypeID INTEGER NOT NULL,
            libraryID INTEGER DEFAULT 1,
            key TEXT UNIQUE NOT NULL,
            dateAdded TEXT,
            dateModified TEXT,
            clientDateModified TEXT
        );

        CREATE TABLE deletedItems (
            itemID INTEGER PRIMARY KEY
        );

        CREATE TABLE fields (
            fieldID INTEGER PRIMARY KEY,
            fieldName TEXT NOT NULL
        );
        INSERT INTO fields VALUES (1, 'title');
        INSERT INTO fields VALUES (2, 'abstractNote');
        INSERT INTO fields VALUES (3, 'date');
        INSERT INTO fields VALUES (4, 'publisher');
        INSERT INTO fields VALUES (5, 'language');
        INSERT INTO fields VALUES (6, 'ISBN');
        INSERT INTO fields VALUES (7, 'DOI');
        INSERT INTO fields VALUES (8, 'series');
        INSERT INTO fields VALUES (9, 'shortTitle');
        INSERT INTO fields VALUES (10, 'ISSN');

        CREATE TABLE itemDataValues (
            valueID INTEGER PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE itemData (
            itemID INTEGER NOT NULL,
            fieldID INTEGER NOT NULL,
            valueID INTEGER NOT NULL,
            PRIMARY KEY (itemID, fieldID)
        );

        CREATE TABLE creatorTypes (
            creatorTypeID INTEGER PRIMARY KEY,
            creatorType TEXT NOT NULL
        );
        INSERT INTO creatorTypes VALUES (1, 'author');
        INSERT INTO creatorTypes VALUES (2, 'editor');
        INSERT INTO creatorTypes VALUES (3, 'translator');

        CREATE TABLE creators (
            creatorID INTEGER PRIMARY KEY,
            firstName TEXT,
            lastName TEXT NOT NULL
        );

        CREATE TABLE itemCreators (
            itemID INTEGER NOT NULL,
            creatorID INTEGER NOT NULL,
            creatorTypeID INTEGER NOT NULL,
            orderIndex INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE tags (
            tagID INTEGER PRIMARY KEY,
            name TEXT NOT NULL
        );

        CREATE TABLE itemTags (
            itemID INTEGER NOT NULL,
            tagID INTEGER NOT NULL,
            type INTEGER DEFAULT 0
        );

        CREATE TABLE itemAttachments (
            itemID INTEGER PRIMARY KEY,
            parentItemID INTEGER,
            linkMode INTEGER,
            contentType TEXT,
            path TEXT
        );

        CREATE TABLE itemNotes (
            itemID INTEGER PRIMARY KEY,
            parentItemID INTEGER,
            note TEXT,
            title TEXT
        );

        CREATE TABLE itemAnnotations (
            itemID INTEGER PRIMARY KEY,
            parentItemID INTEGER,
            type TEXT,
            text TEXT,
            comment TEXT,
            color TEXT,
            sortIndex TEXT,
            position TEXT
        );

        CREATE TABLE collections (
            collectionID INTEGER PRIMARY KEY,
            collectionName TEXT,
            parentCollectionID INTEGER,
            libraryID INTEGER,
            key TEXT
        );

        CREATE TABLE collectionItems (
            collectionID INTEGER NOT NULL,
            itemID INTEGER NOT NULL
        );
    """)

    _value_counter = [0]

    def _add_value(conn, text):
        _value_counter[0] += 1
        vid = _value_counter[0]
        conn.execute("INSERT INTO itemDataValues (valueID, value) VALUES (?, ?)", (vid, text))
        return vid

    def _set_field(conn, item_id, field_name, value):
        field_id = conn.execute(
            "SELECT fieldID FROM fields WHERE fieldName = ?", (field_name,)
        ).fetchone()[0]
        vid = _add_value(conn, value)
        conn.execute(
            "INSERT INTO itemData (itemID, fieldID, valueID) VALUES (?, ?, ?)",
            (item_id, field_id, vid),
        )

    if items is None:
        items = [
            {
                "itemID": 1,
                "key": "ABCD1234",
                "itemTypeID": 7,  # book
                "title": "The Test Book",
                "authors": [("Jane", "Doe"), ("John", "Smith")],
                "date": "2020",
                "publisher": "Test Press",
                "language": "eng",
                "isbn": "978-3-16-148410-0",
                "abstractNote": "A fine book about testing.",
                "tags": ["History", "Testing"],
                "dateAdded": "2025-01-15T10:00:00",
                "dateModified": "2025-06-01T14:30:00",
                "attachment": {
                    "itemID": 100,
                    "key": "ATT00001",
                    "linkMode": 0,
                    "contentType": "application/pdf",
                    "path": "storage:test-book.pdf",
                    "filename": "test-book.pdf",
                },
                "notes": [
                    '<div class="zotero-note znv1"><p>This is an <b>important</b> note.</p></div>',
                ],
            },
        ]

    creator_counter = 0
    tag_counter = 0
    note_counter = 200
    ann_counter = 300

    for item in items:
        # Insert item
        conn.execute(
            "INSERT INTO items (itemID, itemTypeID, key, dateAdded, dateModified) VALUES (?, ?, ?, ?, ?)",
            (item["itemID"], item["itemTypeID"], item["key"],
             item.get("dateAdded"), item.get("dateModified")),
        )

        # Set EAV fields
        for field in ("title", "abstractNote", "date", "publisher", "language", "ISBN", "DOI", "series", "shortTitle", "ISSN"):
            mapped = field
            if field == "ISBN":
                mapped = "isbn"
            elif field == "DOI":
                mapped = "doi"
            elif field == "ISSN":
                mapped = "issn"
            val = item.get(mapped if mapped != field else field)
            if val:
                _set_field(conn, item["itemID"], field, val)

        # Creators
        for first, last in item.get("authors", []):
            creator_counter += 1
            conn.execute(
                "INSERT INTO creators (creatorID, firstName, lastName) VALUES (?, ?, ?)",
                (creator_counter, first, last),
            )
            conn.execute(
                "INSERT INTO itemCreators (itemID, creatorID, creatorTypeID, orderIndex) VALUES (?, ?, 1, ?)",
                (item["itemID"], creator_counter, creator_counter - 1),
            )

        for first, last in item.get("editors", []):
            creator_counter += 1
            conn.execute(
                "INSERT INTO creators (creatorID, firstName, lastName) VALUES (?, ?, ?)",
                (creator_counter, first, last),
            )
            conn.execute(
                "INSERT INTO itemCreators (itemID, creatorID, creatorTypeID, orderIndex) VALUES (?, ?, 2, ?)",
                (item["itemID"], creator_counter, creator_counter - 1),
            )

        # Tags
        for tag_name in item.get("tags", []):
            tag_counter += 1
            conn.execute("INSERT OR IGNORE INTO tags (tagID, name) VALUES (?, ?)", (tag_counter, tag_name))
            conn.execute("INSERT INTO itemTags (itemID, tagID) VALUES (?, ?)", (item["itemID"], tag_counter))

        # Attachment
        att = item.get("attachment")
        if att:
            conn.execute(
                "INSERT INTO items (itemID, itemTypeID, key, dateAdded, dateModified) VALUES (?, 3, ?, ?, ?)",
                (att["itemID"], att["key"], item.get("dateAdded"), item.get("dateModified")),
            )
            conn.execute(
                "INSERT INTO itemAttachments (itemID, parentItemID, linkMode, contentType, path) VALUES (?, ?, ?, ?, ?)",
                (att["itemID"], item["itemID"], att["linkMode"], att["contentType"], att["path"]),
            )
            # Create the actual file
            storage_dir = library_path / "storage" / att["key"]
            storage_dir.mkdir(parents=True, exist_ok=True)
            (storage_dir / att["filename"]).write_bytes(b"dummy content")

        # Notes
        for note_html in item.get("notes", []):
            note_counter += 1
            conn.execute(
                "INSERT INTO items (itemID, itemTypeID, key, dateAdded, dateModified) VALUES (?, 27, ?, ?, ?)",
                (note_counter, f"NOTE{note_counter:04d}", item.get("dateAdded"), item.get("dateModified")),
            )
            conn.execute(
                "INSERT INTO itemNotes (itemID, parentItemID, note) VALUES (?, ?, ?)",
                (note_counter, item["itemID"], note_html),
            )

        # Annotations
        for ann in item.get("annotations", []):
            ann_counter += 1
            parent_att = att["itemID"] if att else item["itemID"]
            conn.execute(
                "INSERT INTO items (itemID, itemTypeID, key, dateAdded, dateModified) VALUES (?, 1, ?, ?, ?)",
                (ann_counter, f"ANN{ann_counter:04d}", item.get("dateAdded"), item.get("dateModified")),
            )
            conn.execute(
                "INSERT INTO itemAnnotations (itemID, parentItemID, type, text, comment) VALUES (?, ?, ?, ?, ?)",
                (ann_counter, parent_att, ann.get("type", "highlight"), ann.get("text", ""), ann.get("comment", "")),
            )

        # Deleted items
        if item.get("deleted"):
            conn.execute("INSERT INTO deletedItems (itemID) VALUES (?)", (item["itemID"],))

    conn.commit()
    conn.close()


@pytest.fixture
def zotero_library(tmp_path):
    """Create a minimal Zotero library with one test book."""
    _create_zotero_db(tmp_path)
    return tmp_path


@pytest.fixture
def zotero_library_multi(tmp_path):
    """Create a Zotero library with multiple items for filter/edge-case tests."""
    items = [
        {
            "itemID": 1,
            "key": "BOOK0001",
            "itemTypeID": 7,
            "title": "Ancient Rome",
            "authors": [("Mary", "Johnson")],
            "date": "2019-05-01",
            "publisher": "Academic Press",
            "language": "eng",
            "isbn": "111-1-11-111111-1",
            "abstractNote": "About ancient Rome.",
            "tags": ["History", "Antiquity"],
            "dateAdded": "2025-01-01T00:00:00",
            "dateModified": "2025-06-01T00:00:00",
            "attachment": {
                "itemID": 100,
                "key": "ATT10001",
                "linkMode": 0,
                "contentType": "application/pdf",
                "path": "storage:rome.pdf",
                "filename": "rome.pdf",
            },
            "notes": [
                '<div class="zotero-note znv1"><p>Key insight about Roman trade.</p></div>',
            ],
            "annotations": [
                {"type": "highlight", "text": "The Roman economy was vast.", "comment": "Important!"},
            ],
        },
        {
            "itemID": 2,
            "key": "ARTICLE1",
            "itemTypeID": 12,  # journalArticle
            "title": "Quantum Physics Today",
            "authors": [("", "Einstein")],
            "date": "2022",
            "language": "deu",
            "tags": ["Science", "Physics"],
            "dateAdded": "2025-02-01T00:00:00",
            "dateModified": "2025-03-01T00:00:00",
            # No attachment — metadata-only
        },
        {
            "itemID": 3,
            "key": "DELETED1",
            "itemTypeID": 7,
            "title": "Deleted Book",
            "authors": [],
            "deleted": True,
        },
        {
            "itemID": 4,
            "key": "NOAUTHOR",
            "itemTypeID": 7,
            "title": "Anonymous Work",
            "editors": [("Ed", "Itor")],
            "tags": ["Doublette"],
        },
    ]
    _create_zotero_db(tmp_path, items)
    return tmp_path


# ── Auto-Detection ──────────────────────────────────────────────


class TestZoteroDetection:
    def test_zotero_detected(self, zotero_library):
        assert detect_adapter_type(zotero_library) == "zotero"

    def test_calibre_takes_priority(self, tmp_path):
        """If both metadata.db and zotero.sqlite exist, Calibre wins."""
        (tmp_path / "metadata.db").touch()
        (tmp_path / "zotero.sqlite").touch()
        assert detect_adapter_type(tmp_path) == "calibre"

    def test_factory_creates_zotero(self, zotero_library):
        adapter = create_adapter(zotero_library)
        assert adapter.adapter_type == "zotero"

    def test_factory_explicit_zotero(self, zotero_library):
        adapter = create_adapter(zotero_library, "zotero")
        assert adapter.adapter_type == "zotero"

    def test_factory_missing_db_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            create_adapter(tmp_path, "zotero")


# ── Basic Metadata ──────────────────────────────────────────────


class TestZoteroMetadata:
    def test_adapter_type(self, zotero_library):
        adapter = create_adapter(zotero_library)
        assert adapter.adapter_type == "zotero"

    def test_library_path(self, zotero_library):
        adapter = create_adapter(zotero_library)
        assert adapter.library_path == zotero_library

    def test_list_documents(self, zotero_library):
        adapter = create_adapter(zotero_library)
        docs = adapter.list_documents()
        assert len(docs) == 1
        doc = docs[0]
        assert isinstance(doc, DocumentMetadata)
        assert doc.doc_id == "ABCD1234"
        assert doc.title == "The Test Book"
        assert doc.authors == ["Jane Doe", "John Smith"]
        assert doc.language == "eng"
        assert doc.year == 2020
        assert doc.publisher == "Test Press"
        assert doc.identifiers.get("isbn") == "978-3-16-148410-0"

    def test_list_documents_excludes_deleted(self, zotero_library_multi):
        adapter = create_adapter(zotero_library_multi)
        docs = adapter.list_documents()
        keys = {d.doc_id for d in docs}
        assert "DELETED1" not in keys

    def test_list_documents_excludes_attachments_and_notes(self, zotero_library):
        """Attachment and note items should not appear as documents."""
        adapter = create_adapter(zotero_library)
        docs = adapter.list_documents()
        assert len(docs) == 1  # only the book, not the attachment or note

    def test_tag_filter(self, zotero_library_multi):
        adapter = create_adapter(zotero_library_multi)
        docs = adapter.list_documents(tag_filter="History")
        assert len(docs) == 1
        assert docs[0].doc_id == "BOOK0001"

    def test_exclude_tag(self, zotero_library_multi):
        adapter = create_adapter(zotero_library_multi)
        docs = adapter.list_documents(exclude_tag="Doublette")
        keys = {d.doc_id for d in docs}
        assert "NOAUTHOR" not in keys

    def test_get_metadata(self, zotero_library):
        adapter = create_adapter(zotero_library)
        meta = adapter.get_metadata("ABCD1234")
        assert meta is not None
        assert meta.title == "The Test Book"
        assert meta.tags == ["History", "Testing"]
        assert meta.comments == "A fine book about testing."

    def test_get_metadata_not_found(self, zotero_library):
        adapter = create_adapter(zotero_library)
        assert adapter.get_metadata("NONEXIST") is None

    def test_timestamps(self, zotero_library):
        adapter = create_adapter(zotero_library)
        meta = adapter.get_metadata("ABCD1234")
        assert meta.timestamps.created_at == "2025-01-15T10:00:00"
        assert meta.timestamps.modified_at == "2025-06-01T14:30:00"
        assert meta.timestamps.imported_at is None
        assert meta.timestamps.indexed_at is None

    def test_editor_fallback(self, zotero_library_multi):
        """Items with editors but no authors should list editors."""
        adapter = create_adapter(zotero_library_multi)
        meta = adapter.get_metadata("NOAUTHOR")
        assert meta.authors == ["Ed Itor"]

    def test_metadata_only_item(self, zotero_library_multi):
        """Items without attachments should still appear with empty file_path."""
        adapter = create_adapter(zotero_library_multi)
        meta = adapter.get_metadata("ARTICLE1")
        assert meta is not None
        assert meta.title == "Quantum Physics Today"
        assert str(meta.file_path) in ("", ".")
        assert meta.file_format == ""

    def test_lastname_only_author(self, zotero_library_multi):
        """Author with empty firstName should use lastName only."""
        adapter = create_adapter(zotero_library_multi)
        meta = adapter.get_metadata("ARTICLE1")
        assert meta.authors == ["Einstein"]


# ── File Paths ──────────────────────────────────────────────────


class TestZoteroFilePaths:
    def test_get_file_path_imported(self, zotero_library):
        adapter = create_adapter(zotero_library)
        fp = adapter.get_file_path("ABCD1234")
        assert fp is not None
        assert fp.name == "test-book.pdf"
        assert fp.exists()

    def test_get_file_path_no_attachment(self, zotero_library_multi):
        adapter = create_adapter(zotero_library_multi)
        assert adapter.get_file_path("ARTICLE1") is None

    def test_get_file_path_not_found(self, zotero_library):
        adapter = create_adapter(zotero_library)
        assert adapter.get_file_path("NONEXIST") is None

    def test_file_format_pdf(self, zotero_library):
        adapter = create_adapter(zotero_library)
        meta = adapter.get_metadata("ABCD1234")
        assert meta.file_format == "pdf"


# ── Annotations & Notes ────────────────────────────────────────


class TestZoteroAnnotations:
    def test_notes_extracted(self, zotero_library):
        adapter = create_adapter(zotero_library)
        anns = adapter.get_annotations("ABCD1234")
        assert len(anns) == 1
        ann = anns[0]
        assert isinstance(ann, DocumentAnnotation)
        assert ann.annotation_type == "note"
        assert "important note" in ann.text.lower()
        assert "<b>" not in ann.text  # HTML stripped

    def test_highlights_and_notes(self, zotero_library_multi):
        adapter = create_adapter(zotero_library_multi)
        anns = adapter.get_annotations("BOOK0001")
        types = {a.annotation_type for a in anns}
        assert "highlight" in types
        assert "note" in types

    def test_highlight_text_and_comment(self, zotero_library_multi):
        adapter = create_adapter(zotero_library_multi)
        anns = adapter.get_annotations("BOOK0001")
        highlight = [a for a in anns if a.annotation_type == "highlight"][0]
        assert "Roman economy" in highlight.text
        assert "Important" in highlight.note

    def test_annotations_empty_for_missing(self, zotero_library):
        adapter = create_adapter(zotero_library)
        assert adapter.get_annotations("NONEXIST") == []


# ── Comments ────────────────────────────────────────────────────


class TestZoteroComments:
    def test_get_comments(self, zotero_library):
        adapter = create_adapter(zotero_library)
        comments = adapter.get_comments("ABCD1234")
        assert "fine book" in comments

    def test_get_comments_empty(self, zotero_library_multi):
        adapter = create_adapter(zotero_library_multi)
        assert adapter.get_comments("NOAUTHOR") == ""

    def test_get_comments_not_found(self, zotero_library):
        adapter = create_adapter(zotero_library)
        assert adapter.get_comments("NONEXIST") == ""
