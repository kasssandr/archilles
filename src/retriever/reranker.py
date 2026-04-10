"""
Cross-encoder reranker for ARCHILLES search results.

Uses BAAI/bge-reranker-v2-m3 (multilingual) to rerank search results
after the initial hybrid search (RRF). The cross-encoder scores each
query-document pair independently, producing more accurate relevance
rankings than bi-encoder similarity alone.

The model is loaded lazily on first use. If loading fails (e.g. OOM),
search falls back gracefully to RRF-only ranking.
"""

import logging

logger = logging.getLogger(__name__)


class CrossEncoderReranker:
    """Cross-encoder reranker using sentence-transformers."""

    DEFAULT_MODEL = "BAAI/bge-reranker-v2-m3"

    def __init__(
        self,
        model_name: str | None = None,
        device: str | None = None,
        max_length: int = 512,
    ):
        """
        Initialize reranker (model loading is deferred to first use).

        Args:
            model_name: Cross-encoder model name (default: bge-reranker-v2-m3)
            device: Device for inference (None = auto-detect, 'cpu', 'cuda')
            max_length: Maximum token length for cross-encoder input
        """
        self._model = None
        self._model_name = model_name or self.DEFAULT_MODEL
        self._device = device
        self._max_length = max_length
        self._load_attempted = False

    def _ensure_loaded(self) -> bool:
        """Lazy-load the cross-encoder model. Returns True if available."""
        if self._model is not None:
            return True
        if self._load_attempted:
            return False

        self._load_attempted = True
        try:
            from sentence_transformers import CrossEncoder

            logger.info(f"Loading cross-encoder: {self._model_name}")
            self._model = CrossEncoder(
                self._model_name,
                max_length=self._max_length,
                **({"device": self._device} if self._device else {}),
            )
            logger.info(f"Cross-encoder loaded successfully on {self._model.device}")
            return True
        except Exception as e:
            logger.warning(
                f"Cross-encoder reranker not available: {e}. "
                "Search will use RRF ranking only."
            )
            return False

    @property
    def is_available(self) -> bool:
        """Whether the cross-encoder model is loaded and ready."""
        return self._model is not None

    def rerank(
        self,
        query: str,
        results: list[dict],
        top_k: int = 10,
    ) -> list[dict]:
        """
        Rerank search results using cross-encoder scoring.

        Args:
            query: Original search query
            results: List of result dicts (must have 'text' key)
            top_k: Number of results to return after reranking

        Returns:
            Reranked list truncated to top_k.
            If model unavailable, returns input unchanged (truncated to top_k).
        """
        if not results:
            return results

        if not self._ensure_loaded():
            logger.debug("Reranker not available, returning RRF-ranked results")
            return results[:top_k]

        # Build query-document pairs
        pairs = [(query, r["text"]) for r in results]

        # Score with cross-encoder
        scores = self._model.predict(pairs)

        # Attach scores and sort
        for result, score in zip(results, scores):
            result["rerank_score"] = float(score)

        reranked = sorted(results, key=lambda x: x["rerank_score"], reverse=True)

        # Re-assign ranks
        for i, result in enumerate(reranked[:top_k]):
            result["rank"] = i + 1

        return reranked[:top_k]
