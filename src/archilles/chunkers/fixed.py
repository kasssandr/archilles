"""
ARCHILLES Fixed-Size Chunker

Simple chunker that splits text into fixed-size chunks.
Useful when consistent chunk sizes are needed (e.g., for batching).
"""

from typing import List, Optional

from .base import TextChunker, TextChunk, ChunkerConfig


def _sliding_window_chunks(
    text: str,
    source_file: str,
    chunk_size: int,
    overlap: int,
    min_size: int,
    respect_word_boundaries: bool = True,
    token_count_fn=None,
) -> List[TextChunk]:
    """
    Core sliding-window chunking used by both FixedSizeChunker and TokenBasedChunker.

    Args:
        text: Pre-stripped text to chunk
        source_file: Source file path for metadata
        chunk_size: Maximum chunk size in characters
        overlap: Overlap between consecutive chunks in characters
        min_size: Minimum chunk size to emit
        respect_word_boundaries: Whether to break at word boundaries
        token_count_fn: Optional callable to compute token count per chunk
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
            token_count = token_count_fn(stripped) if token_count_fn else None
            chunks.append(TextChunk(
                text=stripped,
                chunk_index=len(chunks),
                source_file=source_file,
                start_char=position,
                end_char=end,
                char_count=len(stripped),
                token_count=token_count,
            ))

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


class TokenBasedChunker(TextChunker):
    """
    Token-based chunker using approximate token counts.

    Useful when targeting specific token limits for embedding models.
    Uses a configurable chars-per-token ratio (default ~4) to convert
    token limits into character limits for the sliding window.
    """

    def __init__(
        self,
        config: Optional[ChunkerConfig] = None,
        chars_per_token: float = 4.0,
    ):
        super().__init__(config)
        self.chars_per_token = chars_per_token

    @property
    def name(self) -> str:
        return "token-based"

    @property
    def description(self) -> str:
        return f"Chunks text by approximate token count (~{self.chars_per_token} chars/token)"

    def chunk(self, text: str, source_file: str = "") -> List[TextChunk]:
        if not text or not text.strip():
            return []

        ratio = self.chars_per_token
        return _sliding_window_chunks(
            text=text.strip(),
            source_file=source_file,
            chunk_size=int(self.config.chunk_size * ratio),
            overlap=int(self.config.chunk_overlap * ratio),
            min_size=int(self.config.min_chunk_size * ratio),
            respect_word_boundaries=True,
            token_count_fn=self.estimate_tokens,
        )

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count using configured ratio."""
        return int(len(text) / self.chars_per_token)


def create_fixed_chunker(
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
    **kwargs
) -> FixedSizeChunker:
    """
    Factory function to create a fixed-size chunker.

    Args:
        chunk_size: Target chunk size in characters
        chunk_overlap: Overlap between chunks
        **kwargs: Additional ChunkerConfig parameters

    Returns:
        Configured FixedSizeChunker instance
    """
    config = ChunkerConfig(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        **kwargs
    )
    return FixedSizeChunker(config)


def create_token_chunker(
    max_tokens: int = 256,
    token_overlap: int = 50,
    chars_per_token: float = 4.0,
    **kwargs
) -> TokenBasedChunker:
    """
    Factory function to create a token-based chunker.

    Args:
        max_tokens: Maximum tokens per chunk
        token_overlap: Token overlap between chunks
        chars_per_token: Character-to-token ratio
        **kwargs: Additional ChunkerConfig parameters

    Returns:
        Configured TokenBasedChunker instance
    """
    config = ChunkerConfig(
        chunk_size=max_tokens,
        chunk_overlap=token_overlap,
        size_unit="tokens",
        **kwargs
    )
    return TokenBasedChunker(config, chars_per_token)


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

    print("\nToken-based chunker:")
    token_chunker = TokenBasedChunker(
        ChunkerConfig(chunk_size=50, chunk_overlap=10, size_unit="tokens")
    )
    chunks = token_chunker.chunk(test_text, "test.txt")
    for chunk in chunks:
        print(f"  [{chunk.chunk_index}] ~{chunk.token_count} tokens: {chunk.text[:50]}...")
