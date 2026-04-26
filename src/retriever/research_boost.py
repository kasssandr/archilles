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


def load_effective_research_interests(
    library_dir: str | Path | None,
    master_dir: str | Path | None = None,
) -> tuple[list[str], float]:
    """Load research interests with master + library-local override.

    Lookup order — a layer with non-empty keywords replaces the previous one:

    1. ``<master_dir>/research_interests.json`` (defaults to
       :func:`src.archilles.config.master_archilles_dir`)
    2. ``<library_dir>/research_interests.json``  (per-source override)

    Layers do not merge: when the user sets a Zotero-specific list, it
    replaces the master list outright, since "boost everything" is rarely
    the intention behind a per-source config.

    Returns ``([], 0.0)`` if no layer has keywords. ``library_dir`` may be
    ``None`` for the master-only case (e.g. an aggregated view with no
    specific source context).
    """
    if master_dir is None:
        try:
            from src.archilles.config import master_archilles_dir
            master_dir = master_archilles_dir()
        except Exception:
            master_dir = None

    keywords: list[str] = []
    boost: float = 0.0

    if master_dir is not None:
        m_kw, m_boost = load_research_interests(master_dir)
        if m_kw:
            keywords, boost = m_kw, m_boost

    if library_dir is not None:
        l_kw, l_boost = load_research_interests(library_dir)
        if l_kw:
            keywords, boost = l_kw, l_boost

    return keywords, boost


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
