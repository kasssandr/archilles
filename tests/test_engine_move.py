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


class TestFacadeComposition:
    """Schritt 2: Fassade komponiert die Engine-Teile; öffentliche API unverändert."""

    def test_searcher_composed(self, tmp_path):
        from src.archilles.engine import ArchillesRAG
        from src.archilles.engine.search import Searcher
        rag = ArchillesRAG(db_path=str(tmp_path / "db"), skip_model=True)
        assert isinstance(rag.searcher, Searcher)
        # Extern genutzte Such-API bleibt auf der Fassade erreichbar:
        assert callable(rag.query)
        assert callable(rag._exact_phrase_search)
        assert callable(rag._apply_min_similarity)
        assert callable(rag.print_results)

    def test_export_to_markdown_with_query_text(self, tmp_path):
        """Regression: export_to_markdown nutzt Searcher._get_context_snippet,
        nicht self._get_context_snippet (der nach dem Umzug nicht mehr existiert)."""
        from src.archilles.engine import ArchillesRAG
        rag = ArchillesRAG(db_path=str(tmp_path / "db"), skip_model=True)
        results = [
            {
                'rank': 1,
                'similarity': 0.75,
                'text': 'Dies ist ein Testtext über Theologie und Geschichte.',
                'metadata': {
                    'book_title': 'Testbuch',
                    'book_id': 'testbuch_1',
                },
            }
        ]
        output_file = str(tmp_path / "export_test.md")
        returned = rag.export_to_markdown(results, query_text="Theologie", output_file=output_file)
        assert Path(returned).exists()

    def test_prompt_builder_composed(self, tmp_path):
        from src.archilles.engine import ArchillesRAG
        from src.archilles.engine.prompting import PromptBuilder
        rag = ArchillesRAG(db_path=str(tmp_path / "db"), skip_model=True)
        assert isinstance(rag.prompt_builder, PromptBuilder)
        assert callable(rag.create_claude_prompt)
        assert callable(rag.export_to_markdown)

    def test_create_claude_prompt_exercises_backrefs(self, tmp_path):
        """Regression: create_claude_prompt läuft durch die Rückreferenzen
        _rag._format_section_meta/_rag._resolve_page_info (Bug-Klasse Task 5)."""
        from src.archilles.engine import ArchillesRAG
        rag = ArchillesRAG(db_path=str(tmp_path / "db"), skip_model=True)
        results = [
            {
                'rank': 1,
                'similarity': 0.75,
                'text': 'Dies ist ein Testtext über Theologie und Geschichte.',
                'metadata': {
                    'author': 'Testautor',
                    'book_title': 'Testbuch',
                    'section_title': 'Kapitel Eins',
                    'page_number': 42,
                },
            }
        ]
        prompt = rag.create_claude_prompt(results, "Theologie")
        assert prompt['num_sources'] == 1
        assert '<system_instructions>' in prompt['system']
        assert 'Testbuch' in prompt['user']

    def test_indexer_composed(self, tmp_path):
        from src.archilles.engine import ArchillesRAG
        from src.archilles.engine.indexing import Indexer
        rag = ArchillesRAG(db_path=str(tmp_path / "db"), skip_model=True)
        assert isinstance(rag.indexer, Indexer)
        # Extern genutzte Index-API (watchdog, batch_index, Tests):
        assert callable(rag.index_book)
        assert callable(rag.prepare_book)
        assert callable(rag.embed_prepared)
        assert callable(rag._update_metadata_only)
        assert callable(rag._extract_calibre_metadata)
        assert callable(rag._build_comment_chunks)
        assert callable(rag._compute_metadata_hash)
        assert callable(rag._compute_annotation_hash)
