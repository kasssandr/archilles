"""verify_citation: does the quotation still stand where the citation says?

The address is the one the prepared-format spec states in §4.7 -- volume,
printed page, occurrence, wording -- and the answer never repairs it silently.
Both witnesses are tested: the bundle, which resolves through Scriptor's own
``Bundle.locate``, and the index, the fallback for a volume without one.
"""

import json

from src.archilles.citation_check import verify_citation

MASTER = """---
format_version: 0.4.0
chunking_strategy: basic
---

[p. 87] Auf der Seite davor steht ein ganz anderer, hinreichend langer Satz.

[p. 88] Vielmehr ging es um die Aneignung der Form und der Motive, die Schüler
führten die einzelnen Arbeiten aus.

[p. 89] Und auf der Seite danach steht wieder etwas ganz anderes, lang genug.

[p. 90] Auch diese Seite trägt einen Satz, der ihr allein gehört, hier steht er.

[p. 91] Und diese ebenso, mit wieder anderen Wörtern, damit nichts sich gleicht.

[p. 200] Weit hinten im Band steht ein Satz, der sonst nirgendwo vorkommt hier.
"""

PAGES = [{"pos": 87, "label": "87", "source": "printed", "confidence": 1.0},
         {"pos": 88, "label": "88", "source": "printed", "confidence": 1.0},
         {"pos": 89, "label": "89", "source": "computed", "confidence": 0.5},
         {"pos": 90, "label": "90", "source": "printed", "confidence": 1.0},
         {"pos": 91, "label": "91", "source": "printed", "confidence": 1.0},
         {"pos": 200, "label": "200", "source": "printed", "confidence": 1.0}]

QUOTE = ("Vielmehr ging es um die Aneignung der Form und der Motive, "
         "die Schüler führten die einzelnen Arbeiten aus.")
FAR = "Weit hinten im Band steht ein Satz, der sonst nirgendwo vorkommt hier."
GONE = "Ein Satz, den dieser Band nirgends druckt, in keiner seiner Zeilen."


def _sidecar(pages=PAGES, version=1):
    return json.dumps({"version": version,
                       "profile": {"edge": "bottom", "attested": 0.9, "band": None},
                       "segments": [], "pages": pages, "rejected": []})


class FakeStore:
    """The chunk store, as much of it as verify_citation asks for.

    A volume is "in the index" when its id is in ``books``; the chunks are what
    the index branch reads. The bundle tests need the first and not the second.
    """

    def __init__(self, chunks=(), books=("10593",)):
        self.chunks = list(chunks)
        self.books = set(books)

    def get_by_book_id(self, book_id, limit=100):
        if book_id not in self.books:
            return []
        rows = [c for c in self.chunks if c.get("book_id") == book_id]
        return rows[:limit] if rows else [{"book_id": book_id}][:limit]

    def get_by_id(self, chunk_id):
        return next((c for c in self.chunks if c.get("id") == chunk_id), None)


def _zone(tmp_path, master=MASTER, sidecar=None, key="10593"):
    """A library's extension zone with one book's bundle in it."""
    folder = tmp_path / ".archilles" / "scriptor" / key
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "book.md").write_text(master, encoding="utf-8")
    if sidecar is not False:
        (folder / "book.md.pagination.json").write_text(
            sidecar if sidecar is not None else _sidecar(), encoding="utf-8")
    return tmp_path / ".archilles"


def _chunk(id_, page, text, window=None, book_id="10593", label_source="printed"):
    return {"id": id_, "book_id": book_id, "page_label": page, "page_number": 0,
            "text": text, "window_text": window if window is not None else text,
            "label_source": label_source}


# the volume itself ---------------------------------------------------------

def test_a_volume_the_index_does_not_know_is_not_answered_for(tmp_path):
    out = verify_citation(FakeStore(books=()), _zone(tmp_path), "10593", "88", QUOTE)
    assert out["status"] == "unknown_volume"
    assert out["address"]["quote"] == QUOTE       # the address travels back whole


