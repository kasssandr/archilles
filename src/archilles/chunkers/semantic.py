"""
ARCHILLES Semantic Chunker

Chunks text while respecting natural boundaries:
- Paragraph breaks
- Sentence endings
- Section headers

This produces more coherent chunks for embedding.
"""

import re
from typing import List, Optional

from .base import TextChunker, TextChunk, ChunkerConfig


class SemanticChunker(TextChunker):
    """
    Semantic text chunker that respects natural text boundaries.

    Tries to break at:
    1. Paragraph boundaries (double newlines)
    2. Sentence boundaries (., !, ?)
    3. Clause boundaries (;, :, ,)
    4. Word boundaries (spaces)

    Falls back to character boundaries only as last resort.
    """

    # Sentence ending patterns
    SENTENCE_ENDINGS = re.compile(r'[.!?]+[\s\n]+')

    # Paragraph pattern (2+ newlines)
    PARAGRAPH_BREAK = re.compile(r'\n\s*\n')

    @property
    def name(self) -> str:
        return "semantic"

    @property
    def description(self) -> str:
        return "Chunks text respecting sentence and paragraph boundaries"

    def chunk(self, text: str, source_file: str = "") -> List[TextChunk]:
        """
        Split text into semantically coherent chunks.

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

        # Split into paragraphs first
        paragraphs = self.PARAGRAPH_BREAK.split(text)
        paragraphs = [p.strip() for p in paragraphs if p.strip()]

        current_chunk_text = ""
        current_start = 0
        text_position = 0  # Track position in original text

        for para in paragraphs:
            # Find actual position of this paragraph in original text
            para_start = text.find(para, text_position)
            if para_start == -1:
                para_start = text_position
            text_position = para_start + len(para)

            # Check if adding this paragraph exceeds chunk size
            potential_text = current_chunk_text + ("\n\n" if current_chunk_text else "") + para

            if len(potential_text) <= chunk_size:
                # Fits in current chunk
                if not current_chunk_text:
                    current_start = para_start
                current_chunk_text = potential_text
            else:
                # Need to handle overflow
                if current_chunk_text:
                    # Save current chunk if it meets minimum size
                    if len(current_chunk_text) >= min_size:
                        chunks.append(self._create_chunk(
                            current_chunk_text,
                            len(chunks),
                            source_file,
                            current_start,
                            current_start + len(current_chunk_text)
                        ))

                # Handle the paragraph that didn't fit
                if len(para) <= chunk_size:
                    # Paragraph fits in a single chunk
                    current_chunk_text = para
                    current_start = para_start
                else:
                    # Paragraph is too long, need to split it
                    para_chunks = self._split_long_paragraph(
                        para, chunk_size, overlap, min_size
                    )
                    for i, para_chunk in enumerate(para_chunks[:-1]):
                        chunks.append(self._create_chunk(
                            para_chunk,
                            len(chunks),
                            source_file,
                            para_start,
                            para_start + len(para_chunk)
                        ))
                    # Keep last part as current chunk for potential merging
                    if para_chunks:
                        current_chunk_text = para_chunks[-1]
                        current_start = para_start + len(para) - len(current_chunk_text)
                    else:
                        current_chunk_text = ""

        # Don't forget the last chunk
        if current_chunk_text and len(current_chunk_text) >= min_size:
            chunks.append(self._create_chunk(
                current_chunk_text,
                len(chunks),
                source_file,
                current_start,
                current_start + len(current_chunk_text)
            ))
        elif current_chunk_text and chunks:
            # Merge small final chunk with previous
            last_chunk = chunks[-1]
            merged_text = last_chunk.text + "\n\n" + current_chunk_text
            chunks[-1] = self._create_chunk(
                merged_text,
                last_chunk.chunk_index,
                source_file,
                last_chunk.start_char,
                current_start + len(current_chunk_text)
            )

        # Apply overlap by extending chunks
        if overlap > 0 and len(chunks) > 1:
            chunks = self._apply_overlap(chunks, text, overlap)

        return chunks

    def _split_long_paragraph(
        self,
        para: str,
        chunk_size: int,
        overlap: int,
        min_size: int
    ) -> List[str]:
        """
        Split a paragraph that's too long into smaller chunks.

        Tries to break at sentence boundaries.
        """
        if len(para) <= chunk_size:
            return [para]

        chunks = []
        sentences = self.SENTENCE_ENDINGS.split(para)

        current = ""
        for i, sent in enumerate(sentences):
            sent = sent.strip()
            if not sent:
                continue

            # Re-add sentence ending if not last
            if i < len(sentences) - 1:
                # Find the ending that was removed
                match = self.SENTENCE_ENDINGS.search(para, para.find(sent) + len(sent) - 1)
                if match:
                    sent += match.group().rstrip()

            potential = current + (" " if current else "") + sent

            if len(potential) <= chunk_size:
                current = potential
            else:
                if current:
                    chunks.append(current)
                # Handle sentence longer than chunk_size
                if len(sent) > chunk_size:
                    # Split by words
                    word_chunks = self._split_by_words(sent, chunk_size)
                    chunks.extend(word_chunks[:-1])
                    current = word_chunks[-1] if word_chunks else ""
                else:
                    current = sent

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


def create_semantic_chunker(
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
    **kwargs
) -> SemanticChunker:
    """
    Factory function to create a semantic chunker.

    Args:
        chunk_size: Target chunk size in characters
        chunk_overlap: Overlap between chunks
        **kwargs: Additional ChunkerConfig parameters

    Returns:
        Configured SemanticChunker instance
    """
    config = ChunkerConfig(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        **kwargs
    )
    return SemanticChunker(config)


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
