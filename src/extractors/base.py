"""Base class for all text extractors."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Dict, Any
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
        """
        Initialize extractor.

        Args:
            chunk_size: Target chunk size in tokens (approximate)
            overlap: Overlap between chunks in tokens
        """
        self.chunk_size = chunk_size
        self.overlap = overlap

    @abstractmethod
    def extract(self, file_path: Path) -> ExtractedText:
        """
        Extract text from file.

        Args:
            file_path: Path to file

        Returns:
            ExtractedText with full text, chunks, and metadata

        Raises:
            ExtractionError: If extraction fails
        """
        pass

    @abstractmethod
    def supports(self, file_path: Path) -> bool:
        """
        Check if this extractor supports the given file.

        Args:
            file_path: Path to file

        Returns:
            True if supported, False otherwise
        """
        pass

    # Separators for recursive splitting (German + English academic texts)
    SEPARATORS = ["\n\n", "\n", ". ", "? ", "! ", "; ", " ", ""]

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

        Each chunk includes:
        - char_start/char_end: Character offsets in the full text
        - window_text: Chunk text + surrounding context (~window_chars before/after)

        Args:
            text: Full text to chunk
            base_metadata: Base metadata to copy to each chunk
            detect_language: If True, automatically detect language for each chunk
            window_chars: Characters of context to add before/after for window_text

        Returns:
            List of chunks with text, window_text, and metadata
        """
        if not text:
            return []

        chunks = []
        paragraphs = text.split('\n\n')

        current_chunk = []
        current_size = 0
        char_position = 0

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            # Rough token count (words * 1.3)
            para_tokens = len(para.split()) * 1.3

            # If adding this paragraph exceeds chunk size, save current chunk
            if current_size + para_tokens > self.chunk_size and current_chunk:
                chunk_text = '\n\n'.join(current_chunk)

                # Create metadata for this chunk
                chunk_meta = ChunkMetadata()
                if base_metadata:
                    for key, value in base_metadata.__dict__.items():
                        setattr(chunk_meta, key, value)

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
            chunk_meta = ChunkMetadata()
            if base_metadata:
                for key, value in base_metadata.__dict__.items():
                    setattr(chunk_meta, key, value)
            chunk_meta.char_start = char_position
            chunk_meta.char_end = char_position + len(chunk_text)

            chunks.append({
                'text': chunk_text,
                'metadata': chunk_meta.__dict__
            })

        # Generate window_text for each chunk (Small-to-Big context expansion)
        if window_chars > 0:
            for chunk in chunks:
                cs = chunk['metadata'].get('char_start', 0)
                ce = chunk['metadata'].get('char_end', 0)
                win_start = max(0, cs - window_chars)
                win_end = min(len(text), ce + window_chars)
                chunk['window_text'] = text[win_start:win_end]

        # Detect language for all chunks
        if detect_language and LanguageDetector.is_available():
            chunks = LanguageDetector.detect_for_chunks(chunks)

        return chunks

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

        Parents are large chunks (~2048 chars) representing sections/paragraphs.
        Children are small chunks (~512 chars) for precise retrieval.
        Each child has a parent_id linking to its parent.

        At retrieval time:
        1. Search on child level (high precision)
        2. Load parent for broader context
        3. Pass both to Claude

        Args:
            text: Full text to chunk
            book_id: Book identifier for generating chunk IDs
            base_metadata: Base metadata to copy to each chunk
            detect_language: If True, detect language per chunk
            parent_size: Target parent chunk size in tokens
            parent_overlap: Overlap between parent chunks in tokens
            child_size: Target child chunk size in tokens
            child_overlap: Overlap between child chunks in tokens
            window_chars: Characters of context for window_text

        Returns:
            List of all chunks (parents + children), each with chunk_type
            set to "parent" or "child" and children having parent_id set.
        """
        if not text:
            return []

        all_chunks = []

        # Step 1: Create parent chunks (large)
        saved_chunk_size = self.chunk_size
        saved_overlap = self.overlap
        self.chunk_size = parent_size
        self.overlap = parent_overlap

        parent_chunks = self._create_chunks(
            text, base_metadata, detect_language=False, window_chars=0
        )

        self.chunk_size = saved_chunk_size
        self.overlap = saved_overlap

        # Step 2: For each parent, create child chunks
        for p_idx, parent in enumerate(parent_chunks):
            parent_id = f"{book_id}_parent_{p_idx}"
            parent['metadata']['chunk_type'] = 'parent'
            parent['chunk_id'] = parent_id
            parent['parent_id'] = ''  # Parents have no parent

            # Generate window_text for parent
            if window_chars > 0:
                cs = parent['metadata'].get('char_start', 0)
                ce = parent['metadata'].get('char_end', 0)
                win_start = max(0, cs - window_chars)
                win_end = min(len(text), ce + window_chars)
                parent['window_text'] = text[win_start:win_end]

            all_chunks.append(parent)

            # Create children from parent text
            parent_text = parent['text']
            saved_chunk_size = self.chunk_size
            saved_overlap = self.overlap
            self.chunk_size = child_size
            self.overlap = child_overlap

            children = self._create_chunks(
                parent_text, base_metadata, detect_language=False, window_chars=0
            )

            self.chunk_size = saved_chunk_size
            self.overlap = saved_overlap

            # Adjust child offsets relative to full text and link to parent
            parent_char_start = parent['metadata'].get('char_start', 0)
            for c_idx, child in enumerate(children):
                child_id = f"{book_id}_parent_{p_idx}_child_{c_idx}"
                child['chunk_id'] = child_id
                child['parent_id'] = parent_id
                child['metadata']['chunk_type'] = 'child'

                # Adjust char offsets to be relative to full text
                child['metadata']['char_start'] = (
                    parent_char_start + child['metadata'].get('char_start', 0)
                )
                child['metadata']['char_end'] = (
                    parent_char_start + child['metadata'].get('char_end', 0)
                )

                # Generate window_text for child using full text
                if window_chars > 0:
                    cs = child['metadata']['char_start']
                    ce = child['metadata']['char_end']
                    win_start = max(0, cs - window_chars)
                    win_end = min(len(text), ce + window_chars)
                    child['window_text'] = text[win_start:win_end]

                all_chunks.append(child)

        # Detect language for all chunks
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
        """
        Create extraction metadata.

        Args:
            file_path: Source file path
            format_name: Detected format
            extraction_time: Time taken to extract
            **kwargs: Additional metadata fields

        Returns:
            ExtractionMetadata object
        """
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
        """
        Wrapper that times the extraction.

        Args:
            file_path: Path to file

        Returns:
            ExtractedText with timing metadata
        """
        start_time = time.time()
        try:
            result = self.extract(file_path)
            result.metadata.extraction_time = time.time() - start_time
            result.metadata.success = True
            return result
        except Exception as e:
            # Create error metadata
            extraction_time = time.time() - start_time
            metadata = self._create_extraction_metadata(
                file_path=file_path,
                format_name='unknown',
                extraction_time=extraction_time,
                success=False,
                errors=[str(e)]
            )
            raise ExtractionError(f"Extraction failed: {e}") from e
