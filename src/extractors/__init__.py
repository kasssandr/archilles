"""
Universal text extraction from e-books in any format.

Supports all common e-book formats through a fallback chain:
1. Native parsers (PDF, EPUB, TXT, HTML) - fast & precise
2. Calibre ebook-convert - reliable for most formats
3. Pandoc fallback - for legacy/exotic formats
"""

from .universal_extractor import UniversalExtractor
from .format_detector import FormatDetector
from .language_detector import LanguageDetector
from .models import ExtractedText, ExtractionMetadata, ChunkMetadata
from .exceptions import (
    ExtractionError,
    UnsupportedFormatError,
    ConversionError,
)

__all__ = [
    'UniversalExtractor',
    'FormatDetector',
    'LanguageDetector',
    'ExtractedText',
    'ExtractionMetadata',
    'ChunkMetadata',
    'ExtractionError',
    'UnsupportedFormatError',
    'ConversionError',
]

__version__ = '0.1.0'
