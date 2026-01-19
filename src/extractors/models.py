"""Data models for extracted text and metadata."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime


@dataclass
class ChunkMetadata:
    """Metadata for a single text chunk."""

    # Source identification
    book_id: Optional[int] = None
    title: Optional[str] = None
    author: Optional[str] = None
    year: Optional[int] = None

    # Position in document
    page: Optional[int] = None
    page_label: Optional[str] = None  # e.g., "xiv" for roman numerals
    chapter: Optional[str] = None
    section: Optional[str] = None  # Section number, e.g., "19.20", "3.4.2"
    section_title: Optional[str] = None  # Section/chapter title
    section_type: Optional[str] = None  # front_matter, main_content, back_matter
    char_start: Optional[int] = None
    char_end: Optional[int] = None

    # PDF-specific coordinates (for clickable citations)
    pdf_coords: Optional[Dict[str, float]] = None  # {x, y, width, height}

    # Source file
    source_file: Optional[str] = None
    format: Optional[str] = None  # pdf, epub, mobi, etc.

    # Calibre integration
    calibre_uri: Optional[str] = None  # calibre://view/123#page=42

    # Additional metadata
    language: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    custom_fields: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExtractionMetadata:
    """Metadata about the extraction process."""

    # File information
    file_path: Path
    file_size: int
    file_format: str
    detected_format: str  # May differ from extension

    # Extraction details
    extraction_method: str  # native, calibre, pandoc
    extraction_time: float  # seconds
    extracted_at: datetime = field(default_factory=datetime.now)

    # Quality indicators
    success: bool = True
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    # Statistics
    total_pages: Optional[int] = None
    total_chars: int = 0
    total_words: int = 0
    total_chunks: int = 0

    # OCR information (if applicable)
    ocr_applied: bool = False
    ocr_pages: List[int] = field(default_factory=list)
    ocr_confidence: Optional[float] = None


@dataclass
class ExtractedText:
    """Complete extracted text with metadata."""

    # Raw content
    full_text: str

    # Chunked content (for RAG)
    chunks: List[Dict[str, Any]] = field(default_factory=list)
    # Each chunk: {"text": str, "metadata": ChunkMetadata}

    # Extraction metadata
    metadata: ExtractionMetadata = None

    # Table of contents (if available)
    toc: List[Dict[str, Any]] = field(default_factory=list)
    # Each entry: {"title": str, "page": int, "level": int}

    # Footnotes (extracted separately for humanities)
    footnotes: List[Dict[str, Any]] = field(default_factory=list)
    # Each footnote: {"number": str, "text": str, "page": int}

    def __post_init__(self):
        """Auto-calculate statistics if not provided."""
        if self.metadata and self.metadata.total_chars == 0:
            self.metadata.total_chars = len(self.full_text)
            self.metadata.total_words = len(self.full_text.split())
            self.metadata.total_chunks = len(self.chunks)

    def get_chunk_by_page(self, page: int) -> List[Dict[str, Any]]:
        """Get all chunks from a specific page."""
        return [
            chunk for chunk in self.chunks
            if chunk.get('metadata', {}).get('page') == page
        ]

    def get_context_window(self, chunk_index: int, window_size: int = 2) -> str:
        """Get chunk with surrounding context (±window_size chunks)."""
        start = max(0, chunk_index - window_size)
        end = min(len(self.chunks), chunk_index + window_size + 1)

        context_chunks = self.chunks[start:end]
        return "\n\n".join(c['text'] for c in context_chunks)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'full_text': self.full_text,
            'chunks': self.chunks,
            'metadata': self.metadata.__dict__ if self.metadata else None,
            'toc': self.toc,
            'footnotes': self.footnotes,
        }
