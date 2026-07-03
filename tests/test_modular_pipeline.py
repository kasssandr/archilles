"""
Tests for the modular pipeline path (P4 — pre-prod fixes for the
parser → chunker → embedder pipeline).

Covers:
- 3.2  profile.chunk_size is "in tokens"; the chunker must scale it to
       characters instead of treating 512 tokens as 512 characters.
"""

import numpy as np

from src.archilles.profiles import IndexingProfile
from src.archilles.pipeline import ModularPipeline
from src.archilles.parsers.base import (
    DocumentParser, DocumentType, ParserCapabilities, ParsedDocument, ParsedChunk,
)
from src.archilles.embedders.base import (
    TextEmbedder, EmbedderCapabilities, EmbeddingResult,
)


class _FakeParser(DocumentParser):
    """Returns a pre-built ParsedDocument — no real file needed."""

    def __init__(self, parsed):
        self._parsed = parsed

    @property
    def name(self):
        return "fake"

    @property
    def version(self):
        return "1.0.0"

    @property
    def capabilities(self):
        return ParserCapabilities(
            supported_extensions={".pdf", ".txt"},
            supported_types={DocumentType.PDF},
        )

    def parse(self, file_path):
        return self._parsed


class _FakeEmbedder(TextEmbedder):
    """Emits zero vectors of the store's dimension; never loads a model."""

    @property
    def name(self):
        return "fake-embedder"

    @property
    def capabilities(self):
        return EmbedderCapabilities(model_name="fake", embedding_dimension=1024)

    def embed_batch(self, texts):
        return EmbeddingResult(
            embeddings=np.zeros((len(texts), 1024), dtype=np.float32),
            model_name="fake",
            embedding_dimension=1024,
            texts_count=len(texts),
        )

    def load_model(self):
        pass

    def unload_model(self):
        pass


def _pdf_like_parsed():
    """A ParsedDocument as PyMuPDFParser produces it: pre-chunked, page-mapped,
    with rich metadata. Pages are 5, 5, 7 — not 1, 2, 3."""
    chunks = [
        ParsedChunk(
            text="Erster Chunk auf Seite fuenf. " * 3,
            source_file="b.pdf", page_number=5, chunk_index=0,
            section_title="Einleitung", chapter="Kapitel 1",
            start_char=100, end_char=190,
            metadata={
                "page": 5, "page_label": "v", "section_title": "Einleitung",
                "chapter": "Kapitel 1", "section_type": "main",
                "char_start": 100, "char_end": 190,
                "window_text": "Kontext rund um den ersten Chunk.",
            },
        ),
        ParsedChunk(
            text="Zweiter Chunk, ebenfalls Seite fuenf. " * 3,
            source_file="b.pdf", page_number=5, chunk_index=1,
            metadata={"page": 5, "page_label": "v", "char_start": 190, "char_end": 280},
        ),
        ParsedChunk(
            text="Dritter Chunk auf Seite sieben. " * 3,
            source_file="b.pdf", page_number=7, chunk_index=2,
            metadata={"page": 7, "page_label": "vii", "char_start": 500, "char_end": 590},
        ),
    ]
    return ParsedDocument(
        file_path="b.pdf", file_name="b.pdf", file_size_bytes=10,
        full_text="ignored when chunks exist", chunks=chunks,
        title="Testbuch", authors=["Autor"], page_count=7,
        parser_name="fake", parser_version="1.0.0",
    )


def _make_pipeline(parsed):
    from src.archilles.chunkers.semantic import SemanticChunker
    return ModularPipeline(
        parser=_FakeParser(parsed),
        chunker=SemanticChunker(),
        embedder=_FakeEmbedder(),
    )


