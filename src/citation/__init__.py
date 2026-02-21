"""Citation configuration and formatting for ARCHILLES.

This module provides:
- CitationConfig: user preferences for citation style and locale
- CITATION_STYLES: registry of supported styles with prompt fragments
- format_bibliography_instruction(): generates the instruction block
  that is injected into the RAG system prompt so that Claude renders
  the bibliography in the requested style.

Future extension points:
- CSL processing via citeproc-py (optional dependency)
- Zotero API integration (export/import)
"""

from .config import CitationConfig, CITATION_STYLES, format_bibliography_instruction

__all__ = [
    "CitationConfig",
    "CITATION_STYLES",
    "format_bibliography_instruction",
]
