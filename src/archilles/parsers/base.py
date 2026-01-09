"""
ARCHILLES Parser Base Classes

Abstract base class and data structures for document parsing.

Design Philosophy:
- Parsers are stateless - all configuration via constructor
- Each parser declares its capabilities upfront
- ParsedDocument is a complete, self-contained result
- Chunks can be created by the parser or by a separate chunker
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Dict, Any, Optional, Set
from enum import Enum, auto


class DocumentType(Enum):
    """Supported document types."""
    PDF = auto()
    EPUB = auto()
    MOBI = auto()
    TXT = auto()
    HTML = auto()
    MARKDOWN = auto()
    DOCX = auto()
    RTF = auto()


@dataclass
class ParserCapabilities:
    """
    Declares what a parser can handle.

    Used by the registry to select appropriate parsers
    and by callers to understand parser limitations.
    """

    # Supported file extensions (e.g., {'.pdf', '.PDF'})
    supported_extensions: Set[str]

    # Supported document types
    supported_types: Set[DocumentType]

    # Feature flags
    extracts_images: bool = False
    extracts_tables: bool = False
    extracts_metadata: bool = True
    preserves_formatting: bool = False
    supports_ocr: bool = False

    # Performance characteristics
    memory_efficient: bool = True  # Can handle large files without loading fully into memory
    parallel_safe: bool = True     # Safe to use from multiple threads/processes

    # Quality tier (for parser selection when multiple options exist)
    # Higher = better quality, potentially slower
    quality_tier: int = 1

    def supports_extension(self, ext: str) -> bool:
        """Check if this parser supports a file extension."""
        return ext.lower() in {e.lower() for e in self.supported_extensions}

    def supports_type(self, doc_type: DocumentType) -> bool:
        """Check if this parser supports a document type."""
        return doc_type in self.supported_types


@dataclass
class ParsedChunk:
    """
    A chunk of parsed content.

    This represents a logical unit of text that can be embedded.
    Chunks may be created by the parser itself or by a separate chunker.
    """

    # The actual text content
    text: str

    # Source information
    source_file: str = ""
    page_number: Optional[int] = None  # 1-indexed, None if not applicable
    chunk_index: int = 0               # Index within the document

    # Structural information
    section_title: Optional[str] = None
    chapter: Optional[str] = None

    # Character offsets in original document (if available)
    start_char: Optional[int] = None
    end_char: Optional[int] = None

    # Token count (if pre-computed)
    token_count: Optional[int] = None

    # Additional metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def char_count(self) -> int:
        """Get character count of this chunk."""
        return len(self.text)

    def __repr__(self) -> str:
        preview = self.text[:50] + "..." if len(self.text) > 50 else self.text
        return f"ParsedChunk(page={self.page_number}, chars={self.char_count}, text='{preview}')"


@dataclass
class ParsedDocument:
    """
    Complete result of parsing a document.

    Contains the full text, optional pre-chunked content,
    and all extracted metadata.
    """

    # Source file information
    file_path: str
    file_name: str
    file_size_bytes: int

    # Document content
    full_text: str                           # Complete extracted text
    chunks: List[ParsedChunk] = field(default_factory=list)  # Optional pre-chunked content

    # Document metadata
    title: Optional[str] = None
    authors: List[str] = field(default_factory=list)
    language: Optional[str] = None
    page_count: Optional[int] = None

    # Extraction metadata
    parser_name: str = ""
    parser_version: str = ""
    parse_duration_seconds: float = 0.0

    # Additional metadata from the document
    metadata: Dict[str, Any] = field(default_factory=dict)

    # Warnings/issues encountered during parsing
    warnings: List[str] = field(default_factory=list)

    @property
    def char_count(self) -> int:
        """Get total character count."""
        return len(self.full_text)

    @property
    def has_chunks(self) -> bool:
        """Check if document has pre-chunked content."""
        return len(self.chunks) > 0

    @property
    def chunk_count(self) -> int:
        """Get number of chunks."""
        return len(self.chunks)

    def get_text_by_page(self, page_number: int) -> str:
        """
        Get text for a specific page.

        Args:
            page_number: 1-indexed page number

        Returns:
            Text from that page, or empty string if not available
        """
        if not self.has_chunks:
            return ""

        page_chunks = [c for c in self.chunks if c.page_number == page_number]
        return "\n".join(c.text for c in page_chunks)

    def __repr__(self) -> str:
        return (
            f"ParsedDocument(file='{self.file_name}', "
            f"pages={self.page_count}, chars={self.char_count}, "
            f"chunks={self.chunk_count})"
        )


class DocumentParser(ABC):
    """
    Abstract base class for document parsers.

    Implementations should:
    1. Declare capabilities in the capabilities property
    2. Implement parse() to extract text and metadata
    3. Be stateless (configuration via __init__)
    4. Handle errors gracefully with informative messages

    Example implementation:
        class MyPDFParser(DocumentParser):
            @property
            def name(self) -> str:
                return "my-pdf-parser"

            @property
            def version(self) -> str:
                return "1.0.0"

            @property
            def capabilities(self) -> ParserCapabilities:
                return ParserCapabilities(
                    supported_extensions={'.pdf'},
                    supported_types={DocumentType.PDF},
                    extracts_metadata=True,
                )

            def parse(self, file_path: Path) -> ParsedDocument:
                # Implementation here
                pass
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """
        Unique identifier for this parser.

        Used in registry lookups and logging.
        Should be lowercase with hyphens (e.g., "pymupdf", "pdfplumber").
        """
        pass

    @property
    @abstractmethod
    def version(self) -> str:
        """
        Version string for this parser.

        Should follow semver (e.g., "1.0.0").
        Include underlying library version if relevant.
        """
        pass

    @property
    @abstractmethod
    def capabilities(self) -> ParserCapabilities:
        """
        Declare what this parser can handle.

        Returns:
            ParserCapabilities describing supported formats and features
        """
        pass

    @abstractmethod
    def parse(self, file_path: Path) -> ParsedDocument:
        """
        Parse a document and extract its content.

        Args:
            file_path: Path to the document file

        Returns:
            ParsedDocument with extracted text and metadata

        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If file type is not supported
            RuntimeError: If parsing fails
        """
        pass

    def can_parse(self, file_path: Path) -> bool:
        """
        Check if this parser can handle a file.

        Args:
            file_path: Path to check

        Returns:
            True if this parser supports the file type
        """
        return self.capabilities.supports_extension(file_path.suffix)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name='{self.name}', version='{self.version}')"


# Quick test
if __name__ == "__main__":
    # Test data structures
    chunk = ParsedChunk(
        text="This is a test chunk with some content.",
        source_file="test.pdf",
        page_number=1,
        chunk_index=0
    )
    print(f"Chunk: {chunk}")

    doc = ParsedDocument(
        file_path="/path/to/test.pdf",
        file_name="test.pdf",
        file_size_bytes=1024,
        full_text="Full document text here...",
        chunks=[chunk],
        title="Test Document",
        authors=["Author One"],
        page_count=10,
        parser_name="test-parser",
        parser_version="1.0.0"
    )
    print(f"Document: {doc}")

    caps = ParserCapabilities(
        supported_extensions={'.pdf', '.PDF'},
        supported_types={DocumentType.PDF},
        extracts_metadata=True
    )
    print(f"Supports .pdf: {caps.supports_extension('.pdf')}")
    print(f"Supports .epub: {caps.supports_extension('.epub')}")
