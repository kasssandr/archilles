"""
ARCHILLES Modular Pipeline

Integrates the parser → chunker → embedder pipeline into a unified
indexing system that can be used with the existing RAG infrastructure.

This module provides:
- ModularPipeline: Configurable pipeline for document processing
- Factory functions for profile-based setup
- Integration with LanceDB storage
"""

import re
import time
import logging
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Optional, Iterator

from .profiles import IndexingProfile, get_profile
from .parsers.base import DocumentParser
from .parsers.registry import ParserRegistry
from .chunkers.base import TextChunker, TextChunk, ChunkerConfig
from .embedders.base import TextEmbedder

logger = logging.getLogger(__name__)


@dataclass
class ProcessedDocument:
    """
    Result of processing a document through the full pipeline.

    Contains chunks with embeddings ready for storage.
    """

    # Source information
    file_path: str
    file_name: str

    # Processing results
    chunks: List[TextChunk]
    embeddings: List[List[float]]  # One embedding per chunk

    # Metadata from parsing
    title: Optional[str] = None
    authors: List[str] = field(default_factory=list)
    page_count: Optional[int] = None

    # Timing information
    parse_time: float = 0.0
    chunk_time: float = 0.0
    embed_time: float = 0.0

    @property
    def total_time(self) -> float:
        return self.parse_time + self.chunk_time + self.embed_time

    @property
    def chunk_count(self) -> int:
        return len(self.chunks)

    def __repr__(self) -> str:
        return (
            f"ProcessedDocument(file='{self.file_name}', "
            f"chunks={self.chunk_count}, time={self.total_time:.2f}s)"
        )


