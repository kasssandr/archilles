"""
Annotation Provider Registry.

Central registry for discovering and selecting annotation providers,
following the same pattern as ParserRegistry/ChunkerRegistry/EmbedderRegistry.
"""

import logging
from typing import Optional

from .base import Annotation, AnnotationProvider

logger = logging.getLogger(__name__)


class AnnotationProviderRegistry:
    """Registry for annotation source providers."""

    def __init__(self):
        self._providers: dict[str, AnnotationProvider] = {}

    def register(self, provider: AnnotationProvider) -> None:
        if provider.name in self._providers:
            raise ValueError(f"Provider '{provider.name}' is already registered")
        self._providers[provider.name] = provider
        logger.debug(f"Registered annotation provider: {provider.name}")

    def get(self, name: str) -> Optional[AnnotationProvider]:
        return self._providers.get(name)

    def detect(self, path: str) -> Optional[AnnotationProvider]:
        """Auto-detect which provider can handle a path."""
        for provider in self._providers.values():
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
                    f"Available: {list(self._providers.keys())}"
                )
            return provider.extract(path)

        provider = self.detect(path)
        if not provider:
            raise ValueError(f"No provider can handle: {path}")
        return provider.extract(path)

    @property
    def available(self) -> list[str]:
        return list(self._providers.keys())
