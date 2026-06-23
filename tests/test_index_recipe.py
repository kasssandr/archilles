"""Tests for the IndexRecipe — the single source of truth for the index
schema (model, dimension, chunk sizes) of the main indexing path.

Etappe 1 of the Hardware-Tiers-V2 concept
(docs/internal/CONCEPT_2026-06-23_HARDWARE_TIERS_V2.md §10.1).

The canonical defaults MUST match the effective values of the running
full-corpus refresh (child 512 / overlap 64 / parent 2048, hierarchical,
BGE-M3 1024) — consolidating means unifying, not changing values.
"""
import dataclasses

import pytest

from src.archilles.recipe import IndexRecipe, default_recipe


class TestDefaultRecipe:
    def test_canonical_values_match_running_refresh(self):
        r = default_recipe()
        assert r.embedding_model == "BAAI/bge-m3"
        assert r.embedding_dimension == 1024
        assert r.hierarchical is True
        assert r.child_chunk_size == 512
        assert r.child_overlap == 64
        assert r.parent_size == 2048

    def test_default_recipe_returns_index_recipe(self):
        assert isinstance(default_recipe(), IndexRecipe)

    def test_recipe_is_immutable(self):
        """The recipe is the identity/schema source — it must not be mutated
        in place (frozen dataclass)."""
        r = default_recipe()
        with pytest.raises(dataclasses.FrozenInstanceError):
            r.child_chunk_size = 999  # type: ignore[misc]


class TestHierarchicalChunkingUsesRecipe:
    def test_apply_hierarchical_uses_recipe_parent_size(self, monkeypatch):
        """The parent budget must come from the recipe, not a hard-coded 2048."""
        import types

        from src.archilles.engine.indexing import Indexer
        import src.extractors.base as base_mod

        captured = {}

        def fake_group(child_chunks, book_id, parent_size):
            captured["parent_size"] = parent_size
            return child_chunks

        monkeypatch.setattr(
            base_mod.BaseExtractor,
            "_group_chunks_hierarchically",
            staticmethod(fake_group),
        )

        recipe = IndexRecipe(parent_size=777)
        mock_rag = types.SimpleNamespace(recipe=recipe)
        indexer = Indexer(mock_rag)

        extracted = types.SimpleNamespace(chunks=[{"text": "x"}])
        indexer._apply_hierarchical_chunking(extracted, "book1")

        assert captured["parent_size"] == 777


class TestArchillesRagUsesRecipe:
    def test_rag_exposes_default_recipe(self, tmp_path):
        from src.archilles.engine.core import ArchillesRAG

        rag = ArchillesRAG(db_path=str(tmp_path / "db"), skip_model=True)
        assert rag.recipe == default_recipe()

    def test_live_extractor_uses_recipe_child_sizes(self, tmp_path):
        """The live index_book extractor must use the recipe's child size/overlap
        (512/64) — unifying the previous hard-coded 512/128."""
        from src.archilles.engine.core import ArchillesRAG

        rag = ArchillesRAG(db_path=str(tmp_path / "db"), skip_model=True)
        sub = rag.extractor.pdf_extractor
        assert sub.chunk_size == rag.recipe.child_chunk_size == 512
        assert sub.overlap == rag.recipe.child_overlap == 64

    def test_prepare_defaults_derive_from_recipe(self, tmp_path):
        """With no explicit --prepare-chunk-size/--prepare-overlap, the prepare
        path falls back to the recipe's child values (512/64)."""
        from src.archilles.engine.core import ArchillesRAG

        rag = ArchillesRAG(db_path=str(tmp_path / "db"), skip_model=True)
        assert rag._prepare_chunk_size == rag.recipe.child_chunk_size == 512
        assert rag._prepare_overlap == rag.recipe.child_overlap == 64


class TestProfileDeadFieldsRemoved:
    """The chunk schema/identity now lives in IndexRecipe; the dead profile
    fields (never read by production code) are removed from IndexingProfile."""

    def test_dead_fields_removed(self):
        from src.archilles.profiles import get_profile

        p = get_profile("minimal")
        for dead in ("max_parallel_docs", "max_tokens_per_chunk", "embedding_dimension"):
            assert not hasattr(p, dead), (
                f"{dead} should be removed from IndexingProfile (dead field)"
            )

    def test_profile_keeps_live_fields(self):
        """Fields still consumed (durchsatz + the deferred modular path) stay."""
        from src.archilles.profiles import get_profile

        p = get_profile("minimal")
        for kept in ("name", "embedding_model", "embedding_device", "batch_size"):
            assert hasattr(p, kept)


class TestBatchIndexPrepareDefaults:
    """The CLI must not override the recipe: with no explicit flag the prepare
    sizes default to None so ArchillesRAG falls back to the recipe (512/64),
    resolving the old 1024/128 default sprawl."""

    def test_prepare_args_default_to_none(self):
        from scripts.batch_index import build_parser

        args = build_parser().parse_args(["--all"])
        assert args.prepare_chunk_size is None
        assert args.prepare_overlap is None
