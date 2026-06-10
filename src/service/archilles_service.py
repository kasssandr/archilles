"""
Central service layer for ARCHILLES.

Wraps archillesRAG and provides a clean interface used by:
- MCP server (src/calibre_mcp/server.py)
- Web UI (scripts/web_ui.py)
- CLI (scripts/rag_demo.py)

Handles lazy initialization, stdout redirection (for MCP safety),
and optional cross-encoder reranking.
"""

import logging
import sys
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Literal

from src.archilles.constants import ChunkType, SectionType
from src.retriever.results import diversify_results, matches_tag_filter  # noqa: F401  (Re-Export — Alt-Abnehmer importieren von hier)

logger = logging.getLogger(__name__)


_redirect_lock = threading.Lock()
_redirect_depth = 0
_redirect_original_stdout: Any = None


# Serialises embedding-/reranker-model construction across ALL service instances.
# transformers/sentence-transformers initialise a model on the 'meta' device and
# then materialise its weights via .to_empty(); running that from several threads
# at once — as the unified server does when it initialises every source in
# parallel — races and raises "Cannot copy out of meta tensor". Holding this lock
# means at most one model is built at a time (loads run sequentially, once each).
_model_init_lock = threading.Lock()


@contextmanager
def _redirect_stdout_to_stderr():
    """Temporarily redirect stdout to stderr (prevents MCP JSON-RPC corruption).

    Thread-safe via refcount: the first concurrent enter captures and replaces
    sys.stdout under a lock; subsequent enters increment the counter without
    touching sys.stdout. The original is restored only when the last holder
    exits. This keeps cross-source fan-out parallelism intact while preventing
    the save/restore race that previously could leave stdout permanently
    pointed at stderr.
    """
    global _redirect_depth, _redirect_original_stdout
    with _redirect_lock:
        if _redirect_depth == 0:
            _redirect_original_stdout = sys.stdout
            sys.stdout = sys.stderr
        _redirect_depth += 1
    try:
        yield
    finally:
        with _redirect_lock:
            _redirect_depth -= 1
            if _redirect_depth == 0:
                sys.stdout = _redirect_original_stdout
                _redirect_original_stdout = None


def _filter_by_rerank_score(results: list[dict], min_similarity: float) -> list[dict]:
    """Filter reranked results by min_similarity (finding 4.1).

    rerank_score is sigmoid-bounded 0-1 (see CrossEncoderReranker), so a
    cosine-style threshold is meaningful there. Results WITHOUT a
    rerank_score (reranker unavailable mid-flight) pass through unfiltered —
    their RRF-scale score (~1/60) must never be compared against a 0-1
    threshold, which would silently empty the list.
    """
    if min_similarity <= 0:
        return results
    return [
        r for r in results
        if r.get("rerank_score") is None or r["rerank_score"] >= min_similarity
    ]