class ModularPipeline:
    """
    Modular document processing pipeline.

    Combines parser, chunker, and embedder into a unified workflow.
    Each component can be swapped independently.

    Usage:
        # Create from profile
        pipeline = ModularPipeline.from_profile('minimal')

        # Or configure manually
        pipeline = ModularPipeline(
            parser=PyMuPDFParser(),
            chunker=SemanticChunker(config),
            embedder=BGEEmbedder('bge-small')
        )

        # Process a document
        result = pipeline.process('/path/to/book.pdf')

        # Access results
        for chunk, embedding in zip(result.chunks, result.embeddings):
            print(f"Chunk: {chunk.text[:50]}...")
            print(f"Embedding dim: {len(embedding)}")
    """

    def __init__(
        self,
        parser: Optional[DocumentParser] = None,
        chunker: Optional[TextChunker] = None,
        embedder: Optional[TextEmbedder] = None,
        profile: Optional[IndexingProfile] = None
    ):
        """
        Initialize the pipeline.

        Args:
            parser: Document parser (auto-selected if None)
            chunker: Text chunker (default semantic if None)
            embedder: Text embedder (required or from profile)
            profile: IndexingProfile for configuration
        """
        self.profile = profile
        self._parser = parser
        self._chunker = chunker
        self._embedder = embedder

        # Parser registry for auto-selection
        self._parser_registry = ParserRegistry()

        # Track if embedder is loaded
        self._embedder_loaded = False

        # Lazily initialised alternative chunkers
        self._dialogue_chunker: Optional[TextChunker] = None

    @classmethod
    def from_profile(cls, profile_name: str) -> 'ModularPipeline':
        """
        Create a pipeline configured for a hardware profile.

        Args:
            profile_name: 'minimal', 'balanced', or 'maximal'

        Returns:
            Configured ModularPipeline instance
        """
        profile = get_profile(profile_name)
        return cls._create_from_profile(profile)

    @classmethod
    def _create_from_profile(cls, profile: IndexingProfile) -> 'ModularPipeline':
        """Create pipeline from IndexingProfile object."""
        # Import implementations
        from .chunkers.semantic import SemanticChunker
        from .chunkers.base import ChunkerConfig

        # Create chunker with profile settings
        chunker_config = ChunkerConfig(
            chunk_size=profile.chunk_size,
            chunk_overlap=profile.chunk_overlap,
            respect_sentences=True,
            respect_paragraphs=True
        )
        chunker = SemanticChunker(chunker_config)

        # Embedder will be created lazily to avoid loading model until needed
        return cls(
            parser=None,  # Auto-select based on file type
            chunker=chunker,
            embedder=None,  # Created lazily
            profile=profile
        )

    def _get_parser_for_file(self, file_path: Path) -> DocumentParser:
        """Get appropriate parser for a file type."""
        if self._parser:
            return self._parser

        # Try registry first
        parser = self._parser_registry.get_for_file(file_path)
        if parser:
            return parser

        # Try to discover and register parsers on demand
        self._try_register_parsers()

        # Retry after registration
        parser = self._parser_registry.get_for_file(file_path)
        if parser:
            return parser

        raise ValueError(f"No parser available for {file_path.suffix}")

    def _try_register_parsers(self) -> None:
        """Attempt to register all known parsers that are not yet registered."""
        parser_factories = [
            ('pymupdf', self._try_create_pymupdf_parser),
            ('epub', self._try_create_epub_parser),
        ]
        for name, factory in parser_factories:
            if self._parser_registry.get(name):
                continue
            parser = factory()
            if parser:
                try:
                    self._parser_registry.register(parser)
                except ValueError:
                    pass  # Already registered by another path

    @staticmethod
    def _try_create_pymupdf_parser() -> Optional[DocumentParser]:
        try:
            from .parsers.pymupdf_parser import PyMuPDFParser, PYMUPDF_AVAILABLE
            if PYMUPDF_AVAILABLE:
                return PyMuPDFParser()
        except ImportError:
            pass
        return None

    @staticmethod
    def _try_create_epub_parser() -> Optional[DocumentParser]:
        try:
            from .parsers.epub_parser import EPUBParser
            return EPUBParser()
        except ImportError:
            pass
        return None

    def _get_embedder(self) -> TextEmbedder:
        """Get or create embedder (lazy loading)."""
        if self._embedder_loaded:
            return self._embedder

        if not self._embedder:
            self._embedder = self._create_embedder_from_profile()

        self._embedder.load_model()
        self._embedder_loaded = True
        return self._embedder

    def _create_embedder_from_profile(self) -> TextEmbedder:
        """Create an embedder instance from the current profile."""
        if not self.profile:
            raise ValueError("No embedder configured and no profile provided")

        from .embedders.bge import BGEEmbedder, SENTENCE_TRANSFORMERS_AVAILABLE

        if not SENTENCE_TRANSFORMERS_AVAILABLE:
            raise ImportError(
                "sentence-transformers required for embedding. "
                "Install with: pip install sentence-transformers"
            )

        model_map = {
            'BAAI/bge-small-en-v1.5': 'bge-small',
            'BAAI/bge-base-en-v1.5': 'bge-base',
            'BAAI/bge-m3': 'bge-m3',
        }
        model_name = model_map.get(self.profile.embedding_model, 'bge-small')

        return BGEEmbedder(
            model_name=model_name,
            device=self.profile.embedding_device,
            batch_size=self.profile.batch_size
        )

    # ── Chunker selection ────────────────────────────────────────

    def _read_frontmatter_field(self, file_path: Path, field_name: str) -> str:
        """Return a scalar YAML frontmatter field from a Markdown file, or ''."""
        try:
            text = file_path.read_text(encoding='utf-8', errors='replace')
            if not text.startswith('---'):
                return ''
            end = text.find('\n---', 3)
            if end == -1:
                return ''
            yaml_block = text[3:end]
            m = re.search(
                r'^' + re.escape(field_name) + r':\s*([^\n]+)',
                yaml_block,
                re.MULTILINE,
            )
            return m.group(1).strip().strip('"\'') if m else ''
        except Exception:
            return ''

    def _select_chunker(self, file_path: Path) -> TextChunker:
        """Return the appropriate chunker for *file_path*.

        Checks ``chunking_strategy`` in the YAML frontmatter for Markdown files.
        Falls back to the default chunker for all other formats and strategies.
        """
        if file_path.suffix.lower() in {'.md', '.markdown'}:
            strategy = self._read_frontmatter_field(file_path, 'chunking_strategy')
            if strategy == 'dialogue':
                return self._get_dialogue_chunker()
        return self._get_default_chunker()

    def _get_default_chunker(self) -> TextChunker:
        if self._chunker is not None:
            return self._chunker
        from .chunkers.semantic import SemanticChunker
        self._chunker = SemanticChunker()
        return self._chunker

    def _get_dialogue_chunker(self) -> TextChunker:
        if self._dialogue_chunker is None:
            from .chunkers.dialogue import DialogueChunker
            self._dialogue_chunker = DialogueChunker()
        return self._dialogue_chunker

    # ── Main processing ─────────────────────────────────────────

    def process(self, file_path: str | Path) -> ProcessedDocument:
        """
        Process a document through the full pipeline.

        Args:
            file_path: Path to document file

        Returns:
            ProcessedDocument with chunks and embeddings
        """
        file_path = Path(file_path)
        logger.info(f"Processing: {file_path}")

        # Step 1: Parse
        start = time.time()
        parser = self._get_parser_for_file(file_path)
        parsed = parser.parse(file_path)
        parse_time = time.time() - start
        logger.info(f"Parsed in {parse_time:.2f}s: {parsed.page_count} pages")

        # Step 2: Chunk — select chunker based on file type / frontmatter
        chunker = self._select_chunker(file_path)
        start = time.time()
        if parsed.has_chunks:
            # Parser already chunked by page, re-chunk with our chunker
            page_texts = [c.text for c in parsed.chunks]
            chunks = chunker.chunk_with_pages(page_texts, str(file_path))
        else:
            chunks = chunker.chunk(parsed.full_text, str(file_path))

        # DialogueChunker returns [] when no turn markers are found → fall back
        if not chunks and chunker is not self._get_default_chunker():
            logger.info("Dialogue chunker found no turns, falling back to default chunker")
            default = self._get_default_chunker()
            if parsed.has_chunks:
                chunks = default.chunk_with_pages(page_texts, str(file_path))
            else:
                chunks = default.chunk(parsed.full_text, str(file_path))

        chunk_time = time.time() - start
        logger.info(f"Chunked in {chunk_time:.2f}s: {len(chunks)} chunks")

        # Step 3: Embed
        start = time.time()
        embedder = self._get_embedder()
        texts = [chunk.text for chunk in chunks]

        if texts:
            result = embedder.embed_batch(texts)
            embeddings = result.embeddings.tolist()
        else:
            embeddings = []

        embed_time = time.time() - start
        logger.info(f"Embedded in {embed_time:.2f}s: {len(embeddings)} vectors")

        return ProcessedDocument(
            file_path=str(file_path),
            file_name=file_path.name,
            chunks=chunks,
            embeddings=embeddings,
            title=parsed.title,
            authors=parsed.authors,
            page_count=parsed.page_count,
            parse_time=parse_time,
            chunk_time=chunk_time,
            embed_time=embed_time
        )

    def process_batch(
        self,
        file_paths: List[str | Path],
        progress_callback: Optional[callable] = None
    ) -> Iterator[ProcessedDocument]:
        """
        Process multiple documents.

        Args:
            file_paths: List of document paths
            progress_callback: Optional callback(current, total, doc)

        Yields:
            ProcessedDocument for each file
        """
        total = len(file_paths)
        for i, file_path in enumerate(file_paths):
            try:
                result = self.process(file_path)
                if progress_callback:
                    progress_callback(i + 1, total, result)
                yield result
            except Exception as e:
                logger.error(f"Failed to process {file_path}: {e}")
                if progress_callback:
                    progress_callback(i + 1, total, None)

    def unload(self) -> None:
        """Unload models to free memory."""
        if self._embedder and self._embedder_loaded:
            self._embedder.unload_model()
            self._embedder_loaded = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.unload()
        return False


# Quick test
if __name__ == "__main__":
    import sys

    # Check for test file argument
    if len(sys.argv) < 2:
        print("Usage: python -m src.archilles.pipeline <file.pdf> [profile]")
        print("Profiles: minimal, balanced, maximal")
        sys.exit(1)

    file_path = sys.argv[1]
    profile = sys.argv[2] if len(sys.argv) > 2 else 'minimal'

    print(f"Processing {file_path} with {profile} profile...")

    try:
        result = process_document(file_path, profile)
        print(f"\nResult: {result}")
        print(f"  Chunks: {result.chunk_count}")
        print(f"  Parse time: {result.parse_time:.2f}s")
        print(f"  Chunk time: {result.chunk_time:.2f}s")
        print(f"  Embed time: {result.embed_time:.2f}s")
        print(f"  Total time: {result.total_time:.2f}s")

        if result.chunks:
            print(f"\nFirst chunk preview:")
            print(f"  {result.chunks[0].text[:100]}...")
            print(f"  Embedding dim: {len(result.embeddings[0])}")

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
