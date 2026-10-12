"""open_original: the way from a citation to the original on this machine.

Claude Desktop renders no link to a local target, so the MCP server opens the
file itself. Nothing is launched here: ``_spawn`` and ``_start`` are replaced
by recorders, and the tests read what would have been run.
"""

from pathlib import Path
from types import SimpleNamespace

import pytest

from src.archilles import open_original as oo


@pytest.fixture
def launched(monkeypatch):
    calls = []
    monkeypatch.setattr(oo, "_spawn", lambda cmd: calls.append(("spawn", cmd)))
    monkeypatch.setattr(oo, "_start", lambda target: calls.append(("start", target)))
    return calls


@pytest.fixture
def pdf(tmp_path):
    f = tmp_path / "Aneignung (10593)" / "Aneignung.pdf"
    f.parent.mkdir()
    f.write_bytes(b"%PDF")
    return f


def _viewer(tmp_path, monkeypatch, name):
    exe = tmp_path / name
    exe.write_bytes(b"")
    monkeypatch.setenv(oo.VIEWER_ENV, str(exe))
    return exe


# the command line ------------------------------------------------------------------

def test_sumatra_opens_a_pdf_at_the_page(tmp_path, monkeypatch, launched, pdf):
    exe = _viewer(tmp_path, monkeypatch, "SumatraPDF.exe")
    res = oo.open_file(pdf, page=104)
    assert launched == [("spawn", [str(exe), "-reuse-instance", "-page", "104", str(pdf)])]
    assert (res["status"], res["page"], res["viewer"]) == ("opened", 104, "SumatraPDF")


def test_acrobat_takes_the_page_as_an_open_parameter(tmp_path, monkeypatch, launched, pdf):
    exe = _viewer(tmp_path, monkeypatch, "Acrobat.exe")
    oo.open_file(pdf, page=7)
    assert launched == [("spawn", [str(exe), "/A", "page=7", str(pdf)])]


def test_without_a_page_viewer_the_default_program_opens_it_and_says_so(
        tmp_path, monkeypatch, launched, pdf):
    _viewer(tmp_path, monkeypatch, "PDF24.exe")     # no page switch known
    res = oo.open_file(pdf, page=104)
    assert launched == [("start", str(pdf))]
    assert res["page"] is None and "note" in res


def test_an_epub_goes_to_its_default_program(tmp_path, launched):
    book = tmp_path / "Aneignung.epub"
    book.write_bytes(b"PK")
    oo.open_file(book, page=12)
    assert launched == [("start", str(book))]


# what is never opened --------------------------------------------------------------

def test_a_program_is_never_started(tmp_path, launched):
    exe = tmp_path / "setup.exe"
    exe.write_bytes(b"MZ")
    assert oo.open_file(exe)["status"] == "refused"
    assert launched == []


def test_a_file_that_is_gone_is_reported_not_opened(tmp_path, launched):
    assert oo.open_file(tmp_path / "gone.pdf")["status"] == "missing"
    assert launched == []


# the server ------------------------------------------------------------------------

def _server(adapter):
    from src.calibre_mcp.server import CalibreMCPServer
    server = object.__new__(CalibreMCPServer)
    server.adapter = adapter
    return server


def _calibre(files):
    def get_file_path(doc_id):
        return files.get(int(doc_id))     # int() raises on a Zotero key, as the real one does
    return SimpleNamespace(adapter_type="calibre", get_file_path=get_file_path)


def test_the_id_is_resolved_by_the_library_not_taken_as_a_path(launched, pdf):
    res = _server(_calibre({10593: pdf})).open_original_tool(id="10593")
    assert res["status"] == "opened" and launched == [("start", str(pdf))]


def test_another_library_s_id_is_unknown_here(launched):
    assert _server(_calibre({})).open_original_tool(id="ZA7ZHAD8")["status"] == "unknown_volume"
    assert launched == []


def test_in_calibre_selects_the_book_there(launched):
    res = _server(_calibre({})).open_original_tool(id="8695", in_calibre=True)
    assert launched == [("start", "calibre://show-book/_/8695")]
    assert res["status"] == "opened"


def test_the_unified_server_asks_until_a_source_knows_the_id(tmp_path, launched, pdf):
    from src.calibre_mcp.unified_server import UnifiedMCPServer
    zotero = _server(SimpleNamespace(adapter_type="zotero",
                                     get_file_path=lambda k: pdf if k == "ZA7ZHAD8" else None))
    unified = UnifiedMCPServer(servers={"lib": _server(_calibre({})), "zot": zotero},
                               default_source="lib", master_dir=tmp_path)
    res = unified.open_original_tool(id="ZA7ZHAD8")
    assert (res["status"], res["source"]) == ("opened", "zot")


def test_the_tool_is_offered_and_dispatched():
    import mcp_server
    from src.calibre_mcp.server import CalibreMCPServer, create_mcp_tools
    assert mcp_server.TOOL_MAP["open_original"] == "open_original_tool"
    tool = next(t for t in create_mcp_tools(object.__new__(CalibreMCPServer))
                if t["name"] == "open_original")
    assert tool["inputSchema"]["required"] == ["id"]