class ArchillesService:
    """Central service facade for ARCHILLES RAG system."""

    def __init__(
        self,
        db_path: str = "./archilles_rag_db",
        model_name: str | None = None,
        profile: str | None = None,
        enable_ocr: bool = False,
        force_ocr: bool = False,
        ocr_backend: str = "auto",
        ocr_language: str = "deu+eng",
        hierarchical: bool = False,
        enable_reranking: bool = False,
        reranker_model: str | None = None,
        reranker_device: str | None = None,
        citation_config: Any | None = None,
        archilles_dir: str | None = None,
        adapter=None,
    ):
        """
        Initialize service (RAG loading is deferred to first use).

        Args:
            db_path: Path to LanceDB storage
            model_name: Sentence transformer model (overrides profile)
            profile: Hardware profile (minimal/balanced/maximal)
            enable_ocr: Enable OCR for scanned PDFs
            force_ocr: Force OCR even for digital PDFs
            ocr_backend: OCR backend (auto, tesseract, lighton, olmocr)
            ocr_language: Language codes for Tesseract
            hierarchical: Enable parent-child chunking
            enable_reranking: Enable cross-encoder reranking
            reranker_model: Cross-encoder model name (default: bge-reranker-v2-m3)
            reranker_device: Device for reranker (None = auto)
            citation_config: CitationConfig instance for bibliography formatting
            archilles_dir: Path to .archilles/ directory (for research_interests.json)
        """
        self._config = {
            "db_path": db_path,
            "model_name": model_name,
            "profile": profile,
            "enable_ocr": enable_ocr,
            "force_ocr": force_ocr,
            "ocr_backend": ocr_backend,
            "ocr_language": ocr_language,
            "hierarchical": hierarchical,
            "adapter": adapter,
        }
        self._rag = None
        self._init_attempted = False
        self._enable_reranking = enable_reranking
        self._reranker = None
        self._reranker_model = reranker_model
        self._reranker_device = reranker_device
        self._citation_config = citation_config
        self._archilles_dir = Path(archilles_dir) if archilles_dir else None
        self._adapter = adapter  # Optional SourceAdapter for metadata lookup

    def _ensure_initialized(self) -> bool:
        """
        Lazy-load the RAG system. Returns True if available.

        Redirects stdout to stderr during initialization to prevent
        print statements from corrupting MCP JSON-RPC communication.
        """
        if self._rag is not None:
            return True
        if self._init_attempted:
            return False

        # Serialise model construction across all sources: the unified server
        # initialises every source in parallel threads, and concurrent
        # meta-device weight materialisation races ("Cannot copy out of meta
        # tensor"). The lock ensures models load one at a time.
        with _model_init_lock:
            # Re-check under the lock — another thread may have advanced state
            # while we were waiting.
            if self._rag is not None:
                return True
            if self._init_attempted:
                return False

            self._init_attempted = True

            try:
                from src.archilles.engine import ArchillesRAG
            except ImportError:
                logger.warning("ArchillesRAG not available (import failed)")
                return False

            try:
                logger.info("Initializing RAG system (lazy loading)...")
                with _redirect_stdout_to_stderr():
                    self._rag = ArchillesRAG(**self._config)
                logger.info(f"RAG system initialized: {self._config['db_path']}")
                return True
            except Exception as e:
                logger.error(f"Failed to initialize RAG system: {e}", exc_info=True)
                self._rag = None
                return False

    def _get_reranker(self):
        """Lazy-load the cross-encoder reranker."""
        if self._reranker is not None:
            return self._reranker
        if not self._enable_reranking:
            return None

        # Same race as the embedding model: serialise reranker construction so
        # parallel sources don't materialise meta tensors concurrently.
        with _model_init_lock:
            if self._reranker is not None:
                return self._reranker
            if not self._enable_reranking:
                return None
            try:
                from src.retriever import CrossEncoderReranker
                self._reranker = CrossEncoderReranker(
                    model_name=self._reranker_model,
                    device=self._reranker_device,
                )
                return self._reranker
            except Exception as e:
                logger.warning(f"Failed to create reranker: {e}")
                self._enable_reranking = False
                return None

    @property
    def is_initialized(self) -> bool:
        """Whether the RAG system is loaded and ready."""
        return self._rag is not None

    # ── Search ──────────────────────────────────────────────────

    def search(
        self,
        query: str,
        mode: Literal["semantic", "keyword", "hybrid"] = "hybrid",
        top_k: int = 10,
        language: str | None = None,
        book_id: str | None = None,
        exact_phrase: bool = False,
        tag_filter: list[str] | None = None,
        section_filter: str = SectionType.MAIN,
        chunk_type_filter: str = ChunkType.CONTENT,
        max_per_book: int = 2,
        min_similarity: float = 0.0,
    ) -> list[dict[str, Any]]:
        """
        Search for relevant passages.

        Delegates to archillesRAG.query() and optionally applies
        cross-encoder reranking before returning results.

        Returns:
            List of result dicts with text, metadata, and scores.
        """
        if not self._ensure_initialized():
            return []

        reranker = self._get_reranker()

        query_kwargs = dict(
            query_text=query,
            mode=mode,
            language=language,
            book_id=book_id,
            exact_phrase=exact_phrase,
            tag_filter=tag_filter,
            section_filter=section_filter,
            chunk_type_filter=chunk_type_filter,
        )

        with _redirect_stdout_to_stderr():
            if reranker is None:
                return self._rag.query(
                    **query_kwargs,
                    top_k=top_k,
                    max_per_book=max_per_book,
                    min_similarity=min_similarity,
                )

            # Fetch more undiversified results for reranking
            raw_results = self._rag.query(
                **query_kwargs,
                top_k=30,
                max_per_book=999,
                min_similarity=0.0,
            )

        reranked = reranker.rerank(query, raw_results, top_k=top_k * 3)
        results = self._diversify(reranked, max_per_book, top_k)

        return _filter_by_rerank_score(results, min_similarity)

    def search_with_citations(
        self,
        query: str,
        top_k: int = 10,
        mode: Literal["hybrid", "semantic", "keyword"] = "hybrid",
        language: str | None = None,
        tags: list[str] | None = None,
        expand_context: bool = False,
        boost_research_interests: bool = True,
        max_per_book: int = 3,
    ) -> dict[str, Any]:
        """
        Search and generate XML-structured prompts with citation support.

        If boost_research_interests is True and archilles_dir was provided at
        init time, applies keyword boosting from research_interests.json before
        ranking results.

        Returns:
            Dictionary with system_prompt, user_prompt, num_sources, results.
        """
        if not self._ensure_initialized():
            return {
                "error": "RAG system not available",
                "help": "Check ~/.archilles/mcp_server.log for details",
            }

        reranker = self._get_reranker()

        with _redirect_stdout_to_stderr():
            if reranker is None:
                results = self._rag.query(
                    query_text=query,
                    top_k=top_k,
                    mode=mode,
                    language=language,
                    tag_filter=tags,
                    max_per_book=max_per_book,
                )
            else:
                # Finding 4.3: the citation path (primary MCP path) used to
                # skip the cross-encoder while search() reranked — same
                # pattern as search(): broad fetch, rerank, then diversify.
                raw_results = self._rag.query(
                    query_text=query,
                    top_k=30,
                    mode=mode,
                    language=language,
                    tag_filter=tags,
                    max_per_book=999,
                )
                reranked = reranker.rerank(query, raw_results, top_k=top_k * 3)
                results = self._diversify(reranked, max_per_book, top_k)

        if boost_research_interests and self._archilles_dir:
            try:
                from src.retriever.research_boost import (
                    apply_research_boost,
                    load_effective_research_interests,
                )
                keywords, boost_factor = load_effective_research_interests(self._archilles_dir)
                if keywords:
                    results = apply_research_boost(results, keywords, boost_factor)
                    logger.debug("Applied research boost (%d keywords)", len(keywords))
            except Exception as e:
                logger.warning("Research boost failed (non-fatal): %s", e)

        if not results:
            return {
                "results": [],
                "message": "No results found",
                "query": query,
            }

        claude_prompt = self._rag.create_claude_prompt(
            results=results,
            query_text=query,
            expand_context=expand_context,
            citation_config=self._citation_config,
        )

        return {
            "query": query,
            "num_results": len(results),
            "search_mode": mode,
            "language_filter": language,
            "system_prompt": claude_prompt["system"],
            "user_prompt": claude_prompt["user"],
            "results": results,
        }

    # ── Index operations ────────────────────────────────────────

    def get_index_status(self) -> dict[str, Any]:
        """Get database statistics (total chunks, books, file types, etc.)."""
        if not self._ensure_initialized():
            return {"total_chunks": 0, "total_books": 0}
        return self._rag.store.get_stats()

    def get_book_list(self) -> list[dict[str, Any]]:
        """Get list of all indexed books with statistics."""
        if not self._ensure_initialized():
            return []
        return self._rag.store.get_indexed_books()

    def get_chunk_by_id(self, chunk_id: str) -> dict[str, Any] | None:
        """Get a single chunk by its ID (used for parent lookup)."""
        if not self._ensure_initialized():
            return None
        return self._rag.store.get_by_id(chunk_id)

    # ── Internal helpers ────────────────────────────────────────

    @staticmethod
    def _diversify(
        results: list[dict[str, Any]],
        max_per_book: int,
        top_k: int,
    ) -> list[dict[str, Any]]:
        return diversify_results(results, max_per_book, top_k)
