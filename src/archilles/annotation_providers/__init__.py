"""
Annotation Providers — source-agnostic architecture for extracting
annotations from any reading platform (PDF, Calibre Viewer, Kindle,
Zotero, Kobo, …).
"""

from .base import Annotation, AnnotationProvider
from .registry import AnnotationProviderRegistry
from .pdf_provider import PdfAnnotationProvider
from .calibre_viewer_provider import CalibreViewerProvider
from .kindle_provider import KindleProvider
from .zotero_provider import ZoteroAnnotationProvider


def create_default_registry(**kwargs) -> AnnotationProviderRegistry:
    """Create registry with all built-in providers."""
    reg = AnnotationProviderRegistry()
    reg.register(PdfAnnotationProvider())
    reg.register(CalibreViewerProvider(annotations_dir=kwargs.get("annotations_dir")))
    reg.register(KindleProvider())
    reg.register(ZoteroAnnotationProvider())
    return reg


__all__ = [
    "Annotation",
    "AnnotationProvider",
    "AnnotationProviderRegistry",
    "PdfAnnotationProvider",
    "CalibreViewerProvider",
    "KindleProvider",
    "ZoteroAnnotationProvider",
    "create_default_registry",
]
