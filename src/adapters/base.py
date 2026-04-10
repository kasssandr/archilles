"""
SourceAdapter ABC and adapter-agnostic data classes.

This module defines the interface that all library backends must implement.
The Core (pipeline, storage, retriever, service) only depends on this interface,
never on a specific backend like Calibre or Zotero.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class DocumentTimestamps:
    """Four-timestamp model for heterogeneous documents.

    All timestamps are ISO 8601 strings, all optional.
    ``created_at`` and ``modified_at`` come from the source adapter.
    ``imported_at`` and ``indexed_at`` are set by ARCHILLES itself.
    """

    created_at: str | None = None
    modified_at: str | None = None
    imported_at: str | None = None
    indexed_at: str | None = None


@dataclass
class DocumentMetadata:
    """Adapter-agnostic document metadata."""

    doc_id: str
    title: str
    authors: list[str]
    file_path: Path
    file_format: str
    tags: list[str] = field(default_factory=list)
    comments: str = ""
    comments_html: str = ""  # Raw HTML from Calibre (for structured indexing)
    language: str = ""
    year: int | None = None
    publisher: str = ""
    series: str = ""
    identifiers: dict = field(default_factory=dict)
    custom_fields: dict = field(default_factory=dict)
    timestamps: DocumentTimestamps = field(default_factory=DocumentTimestamps)


@dataclass
class DocumentAnnotation:
    """A single annotation (highlight, note, bookmark)."""

    text: str
    note: str = ""
    annotation_type: str = "highlight"
    page: int | None = None
    chapter: str = ""
    created: str = ""


class SourceAdapter(ABC):
    """Interface for all library backends.

    Every adapter provides read access to a document collection.  The Core
    never accesses Calibre, Zotero or the filesystem directly — it always
    goes through this interface.
    """

    # ── Required ────────────────────────────────────────────────

    @abstractmethod
    def list_documents(
        self,
        tag_filter: str | None = None,
        exclude_tag: str | None = None,
    ) -> list[DocumentMetadata]:
        """List all documents, optionally filtered by tag."""
        ...

    @abstractmethod
    def get_metadata(self, doc_id: str) -> DocumentMetadata | None:
        """Metadata for a single document, or ``None`` if not found."""
        ...

    @abstractmethod
    def get_file_path(self, doc_id: str) -> Path | None:
        """Absolute path to the primary file (PDF > EPUB > other)."""
        ...

    @abstractmethod
    def get_annotations(self, doc_id: str) -> list[DocumentAnnotation]:
        """Annotations (highlights, notes) for a document."""
        ...

    @abstractmethod
    def get_comments(self, doc_id: str) -> str:
        """Free-text comment / description for a document."""
        ...

    @property
    @abstractmethod
    def adapter_type(self) -> str:
        """Short identifier: ``'calibre'``, ``'zotero'``, ``'folder'``, etc."""
        ...

    @property
    @abstractmethod
    def library_path(self) -> Path:
        """Root directory of the library."""
        ...

    # ── Optional (stubs) ────────────────────────────────────────

    def watch_inbox(self, callback=None) -> None:
        """Watch the inbox/ subdirectory for new files.

        No-op by default.  Implementations may use ``watchdog`` or similar.
        """

    def get_metadata_by_path(self, file_path: Path) -> DocumentMetadata | None:
        """Look up metadata by file path instead of doc_id.

        Useful during indexing when only the file path is known.
        Default implementation iterates ``list_documents()`` — adapters
        should override with an efficient lookup.
        """
        file_path = Path(file_path).resolve()
        for doc in self.list_documents():
            if doc.file_path.resolve() == file_path:
                return doc
        return None
