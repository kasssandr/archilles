"""Plain text extractor."""

from pathlib import Path
import chardet

from .base import BaseExtractor
from .models import ExtractedText, ChunkMetadata
from .exceptions import ExtractionError


class TXTExtractor(BaseExtractor):
    """Extract text from plain text files with robust encoding detection."""

    SUPPORTED_EXTENSIONS = {'.txt', '.text', '.log', '.md', '.markdown', '.rst'}

    def supports(self, file_path: Path) -> bool:
        """Check if file is a text file."""
        return file_path.suffix.lower() in self.SUPPORTED_EXTENSIONS

    def extract(self, file_path: Path) -> ExtractedText:
        """
        Extract text from plain text file.

        Handles:
        - Automatic encoding detection (UTF-8, Latin-1, Windows-1252, etc.)
        - BOM removal
        - Line ending normalization

        Args:
            file_path: Path to text file

        Returns:
            ExtractedText object
        """
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        try:
            # Detect encoding
            with open(file_path, 'rb') as f:
                raw_data = f.read()

            # Try to detect encoding
            detected = chardet.detect(raw_data)
            encoding = detected.get('encoding', 'utf-8')

            # Fallback encodings to try if detection fails
            encodings_to_try = [
                encoding,
                'utf-8',
                'latin-1',
                'windows-1252',
                'iso-8859-1',
            ]

            text = None
            used_encoding = None

            for enc in encodings_to_try:
                try:
                    text = raw_data.decode(enc)
                    used_encoding = enc
                    break
                except (UnicodeDecodeError, AttributeError):
                    continue

            if text is None:
                raise ExtractionError(f"Could not decode file with any known encoding")

            # Normalize line endings
            text = text.replace('\r\n', '\n').replace('\r', '\n')

            # Remove BOM if present
            if text.startswith('\ufeff'):
                text = text[1:]

            # Create base metadata
            base_metadata = ChunkMetadata(
                source_file=str(file_path),
                format='txt',
            )

            # Create chunks
            chunks = self._create_chunks(text, base_metadata)

            # Create extraction metadata
            extraction_metadata = self._create_extraction_metadata(
                file_path=file_path,
                format_name='txt',
                extraction_time=0,  # Will be set by wrapper
                total_chars=len(text),
                total_words=len(text.split()),
                total_chunks=len(chunks),
            )
            extraction_metadata.warnings.append(f"Detected encoding: {used_encoding}")

            return ExtractedText(
                full_text=text,
                chunks=chunks,
                metadata=extraction_metadata,
            )

        except Exception as e:
            raise ExtractionError(f"Failed to extract text: {e}") from e
