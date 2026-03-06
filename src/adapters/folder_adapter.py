"""
Folder adapter — indexes any directory of files.

This is the adapter for the Archilles Lab and for users without Calibre/Zotero.
Full implementation in Phase 6; this stub satisfies the factory import.
"""

import logging
from pathlib import Path
from typing import Optional

from src.adapters.base import (
    DocumentAnnotation,
    DocumentMetadata,
    SourceAdapter,
)

logger = logging.getLogger(__name__)


class FolderAdapter(SourceAdapter):
    """Adapter for plain directory structures.

    Reads a directory recursively.  Metadata comes from:
    1. Sidecar JSON (``<library>/.archilles/metadata/<relative-path>.json``)
    2. File properties (PDF metadata, etc.)
    3. Filename parsing
    """

    def __init__(self, library_path: Path):
        self._library_path = Path(library_path)
        if not self._library_path.is_dir():
            raise NotADirectoryError(f"Not a directory: {self._library_path}")

    @property
    def adapter_type(self) -> str:
        return "folder"

    @property
    def library_path(self) -> Path:
        return self._library_path

    def list_documents(
        self,
        tag_filter: Optional[str] = None,
        exclude_tag: Optional[str] = None,
    ) -> list[DocumentMetadata]:
        raise NotImplementedError("FolderAdapter.list_documents() — Phase 6")

    def get_metadata(self, doc_id: str) -> Optional[DocumentMetadata]:
        raise NotImplementedError("FolderAdapter.get_metadata() — Phase 6")

    def get_file_path(self, doc_id: str) -> Optional[Path]:
        raise NotImplementedError("FolderAdapter.get_file_path() — Phase 6")

    def get_annotations(self, doc_id: str) -> list[DocumentAnnotation]:
        return []

    def get_comments(self, doc_id: str) -> str:
        return ""
