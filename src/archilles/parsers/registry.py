"""
ARCHILLES Parser Registry

Central registry for discovering and selecting document parsers.

Features:
- Register parsers by name
- Auto-select parser based on file extension
- Quality-based selection when multiple parsers match
"""

from pathlib import Path
from typing import Dict, List, Optional, Type
import logging

from .base import DocumentParser, DocumentType

logger = logging.getLogger(__name__)


class ParserRegistry:
    """
    Registry for document parsers.

    Maintains a collection of available parsers and provides
    methods to select the best parser for a given file.
    """

    def __init__(self):
        self._parsers: Dict[str, DocumentParser] = {}

    def register(self, parser: DocumentParser) -> None:
        """
        Register a parser instance.

        Args:
            parser: Parser instance to register

        Raises:
            ValueError: If a parser with this name is already registered
        """
        if parser.name in self._parsers:
            raise ValueError(f"Parser '{parser.name}' is already registered")

        self._parsers[parser.name] = parser
        logger.debug(f"Registered parser: {parser.name} v{parser.version}")

    def unregister(self, name: str) -> bool:
        """
        Remove a parser from the registry.

        Args:
            name: Name of parser to remove

        Returns:
            True if parser was removed, False if not found
        """
        if name in self._parsers:
            del self._parsers[name]
            return True
        return False

    def get(self, name: str) -> Optional[DocumentParser]:
        """
        Get a parser by name.

        Args:
            name: Parser name

        Returns:
            Parser instance or None if not found
        """
        return self._parsers.get(name)

    def get_for_file(self, file_path: Path) -> Optional[DocumentParser]:
        """
        Get the best parser for a file.

        Selects based on file extension, preferring higher quality_tier.

        Args:
            file_path: Path to file

        Returns:
            Best matching parser, or None if no parser supports this file
        """
        file_path = Path(file_path)
        extension = file_path.suffix.lower()

        candidates: List[DocumentParser] = []
        for parser in self._parsers.values():
            if parser.capabilities.supports_extension(extension):
                candidates.append(parser)

        if not candidates:
            return None

        # Sort by quality tier (descending) and return best
        candidates.sort(key=lambda p: p.capabilities.quality_tier, reverse=True)
        return candidates[0]

    def get_for_type(self, doc_type: DocumentType) -> Optional[DocumentParser]:
        """
        Get the best parser for a document type.

        Args:
            doc_type: Document type to parse

        Returns:
            Best matching parser, or None if no parser supports this type
        """
        candidates: List[DocumentParser] = []
        for parser in self._parsers.values():
            if parser.capabilities.supports_type(doc_type):
                candidates.append(parser)

        if not candidates:
            return None

        candidates.sort(key=lambda p: p.capabilities.quality_tier, reverse=True)
        return candidates[0]

    def list_parsers(self) -> List[str]:
        """Get list of registered parser names."""
        return list(self._parsers.keys())

    def list_supported_extensions(self) -> List[str]:
        """Get list of all supported file extensions."""
        extensions = set()
        for parser in self._parsers.values():
            extensions.update(parser.capabilities.supported_extensions)
        return sorted(extensions)

    def print_info(self) -> None:
        """Print information about registered parsers."""
        print()
        print("=" * 64)
        print("  REGISTERED PARSERS")
        print("=" * 64)

        if not self._parsers:
            print("  No parsers registered.")
        else:
            for name, parser in sorted(self._parsers.items()):
                caps = parser.capabilities
                exts = ", ".join(sorted(caps.supported_extensions))
                print(f"\n  [{name}] v{parser.version}")
                print(f"    Extensions: {exts}")
                print(f"    Quality tier: {caps.quality_tier}")
                features = []
                if caps.extracts_images:
                    features.append("images")
                if caps.extracts_tables:
                    features.append("tables")
                if caps.extracts_metadata:
                    features.append("metadata")
                if caps.supports_ocr:
                    features.append("OCR")
                if features:
                    print(f"    Features: {', '.join(features)}")

        print()
        print("=" * 64)
        print()


# Global registry instance
_global_registry = ParserRegistry()


def get_registry() -> ParserRegistry:
    """Get the global parser registry."""
    return _global_registry


def register_parser(parser: DocumentParser) -> None:
    """
    Register a parser in the global registry.

    Args:
        parser: Parser instance to register
    """
    _global_registry.register(parser)


def get_parser(name_or_path) -> Optional[DocumentParser]:
    """
    Get a parser by name or for a file path.

    Args:
        name_or_path: Parser name (str) or file path (str/Path)

    Returns:
        Parser instance or None if not found
    """
    if isinstance(name_or_path, Path):
        return _global_registry.get_for_file(name_or_path)
    elif isinstance(name_or_path, str):
        # Check if it's a file path or a parser name
        if '/' in name_or_path or '\\' in name_or_path or '.' in name_or_path:
            return _global_registry.get_for_file(Path(name_or_path))
        else:
            return _global_registry.get(name_or_path)
    return None


def list_parsers() -> List[str]:
    """Get list of registered parser names."""
    return _global_registry.list_parsers()


# Quick test
if __name__ == "__main__":
    from .base import ParserCapabilities, ParsedDocument

    # Create a mock parser for testing
    class MockPDFParser(DocumentParser):
        @property
        def name(self) -> str:
            return "mock-pdf"

        @property
        def version(self) -> str:
            return "1.0.0"

        @property
        def capabilities(self) -> ParserCapabilities:
            return ParserCapabilities(
                supported_extensions={'.pdf'},
                supported_types={DocumentType.PDF},
                quality_tier=1
            )

        def parse(self, file_path: Path) -> ParsedDocument:
            return ParsedDocument(
                file_path=str(file_path),
                file_name=file_path.name,
                file_size_bytes=0,
                full_text="Mock content"
            )

    # Test registry
    registry = ParserRegistry()
    registry.register(MockPDFParser())
    registry.print_info()

    # Test lookup
    parser = registry.get_for_file(Path("test.pdf"))
    print(f"Parser for test.pdf: {parser}")
