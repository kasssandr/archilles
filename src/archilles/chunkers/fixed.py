"""
ARCHILLES Fixed-Size Chunker

Simple chunker that splits text into fixed-size chunks.
Useful when consistent chunk sizes are needed (e.g., for batching).
"""

from typing import List, Optional

from .base import TextChunker, TextChunk, ChunkerConfig


class FixedSizeChunker(TextChunker):
    """
    Fixed-size text chunker.

    Splits text into chunks of approximately equal size.
    Can break at word boundaries to avoid splitting words.
    """

    @property
    def name(self) -> str:
        return "fixed-size"

    @property
    def description(self) -> str:
        return "Chunks text into fixed-size pieces"

    def chunk(self, text: str, source_file: str = "") -> List[TextChunk]:
        """
        Split text into fixed-size chunks.

        Args:
            text: The text to chunk
            source_file: Optional source file path for metadata

        Returns:
            List of TextChunk objects
        """
        if not text or not text.strip():
            return []

        chunks = []
        chunk_size = self.config.chunk_size
        overlap = self.config.chunk_overlap
        min_size = self.config.min_chunk_size

        # Calculate step size (chunk_size - overlap)
        step = chunk_size - overlap
        if step <= 0:
            step = chunk_size // 2  # Fallback

        text = text.strip()
        text_len = len(text)
        position = 0

        while position < text_len:
            # Calculate end position
            end = min(position + chunk_size, text_len)

            # Extract chunk
            chunk_text = text[position:end]

            # Adjust to word boundary if not at end
            if end < text_len and self.config.respect_sentences:
                # Find last space in chunk
                last_space = chunk_text.rfind(' ')
                if last_space > min_size:
                    chunk_text = chunk_text[:last_space]
                    end = position + last_space

            # Create chunk if meets minimum size
            if len(chunk_text.strip()) >= min_size:
                chunks.append(TextChunk(
                    text=chunk_text.strip(),
                    chunk_index=len(chunks),
                    source_file=source_file,
                    start_char=position,
                    end_char=end,
                    char_count=len(chunk_text.strip())
                ))

            # Move to next position
            position = position + step

            # Avoid infinite loop
            if position >= end and end < text_len:
                position = end

        return chunks


class TokenBasedChunker(TextChunker):
    """
    Token-based chunker using approximate token counts.

    Useful when targeting specific token limits for embedding models.
    Uses ~4 chars per token as default approximation.
    """

    def __init__(
        self,
        config: Optional[ChunkerConfig] = None,
        chars_per_token: float = 4.0
    ):
        """
        Initialize token-based chunker.

        Args:
            config: Chunking configuration
            chars_per_token: Character-to-token ratio (default: 4.0)
        """
        super().__init__(config)
        self.chars_per_token = chars_per_token

    @property
    def name(self) -> str:
        return "token-based"

    @property
    def description(self) -> str:
        return f"Chunks text by approximate token count (~{self.chars_per_token} chars/token)"

    def chunk(self, text: str, source_file: str = "") -> List[TextChunk]:
        """
        Split text into chunks based on token count.

        Args:
            text: The text to chunk
            source_file: Optional source file path for metadata

        Returns:
            List of TextChunk objects with token_count set
        """
        if not text or not text.strip():
            return []

        # Convert token-based config to character-based
        char_chunk_size = int(self.config.chunk_size * self.chars_per_token)
        char_overlap = int(self.config.chunk_overlap * self.chars_per_token)
        char_min_size = int(self.config.min_chunk_size * self.chars_per_token)

        chunks = []
        step = char_chunk_size - char_overlap
        if step <= 0:
            step = char_chunk_size // 2

        text = text.strip()
        text_len = len(text)
        position = 0

        while position < text_len:
            end = min(position + char_chunk_size, text_len)
            chunk_text = text[position:end]

            # Adjust to word boundary
            if end < text_len:
                last_space = chunk_text.rfind(' ')
                if last_space > char_min_size:
                    chunk_text = chunk_text[:last_space]
                    end = position + last_space

            chunk_text = chunk_text.strip()
            if len(chunk_text) >= char_min_size:
                token_count = self.estimate_tokens(chunk_text)
                chunks.append(TextChunk(
                    text=chunk_text,
                    chunk_index=len(chunks),
                    source_file=source_file,
                    start_char=position,
                    end_char=end,
                    char_count=len(chunk_text),
                    token_count=token_count
                ))

            position = position + step
            if position >= end and end < text_len:
                position = end

        return chunks

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
