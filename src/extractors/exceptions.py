"""Custom exceptions for text extraction."""


class ExtractionError(Exception):
    """Base exception for all extraction errors."""
    pass


class UnsupportedFormatError(ExtractionError):
    """Raised when file format is not supported."""
    pass


class ConversionError(ExtractionError):
    """Raised when format conversion fails."""
    pass


class PDFExtractionError(ExtractionError):
    """Raised when PDF extraction fails."""
    pass


class EPUBExtractionError(ExtractionError):
    """Raised when EPUB extraction fails."""
    pass


class CalibreNotFoundError(ExtractionError):
    """Raised when Calibre tools are not available."""
    pass


class PandocNotFoundError(ExtractionError):
    """Raised when Pandoc is not available."""
    pass