def test_a_quotation_too_short_to_address_a_passage_is_refused(tmp_path):
    out = verify_citation(FakeStore(), _zone(tmp_path), "10593", "88", "zu kurz")
    assert out["status"] == "quote_too_short"
    assert "at least 8 words" in out["error"]


# the bundle ----------------------------------------------------------------

def test_the_bundle_confirms_the_page_the_citation_names(tmp_path):
    out = verify_citation(FakeStore(), _zone(tmp_path), "10593", "88", QUOTE)
    assert out["status"] == "confirmed"
    assert out["checked_against"] == "bundle"
    assert out["label_source"] == "printed"
    assert out["page_found"] is True
    assert out["note_checked"] is False


def test_a_computed_label_confirms_as_a_computed_one(tmp_path):
    """Spec §6.3: the witness behind a label is part of the answer. A page the
    producer counted to is not one it read."""
    quote = "Und auf der Seite danach steht wieder etwas ganz anderes, lang genug."
    out = verify_citation(FakeStore(), _zone(tmp_path), "10593", "89", quote)
    assert (out["status"], out["label_source"]) == ("confirmed", "computed")


def test_the_neighbouring_page_is_offered_as_a_proposal_not_as_a_repair(tmp_path):
    out = verify_citation(FakeStore(), _zone(tmp_path), "10593", "87", QUOTE)
    assert out["status"] == "relocated"
    assert out["proposal"] == {"page": "88", "occurrence": 1}
    assert out["address"]["page"] == "87"      # what was asked stays what was asked


def test_a_passage_further_off_than_three_pages_is_stale(tmp_path):
    """``nearest`` reaches three page markers in either direction; a wording
    that moved further than that is a different passage, and the honest answer
    is that this address is gone."""
    out = verify_citation(FakeStore(), _zone(tmp_path), "10593", "88", FAR)
    assert out["status"] == "stale"
    assert out["proposal"] is None
    assert out["page_found"] is True


def test_a_wording_the_volume_does_not_carry_is_stale(tmp_path):
    out = verify_citation(FakeStore(), _zone(tmp_path), "10593", "88", GONE)
    assert out["status"] == "stale"


def test_a_page_the_volume_never_prints_says_so(tmp_path):
    out = verify_citation(FakeStore(), _zone(tmp_path), "10593", "999", QUOTE)
    assert (out["status"], out["page_found"]) == ("stale", False)


def test_a_repeated_label_is_addressed_by_its_occurrence(tmp_path):
    """A volume in parts restarts its numbering; then the label alone names no
    page and the occurrence does (§4.7)."""
    master = MASTER + "\n[p. 88] Der zweite Teil beginnt seine Zählung von vorn, hier.\n"
    pages = PAGES + [{"pos": 300, "label": "88", "source": "catalogue",
                      "confidence": 1.0}]
    zone = _zone(tmp_path, master=master, sidecar=_sidecar(pages))
    second = "Der zweite Teil beginnt seine Zählung von vorn, hier."

    first = verify_citation(FakeStore(), zone, "10593", "88", second)
    assert first["status"] == "stale"          # not on the first page 88, and far off
    again = verify_citation(FakeStore(), zone, "10593", "88", second, occurrence=2)
    assert (again["status"], again["label_source"]) == ("confirmed", "catalogue")


# the chunk id, which is a cache and no anchor ------------------------------

def test_a_chunk_id_that_moved_is_reported_and_the_address_still_holds(tmp_path):
    """Measured (P-M2): 80 to 97 per cent of chunk ids point at other text after
    a re-chunking, and they all still exist. So the chunk is asked whether it
    holds the quotation -- and the address is checked either way."""
    store = FakeStore([_chunk("c1", "88", "Ganz anderer Text steht inzwischen hier.")])
    out = verify_citation(store, _zone(tmp_path), "10593", "88", QUOTE, chunk_id="c1")
    assert out["chunk_stale"] is True
    assert out["status"] == "confirmed"

    gone = verify_citation(store, _zone(tmp_path), "10593", "88", QUOTE,
                           chunk_id="c-does-not-exist")
    assert gone["chunk_stale"] is True and gone["status"] == "confirmed"


