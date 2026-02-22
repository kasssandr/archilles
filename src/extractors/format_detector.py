"""Detect e-book format from file content (not just extension)."""

from pathlib import Path
from typing import Optional, Tuple
import mimetypes

# Try to import python-magic (optional dependency)
try:
    import magic
    MAGIC_AVAILABLE = True
except ImportError:
    MAGIC_AVAILABLE = False


class FormatDetector:
    """
    Detect file format using multiple strategies:
    1. Magic bytes (most reliable)
    2. MIME type
    3. File extension (fallback)
    """

    # Magic bytes for common formats
    # Note: PK\x03\x04 (ZIP) covers EPUB, DOCX, and other ZIP-based formats.
    # These are disambiguated in _detect_by_magic via content inspection.
    MAGIC_SIGNATURES = {
        b'%PDF': 'pdf',
        b'PK\x03\x04': 'zip',  # ZIP-based: EPUB, DOCX, etc. (disambiguated below)
        b'<?xml': 'html',
        b'<!DOCTYPE html': 'html',
        b'<html': 'html',
        b'MOBI': 'mobi',
        b'\xd0\xcf\x11\xe0': 'doc',
        b'{\\rtf': 'rtf',
        b'AT&TFORM': 'djvu',
    }

    # MIME type mapping
    MIME_TO_FORMAT = {
        'application/pdf': 'pdf',
        'application/epub+zip': 'epub',
        'application/x-mobipocket-ebook': 'mobi',
        'application/vnd.amazon.ebook': 'azw3',
        'image/vnd.djvu': 'djvu',
        'text/html': 'html',
        'text/plain': 'txt',
        'application/msword': 'doc',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'docx',
        'application/rtf': 'rtf',
        'application/vnd.oasis.opendocument.text': 'odt',
        'application/x-chm': 'chm',
    }

    @classmethod
    def detect(cls, file_path: Path) -> Tuple[str, str]:
        """
        Detect file format.

        Returns:
            Tuple of (detected_format, detection_method)
            detection_method can be: 'magic', 'mime', 'extension', 'unknown'
        """
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # Try magic bytes first
        try:
            detected = cls._detect_by_magic(file_path)
            if detected:
                return detected, 'magic'
        except Exception:
            pass

        # Try MIME type
        try:
            detected = cls._detect_by_mime(file_path)
            if detected:
                return detected, 'mime'
        except Exception:
            pass

        # Fallback to extension
        ext = file_path.suffix.lower()[1:]  # Remove dot
        if ext:
            return ext, 'extension'

        return 'unknown', 'unknown'

    @classmethod
    def _detect_by_magic(cls, file_path: Path) -> Optional[str]:
        """Detect format by reading magic bytes."""
        with open(file_path, 'rb') as f:
            header = f.read(512)

        # Check known signatures
        for signature, fmt in cls.MAGIC_SIGNATURES.items():
            if header.startswith(signature):
                if fmt != 'zip':
                    return fmt

                # ZIP-based format: disambiguate by inspecting content
                with open(file_path, 'rb') as f:
                    content = f.read(4096)
                if b'mimetype' in content and b'application/epub+zip' in content:
                    return 'epub'
                if b'word/' in content or b'[Content_Types].xml' in content:
                    return 'docx'
                return 'epub'  # Default ZIP-based ebook assumption

        return None

    @classmethod
    def _detect_by_mime(cls, file_path: Path) -> Optional[str]:
        """Detect format by MIME type."""
        # Try python-magic if available
        if MAGIC_AVAILABLE:
            try:
                mime = magic.from_file(str(file_path), mime=True)
                return cls.MIME_TO_FORMAT.get(mime)
            except Exception:
                pass

        # Fallback to mimetypes module (always available)
        try:
            mime, _ = mimetypes.guess_type(str(file_path))
            return cls.MIME_TO_FORMAT.get(mime) if mime else None
        except Exception:
            return None

    @classmethod
    def is_supported(cls, file_path: Path) -> bool:
        """Check if format is supported."""
        fmt, _ = cls.detect(file_path)
        return fmt != 'unknown'

    @classmethod
    def get_format_info(cls, file_path: Path) -> dict:
        """Get detailed format information."""
        fmt, method = cls.detect(file_path)
        ext = file_path.suffix.lower()[1:]

        return {
            'detected_format': fmt,
            'detection_method': method,
            'file_extension': ext,
            'extension_matches': fmt == ext,
            'supported': fmt != 'unknown',
        }
