# Backwards-compatibility shim — real implementation moved to src/archilles/annotation_providers/
from src.archilles.annotation_providers import (  # noqa: F401
    Annotation,
    AnnotationProvider,
    AnnotationProviderRegistry,
    PdfAnnotationProvider,
    CalibreViewerProvider,
    KindleProvider,
    ZoteroAnnotationProvider,
    create_default_registry,
)
