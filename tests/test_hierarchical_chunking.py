"""
Tests für hierarchisches (Parent-Child / Small-to-Big) Chunking — Option A.

Der hierarchische Pfad baut die Hierarchie aus den bereits strukturbewusst
extrahierten Chunks (``extracted.chunks``): die Eingabe-Chunks werden zu
CHILD-Chunks (Metadaten — section_type/page/page_label/chapter — und char-
Offsets bleiben erhalten), aufeinanderfolgende Children derselben Sektion
werden zu PARENT-Chunks gruppiert.

Das ist die Korrektur des Regresses, den die Validierung (Briefing „Parent-
Child-Validierung", Prüfschritt 1) gefunden hatte: der frühere Pfad chunkte
``full_text`` neu und verlor dabei alle Struktur-/Seiten-Metadaten.

Embedding-frei — reine Gruppierungs-Logik, analog zu ``test_chunker_textloss``.
"""

from src.extractors.base import BaseExtractor
from src.archilles.constants import ChunkType


PARENT_SIZE = 200  # Token-Budget für Parents im Test (klein → mehrere Parents)


def _structured_chunks():
    """Simuliert strukturbewusste Extractor-Chunks (PDF-Extractor-Form):
    metadata-Dict mit section_type/page/page_label/chapter/section_title und
    char_start/char_end; jeder Chunk trägt window_text."""
    # (chapter, section_title, n_chunks, start_page)
    specs = [
        ("Einleitung", None, 5, 1),
        ("Hauptteil", "Abschnitt A", 8, 5),
        ("Hauptteil", "Abschnitt B", 8, 12),
        ("Schluss", None, 4, 20),
    ]
    chunks = []
    pos = 0
    for chapter, section_title, n, start_page in specs:
        for k in range(n):
            idx = len(chunks)
            text = f"{chapter[:3]} Absatz {k:02d}. " + " ".join(
                f"w{idx}_{j}" for j in range(40)
            )
            meta = {
                "section_type": "main_content",
                "page": start_page + k // 2,
                "page_label": str(start_page + k // 2),
                "chapter": chapter,
                "section_title": section_title,
                "char_start": pos,
                "char_end": pos + len(text),
                "source_file": "book.pdf",
                "format": "pdf",
            }
            chunks.append({"text": text, "metadata": meta, "window_text": f"<<{text}>>"})
            pos += len(text) + 2
    return chunks


def _group(chunks=None, parent_size=PARENT_SIZE):
    chunks = _structured_chunks() if chunks is None else chunks
    return BaseExtractor._group_chunks_hierarchically(
        chunks, book_id="TESTBOOK", parent_size=parent_size
    )


def _split(out):
    parents = [c for c in out if c["metadata"]["chunk_type"] == ChunkType.PARENT]
    children = [c for c in out if c["metadata"]["chunk_type"] == ChunkType.CHILD]
    return parents, children


def _sect_key(meta):
    return (meta.get("section_type"), meta.get("chapter"), meta.get("section_title"))


def _tokens(text):
    return len(text.split()) * 1.3


class TestStructure:
    def test_produces_parents_and_children(self):
        parents, children = _split(_group())
        assert len(parents) >= 2
        assert len(children) == len(_structured_chunks())

    def test_chunk_types_partition_all_chunks(self):
        out = _group()
        assert {c["metadata"]["chunk_type"] for c in out} <= {
            ChunkType.PARENT,
            ChunkType.CHILD,
        }

    def test_chunk_ids_unique(self):
        out = _group()
        ids = [c["chunk_id"] for c in out]
        assert len(ids) == len(set(ids))


class TestLinkage:
    def test_parents_have_empty_parent_id(self):
        parents, _ = _split(_group())
        assert all(p["parent_id"] == "" for p in parents)

    def test_every_child_references_existing_parent(self):
        parents, children = _split(_group())
        parent_ids = {p["chunk_id"] for p in parents}
        assert parent_ids
        for child in children:
            assert child["parent_id"] in parent_ids

    def test_every_parent_has_at_least_one_child(self):
        parents, children = _split(_group())
        with_children = {c["parent_id"] for c in children}
        for parent in parents:
            assert parent["chunk_id"] in with_children


class TestMetadataInheritance:
    """Kern der Korrektur (Prüfschritt 1): Children erben Struktur-/Seiten-Metadaten."""

    def test_children_inherit_section_and_page_metadata(self):
        src = _structured_chunks()
        by_text = {c["text"]: c["metadata"] for c in src}
        _, children = _split(_group(src))
        assert children
        for child in children:
            origin = by_text[child["text"]]
            cm = child["metadata"]
            for key in ("section_type", "page", "page_label", "chapter", "section_title"):
                assert cm.get(key) == origin.get(key), (
                    f"{child['chunk_id']}.{key}={cm.get(key)!r} != "
                    f"Quelle {origin.get(key)!r}"
                )

    def test_child_char_offsets_preserved(self):
        src = _structured_chunks()
        by_text = {c["text"]: c["metadata"] for c in src}
        _, children = _split(_group(src))
        for child in children:
            origin = by_text[child["text"]]
            assert child["metadata"]["char_start"] == origin["char_start"]
            assert child["metadata"]["char_end"] == origin["char_end"]

    def test_window_text_preserved_on_children(self):
        _, children = _split(_group())
        assert children
        for child in children:
            assert child["window_text"].startswith("<<")

    def test_parents_carry_section_metadata(self):
        parents, _ = _split(_group())
        for parent in parents:
            pm = parent["metadata"]
            assert pm.get("section_type") == "main_content"
            assert pm.get("chapter")  # nicht leer
            assert pm.get("char_start") is not None
            assert pm.get("char_end") is not None


class TestSectionBoundaries:
    def test_parents_do_not_cross_section_boundaries(self):
        parents, children = _split(_group())
        children_by_parent = {}
        for child in children:
            children_by_parent.setdefault(child["parent_id"], []).append(child)
        for parent in parents:
            keys = {
                _sect_key(c["metadata"]) for c in children_by_parent[parent["chunk_id"]]
            }
            assert len(keys) == 1, f"{parent['chunk_id']} mischt Sektionen: {keys}"
            # Parent erbt die Sektion seiner Children
            assert _sect_key(parent["metadata"]) == keys.pop()


class TestTokenBudget:
    def test_parent_respects_token_budget(self):
        parents, children = _split(_group())
        children_by_parent = {}
        for child in children:
            children_by_parent.setdefault(child["parent_id"], []).append(child)
        for parent in parents:
            kids = children_by_parent[parent["chunk_id"]]
            total = sum(_tokens(c["text"]) for c in kids)
            # Budget darf nur überschritten werden, wenn ein einzelner Child
            # für sich schon zu groß ist (dann Gruppe der Größe 1).
            assert total <= PARENT_SIZE or len(kids) == 1


class TestNoTextLoss:
    def test_every_source_chunk_survives_as_child(self):
        src = _structured_chunks()
        _, children = _split(_group(src))
        assert {c["text"] for c in children} == {c["text"] for c in src}

    def test_parent_text_contains_child_text(self):
        parents, children = _split(_group())
        children_by_parent = {}
        for child in children:
            children_by_parent.setdefault(child["parent_id"], []).append(child)
        for parent in parents:
            for child in children_by_parent[parent["chunk_id"]]:
                assert child["text"] in parent["text"]


class TestEdgeCases:
    def test_empty_input_returns_empty(self):
        assert _group([]) == []

    def test_single_oversized_chunk_becomes_its_own_parent(self):
        big = {
            "text": " ".join(f"x{j}" for j in range(500)),  # >> PARENT_SIZE Tokens
            "metadata": {"section_type": "main_content", "chapter": "K", "char_start": 0, "char_end": 1},
        }
        parents, children = _split(_group([big], parent_size=PARENT_SIZE))
        assert len(parents) == 1
        assert len(children) == 1
        assert children[0]["parent_id"] == parents[0]["chunk_id"]
