"""
Shared configuration helpers.

Centralises the library-path lookup that was duplicated across five scripts.
"""

import os
import sys
from pathlib import Path

# Environment variable names, checked in priority order
_ENV_VARS = ("ARCHILLES_LIBRARY_PATH", "CALIBRE_LIBRARY_PATH", "CALIBRE_LIBRARY")


def get_library_path(*, required: bool = True) -> Path | None:
    """Return the Calibre library path from environment variables.

    Checks ``ARCHILLES_LIBRARY_PATH``, then the legacy
    ``CALIBRE_LIBRARY_PATH`` and ``CALIBRE_LIBRARY`` fallbacks.

    Args:
        required: If *True* (default), print a helpful error message and
            ``sys.exit(1)`` when no variable is set.  If *False*, return
            *None* instead.
    """
    for var in _ENV_VARS:
        value = os.environ.get(var)
        if value:
            return Path(value)

    if not required:
        return None

    print("\n" + "=" * 60)
    print("ERROR: Library path not set")
    print("=" * 60 + "\n")
    print("Please set one of these environment variables:\n")
    print("  Windows (PowerShell):")
    print('    $env:ARCHILLES_LIBRARY_PATH = "C:\\path\\to\\Library"\n')
    print("  Linux/macOS:")
    print('    export ARCHILLES_LIBRARY_PATH="/path/to/Library"\n')
    print("  Legacy: CALIBRE_LIBRARY_PATH is also accepted.\n")
    sys.exit(1)


def get_rag_db_path(library_path: Path | None = None) -> str:
    """Return the RAG database path, reading config.json if present."""
    if library_path is None:
        library_path = get_library_path()

    config_path = library_path / ".archilles" / "config.json"
    if config_path.exists():
        import json
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        custom = config.get("rag_db_path")
        if custom:
            return str(Path(custom) if os.path.isabs(custom) else library_path / custom)

    return str(library_path / ".archilles" / "rag_db")
