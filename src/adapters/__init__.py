"""
Adapter factory — create the right SourceAdapter for a given library path.

Usage::

    from src.adapters import create_adapter

    adapter = create_adapter(Path("D:/Calibre-Bibliothek"))          # auto-detect
    adapter = create_adapter(Path("D:/Archilles-Lab"), "folder")     # explicit
"""

from pathlib import Path
from typing import Optional

from src.adapters.base import SourceAdapter


def detect_adapter_type(library_path: Path) -> str:
    """Auto-detect the adapter type for a given library path.

    Detection order:
      1. ``metadata.db`` present  → ``calibre``
      2. ``zotero.sqlite`` present → ``zotero``
      3. ``.obsidian/`` present   → ``obsidian``
      4. Everything else          → ``folder``
    """
    library_path = Path(library_path)

    if (library_path / "metadata.db").exists():
        return "calibre"

    if (library_path / "zotero.sqlite").exists():
        return "zotero"

    if (library_path / ".obsidian").is_dir():
        return "obsidian"

    return "folder"


def create_adapter(
    library_path: Path,
    adapter_type: Optional[str] = None,
) -> SourceAdapter:
    """Create the appropriate SourceAdapter for *library_path*.

    Parameters
    ----------
    library_path:
        Root directory of the library.
    adapter_type:
        ``"calibre"``, ``"zotero"``, ``"folder"``, or ``None`` for auto-detection.
    """
    library_path = Path(library_path)

    if adapter_type is None:
        adapter_type = detect_adapter_type(library_path)

    if adapter_type == "calibre":
        from src.adapters.calibre_adapter import CalibreAdapter

        return CalibreAdapter(library_path)

    if adapter_type == "zotero":
        from src.adapters.zotero_adapter import ZoteroAdapter

        return ZoteroAdapter(library_path)

    if adapter_type == "obsidian":
        from src.adapters.obsidian_adapter import ObsidianAdapter

        return ObsidianAdapter(library_path)

    if adapter_type == "folder":
        from src.adapters.folder_adapter import FolderAdapter

        return FolderAdapter(library_path)

    raise ValueError(
        f"Unknown adapter type: {adapter_type!r}. "
        f"Supported: 'calibre', 'zotero', 'obsidian', 'folder'."
    )
