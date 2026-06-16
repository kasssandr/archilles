"""
Tests for silent text loss in chunkers (Befund 3.3).

When an accumulated/trailing fragment is shorter than min_chunk_size, the
chunkers used to drop it instead of merging it with a neighbour — short
paragraphs before long sections vanished from the index. The trailing case
in _chunk_plain already merged correctly; these tests pin the missing cases.
"""

from src.archilles.chunkers.semantic import SemanticChunker
from src.archilles.chunkers.fixed import FixedSizeChunker
from src.archilles.chunkers.base import ChunkerConfig


def make_semantic(chunk_size=500, overlap=0, min_size=20):
    return SemanticChunker(
        ChunkerConfig(chunk_size=chunk_size, chunk_overlap=overlap, min_chunk_size=min_size)
    )


class TestSemanticMarkdownLoss:
    def test_short_trailing_section_not_lost(self):
        """A tiny final ## section must not vanish (markdown flush path)."""
        chunker = make_semantic(chunk_size=2000, min_size=20)
        text = "# Kapitel 1\n\n" + ("Langer Inhalt hier. " * 10) + "\n\n# K2\n\nx"
        chunks = chunker.chunk(text)
        full = "\n".join(c.text for c in chunks)
        assert "K2" in full, "short trailing heading section was dropped"


class TestSemanticPlainLoss:
    def test_short_paragraph_before_long_not_lost(self):
        """A short paragraph immediately before an oversized one must survive."""
        chunker = make_semantic(chunk_size=100, min_size=20)
        short = "Kurz."
        long = "Wort " * 40  # ~200 chars, exceeds chunk_size
        text = f"{short}\n\n{long.strip()}"
        chunks = chunker.chunk(text)
        full = " ".join(c.text for c in chunks)
        assert "Kurz" in full, "short paragraph before a long one was dropped"


class TestMarkdownOffsets:
    def test_markdown_chunks_have_real_offsets(self):
        """Markdown chunks must carry real source offsets, not 0/len (Befund 3.4)."""
        chunker = make_semantic(chunk_size=200, overlap=0, min_size=20)
        text = (
            "# Kapitel 1\n\n" + ("Inhalt eins. " * 5).strip() + "\n\n"
            "# Kapitel 2\n\n" + ("Inhalt zwei. " * 5).strip() + "\n\n"
            "# Kapitel 3\n\n" + ("Inhalt drei. " * 5).strip()
        )
        chunks = chunker.chunk(text)
        assert len(chunks) == 3
        starts = [c.start_char for c in chunks]
        # Phantom offsets would make every start identical (0)
        assert len(set(starts)) == 3, f"phantom offsets: {starts}"
        assert starts == sorted(starts)
        # Each chunk's start offset must land on its heading in the source
        for i, kap in enumerate(["Kapitel 1", "Kapitel 2", "Kapitel 3"]):
            window = text[chunks[i].start_char:chunks[i].start_char + 20]
            assert kap in window, f"chunk {i} start {chunks[i].start_char} not at {kap}: {window!r}"


class TestFixedSlidingWindowLoss:
    def test_trailing_remainder_not_lost(self):
        """A trailing remainder shorter than min_chunk_size must merge, not drop."""
        chunker = FixedSizeChunker(
            ChunkerConfig(chunk_size=100, chunk_overlap=0, min_chunk_size=20)
        )
        text = "a" * 100 + "ENDMARKER"  # final 9 chars < min_size
        chunks = chunker.chunk(text)
        full = "".join(c.text for c in chunks)
        assert "ENDMARKER" in full, "trailing remainder was dropped"
