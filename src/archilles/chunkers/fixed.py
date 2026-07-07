"""
ARCHILLES Fixed-Size Chunker

Simple chunker that splits text into fixed-size chunks.
Useful when consistent chunk sizes are needed (e.g., for batching).
"""

from typing import List

from .base import TextChunker, TextChunk, ChunkerConfig


def _sliding_window_chunks(
    text: str,
    source_file: str,
    chunk_size: int,
    overlap: int,
    min_size: int,
    respect_word_boundaries: bool = True,
) -> List[TextChunk]:
    """
    Core sliding-window chunking used by FixedSizeChunker.

    Args:
        text: Pre-stripped text to chunk
        source_file: Source file path for metadata
        chunk_size: Maximum chunk size in characters
        overlap: Overlap between consecutive chunks in characters
        min_size: Minimum chunk size to emit
        respect_word_boundaries: Whether to break at word boundaries
    """
    step = chunk_size - overlap
    if step <= 0:
        step = chunk_size // 2

    chunks: List[TextChunk] = []
    text_len = len(text)
    position = 0

    while position < text_len:
        end = min(position + chunk_size, text_len)
        chunk_text = text[position:end]

        if end < text_len and respect_word_boundaries:
            last_space = chunk_text.rfind(' ')
            if last_space > min_size:
                chunk_text = chunk_text[:last_space]
                end = position + last_space

        stripped = chunk_text.strip()
        if len(stripped) >= min_size:
            chunks.append(TextChunk(
                text=stripped,
                chunk_index=len(chunks),
                source_file=source_file,
                start_char=position,
                end_char=end,
                char_count=len(stripped),
            ))
        elif stripped and end >= text_len and chunks:
            # Trailing remainder shorter than min_size → merge into the
            # previous chunk instead of dropping it (Befund 3.3).
            last = chunks[-1]
            merged = last.text + " " + stripped
            chunks[-1] = TextChunk(
                text=merged,
                chunk_index=last.chunk_index,
                source_file=source_file,
                start_char=last.start_char,
                end_char=end,
                char_count=len(merged),
            )

        position += step

        # Avoid infinite loop when step does not advance past the current end
        if position >= end and end < text_len:
            position = end

    return chunks


class FixedSizeChunker(TextChunker):
    """
    Fixed-size text chunker.

    Splits text into chunks of approximately equal size,
    optionally breaking at word boundaries to avoid splitting words.
    """

    @property
    def name(self) -> str:
        return "fixed-size"

    @property
    def description(self) -> str:
        return "Chunks text into fixed-size pieces"

    def chunk(self, text: str, source_file: str = "") -> List[TextChunk]:
        if not text or not text.strip():
            return []

        return _sliding_window_chunks(
            text=text.strip(),
            source_file=source_file,
            chunk_size=self.config.chunk_size,
            overlap=self.config.chunk_overlap,
            min_size=self.config.min_chunk_size,
            respect_word_boundaries=self.config.respect_sentences,
        )


# Quick test
if __name__ == "__main__":
    test_text = """
    Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod
    tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam,
    quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo
    consequat. Duis aute irure dolor in reprehenderit in voluptate velit esse
    cillum dolore eu fugiat nulla pariatur. Excepteur sint occaecat cupidatat
    non proident, sunt in culpa qui officia deserunt mollit anim id est laborum.
    """ * 3

    print("Fixed-size chunker:")
    chunker = FixedSizeChunker(ChunkerConfig(chunk_size=200, chunk_overlap=40))
    chunks = chunker.chunk(test_text, "test.txt")
    for chunk in chunks:
        print(f"  [{chunk.chunk_index}] {chunk.char_count} chars: {chunk.text[:50]}...")
