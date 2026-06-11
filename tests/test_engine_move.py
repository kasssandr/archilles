"""Architektur- und Regressionstests für den Engine-Umzug (P2 Etappe 1).

Spec: docs/internal/SPEC_2026-06-11_ENGINE_UMZUG.md
Review: docs/internal/CODE_REVIEW_2026-06-10.md (4.9/8.16, 5.14, 5.15, 7.18)
"""
import subprocess  # noqa: F401
import sys  # noqa: F401
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


class TestCanonicalImportRoot:
    """5.14: Entry-Point nutzt ausschließlich die kanonische src.*-Wurzel."""

    def test_mcp_server_entry_has_no_bare_imports(self):
        source = (REPO_ROOT / "mcp_server.py").read_text(encoding="utf-8")
        assert "from calibre_mcp" not in source
        assert "from citation.config" not in source
        assert 'parent / "src"' not in source  # sys.path-Insert der src-Wurzel entfernt

    def test_unified_server_has_no_bare_import_fallback(self):
        source = (REPO_ROOT / "src" / "calibre_mcp" / "unified_server.py").read_text(encoding="utf-8")
        assert "from citation.config" not in source


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


class TestEngineMove:
    """4.9: Die Engine lebt in src/ und ist ohne scripts/ nutzbar."""

    def test_engine_import_does_not_load_scripts(self):
        """Subprocess für saubere sys.modules — Kern-Architekturziel."""
        code = (
            "import sys; "
            "import src.archilles.engine; "
            "bad = [m for m in sys.modules if m.startswith('scripts')]; "
            "assert not bad, 'engine zieht scripts-Module: %s' % bad; "
            "from src.archilles.engine import ArchillesRAG, LanceDBError; "
            "print(ArchillesRAG.__name__)"
        )
        proc = subprocess.run(
            [sys.executable, "-c", code],
            capture_output=True, text=True, cwd=str(REPO_ROOT), timeout=300,
        )
        assert proc.returncode == 0, proc.stderr
        assert "ArchillesRAG" in proc.stdout

    def test_legacy_shim_same_class(self):
        """Kompat-Shim: Alt-Import liefert dieselben Objekte."""
        from scripts.rag_demo import LanceDBError as ShimError
        from scripts.rag_demo import archillesRAG
        from src.archilles.engine import ArchillesRAG, LanceDBError
        assert archillesRAG is ArchillesRAG
        assert ShimError is LanceDBError


class TestPublicPromptPath:
    """5.15: Kein Durchgriff auf service._rag mehr aus dem Unified-Server."""

    def test_service_has_public_build_claude_prompt(self):
        from src.service.archilles_service import ArchillesService
        assert callable(getattr(ArchillesService, "build_claude_prompt", None))

    def test_unified_server_does_not_touch_rag_internals(self):
        # Quelltext-Ratsche: verhindert Rückfall auf den privaten Durchgriff
        # service._rag, nachdem 5.15 den öffentlichen Pfad eingeführt hat.
        source = (REPO_ROOT / "src" / "calibre_mcp" / "unified_server.py").read_text(encoding="utf-8")
        assert "service._rag" not in source
