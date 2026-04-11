"""
Annotation Provider Registry.

Central registry for discovering and selecting annotation providers,
using the shared BaseRegistry pattern.
"""

from typing import Optional

from src.archilles.registry import BaseRegistry
from .base import Annotation, AnnotationProvider


class AnnotationProviderRegistry(BaseRegistry[AnnotationProvider]):
    """Registry for annotation source providers."""

    _label = "annotation provider"

    def detect(self, path: str) -> Optional[AnnotationProvider]:
        """Auto-detect which provider can handle a path."""
        for provider in self:
            if provider.can_handle(path):
                return provider
        return None

    def extract_all(self, path: str, source: Optional[str] = None) -> list[Annotation]:
        """Extract annotations using specified or auto-detected provider."""
        if source:
            provider = self.get(source)
            if not provider:
                raise ValueError(
                    f"Unknown annotation provider: '{source}'. "
                    f"Available: {self.list_names()}"
                )
            return provider.extract(path)

        provider = self.detect(path)
        if not provider:
            raise ValueError(f"No provider can handle: {path}")
        return provider.extract(path)

    @property
    def available(self) -> list[str]:
        return self.list_names()