class TestParserChunksTakenDirectly:
    def test_page_numbers_preserved(self):
        """has_chunks → real page numbers, not chunk ordinals (Befund 3.1)."""
        result = _make_pipeline(_pdf_like_parsed()).process("b.pdf")
        pages = [c.page_start for c in result.chunks]
        assert pages == [5, 5, 7], f"page numbers re-derived as ordinals: {pages}"
        assert len(result.chunks) == 3, "parser chunks were re-chunked"

    def test_metadata_preserved(self):
        """section_title, chapter, char offsets, window_text survive (3.1/2.17/1.28)."""
        result = _make_pipeline(_pdf_like_parsed()).process("b.pdf")
        first = result.chunks[0]
        assert first.metadata.get("section_title") == "Einleitung"
        assert first.metadata.get("chapter") == "Kapitel 1"
        assert first.start_char == 100
        assert first.end_char == 190
        assert first.metadata.get("window_text") == "Kontext rund um den ersten Chunk."

    def test_no_chunks_falls_back_to_fulltext(self):
        """Without parser chunks (TXT/MD), full_text is chunked."""
        parsed = ParsedDocument(
            file_path="n.txt", file_name="n.txt", file_size_bytes=10,
            full_text=("Ein laengerer Absatz mit genug Inhalt. " * 200),
            chunks=[], title="T", authors=[],
        )
        result = _make_pipeline(parsed).process("n.txt")
        assert len(result.chunks) >= 1
        assert all(c.text for c in result.chunks)


class TestStoreProcessedDocuments:
    def test_metadata_written_without_attribute_error(self, tmp_path):
        """add_processed_documents must read metadata from chunk.metadata
        (no chunk.chapter/.section_title AttributeError) and wire through
        page_number/page_label/section_type/char offsets/window_text (3.1/2.17/1.28)."""
        from src.storage.lancedb_store import LanceDBStore

        store = LanceDBStore(db_path=str(tmp_path / "db"))
        processed = _make_pipeline(_pdf_like_parsed()).process("b.pdf")
        added = store.add_processed_documents(
            processed, book_metadata={"book_id": "tb"}, calibre_id=1
        )
        assert added == 3

        rows = sorted(store.get_by_source_id("1"), key=lambda r: r["chunk_index"])
        first = rows[0]
        assert first["page_number"] == 5
        assert first["page_label"] == "v"
        assert first["section_title"] == "Einleitung"
        assert first["chapter"] == "Kapitel 1"
        assert first["section_type"] == "main"
        assert first["char_start"] == 100
        assert first["char_end"] == 190
        assert first["window_text"] == "Kontext rund um den ersten Chunk."
        # third chunk is on page 7, not "page 3"
        assert rows[2]["page_number"] == 7


def _profile(chunk_size=512, chunk_overlap=128):
    """A minimal profile without invoking torch-backed device detection."""
    return IndexingProfile(
        name="minimal",
        embedding_model="BAAI/bge-m3",
        embedding_device="cpu",
        batch_size=8,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        description="test profile",
    )


class TestTokenSizeUnit:
    def test_profile_chunk_size_treated_as_tokens(self):
        """512-token profile must yield chunks far larger than 512 chars (Befund 3.2)."""
        pipeline = ModularPipeline._create_from_profile(_profile(chunk_size=512))
        chunker = pipeline._chunker
        text = "Dies ist ein Satz mit mehreren Worten darin. " * 400  # ~18k chars
        chunks = chunker.chunk(text)
        max_chars = max(len(c.text) for c in chunks)
        # 512 tokens ≈ 2000 chars. A char-misinterpretation caps chunks at ~512.
        assert max_chars > 1000, (
            f"chunks too small ({max_chars} chars) — token size treated as characters"
        )

    def test_character_size_unit_unchanged(self):
        """Explicit character sizing must not be rescaled."""
        from src.archilles.chunkers.semantic import SemanticChunker
        from src.archilles.chunkers.base import ChunkerConfig

        chunker = SemanticChunker(
            ChunkerConfig(chunk_size=300, chunk_overlap=0, min_chunk_size=20,
                          size_unit="characters")
        )
        text = "Dies ist ein Satz. " * 100
        chunks = chunker.chunk(text)
        max_chars = max(len(c.text) for c in chunks)
        # With 300-char budget, chunks should not balloon to token-scaled sizes
        assert max_chars <= 400, f"character sizing was rescaled: {max_chars}"
