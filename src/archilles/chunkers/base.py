"""
ARCHILLES Chunker Base Classes

Abstract base class and data structures for text chunking.

Design Philosophy:
- Chunkers split parsed text into embedding-ready pieces
- Configurable chunk size and overlap
- Support both character and token-based sizing
- Preserve source metadata through the chunking process
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Literal


SizeUnit = Literal["characters", "tokens"]


@dataclass
class ChunkerConfig:
    """Configuration for text chunking."""

    chunk_size: int = 1000
    chunk_overlap: int = 200
    size_unit: SizeUnit = "characters"
    min_chunk_size: int = 100
    max_chunk_size: Optional[int] = None
    respect_sentences: bool = True
    respect_paragraphs: bool = True

    def __post_init__(self):
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap must be less than chunk_size")
        if self.min_chunk_size > self.chunk_size:
            raise ValueError("min_chunk_size must not exceed chunk_size")


@dataclass
class TextChunk:
    """
    A chunk of text ready for embedding.

    Contains the text content and metadata about its source.
    """

    # The actual text content
    text: str

    # Position in the chunking sequence
    chunk_index: int = 0

    # Source information (inherited from parsed document)
    source_file: str = ""
    page_start: Optional[int] = None  # First page this chunk covers
    page_end: Optional[int] = None    # Last page this chunk covers

    # Character offsets in the source text
    start_char: int = 0
    end_char: int = 0

    # Size information
    char_count: int = 0
    token_count: Optional[int] = None  # If computed

    # Additional metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if self.char_count == 0:
            self.char_count = len(self.text)

    @property
    def page_range(self) -> str:
        """Get page range as string (e.g., '1-3' or '5')."""
        if self.page_start is None:
            return ""
        if self.page_end is None or self.page_start == self.page_end:
            return str(self.page_start)
        return f"{self.page_start}-{self.page_end}"

    def __repr__(self) -> str:
        preview = self.text[:40] + "..." if len(self.text) > 40 else self.text
        preview = preview.replace('\n', ' ')
        return f"TextChunk(idx={self.chunk_index}, chars={self.char_count}, text='{preview}')"


class TextChunker(ABC):
    """
    Abstract base class for text chunkers.

    Implementations should:
    1. Accept a ChunkerConfig for configuration
    2. Implement chunk() to split text into chunks
    3. Optionally implement chunk_with_pages() for page-aware chunking

    Example implementation:
        class MyChunker(TextChunker):
            @property
            def name(self) -> str:
                return "my-chunker"

            def chunk(self, text: str, source_file: str = "") -> List[TextChunk]:
                # Implementation here
                pass
    """

    def __init__(self, config: Optional[ChunkerConfig] = None):
        self.config = config or ChunkerConfig()

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier, lowercase with hyphens (e.g., "semantic", "fixed-size")."""
        pass

    @property
    def description(self) -> str:
        """Human-readable description of this chunker."""
        return f"{self.name} chunker"

    @abstractmethod
    def chunk(self, text: str, source_file: str = "") -> List[TextChunk]:
        """Split text into chunks."""
        pass

    def chunk_with_pages(
        self,
        pages: List[str],
        source_file: str = ""
    ) -> List[TextChunk]:
        """Chunk text while preserving page information.

        Joins pages, chunks the combined text, then maps chunks back to
        their source pages. Subclasses can override for page-aware chunking.
        """
        if not pages:
            return []

        # Track page boundaries in the combined text
        page_boundaries = []  # (start_char, end_char, page_num)
        current_pos = 0

        combined_parts = []
        for page_num, page_text in enumerate(pages, start=1):
            start = current_pos
            combined_parts.append(page_text)
            current_pos += len(page_text) + 2  # +2 for \n\n separator
            page_boundaries.append((start, current_pos - 2, page_num))

        combined_text = "\n\n".join(combined_parts)

        # Chunk the combined text
        chunks = self.chunk(combined_text, source_file)

        # Map chunks back to pages
        for chunk in chunks:
            chunk_start = chunk.start_char
            chunk_end = chunk.end_char

            # Find which pages this chunk spans
            pages_covered = []
            for start, end, page_num in page_boundaries:
                # Check if chunk overlaps with this page
                if chunk_start < end and chunk_end > start:
                    pages_covered.append(page_num)

            if pages_covered:
                chunk.page_start = min(pages_covered)
                chunk.page_end = max(pages_covered)

        return chunks

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count (~4 chars/token). Override with actual tokenizer."""
        return len(text) // 4

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}(name='{self.name}', "
            f"chunk_size={self.config.chunk_size}, "
            f"overlap={self.config.chunk_overlap})"
        )


# Quick test
if __name__ == "__main__":
    # Test data structures
    config = ChunkerConfig(
        chunk_size=500,
        chunk_overlap=50,
        respect_sentences=True
    )
    print(f"Config: {config}")

    chunk = TextChunk(
        text="This is a test chunk with some content.",
        chunk_index=0,
        source_file="test.pdf",
        page_start=1,
        page_end=2,
        start_char=0,
        end_char=40
    )
    print(f"Chunk: {chunk}")
    print(f"Page range: {chunk.page_range}")
