"""Research interest boosting for ARCHILLES search results."""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_BOOST_FACTOR = 0.15


def load_research_interests(archilles_dir: str | Path) -> tuple[list[str], float]:
    """Load keywords and boost_factor from .archilles/research_interests.json.

    Returns (keywords, boost_factor). Returns ([], 0.0) if file not found.
    """
    path = Path(archilles_dir) / "research_interests.json"
    if not path.exists():
        return [], 0.0
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        keywords = data.get("keywords", [])
        boost_factor = float(data.get("boost_factor", DEFAULT_BOOST_FACTOR))
        logger.debug("Loaded %d research interest keywords", len(keywords))
        return keywords, boost_factor
    except Exception as e:
        logger.warning("Failed to load research_interests.json: %s", e)
        return [], 0.0


def save_research_interests(
    archilles_dir: str | Path,
    keywords: list[str],
    boost_factor: float = DEFAULT_BOOST_FACTOR,
) -> None:
    """Save keywords and boost_factor to .archilles/research_interests.json."""
    path = Path(archilles_dir) / "research_interests.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {"keywords": keywords, "boost_factor": boost_factor}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Saved %d research interest keywords to %s", len(keywords), path)


def apply_research_boost(
    results: list[dict],
    keywords: list[str],
    boost_factor: float = DEFAULT_BOOST_FACTOR,
) -> list[dict]:
    """Boost results containing research interest keywords.

    For each result, counts how many keywords appear in its text or tags
    and applies an additive boost to the score (capped at 1.0).
    Results are re-sorted by score descending.
    """
    if not keywords or not results:
        return results

    keywords_lower = [kw.lower() for kw in keywords]
    for result in results:
        text_lower = result.get("text", "").lower()
        tags_lower = result.get("tags", "").lower()
        matches = sum(1 for kw in keywords_lower if kw in text_lower or kw in tags_lower)
        if matches > 0:
            result["score"] = min(1.0, result.get("score", 0) + boost_factor * matches)

    return sorted(results, key=lambda x: x.get("score", 0), reverse=True)
