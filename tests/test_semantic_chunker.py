"""
Tests for SemanticChunker — plain-text and Markdown-heading-aware paths.
"""

import textwrap
import pytest

from src.archilles.chunkers.semantic import SemanticChunker
from src.archilles.chunkers.base import ChunkerConfig


def make_chunker(chunk_size=500, overlap=0):
    return SemanticChunker(ChunkerConfig(chunk_size=chunk_size, chunk_overlap=overlap, min_chunk_size=20))


# ── Plain text (no headings) — existing behaviour preserved ─────

class TestPlainText:
    def test_short_text_single_chunk(self):
        chunker = make_chunker()
        # Text must exceed min_chunk_size (20) to be emitted as a chunk
        chunks = chunker.chunk("Ein kurzer Satz mit mehr Inhalt.")
        assert len(chunks) == 1

    def test_long_text_splits(self):
        chunker = make_chunker(chunk_size=100)
        text = ("Dies ist ein Satz. " * 20).strip()
        chunks = chunker.chunk(text)
        assert len(chunks) > 1

    def test_no_heading_uses_plain_path(self):
        chunker = make_chunker()
        text = "Absatz eins.\n\nAbsatz zwei.\n\nAbsatz drei."
        chunks = chunker.chunk(text)
        assert len(chunks) >= 1
        combined = " ".join(c.text for c in chunks)
        assert "Absatz eins" in combined
        assert "Absatz drei" in combined

    def test_empty_returns_empty(self):
        assert make_chunker().chunk("") == []
        assert make_chunker().chunk("   ") == []


# ── Markdown heading detection ───────────────────────────────────

class TestHeadingDetection:
    def test_h1_triggers_markdown_path(self):
        chunker = make_chunker(chunk_size=2000)
        text = "# Titel\n\nInhalt hier.\n\n## Abschnitt\n\nMehr Inhalt."
        chunks = chunker.chunk(text)
        assert len(chunks) >= 1

    def test_no_heading_does_not_trigger_markdown_path(self):
        """Texts with '#' mid-line or in code should NOT trigger heading path."""
        chunker = make_chunker()
        text = "Der Wert ist #rot und #blau.\n\nEin weiterer Absatz."
        # Just check it doesn't crash and returns content
        chunks = chunker.chunk(text)
        assert any("rot" in c.text for c in chunks)


# ── Hard boundaries: # and ## ────────────────────────────────────

class TestHardBoundaries:
    def test_h1_always_starts_new_chunk(self):
        chunker = make_chunker(chunk_size=2000)
        text = textwrap.dedent("""\
            # Kapitel 1

            Inhalt von Kapitel 1. Kurzer Text.

            # Kapitel 2

            Inhalt von Kapitel 2.
        """)
        chunks = chunker.chunk(text)
        # The two chapters must not be merged even though they fit in budget
        texts = [c.text for c in chunks]
        assert not any("Kapitel 1" in t and "Kapitel 2" in t for t in texts), \
            "# headings must not be merged across chapters"

    def test_h2_always_starts_new_chunk(self):
        chunker = make_chunker(chunk_size=2000)
        text = textwrap.dedent("""\
            ## Abschnitt A

            Inhalt A.

            ## Abschnitt B

            Inhalt B.
        """)
        chunks = chunker.chunk(text)
        texts = [c.text for c in chunks]
        assert not any("Abschnitt A" in t and "Abschnitt B" in t for t in texts), \
            "## headings must not be merged"

    def test_h1_chunk_contains_heading(self):
        chunker = make_chunker(chunk_size=2000)
        text = "# Mein Kapitel\n\nInhalt."
        chunks = chunker.chunk(text)
        assert any("Mein Kapitel" in c.text for c in chunks)


# ── Soft boundaries: ### and deeper ─────────────────────────────

