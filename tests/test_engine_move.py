"""Architektur- und Regressionstests für den Engine-Umzug (P2 Etappe 1).

Spec: docs/internal/SPEC_2026-06-11_ENGINE_UMZUG.md
Review: docs/internal/CODE_REVIEW_2026-06-10.md (4.9/8.16, 5.14, 5.15, 7.18)
"""
import subprocess  # noqa: F401
import sys  # noqa: F401
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


class TestResultsModule:
    """Die Ergebnis-Utilities leben in einer neutralen Schicht (Zyklus-Bruch)."""

    def test_functions_importable_from_retriever(self):
        from src.retriever.results import diversify_results, matches_tag_filter
        assert callable(diversify_results)
        assert callable(matches_tag_filter)

    def test_service_reexport_is_same_object(self):
        """Alt-Abnehmer importieren weiter aus archilles_service (Re-Export)."""
        from src.retriever import results
        from src.service import archilles_service
        assert archilles_service.diversify_results is results.diversify_results
        assert archilles_service.matches_tag_filter is results.matches_tag_filter
