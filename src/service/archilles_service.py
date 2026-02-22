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
from contextlib import contextmanager
from typing import Any, Dict, List, Literal, Optional

logger = logging.getLogger(__name__)


@contextmanager
def _redirect_stdout_to_stderr():
    """Temporarily redirect stdout to stderr (prevents MCP JSON-RPC corruption)."""
    old_stdout = sys.stdout
    sys.stdout = sys.stderr
    try:
        yield
    finally:
        sys.stdout = old_stdout


class ArchillesService:
    """Central service facade for ARCHILLES RAG system."""

    def __init__(
        self,
        db_path: str = "./archilles_rag_db",
        model_name: Optional[str] = None,
        profile: Optional[str] = None,
        enable_ocr: bool = False,
        force_ocr: bool = False,
        ocr_backend: str = "auto",
        ocr_language: str = "deu+eng",
        hierarchical: bool = False,
        enable_reranking: bool = False,
        reranker_model: Optional[str] = None,
        reranker_device: Optional[str] = None,
        citation_config: Optional[Any] = None,
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
        }
        self._rag = None
        self._init_attempted = False
        self._enable_reranking = enable_reranking
        self._reranker = None
        self._reranker_model = reranker_model
        self._reranker_device = reranker_device
        self._citation_config = citation_config

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

        self._init_attempted = True

        try:
            from scripts.rag_demo import archillesRAG
        except ImportError:
            logger.warning("archillesRAG not available (import failed)")
            return False

        try:
            logger.info("Initializing RAG system (lazy loading)...")
            with _redirect_stdout_to_stderr():
                self._rag = archillesRAG(**self._config)
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
        language: Optional[str] = None,
        book_id: Optional[str] = None,
        exact_phrase: bool = False,
        tag_filter: Optional[List[str]] = None,
        section_filter: str = "main",
        chunk_type_filter: str = "content",
        max_per_book: int = 2,
        min_similarity: float = 0.0,
    ) -> List[Dict[str, Any]]:
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

        if min_similarity > 0:
            results = [
                r for r in results
                if r.get("rerank_score", r.get("score", 0)) >= min_similarity
            ]
        return results

    def search_with_citations(
        self,
        query: str,
        top_k: int = 5,
        mode: str = "hybrid",
        language: Optional[str] = None,
        tags: Optional[List[str]] = None,
        expand_context: bool = False,
    ) -> Dict[str, Any]:
        """
        Search and generate XML-structured prompts with citation support.

        Returns:
            Dictionary with system_prompt, user_prompt, num_sources, results.
        """
        if not self._ensure_initialized():
            return {
                "error": "RAG system not available",
                "help": "Check ~/.archilles/mcp_server.log for details",
            }

        with _redirect_stdout_to_stderr():
            results = self._rag.query(
                query_text=query,
                top_k=top_k,
                mode=mode,
                language=language,
                tag_filter=tags,
            )

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

    def get_index_status(self) -> Dict[str, Any]:
        """Get database statistics (total chunks, books, file types, etc.)."""
        if not self._ensure_initialized():
            return {"total_chunks": 0, "total_books": 0}
        return self._rag.store.get_stats()

    def get_book_list(self) -> List[Dict[str, Any]]:
        """Get list of all indexed books with statistics."""
        if not self._ensure_initialized():
            return []
        return self._rag.store.get_indexed_books()

    def get_chunk_by_id(self, chunk_id: str) -> Optional[Dict[str, Any]]:
        """Get a single chunk by its ID (used for parent lookup)."""
        if not self._ensure_initialized():
            return None
        return self._rag.store.get_by_id(chunk_id)

    # ── Internal helpers ────────────────────────────────────────

    @staticmethod
    def _diversify(
        results: List[Dict[str, Any]],
        max_per_book: int,
        top_k: int,
    ) -> List[Dict[str, Any]]:
        """Apply per-book diversification to reranked results."""
        diversified = []
        book_counts: Dict[str, int] = {}

        for r in results:
            metadata = r.get("metadata", {})
            bid = metadata.get("book_id", r.get("book_id", "unknown"))
            count = book_counts.get(bid, 0)
            if count < max_per_book:
                diversified.append(r)
                book_counts[bid] = count + 1
            if len(diversified) >= top_k:
                break

        # Re-assign ranks
        for i, r in enumerate(diversified):
            r["rank"] = i + 1

        return diversified