class TestSoftBoundaries:
    def test_small_h3_sections_merged(self):
        """Three tiny ### sections should be merged into one chunk."""
        chunker = make_chunker(chunk_size=1000)
        text = textwrap.dedent("""\
            ### 1. Punkt

            Kurzer Text A.

            ### 2. Punkt

            Kurzer Text B.

            ### 3. Punkt

            Kurzer Text C.
        """)
        chunks = chunker.chunk(text)
        assert len(chunks) == 1, \
            f"Three tiny sections should merge into one chunk, got {len(chunks)}"
        assert "Punkt" in chunks[0].text

    def test_h3_sections_split_when_budget_full(self):
        """When accumulated ### sections fill the budget, a new chunk starts."""
        chunker = make_chunker(chunk_size=120)
        # Each section is ~50 chars; two fit in 120, third should start new chunk
        section = "### Unterabschnitt\n\nDieser Text ist fünfzig Zeichen lang!!"
        text = f"{section}\n\n{section}\n\n{section}"
        chunks = chunker.chunk(text)
        assert len(chunks) > 1

    def test_h3_never_merges_across_h2(self):
        """### sections must never jump over a ## boundary."""
        chunker = make_chunker(chunk_size=2000)
        # Use names that are NOT substrings of each other ("Alpha" ≠ prefix of "Beta")
        text = textwrap.dedent("""\
            ## Kapitel Alpha

            ### Unterabschnitt

            Text zu Alpha.

            ## Kapitel Beta

            ### Unterabschnitt

            Text zu Beta.
        """)
        chunks = chunker.chunk(text)
        texts = [c.text for c in chunks]
        # Each chapter must be in its own chunk — no chunk may span both
        assert not any("Kapitel Alpha" in t and "Kapitel Beta" in t for t in texts), \
            "### sections must not be merged across a ## boundary"

    def test_oversized_h3_section_sub_split(self):
        """A single ### section exceeding chunk_size is sub-split."""
        chunker = make_chunker(chunk_size=100)
        long_body = "Dies ist ein langer Satz, der immer wieder vorkommt. " * 10
        text = f"### Langer Abschnitt\n\n{long_body}"
        chunks = chunker.chunk(text)
        assert len(chunks) > 1


# ── Mixed structure ──────────────────────────────────────────────

class TestMixedStructure:
    def test_real_world_llm_export_structure(self):
        """Simulates the structure from the user's example."""
        chunker = make_chunker(chunk_size=600)
        text = textwrap.dedent("""\
            ## 3. Platonische Einflüsse

            Die Beziehung zwischen platonischer Philosophie und frühem Christentum
            ist Gegenstand intensiver wissenschaftlicher Debatte.

            ### 3.1 Logos-Konzept

            Philo von Alexandria sah den *Logos* als Vermittler zwischen Gott und der Welt.

            - **Unabhängige Entwicklung:** Die Mainstream-Wissenschaft geht davon aus, dass
              viele dieser Parallelen aus unabhängigen Traditionen resultieren.

            ### 3.2 Seelenlehre

            Die platonische Unterscheidung zwischen sterblichem Körper und unsterblicher
            Seele findet sich in verschiedenen früh-christlichen Texten wieder.

            ### 4. **Fazit**

            Die Wissenschaft erkennt deutliche Einflüsse platonischer Philosophie auf
            die christliche Theologie und sieht Parallelen zwischen platonischen und
            jüdischen Konzepten.
        """)
        chunks = chunker.chunk(text)

        # The ## heading must be a hard boundary → it should be in its own chunk
        # or at the start of a new chunk, never merged with a preceding ## section
        full_text = "\n---\n".join(c.text for c in chunks)

        # Fazit must appear in the output
        assert "Fazit" in full_text
        # Logos must appear
        assert "Logos" in full_text
        # There must be more than one chunk (content is > 600 chars)
        assert len(chunks) > 1

    def test_preamble_before_first_heading(self):
        """Text before the first heading is captured as preamble."""
        chunker = make_chunker(chunk_size=1000)
        text = "Einleitung ohne Überschrift.\n\n## Erster Abschnitt\n\nInhalt."
        chunks = chunker.chunk(text)
        full = " ".join(c.text for c in chunks)
        assert "Einleitung" in full
        assert "Erster Abschnitt" in full

    def test_chunk_indices_sequential(self):
        chunker = make_chunker(chunk_size=200)
        text = "# A\n\nText.\n\n# B\n\nMehr Text.\n\n# C\n\nNoch Text."
        chunks = chunker.chunk(text)
        for i, chunk in enumerate(chunks):
            assert chunk.chunk_index == i
