"""Base class for all text extractors."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Dict, Any
import time

from .models import ExtractedText, ExtractionMetadata, ChunkMetadata
from .exceptions import ExtractionError


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

    def _create_chunks(
        self,
        text: str,
        base_metadata: ChunkMetadata = None
    ) -> List[Dict[str, Any]]:
        """
        Split text into semantic chunks.

        Uses paragraph boundaries to avoid splitting mid-sentence.
        For humanities texts, preserving argument structure is critical.

        Args:
            text: Full text to chunk
            base_metadata: Base metadata to copy to each chunk

        Returns:
            List of chunks with text and metadata
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
                    # Copy base metadata
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

        return chunks

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
