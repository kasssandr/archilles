"""Base class for all text extractors."""

from abc import ABC, abstractmethod
from contextlib import contextmanager
from pathlib import Path
import re
from typing import Any

from src.archilles.constants import ChunkType
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
        chunks: list[dict[str, Any]], full_text: str, window_chars: int
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
    ) -> list[dict[str, Any]]:
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

    def _split_para_by_words(self, text: str) -> list[str]:
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

        parts: list[str] = []
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

    @staticmethod
    def _group_chunks_hierarchically(
        child_chunks: list[dict[str, Any]],
        book_id: str,
        parent_size: int = 2048,
    ) -> list[dict[str, Any]]:
        """
        Build two-level hierarchy (parent + child) from already-extracted,
        structure-aware chunks (Small-to-Big retrieval).

        The input chunks become the CHILD chunks unchanged — their section/page
        metadata (``section_type``/``page``/``page_label``/``chapter``/
        ``section_title``), char offsets and ``window_text`` are preserved, so
        children stay citation-grade. Consecutive children are grouped into a
        PARENT chunk for broad context; a new parent starts when adding the next
        child would exceed ``parent_size`` tokens or when the child's section
        identity (section_type/chapter/section_title) changes — keeping each
        parent coherent and its inherited metadata consistent.

        This replaces the earlier ``full_text`` re-chunking path, which built
        children from raw text with minimal metadata and thereby dropped all
        structure/page metadata (validation finding #1). Because
        children keep the extractor's offsets, the offset drift of that path is
        gone as well.

        Returns a flat list in [parent, child, child, …, parent, …] order.
        """
        if not child_chunks:
            return []

        def tokens(chunk: dict[str, Any]) -> float:
            return len(chunk["text"].split()) * 1.3

        def section_key(chunk: dict[str, Any]):
            meta = chunk.get("metadata", {})
            return (
                meta.get("section_type"),
                meta.get("chapter"),
                meta.get("section_title"),
            )

        all_chunks: list[dict[str, Any]] = []
        parent_idx = 0
        i = 0
        n = len(child_chunks)
        while i < n:
            group = [child_chunks[i]]
            group_tokens = tokens(child_chunks[i])
            key = section_key(child_chunks[i])
            j = i + 1
            while j < n:
                nxt = child_chunks[j]
                if section_key(nxt) != key:
                    break
                nxt_tokens = tokens(nxt)
                # Always keep at least one child per parent; only stop when the
                # group already has content and the budget would be exceeded.
                if group_tokens + nxt_tokens > parent_size:
                    break
                group.append(nxt)
                group_tokens += nxt_tokens
                j += 1

            parent_id = f"{book_id}_parent_{parent_idx}"
            parent_meta = dict(group[0].get("metadata", {}))
            parent_meta["chunk_type"] = ChunkType.PARENT
            parent_meta["char_start"] = group[0].get("metadata", {}).get("char_start")
            parent_meta["char_end"] = group[-1].get("metadata", {}).get("char_end")
            all_chunks.append(
                {
                    "text": "\n\n".join(c["text"] for c in group),
                    "metadata": parent_meta,
                    "chunk_id": parent_id,
                    "parent_id": "",
                }
            )

            for c_idx, src in enumerate(group):
                child = dict(src)
                child["metadata"] = dict(src.get("metadata", {}))
                child["metadata"]["chunk_type"] = ChunkType.CHILD
                child["chunk_id"] = f"{parent_id}_child_{c_idx}"
                child["parent_id"] = parent_id
                all_chunks.append(child)

            parent_idx += 1
            i = j

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

