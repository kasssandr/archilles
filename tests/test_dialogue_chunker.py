"""
Tests for DialogueChunker and pipeline chunker-selection logic.
"""

import textwrap
from pathlib import Path

import pytest

from src.archilles.chunkers.dialogue import (
    DialogueChunker,
    _parse_turns,
    _group_exchanges,
    DEFAULT_USER_MARKERS,
)


# ── Sample chat texts ────────────────────────────────────────────

SIMPLE_CHAT = textwrap.dedent("""\
    **User:**
    Was ist die Josephus-Hypothese?

    **ChatGPT:**
    Die Josephus-Hypothese besagt, dass Jesus eine literarische Erfindung ist,
    die auf Texten des jüdischen Historikers Flavius Josephus basiert.
""")

MULTI_EXCHANGE = textwrap.dedent("""\
    **User:**
    Erkläre kurz CBDC.

    **Grok:**
    CBDC steht für Central Bank Digital Currency — digitales Zentralbankgeld.

    **User:**
    Welche Länder haben das schon eingeführt?

    **Grok:**
    China (digitaler Yuan), die Bahamas (Sand Dollar) und Nigeria (eNaira).
""")

LONG_RESPONSE = textwrap.dedent("""\
    **User:**
    Gib mir eine ausführliche Zusammenfassung der Rolle Roms in Judäa.

    **ChatGPT:**
    Rom und Judäa hatten eine komplexe Beziehung, die über mehrere Jahrhunderte andauerte.

    Im Jahr 63 v. Chr. eroberte Pompeius Jerusalem und machte Judäa zu einem
    Klientelkönigreich Roms. Herodes der Große regierte dann ab 37 v. Chr. als
    Vasallkönig unter römischer Oberhoheit.

    Der Erste Jüdisch-Römische Krieg (66–73 n. Chr.) endete mit der Zerstörung
    des Zweiten Tempels im Jahr 70 n. Chr. unter Titus.

    Der Bar-Kochba-Aufstand (132–135 n. Chr.) wurde von Kaiser Hadrian
    niedergeschlagen. Danach wurde die Provinz in Syria Palaestina umbenannt
    und Juden war der Zutritt zu Jerusalem verboten.
""")

PLAIN_COLON_CHAT = textwrap.dedent("""\
    User:
    Hallo, wie geht es dir?

    Assistant:
    Mir geht es gut, danke!
""")

NO_TURNS = "Das ist ein normaler Text ohne Gesprächsstruktur.\n\nKein Sprecher hier."

LONG_USER_PROMPT = textwrap.dedent("""\
    **User:**
    Das ist ein sehr langer Nutzer-Prompt. """ + ("Lorem ipsum dolor sit amet. " * 60) + """

    **Claude:**
    Kurze Antwort auf den langen Prompt.
""")


# ── _parse_turns ─────────────────────────────────────────────────

class TestParseTurns:
    def test_bold_colon_inside(self):
        turns = _parse_turns(SIMPLE_CHAT)
        assert len(turns) == 2
        assert turns[0].speaker == "user"
        assert turns[1].speaker == "chatgpt"

    def test_content_extracted(self):
        turns = _parse_turns(SIMPLE_CHAT)
        assert "Josephus" in turns[0].content
        assert "Hypothese" in turns[1].content

    def test_multi_exchange(self):
        turns = _parse_turns(MULTI_EXCHANGE)
        assert len(turns) == 4
        speakers = [t.speaker for t in turns]
        assert speakers == ["user", "grok", "user", "grok"]

    def test_plain_colon_fallback(self):
        turns = _parse_turns(PLAIN_COLON_CHAT)
        assert len(turns) == 2
        assert turns[0].speaker == "user"
        assert turns[1].speaker == "assistant"

    def test_no_turns(self):
        assert _parse_turns(NO_TURNS) == []

    def test_raw_speaker_preserved(self):
        turns = _parse_turns(SIMPLE_CHAT)
        assert turns[1].raw_speaker == "ChatGPT"


# ── _group_exchanges ─────────────────────────────────────────────

