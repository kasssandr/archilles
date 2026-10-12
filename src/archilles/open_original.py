"""Open an original — the file a search result came from — on this machine.

Claude Desktop renders no link to a local target (``calibre://``,
``zotero://``, ``file:///`` — tested 2026-10-12), so the MCP server opens the
work itself: it runs where the library lives. A PDF asked for at a page goes
to a viewer that can jump there (SumatraPDF, else Acrobat); everything else
goes to the program Windows has for the file type.

Only a file an adapter resolved from a library ID is opened, never a path a
client names, and only document types: indexed text reaches the client, and
no text may start a program through this.
"""

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

OPENABLE_SUFFIXES = frozenset({
    ".pdf", ".epub", ".djvu", ".mobi", ".azw3", ".md", ".txt", ".docx", ".odt", ".rtf",
})

# Set to a viewer's .exe to override the search below.
VIEWER_ENV = "ARCHILLES_PDF_VIEWER"


def _viewer_candidates() -> list[Path]:
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    programs = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
    programs_x86 = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
    return [
        local / "SumatraPDF" / "SumatraPDF.exe",
        programs / "SumatraPDF" / "SumatraPDF.exe",
        programs / "Adobe" / "Acrobat DC" / "Acrobat" / "Acrobat.exe",
        programs_x86 / "Adobe" / "Acrobat Reader DC" / "Reader" / "AcroRd32.exe",
    ]


def find_page_viewer() -> Path | None:
    """The PDF viewer that opens a file at a page: ``$ARCHILLES_PDF_VIEWER``,
    else the first SumatraPDF or Acrobat installed. The default PDF program
    stays untouched — PDF24, for one, takes no page on its command line."""
    override = os.environ.get(VIEWER_ENV)
    if override:
        return Path(override) if Path(override).is_file() else None
    return next((p for p in _viewer_candidates() if p.is_file()), None)


def page_command(viewer: Path, file: Path, page: int) -> list[str] | None:
    """The command line that opens ``file`` at the physical ``page``, or None
    for a viewer whose page switch is not known here."""
    name = viewer.stem.lower()
    if "sumatra" in name:
        return [str(viewer), "-reuse-instance", "-page", str(page), str(file)]
    if name in ("acrobat", "acrord32"):
        return [str(viewer), "/A", f"page={page}", str(file)]
    return None


def _spawn(command: list[str]) -> None:
    # Detached and without inherited stdio: the MCP server's stdout carries
    # JSON-RPC, and a viewer writing to it would corrupt the protocol.
    flags = getattr(subprocess, "DETACHED_PROCESS", 0)
    subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, close_fds=True, creationflags=flags)


def _start(target: str) -> None:
    """Hand a file or URL to the program the system has for it."""
    if sys.platform == "win32":
        os.startfile(target)  # noqa: S606 — a resolved document or calibre:// URL
    else:
        _spawn(["open" if sys.platform == "darwin" else "xdg-open", target])


def open_file(file: Path, page: int | None = None) -> dict[str, Any]:
    """Open a resolved original, at ``page`` where it is a PDF and a page
    viewer is installed."""
    if file.suffix.lower() not in OPENABLE_SUFFIXES:
        return {"status": "refused", "file": str(file),
                "error": f"{file.suffix or 'a file without suffix'} is no document type this opens"}
    if not file.is_file():
        return {"status": "missing", "file": str(file),
                "error": "the library names this file, but it is not on disk"}

    if page and file.suffix.lower() == ".pdf":
        viewer = find_page_viewer()
        command = page_command(viewer, file, page) if viewer else None
        if command:
            _spawn(command)
            return {"status": "opened", "file": str(file), "page": page, "viewer": viewer.stem}

    _start(str(file))
    result: dict[str, Any] = {"status": "opened", "file": str(file), "page": None,
                              "viewer": "default"}
    if page:
        result["note"] = ("opened at its start: no viewer that jumps to a page "
                          f"(SumatraPDF, Acrobat or ${VIEWER_ENV}) was found for this file")
    return result


def open_in_calibre(calibre_id: int) -> dict[str, Any]:
    """Select a book in the Calibre library currently open."""
    url = f"calibre://show-book/_/{calibre_id}"
    _start(url)
    return {"status": "opened", "url": url}
