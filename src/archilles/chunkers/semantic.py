"""
ARCHILLES Semantic Chunker

Chunks text while respecting natural boundaries:
- Paragraph breaks
- Sentence endings
- Section headers

This produces more coherent chunks for embedding.
"""

import re
from typing import List

from .base import TextChunker, TextChunk, ChunkerConfig


class SemanticChunker(TextChunker):
    """
    Semantic text chunker that respects natural text boundaries.

    For plain text, tries to break at:
    1. Paragraph boundaries (double newlines)
    2. Sentence boundaries (., !, ?)
    3. Word boundaries (spaces)

    For Markdown text (detected by the presence of ``# Heading`` lines),
    uses a heading-aware strategy:
    - ``#`` / ``##`` headings always start a new chunk (hard boundary).
    - ``###``–``######`` headings are soft boundaries: sections are merged
      greedily until the chunk budget is reached, so small subsections are
      not left as isolated micro-chunks.
    - A section that exceeds ``chunk_size`` on its own is sub-split at
      sentence/word boundaries using the standard paragraph logic.
    """

    # Sentence ending patterns
    SENTENCE_ENDINGS = re.compile(r'[.!?]+[\s\n]+')

    # Paragraph pattern (2+ newlines)
    PARAGRAPH_BREAK = re.compile(r'\n\s*\n')

    # Markdown heading: captures level (###) and title text
    HEADING_RE = re.compile(r'^(#{1,6})\s+(.+)$', re.MULTILINE)

    # Heading levels that always force a chunk flush
    HARD_BREAK_LEVELS = {1, 2}

    @property
    def name(self) -> str:
        return "semantic"

    @property
    def description(self) -> str:
        return "Chunks text respecting sentence, paragraph, and Markdown heading boundaries"

    # ── Public entry point ───────────────────────────────────────

    def chunk(self, text: str, source_file: str = "") -> List[TextChunk]:
        """Split text into semantically coherent chunks."""
        if not text or not text.strip():
            return []

        if self.HEADING_RE.search(text):
            return self._chunk_markdown(text, source_file)

        return self._chunk_plain(text, source_file)

    # ── Markdown-aware path ──────────────────────────────────────

    def _chunk_markdown(self, text: str, source_file: str) -> List[TextChunk]:
        """Heading-aware chunking for Markdown text."""
        sections = self._split_into_sections(text)
        chunk_size = self._to_chars(self.config.chunk_size)
        overlap = self._to_chars(self.config.chunk_overlap)

        chunks: List[TextChunk] = []
        # Accumulator: list of (level, section_text, start_char) triples being merged
        acc: List[tuple[int, str, int]] = []
        acc_chars = 0

        def flush():
            nonlocal acc, acc_chars
            if not acc:
                return
            merged = "\n\n".join(s for _, s, _ in acc).strip()
            # Real source span: first section's start → last section's end (Befund 3.4)
            start = acc[0][2]
            end = acc[-1][2] + len(acc[-1][1])
            self._emit_or_merge(chunks, merged, source_file, start, end)
            acc = []
            acc_chars = 0

        for level, section_text, sec_start in sections:
            if not section_text:
                continue

            is_hard = level in self.HARD_BREAK_LEVELS

            if is_hard:
                # Always flush before a major heading
                flush()

            if len(section_text) > chunk_size:
                # Section is too large on its own — flush accumulator first,
                # then sub-split the section using plain paragraph logic.
                # Shift sub-chunk offsets to absolute positions (Befund 3.4).
                flush()
                sub_chunks = self._chunk_plain(section_text, source_file)
                for sc in sub_chunks:
                    sc.chunk_index = len(chunks)
                    sc.start_char += sec_start
                    sc.end_char += sec_start
                    chunks.append(sc)
            elif acc_chars + len(section_text) > chunk_size and acc:
                # Adding this section would overflow — flush and start fresh
                flush()
                acc.append((level, section_text, sec_start))
                acc_chars = len(section_text)
            else:
                acc.append((level, section_text, sec_start))
                acc_chars += len(section_text)

        flush()

        if overlap > 0 and len(chunks) > 1:
            chunks = self._apply_overlap(chunks, text, overlap)

        return chunks

    def _split_into_sections(self, text: str) -> List[tuple[int, str, int]]:
        """Split *text* into ``(heading_level, section_text, start_char)`` triples.

        ``heading_level`` is 0 for preamble text before the first heading.
        The heading line itself is included at the top of each section body.
        ``start_char`` is the offset of the section's first non-whitespace
        character in the original text — needed for real chunk offsets
        (Befund 3.4) so page mapping and overlap compute correctly.
        """
        def _stripped_start(raw: str, base: int) -> int:
            return base + (len(raw) - len(raw.lstrip()))

        matches = list(self.HEADING_RE.finditer(text))
        if not matches:
            return [(0, text.strip(), _stripped_start(text, 0))]

        sections: List[tuple[int, str, int]] = []

        # Preamble before first heading
        raw_preamble = text[:matches[0].start()]
        preamble = raw_preamble.strip()
        if preamble:
            sections.append((0, preamble, _stripped_start(raw_preamble, 0)))

        for i, m in enumerate(matches):
            level = len(m.group(1))
            body_start = m.start()
            body_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            raw_body = text[body_start:body_end]
            sections.append((level, raw_body.strip(), _stripped_start(raw_body, body_start)))

        return sections

    # ── Plain-text path (unchanged logic) ───────────────────────

    def _chunk_plain(self, text: str, source_file: str) -> List[TextChunk]:
        """Original paragraph-based chunking for non-Markdown text."""
        chunk_size = self._to_chars(self.config.chunk_size)
        overlap = self._to_chars(self.config.chunk_overlap)
        min_size = self._to_chars(self.config.min_chunk_size)

        # Build (text, start_offset) pairs directly from split positions
        # to avoid O(n) text.find() per paragraph.
        raw_paragraphs: list[tuple[str, int]] = []
        prev_end = 0
        for m in self.PARAGRAPH_BREAK.finditer(text):
            seg = text[prev_end:m.start()].strip()
            if seg:
                # start offset = first non-whitespace char in the segment
                raw_paragraphs.append((seg, prev_end + (text[prev_end:m.start()].index(seg[0]) if seg else 0)))
            prev_end = m.end()
        # Trailing segment after last paragraph break
        seg = text[prev_end:].strip()
        if seg:
            raw_paragraphs.append((seg, prev_end + (text[prev_end:].index(seg[0]) if seg else 0)))

        chunks: List[TextChunk] = []
        current_chunk_text = ""
        current_start = 0

        for para, para_start in raw_paragraphs:

            separator = "\n\n" if current_chunk_text else ""
            potential_text = current_chunk_text + separator + para

            if len(potential_text) <= chunk_size:
                if not current_chunk_text:
                    current_start = para_start
                current_chunk_text = potential_text
                continue

            # Flush the current chunk before starting a new one
            if current_chunk_text:
                self._emit_or_merge(
                    chunks, current_chunk_text, source_file,
                    current_start, current_start + len(current_chunk_text),
                )

            # Handle the paragraph that caused overflow
            if len(para) <= chunk_size:
                current_chunk_text = para
                current_start = para_start
            else:
                para_chunks = self._split_long_paragraph(
                    para, chunk_size, overlap, min_size,
                )
                for para_chunk in para_chunks[:-1]:
                    chunks.append(self._create_chunk(
                        para_chunk, len(chunks), source_file,
                        para_start, para_start + len(para_chunk),
                    ))
                if para_chunks:
                    current_chunk_text = para_chunks[-1]
                    current_start = para_start + len(para) - len(current_chunk_text)
                else:
                    current_chunk_text = ""

        # Emit or merge the trailing chunk
        if current_chunk_text:
            self._emit_or_merge(
                chunks, current_chunk_text, source_file,
                current_start, current_start + len(current_chunk_text),
            )

        if overlap > 0 and len(chunks) > 1:
            chunks = self._apply_overlap(chunks, text, overlap)

        return chunks

    def _split_long_paragraph(
        self,
        para: str,
        chunk_size: int,
        overlap: int,
        min_size: int,
    ) -> List[str]:
        """Split a paragraph that exceeds chunk_size, breaking at sentence boundaries."""
        if len(para) <= chunk_size:
            return [para]

        # Use finditer to get sentence boundaries without losing the delimiters
        parts: List[str] = []
        last_end = 0
        for match in self.SENTENCE_ENDINGS.finditer(para):
            parts.append(para[last_end:match.end()].rstrip())
            last_end = match.end()
        if last_end < len(para):
            trailing = para[last_end:].strip()
            if trailing:
                parts.append(trailing)

        chunks: List[str] = []
        current = ""
        for part in parts:
            if not part:
                continue
            potential = current + (" " if current else "") + part
            if len(potential) <= chunk_size:
                current = potential
            else:
                if current:
                    chunks.append(current)
                if len(part) > chunk_size:
                    word_chunks = self._split_by_words(part, chunk_size)
                    chunks.extend(word_chunks[:-1])
                    current = word_chunks[-1] if word_chunks else ""
                else:
                    current = part

        if current:
            chunks.append(current)

        return chunks

    def _split_by_words(self, text: str, chunk_size: int) -> List[str]:
        """Split text by word boundaries when sentences are too long."""
        words = text.split()
        chunks = []
        current = ""

        for word in words:
            potential = current + (" " if current else "") + word
            if len(potential) <= chunk_size:
                current = potential
            else:
                if current:
                    chunks.append(current)
                current = word

        if current:
            chunks.append(current)

        return chunks

    def _apply_overlap(
        self,
        chunks: List[TextChunk],
        original_text: str,
        overlap: int
    ) -> List[TextChunk]:
        """
        Apply overlap between chunks by prepending text from previous chunk.
        """
        if len(chunks) <= 1:
            return chunks

        result = [chunks[0]]  # First chunk stays as is

        for i in range(1, len(chunks)):
            prev_chunk = chunks[i - 1]
            curr_chunk = chunks[i]

            # Get overlap text from end of previous chunk
            prev_text = prev_chunk.text
            overlap_text = prev_text[-overlap:] if len(prev_text) > overlap else prev_text

            # Try to break at word boundary
            space_idx = overlap_text.find(' ')
            if space_idx > 0:
                overlap_text = overlap_text[space_idx + 1:]

            # Prepend overlap to current chunk
            new_text = overlap_text + " " + curr_chunk.text
            new_start = curr_chunk.start_char - len(overlap_text) - 1

            result.append(TextChunk(
                text=new_text,
                chunk_index=curr_chunk.chunk_index,
                source_file=curr_chunk.source_file,
                page_start=curr_chunk.page_start,
                page_end=curr_chunk.page_end,
                start_char=max(0, new_start),
                end_char=curr_chunk.end_char,
                char_count=len(new_text),
                metadata=curr_chunk.metadata
            ))

        return result

    def _create_chunk(
        self,
        text: str,
        index: int,
        source_file: str,
        start: int,
        end: int
    ) -> TextChunk:
        """Helper to create a TextChunk with proper metadata."""
        return TextChunk(
            text=text.strip(),
            chunk_index=index,
            source_file=source_file,
            start_char=start,
            end_char=end,
            char_count=len(text.strip())
        )

    def _emit_or_merge(
        self,
        chunks: List[TextChunk],
        text: str,
        source_file: str,
        start: int,
        end: int,
    ) -> None:
        """Append *text* as a new chunk, or merge it into the previous one.

        Fragments shorter than ``min_chunk_size`` are merged into the
        preceding chunk instead of being silently dropped (Befund 3.3).
        When there is no preceding chunk, the fragment is emitted as-is —
        a short chunk is preferable to losing the text entirely.
        """
        text = text.strip()
        if not text:
            return
        if len(text) >= self._to_chars(self.config.min_chunk_size) or not chunks:
            chunks.append(self._create_chunk(text, len(chunks), source_file, start, end))
        else:
            last = chunks[-1]
            merged = last.text + "\n\n" + text
            chunks[-1] = self._create_chunk(
                merged, last.chunk_index, source_file, last.start_char, end
            )


# Quick test
if __name__ == "__main__":
    test_text = """
    Chapter 1: Introduction

    This is the first paragraph of the introduction. It contains several sentences
    that explain the basic concepts. The reader should understand these before
    proceeding to the next section.

    The second paragraph goes into more detail. It discusses various aspects of
    the topic at hand. There are many important points to consider here.

    Chapter 2: Main Content

    Now we get to the heart of the matter. This chapter contains the most
    important information. Pay close attention to the details presented here.

    The methodology is explained in this paragraph. We use a combination of
    techniques to achieve our goals. The results are quite impressive.
    """

    chunker = SemanticChunker(ChunkerConfig(chunk_size=300, chunk_overlap=50))
    chunks = chunker.chunk(test_text, "test.pdf")

    print(f"Created {len(chunks)} chunks:")
    for chunk in chunks:
        print(f"\n[{chunk.chunk_index}] ({chunk.char_count} chars)")
        print(f"  {chunk.text[:80]}...")