class TestGroupExchanges:
    def test_simple_pair(self):
        turns = _parse_turns(SIMPLE_CHAT)
        exchanges = _group_exchanges(turns, DEFAULT_USER_MARKERS)
        assert len(exchanges) == 1
        user_content, llm_speaker, llm_content = exchanges[0]
        assert "Josephus" in user_content
        assert llm_speaker == "ChatGPT"
        assert "literarische" in llm_content

    def test_two_exchanges(self):
        turns = _parse_turns(MULTI_EXCHANGE)
        exchanges = _group_exchanges(turns, DEFAULT_USER_MARKERS)
        assert len(exchanges) == 2

    def test_trailing_user_flushed(self):
        text = "**User:**\nFrage ohne Antwort\n"
        turns = _parse_turns(text)
        exchanges = _group_exchanges(turns, DEFAULT_USER_MARKERS)
        assert len(exchanges) == 1
        user_content, llm_speaker, llm_content = exchanges[0]
        assert "Frage" in user_content
        assert llm_content == ""


# ── DialogueChunker ──────────────────────────────────────────────

class TestDialogueChunker:
    def test_simple_chat_one_chunk(self):
        chunker = DialogueChunker(max_exchange_tokens=800)
        chunks = chunker.chunk(SIMPLE_CHAT)
        assert len(chunks) == 1
        assert "Josephus" in chunks[0].text
        assert "literarische" in chunks[0].text

    def test_two_exchanges_two_chunks(self):
        chunker = DialogueChunker(max_exchange_tokens=800)
        chunks = chunker.chunk(MULTI_EXCHANGE)
        assert len(chunks) == 2

    def test_chunk_indices_sequential(self):
        chunker = DialogueChunker(max_exchange_tokens=800)
        chunks = chunker.chunk(MULTI_EXCHANGE)
        for i, chunk in enumerate(chunks):
            assert chunk.chunk_index == i

    def test_chunk_metadata_exchange_index(self):
        chunker = DialogueChunker(max_exchange_tokens=800)
        chunks = chunker.chunk(MULTI_EXCHANGE)
        assert chunks[0].metadata["exchange_index"] == 0
        assert chunks[1].metadata["exchange_index"] == 1

    def test_chunk_metadata_type(self):
        chunker = DialogueChunker()
        chunks = chunker.chunk(SIMPLE_CHAT)
        assert chunks[0].metadata["chunk_type"] == "exchange"

    def test_long_response_split(self):
        # Force splitting: tiny token budget
        chunker = DialogueChunker(max_exchange_tokens=80, prompt_header_max_tokens=30)
        chunks = chunker.chunk(LONG_RESPONSE)
        assert len(chunks) > 1

    def test_split_chunks_repeat_prompt(self):
        chunker = DialogueChunker(
            max_exchange_tokens=80,
            repeat_prompt_on_split=True,
            prompt_header_max_tokens=30,
        )
        chunks = chunker.chunk(LONG_RESPONSE)
        # Every continuation chunk should contain the user prompt (or truncated version)
        for chunk in chunks[1:]:
            assert "**User:**" in chunk.text

    def test_split_chunks_no_repeat(self):
        chunker = DialogueChunker(
            max_exchange_tokens=80,
            repeat_prompt_on_split=False,
            prompt_header_max_tokens=30,
        )
        chunks = chunker.chunk(LONG_RESPONSE)
        # First chunk still has user prompt
        assert "**User:**" in chunks[0].text
        # Continuation chunks do NOT have full user header
        for chunk in chunks[1:]:
            assert "Forts." in chunk.text

    def test_no_turns_returns_empty(self):
        chunker = DialogueChunker()
        chunks = chunker.chunk(NO_TURNS)
        assert chunks == []

    def test_source_file_propagated(self):
        chunker = DialogueChunker()
        chunks = chunker.chunk(SIMPLE_CHAT, source_file="test/chat.md")
        assert chunks[0].source_file == "test/chat.md"

    def test_plain_colon_format(self):
        chunker = DialogueChunker(max_exchange_tokens=800)
        chunks = chunker.chunk(PLAIN_COLON_CHAT)
        assert len(chunks) == 1
        assert "Assistant" in chunks[0].text

    def test_user_prompt_preview_in_metadata(self):
        chunker = DialogueChunker()
        chunks = chunker.chunk(SIMPLE_CHAT)
        preview = chunks[0].metadata["user_prompt_preview"]
        assert isinstance(preview, str)
        assert len(preview) <= 120
        assert "\n" not in preview

    def test_name(self):
        assert DialogueChunker().name == "dialogue"