def test_a_chunk_id_that_still_holds_the_quotation_is_not_stale(tmp_path):
    store = FakeStore([_chunk("c1", "88", f"Vorher. {QUOTE} Nachher.")])
    out = verify_citation(store, _zone(tmp_path), "10593", "88", QUOTE, chunk_id="c1")
    assert out["chunk_stale"] is False


def test_without_a_chunk_id_nothing_is_said_about_one(tmp_path):
    out = verify_citation(FakeStore(), _zone(tmp_path), "10593", "88", QUOTE)
    assert out["chunk_stale"] is None


# the index, for a volume without a bundle ----------------------------------

def test_the_index_confirms_from_the_chunk_of_that_page(tmp_path):
    store = FakeStore([_chunk("c1", "87", "Etwas anderes."),
                       _chunk("c2", "88", f"Vorher. {QUOTE} Nachher.")])
    out = verify_citation(store, tmp_path / ".archilles", "10593", "88", QUOTE)
    assert out["status"] == "confirmed"
    assert (out["checked_against"], out["chunk_id"]) == ("index", "c2")
    assert out["label_source"] == "printed"


def test_the_index_reads_the_window_where_the_chunk_boundary_cut_the_passage(tmp_path):
    store = FakeStore([_chunk("c2", "88", "Vielmehr ging es um die Aneignung der Form",
                              window=f"Vorher. {QUOTE} Nachher.")])
    out = verify_citation(store, tmp_path / ".archilles", "10593", "88", QUOTE)
    assert (out["status"], out["chunk_id"]) == ("confirmed", "c2")


def test_the_index_relocates_to_the_page_of_the_chunk_that_holds_it(tmp_path):
    store = FakeStore([_chunk("c1", "87", "Etwas anderes, ganz und gar."),
                       _chunk("c2", "212", f"Vorher. {QUOTE} Nachher.")])
    out = verify_citation(store, tmp_path / ".archilles", "10593", "88", QUOTE)
    assert out["status"] == "relocated"
    assert out["proposal"] == {"page": "212", "occurrence": 1}
    assert out["page_found"] is False


def test_the_index_is_stale_where_no_chunk_holds_the_wording(tmp_path):
    store = FakeStore([_chunk("c1", "88", "Etwas ganz anderes steht hier jetzt.")])
    out = verify_citation(store, tmp_path / ".archilles", "10593", "88", QUOTE)
    assert (out["status"], out["checked_against"]) == ("stale", "index")


def test_a_page_number_stands_in_where_a_chunk_has_no_printed_label(tmp_path):
    chunk = _chunk("c1", "", f"Vorher. {QUOTE} Nachher.", label_source="")
    chunk["page_number"] = 88
    out = verify_citation(FakeStore([chunk]), tmp_path / ".archilles",
                          "10593", "88", QUOTE)
    assert out["status"] == "confirmed" and out["label_source"] is None


# a bundle that cannot be read ----------------------------------------------

def test_a_sidecar_from_the_future_does_not_take_the_volume_down(tmp_path):
    """A sidecar version this reader does not know is refused by load_bundle.
    The volume is still indexed, so the index answers instead of nothing."""
    zone = _zone(tmp_path, sidecar='{"version": 99}')
    store = FakeStore([_chunk("c2", "88", f"Vorher. {QUOTE} Nachher.")])
    out = verify_citation(store, zone, "10593", "88", QUOTE)
    assert (out["status"], out["checked_against"]) == ("confirmed", "index")


