"""
ARCHILLES Parser Registry

Central registry for discovering and selecting document parsers.

Features:
- Register parsers by name
- Auto-select parser based on file extension
- Quality-based selection when multiple parsers match
"""

from pathlib import Path
from typing import Optional
import logging

from src.archilles.registry import BaseRegistry
from .base import DocumentParser

logger = logging.getLogger(__name__)


class ParserRegistry(BaseRegistry[DocumentParser]):
    """
    Registry for document parsers.

    Maintains a collection of available parsers and provides
    methods to select the best parser for a given file.
    """

    _label = "parser"

    def register(self, parser: DocumentParser) -> None:
        super().register(parser)
        logger.debug(f"Registered parser: {parser.name} v{parser.version}")

    def get_for_file(self, file_path: Path) -> Optional[DocumentParser]:
        """
        Get the best parser for a file.

        Selects based on file extension, preferring higher quality_tier.

        Args:
            file_path: Path to file

        Returns:
            Best matching parser, or None if no parser supports this file
        """
        extension = Path(file_path).suffix.lower()
        candidates = [
            p for p in self
            if p.capabilities.supports_extension(extension)
        ]
        return self._best_by_quality(candidates)

    @staticmethod
    def _best_by_quality(candidates: list[DocumentParser]) -> Optional[DocumentParser]:
        """Return the candidate with the highest quality_tier, or None."""
        if not candidates:
            return None
        return max(candidates, key=lambda p: p.capabilities.quality_tier)
