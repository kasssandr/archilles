"""Plain text extractor."""

import zipfile
from pathlib import Path
import chardet

from .base import BaseExtractor
from .models import ExtractedText, ChunkMetadata
from .exceptions import ExtractionError


class TXTExtractor(BaseExtractor):
    """Extract text from plain text files with robust encoding detection.

    Also handles TXTZ (Calibre's zipped text format): a ZIP archive
    containing a single .txt file.
    """

    SUPPORTED_EXTENSIONS = {'.txt', '.text', '.log', '.md', '.markdown', '.rst', '.txtz'}

    def supports(self, file_path: Path) -> bool:
        """Check if file is a text file."""
        return file_path.suffix.lower() in self.SUPPORTED_EXTENSIONS

    def extract(self, file_path: Path) -> ExtractedText:
        """
        Extract text from plain text file or TXTZ archive.

        Handles:
        - TXTZ (Calibre zipped text): reads inner .txt from ZIP
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
            if file_path.suffix.lower() == '.txtz':
                with zipfile.ZipFile(file_path) as zf:
                    txt_names = [n for n in zf.namelist()
                                 if n.endswith('.txt') or n.endswith('.md')]
                    if not txt_names:
                        raise ExtractionError("No text file found inside TXTZ archive")
                    with zf.open(txt_names[0]) as f:
                        raw_data = f.read()
            else:
                with open(file_path, 'rb') as f:
                    raw_data = f.read()

            detected = chardet.detect(raw_data)
            encoding = detected.get('encoding', 'utf-8')

            # Fallback encodings to try if detection fails
            # Note: latin-1 never raises UnicodeDecodeError, so it acts as a
            # guaranteed final fallback.
            encodings_to_try = [encoding, 'utf-8', 'latin-1', 'windows-1252']

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
                raise ExtractionError("Could not decode file with any known encoding")

            # Normalize line endings
            text = text.replace('\r\n', '\n').replace('\r', '\n')

            # Remove BOM if present
            if text.startswith('\ufeff'):
                text = text[1:]

            # Strip YAML frontmatter from Markdown files so the YAML block
            # is not indexed as content (metadata is handled by the adapter)
            if file_path.suffix.lower() in {'.md', '.markdown'}:
                if text.startswith('---'):
                    end = text.find('\n---', 3)
                    if end != -1:
                        text = text[end + 4:].lstrip('\n')

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
