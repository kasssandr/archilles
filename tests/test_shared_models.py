"""Shared model instances across engine/service objects.

The unified MCP server builds one ArchillesRAG per source; before this
change every instance loaded its own SentenceTransformer (3x BGE-M3,
~2.3 GB each) and every ArchillesService its own CrossEncoderReranker.
A process-wide cache keyed by (model_name, device) makes all sources
share one instance of each model.
"""

import numpy as np
import pytest

import src.archilles.engine.core as core
import src.service.archilles_service as service_mod
from src.archilles.engine import ArchillesRAG
from src.service.archilles_service import ArchillesService


class _CountingSentenceTransformer:
    """Stand-in for SentenceTransformer that counts constructions."""

    instances = 0

    def __init__(self, model_name, device=None):
        type(self).instances += 1
        self.model_name = model_name
        self.device = device

    def encode(self, *args, **kwargs):
        return np.zeros((1, 8), dtype=np.float32)

    def half(self):
        return self


class _CountingReranker:
    """Stand-in for CrossEncoderReranker that counts constructions."""

    instances = 0

    def __init__(self, model_name=None, device=None):
        type(self).instances += 1
        self.model_name = model_name
        self.device = device


@pytest.fixture(autouse=True)
def _clean_caches(monkeypatch):
    """Isolate each test from the process-wide model caches."""
    core._shared_embedding_models.clear()
    service_mod._shared_rerankers.clear()
    _CountingSentenceTransformer.instances = 0
    _CountingReranker.instances = 0
    yield
    core._shared_embedding_models.clear()
    service_mod._shared_rerankers.clear()


@pytest.fixture
def _cpu_only(monkeypatch):
    """Force deterministic CPU device selection in ArchillesRAG.__init__."""
    import torch
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)


def _make_rag(tmp_path, name, model_name="dummy-model"):
    return ArchillesRAG(db_path=str(tmp_path / name), model_name=model_name)


class TestSharedEmbeddingModel:
    def test_two_rags_share_one_model(self, tmp_path, monkeypatch, _cpu_only):
        monkeypatch.setattr(core, "SentenceTransformer", _CountingSentenceTransformer)

        rag1 = _make_rag(tmp_path, "db1")
        rag2 = _make_rag(tmp_path, "db2")

        assert rag1.embedding_model is rag2.embedding_model
        assert _CountingSentenceTransformer.instances == 1

    def test_different_model_names_get_distinct_instances(
        self, tmp_path, monkeypatch, _cpu_only
    ):
        monkeypatch.setattr(core, "SentenceTransformer", _CountingSentenceTransformer)

        rag1 = _make_rag(tmp_path, "db1", model_name="model-a")
        rag2 = _make_rag(tmp_path, "db2", model_name="model-b")

        assert rag1.embedding_model is not rag2.embedding_model
        assert _CountingSentenceTransformer.instances == 2

    def test_skip_model_does_not_touch_cache(self, tmp_path, monkeypatch, _cpu_only):
        monkeypatch.setattr(core, "SentenceTransformer", _CountingSentenceTransformer)

        rag = ArchillesRAG(db_path=str(tmp_path / "db"), skip_model=True)

        assert rag.embedding_model is None
        assert _CountingSentenceTransformer.instances == 0


class TestSharedReranker:
    def _make_service(self, tmp_path, name):
        return ArchillesService(
            db_path=str(tmp_path / name),
            enable_reranking=True,
            reranker_device="cpu",
        )

    def test_two_services_share_one_reranker(self, tmp_path, monkeypatch):
        import src.retriever
        monkeypatch.setattr(src.retriever, "CrossEncoderReranker", _CountingReranker)

        svc1 = self._make_service(tmp_path, "db1")
        svc2 = self._make_service(tmp_path, "db2")

        assert svc1._get_reranker() is svc2._get_reranker()
        assert _CountingReranker.instances == 1

    def test_different_devices_get_distinct_rerankers(self, tmp_path, monkeypatch):
        import src.retriever
        monkeypatch.setattr(src.retriever, "CrossEncoderReranker", _CountingReranker)

        svc_cpu = ArchillesService(
            db_path=str(tmp_path / "db1"),
            enable_reranking=True,
            reranker_device="cpu",
        )
        svc_cuda = ArchillesService(
            db_path=str(tmp_path / "db2"),
            enable_reranking=True,
            reranker_device="cuda",
        )

        assert svc_cpu._get_reranker() is not svc_cuda._get_reranker()
        assert _CountingReranker.instances == 2
