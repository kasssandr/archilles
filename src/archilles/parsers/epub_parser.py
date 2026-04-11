"""
ARCHILLES EPUB Parser — Adapter around EPUBExtractor.

Delegates all extraction to the battle-tested EPUBExtractor (src/extractors/)
and converts its ExtractedText output to the ParsedDocument format expected
by the ModularPipeline.
"""

import time
from pathlib import Path
import logging

try:
    import ebooklib  # noqa: F401 — only needed to report availability
    EBOOKLIB_AVAILABLE = True
except ImportError:
    EBOOKLIB_AVAILABLE = False

from .base import (
    DocumentParser,
    DocumentType,
    ParserCapabilities,
    ParsedDocument,
    ParsedChunk,
)

logger = logging.getLogger(__name__)


class EPUBParser(DocumentParser):
    """
    EPUB parser that delegates to EPUBExtractor.

    Provides the DocumentParser interface for the ModularPipeline while
    reusing all extraction logic (TOC-based section splitting, anchor-based
    splitting, section-type classification) from EPUBExtractor.
    """

    @property
    def name(self) -> str:
        return "epub"

    @property
    def version(self) -> str:
        return "1.0.0"

    @property
    def capabilities(self) -> ParserCapabilities:
        return ParserCapabilities(
            supported_extensions={'.epub'},
            supported_types={DocumentType.EPUB},
            extracts_images=False,
            extracts_tables=False,
            extracts_metadata=True,
            preserves_formatting=False,
            supports_ocr=False,
            memory_efficient=True,
            parallel_safe=True,
            quality_tier=2,
        )

    def parse(self, file_path: Path) -> ParsedDocument:
        """Parse an EPUB via EPUBExtractor and convert to ParsedDocument."""
        file_path = Path(file_path)
        start_time = time.time()

        from src.extractors.epub_extractor import EPUBExtractor

        extractor = EPUBExtractor()
        extracted = extractor.extract(file_path)

        # Convert ExtractedText chunks → ParsedChunks (chapter-level)
        chunks = []
        for i, chunk_dict in enumerate(extracted.chunks):
            meta = chunk_dict.get('metadata', {})
            chunks.append(ParsedChunk(
                text=chunk_dict.get('text', ''),
                source_file=str(file_path),
                page_number=meta.get('page'),
                chunk_index=i,
                section_title=meta.get('section_title'),
                chapter=meta.get('chapter'),
                metadata=meta,
            ))

        duration = time.time() - start_time
        ext_meta = extracted.metadata

        # Try to extract title/author from metadata warnings or chunk metadata
        title = None
        authors = []
        language = None
        if chunks:
            first_meta = chunks[0].metadata
            title = first_meta.get('title')
            author = first_meta.get('author')
            if author:
                authors = [author]
            language = first_meta.get('language')

        return ParsedDocument(
            file_path=str(file_path),
            file_name=file_path.name,
            file_size_bytes=file_path.stat().st_size,
            full_text=extracted.full_text,
            chunks=chunks,
            title=title,
            authors=authors,
            language=language,
            page_count=len(chunks),  # chapters as proxy
            parser_name=self.name,
            parser_version=self.version,
            parse_duration_seconds=duration,
            metadata={
                'toc': extracted.toc or [],
                'extraction_method': ext_meta.extraction_method if ext_meta else 'unknown',
            },
            warnings=[w for w in (ext_meta.warnings if ext_meta else [])],
        )