def test_a_master_without_a_format_version_is_no_bundle(tmp_path):
    zone = _zone(tmp_path, master="[p. 88] Eine handgeschriebene Datei ohne Block.\n",
                 sidecar=False)
    store = FakeStore([_chunk("c2", "88", f"Vorher. {QUOTE} Nachher.")])
    out = verify_citation(store, zone, "10593", "88", QUOTE)
    assert out["checked_against"] == "index"


def test_without_a_library_zone_the_index_answers(tmp_path):
    store = FakeStore([_chunk("c2", "88", f"Vorher. {QUOTE} Nachher.")])
    assert verify_citation(store, None, "10593", "88", QUOTE)["checked_against"] == "index"


# the tool, as a client sees it ---------------------------------------------

def test_the_tool_is_declared_and_dispatched():
    """A tool a client cannot call is not a tool: it needs a schema and an
    entry in the dispatch map, and the method the map names must exist."""
    from unittest.mock import MagicMock

    from mcp_server import TOOL_MAP
    from src.calibre_mcp.server import CalibreMCPServer, create_mcp_tools

    tool = next(t for t in create_mcp_tools(MagicMock()) if t["name"] == "verify_citation")
    assert tool["inputSchema"]["required"] == ["book_id", "page", "quote"]
    assert set(tool["inputSchema"]["properties"]) == {
        "book_id", "page", "quote", "occurrence", "note", "chunk_id"}
    assert TOOL_MAP["verify_citation"] == "verify_citation_tool"
    assert hasattr(CalibreMCPServer, "verify_citation_tool")


def test_the_unified_server_offers_the_volume_s_library_as_a_choice():
    from unittest.mock import MagicMock, patch

    from src.calibre_mcp.unified_server import _SOURCE_OPTIONAL, create_unified_tools

    assert "verify_citation" in _SOURCE_OPTIONAL
    srv = MagicMock()
    srv.servers = {"cal1": MagicMock(), "cal2": MagicMock()}
    srv.source_names = ["cal1", "cal2"]
    srv.calibre_sources = ["cal1"]
    srv.default_source = "cal1"
    base = [{"name": "verify_citation", "description": "check",
             "inputSchema": {"type": "object", "properties": {"book_id": {}}}}]
    with patch("src.calibre_mcp.unified_server.create_mcp_tools", return_value=base):
        tools = create_unified_tools(srv)
    source = next(t for t in tools if t["name"] == "verify_citation")
    source = source["inputSchema"]["properties"]["source"]
    assert source["enum"] == ["cal1", "cal2"]
    assert "the library the volume lies in" in source["description"]


def test_without_a_source_each_library_is_asked_the_default_one_first(tmp_path):
    """A book_id belongs to one library, and a client that read it off a merged
    search result has no reason to know which."""
    from unittest.mock import MagicMock

    from src.calibre_mcp.unified_server import UnifiedMCPServer

    asked = []

    def answer(name, status):
        def _tool(**kw):
            asked.append(name)
            return {"status": status, "address": dict(kw)}
        return _tool

    first, second = MagicMock(), MagicMock()
    first.verify_citation_tool = answer("cal1", "unknown_volume")
    second.verify_citation_tool = answer("cal2", "confirmed")
    unified = UnifiedMCPServer({"cal2": second, "cal1": first},
                               default_source="cal1", master_dir=tmp_path)

    out = unified.verify_citation_tool(book_id="10593", page="88", quote=QUOTE)
    assert (out["status"], out["source"]) == ("confirmed", "cal2")
    assert asked == ["cal1", "cal2"]          # the default library first


def test_a_volume_no_library_knows_stays_unknown(tmp_path):
    from unittest.mock import MagicMock

    from src.calibre_mcp.unified_server import UnifiedMCPServer

    srv = MagicMock()
    srv.verify_citation_tool = lambda **kw: {"status": "unknown_volume"}
    unified = UnifiedMCPServer({"cal1": srv}, default_source="cal1", master_dir=tmp_path)
    assert unified.verify_citation_tool(
        book_id="x", page="1", quote=QUOTE)["status"] == "unknown_volume"