# ── Prompt truncation ────────────────────────────────────────────

class TestPromptTruncation:
    def test_short_prompt_not_truncated(self):
        chunker = DialogueChunker(prompt_header_max_tokens=200)
        header = chunker._format_user_header("Kurze Frage.", "ChatGPT")
        assert "[…]" not in header
        assert "Kurze Frage." in header

    def test_long_prompt_truncated(self):
        chunker = DialogueChunker(prompt_header_max_tokens=20)
        long_prompt = "Wort " * 100
        header = chunker._format_user_header(long_prompt, "ChatGPT")
        assert "[…]" in header
        # Header should be much shorter than the original prompt
        assert len(header) < len(long_prompt)

    def test_truncated_header_still_has_llm_label(self):
        chunker = DialogueChunker(prompt_header_max_tokens=20)
        long_prompt = "Wort " * 100
        header = chunker._format_user_header(long_prompt, "Gemini")
        assert "**Gemini:**" in header

    def test_split_chunk_prompt_fits_budget(self):
        """With a low token budget, split chunks must still have room for content."""
        chunker = DialogueChunker(
            max_exchange_tokens=120,
            prompt_header_max_tokens=30,
            repeat_prompt_on_split=True,
        )
        chunks = chunker.chunk(LONG_RESPONSE)
        for chunk in chunks:
            # Each chunk should have at least some LLM content beyond the header
            assert len(chunk.text) > 50


# ── Pipeline chunker selection ───────────────────────────────────

class TestPipelineChunkerSelection:
    def test_dialogue_strategy_selects_dialogue_chunker(self, tmp_path):
        from src.archilles.pipeline import ModularPipeline
        from src.archilles.chunkers.dialogue import DialogueChunker

        md_file = tmp_path / "chat.md"
        md_file.write_text(
            "---\nchunking_strategy: dialogue\n---\n" + SIMPLE_CHAT,
            encoding="utf-8",
        )
        pipeline = ModularPipeline()
        chunker = pipeline._select_chunker(md_file)
        assert isinstance(chunker, DialogueChunker)

    def test_no_strategy_returns_default(self, tmp_path):
        from src.archilles.pipeline import ModularPipeline
        from src.archilles.chunkers.dialogue import DialogueChunker

        md_file = tmp_path / "note.md"
        md_file.write_text("---\ntitle: Kein Chat\n---\nNormaler Text.", encoding="utf-8")
        pipeline = ModularPipeline()
        chunker = pipeline._select_chunker(md_file)
        assert not isinstance(chunker, DialogueChunker)

    def test_pdf_always_default(self, tmp_path):
        from src.archilles.pipeline import ModularPipeline
        from src.archilles.chunkers.dialogue import DialogueChunker

        pdf_file = tmp_path / "book.pdf"
        pdf_file.write_bytes(b"dummy")
        pipeline = ModularPipeline()
        chunker = pipeline._select_chunker(pdf_file)
        assert not isinstance(chunker, DialogueChunker)

    def test_dialogue_chunker_cached(self, tmp_path):
        from src.archilles.pipeline import ModularPipeline

        md_file = tmp_path / "chat.md"
        md_file.write_text(
            "---\nchunking_strategy: dialogue\n---\n" + SIMPLE_CHAT,
            encoding="utf-8",
        )
        pipeline = ModularPipeline()
        c1 = pipeline._select_chunker(md_file)
        c2 = pipeline._select_chunker(md_file)
        assert c1 is c2  # same instance returned both times
