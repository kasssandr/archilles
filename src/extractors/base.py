"""Base class for all text extractors."""

from abc import ABC, abstractmethod
from contextlib import contextmanager
from pathlib import Path
from typing import List, Dict, Any
import re
import time

from .models import ExtractedText, ExtractionMetadata, ChunkMetadata
from .exceptions import ExtractionError
from .language_detector import LanguageDetector


class BaseExtractor(ABC):
    """
    Abstract base class for all format-specific extractors.

    Each extractor must implement:
    - extract(): Main extraction method
    - supports(): Check if format is supported
    """

    def __init__(self, chunk_size: int = 512, overlap: int = 128):
        self.chunk_size = chunk_size
        self.overlap = overlap

    @abstractmethod
    def extract(self, file_path: Path) -> ExtractedText:
        """Extract text from file.

        Raises:
            ExtractionError: If extraction fails
        """
        pass

    @abstractmethod
    def supports(self, file_path: Path) -> bool:
        """Check if this extractor supports the given file."""
        pass

    @contextmanager
    def _temporary_chunk_params(self, chunk_size: int, overlap: int):
        """Temporarily override chunk_size and overlap, restoring on exit."""
        saved_size, saved_overlap = self.chunk_size, self.overlap
        self.chunk_size, self.overlap = chunk_size, overlap
        try:
            yield
        finally:
            self.chunk_size, self.overlap = saved_size, saved_overlap

    @staticmethod
    def _copy_metadata(base_metadata: ChunkMetadata) -> ChunkMetadata:
        """Create a copy of base_metadata, or a blank ChunkMetadata if None."""
        chunk_meta = ChunkMetadata()
        if base_metadata:
            for key, value in base_metadata.__dict__.items():
                setattr(chunk_meta, key, value)
        return chunk_meta

    @staticmethod
    def _add_window_text(
        chunks: List[Dict[str, Any]], full_text: str, window_chars: int
    ) -> None:
        """Add window_text (surrounding context) to each chunk in-place."""
        for chunk in chunks:
            cs = chunk['metadata'].get('char_start', 0)
            ce = chunk['metadata'].get('char_end', 0)
            win_start = max(0, cs - window_chars)
            win_end = min(len(full_text), ce + window_chars)
            chunk['window_text'] = full_text[win_start:win_end]

    def _create_chunks(
        self,
        text: str,
        base_metadata: ChunkMetadata = None,
        detect_language: bool = True,
        window_chars: int = 500
    ) -> List[Dict[str, Any]]:
        """
        Split text into semantic chunks with context windows (Small-to-Big).

        Uses paragraph boundaries to avoid splitting mid-sentence.
        For humanities texts, preserving argument structure is critical.
        """
        if not text:
            return []

        chunks = []
        raw_paragraphs = text.split('\n\n')

        # Pre-split paragraphs that are larger than chunk_size on their own.
        # This handles e.g. YouTube transcripts that have no paragraph breaks
        # and would otherwise end up as a single massive chunk.
        paragraphs = []
        for raw in raw_paragraphs:
            raw = raw.strip()
            if not raw:
                continue
            if len(raw.split()) * 1.3 > self.chunk_size:
                paragraphs.extend(self._split_para_by_words(raw))
            else:
                paragraphs.append(raw)

        current_chunk = []
        current_size = 0
        char_position = 0

        for para in paragraphs:
            para_tokens = len(para.split()) * 1.3

            if current_size + para_tokens > self.chunk_size and current_chunk:
                chunk_text = '\n\n'.join(current_chunk)

                chunk_meta = self._copy_metadata(base_metadata)
                chunk_meta.char_start = char_position
                chunk_meta.char_end = char_position + len(chunk_text)

                chunks.append({
                    'text': chunk_text,
                    'metadata': chunk_meta.__dict__
                })

                # Overlap: keep last paragraph for context
                if self.overlap > 0 and current_chunk:
                    overlap_text = current_chunk[-1]
                    current_chunk = [overlap_text, para]
                    current_size = len(overlap_text.split()) * 1.3 + para_tokens
                    char_position += len(chunk_text) - len(overlap_text)
                else:
                    current_chunk = [para]
                    current_size = para_tokens
                    char_position += len(chunk_text)
            else:
                current_chunk.append(para)
                current_size += para_tokens

        # Add final chunk
        if current_chunk:
            chunk_text = '\n\n'.join(current_chunk)
            chunk_meta = self._copy_metadata(base_metadata)
            chunk_meta.char_start = char_position
            chunk_meta.char_end = char_position + len(chunk_text)

            chunks.append({
                'text': chunk_text,
                'metadata': chunk_meta.__dict__
            })

        if window_chars > 0:
            self._add_window_text(chunks, text, window_chars)

        if detect_language and LanguageDetector.is_available():
            chunks = LanguageDetector.detect_for_chunks(chunks)

        return chunks

    _SENTENCE_END_RE = re.compile(r'[.!?;:»"\')\u201d]\s')

    def _split_para_by_words(self, text: str) -> List[str]:
        """Split a single oversized paragraph into sentence-aligned chunks with overlap.

        Used as a pre-processing step in ``_create_chunks`` for texts that have
        no paragraph breaks (e.g. YouTube transcripts, long EPUB sections).
        Tries to cut at sentence boundaries; falls back to word boundaries
        if no sentence end is found within the target window.
        """
        words = text.split()
        total = len(words)
        if total == 0:
            return []

        words_per_chunk = max(1, int(self.chunk_size / 1.3))
        overlap_words = max(0, int(self.overlap / 1.3))

        parts: List[str] = []
        i = 0
        while i < total:
            end = min(i + words_per_chunk, total)
            candidate = ' '.join(words[i:end])

            # If not the last chunk, try to align to a sentence boundary
            if end < total:
                candidate = self._align_to_sentence_end(candidate)

            parts.append(candidate)

            # Advance: actual words consumed minus overlap
            consumed = len(candidate.split())
            step = max(1, consumed - overlap_words)
            i += step
        return parts

    @classmethod
    def _align_to_sentence_end(cls, text: str) -> str:
        """Trim text to end at the last sentence boundary, if one exists.

        Looks for sentence-ending punctuation followed by whitespace.
        Only trims if at least 40% of the text is retained, to avoid
        degenerate tiny chunks.
        """
        # Find all sentence boundaries
        min_keep = int(len(text) * 0.4)
        last_match = None
        for m in cls._SENTENCE_END_RE.finditer(text):
            if m.end() >= min_keep:
                last_match = m
        if last_match:
            # Include the punctuation, strip trailing whitespace
            return text[:last_match.start() + 1].rstrip()
        return text

    def _create_hierarchical_chunks(
        self,
        text: str,
        book_id: str,
        base_metadata: ChunkMetadata = None,
        detect_language: bool = True,
        parent_size: int = 2048,
        parent_overlap: int = 400,
        child_size: int = 512,
        child_overlap: int = 100,
        window_chars: int = 500
    ) -> List[Dict[str, Any]]:
        """
        Create two-level hierarchical chunks (parent + child).

        Parents are large chunks for broad context. Children are small chunks
        for precise retrieval, each linked to its parent via parent_id.
        """
        if not text:
            return []

        all_chunks = []

        # Create parent chunks (large)
        with self._temporary_chunk_params(parent_size, parent_overlap):
            parent_chunks = self._create_chunks(
                text, base_metadata, detect_language=False, window_chars=0
            )

        # For each parent, create child chunks
        for p_idx, parent in enumerate(parent_chunks):
            parent_id = f"{book_id}_parent_{p_idx}"
            parent['metadata']['chunk_type'] = 'parent'
            parent['chunk_id'] = parent_id
            parent['parent_id'] = ''

            if window_chars > 0:
                self._add_window_text([parent], text, window_chars)

            all_chunks.append(parent)

            # Create children from parent text
            with self._temporary_chunk_params(child_size, child_overlap):
                children = self._create_chunks(
                    parent['text'], base_metadata,
                    detect_language=False, window_chars=0
                )

            # Adjust child offsets relative to full text and link to parent
            parent_char_start = parent['metadata'].get('char_start', 0)
            for c_idx, child in enumerate(children):
                child['chunk_id'] = f"{book_id}_parent_{p_idx}_child_{c_idx}"
                child['parent_id'] = parent_id
                child['metadata']['chunk_type'] = 'child'

                child['metadata']['char_start'] = (
                    parent_char_start + child['metadata'].get('char_start', 0)
                )
                child['metadata']['char_end'] = (
                    parent_char_start + child['metadata'].get('char_end', 0)
                )

                if window_chars > 0:
                    self._add_window_text([child], text, window_chars)

                all_chunks.append(child)

        if detect_language and LanguageDetector.is_available():
            all_chunks = LanguageDetector.detect_for_chunks(all_chunks)

        return all_chunks

    def _create_extraction_metadata(
        self,
        file_path: Path,
        format_name: str,
        extraction_time: float,
        **kwargs
    ) -> ExtractionMetadata:
        """Create extraction metadata for a file."""
        return ExtractionMetadata(
            file_path=file_path,
            file_size=file_path.stat().st_size,
            file_format=file_path.suffix.lower()[1:],
            detected_format=format_name,
            extraction_method=self.__class__.__name__,
            extraction_time=extraction_time,
            **kwargs
        )

    def _extract_with_timing(self, file_path: Path) -> ExtractedText:
        """Wrapper that times the extraction and records success/failure."""
        start_time = time.time()
        try:
            result = self.extract(file_path)
            result.metadata.extraction_time = time.time() - start_time
            result.metadata.success = True
            return result
        except Exception as e:
            raise ExtractionError(f"Extraction failed: {e}") from e
