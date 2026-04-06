"""
Annotation Providers package.

Provides a registry-based architecture for extracting annotations from
multiple reading sources (PDF, Calibre Viewer, Kindle, Kobo, etc.).
"""

from .base import Annotation, AnnotationProvider
from .registry import AnnotationProviderRegistry
from .pdf_provider import PdfAnnotationProvider
from .calibre_provider import CalibreViewerProvider
from .kindle_provider import KindleProvider


def create_default_registry(**kwargs) -> AnnotationProviderRegistry:
    """Create registry with all built-in providers."""
    reg = AnnotationProviderRegistry()
    reg.register(PdfAnnotationProvider())
    reg.register(CalibreViewerProvider(annotations_dir=kwargs.get("annotations_dir")))
    reg.register(KindleProvider())
    return reg


__all__ = [
    "Annotation",
    "AnnotationProvider",
    "AnnotationProviderRegistry",
    "PdfAnnotationProvider",
    "CalibreViewerProvider",
    "KindleProvider",
    "create_default_registry",
]
