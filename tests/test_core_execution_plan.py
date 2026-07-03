"""ArchillesRAG consumes an ExecutionPlan for the throughput knobs (Etappe 3).

When an ExecutionPlan is passed, it drives batch size and embedding device
(identity/model still come from the recipe). The plan's device is honoured only
if physically available — a plan asking for cuda on a CPU-only box falls back to
cpu, exactly like the profile path. Without a plan, the legacy default behaviour
is unchanged (back-compat).

Plans are constructed directly here (not via plan()) so the values are fixed and
the test is deterministic regardless of the host's real hardware.
"""
import torch

from src.archilles.engine.core import ArchillesRAG
from src.archilles.execution import ExecutionPlan


def _plan(*, batch_size, embedding_device, hardware_class="cpu-only", mode="light"):
    return ExecutionPlan(
        hardware_class=hardware_class,
        mode=mode,
        embedding_device=embedding_device,
        batch_size=batch_size,
        embed_local=True,
        hierarchical=False,
        rerank_enabled=True,
        rerank_device="cpu",
    )


def test_plan_drives_batch_size(tmp_path):
    rag = ArchillesRAG(
        db_path=str(tmp_path / "db"),
        skip_model=True,
        execution_plan=_plan(batch_size=64, embedding_device="cpu"),
    )
    assert rag.batch_size == 64


def test_plan_cpu_device_is_cpu(tmp_path):
    rag = ArchillesRAG(
        db_path=str(tmp_path / "db"),
        skip_model=True,
        execution_plan=_plan(batch_size=8, embedding_device="cpu"),
    )
    assert rag.device == "cpu"


def test_plan_cuda_falls_back_to_cpu_without_cuda(tmp_path):
    if torch.cuda.is_available():
        import pytest

        pytest.skip("CUDA present — fallback path not exercised")
    rag = ArchillesRAG(
        db_path=str(tmp_path / "db"),
        skip_model=True,
        execution_plan=_plan(batch_size=32, embedding_device="cuda",
                             hardware_class="gpu-mid", mode="full-local"),
    )
    assert rag.device == "cpu"
    assert rag.batch_size == 32  # batch still comes from the plan


def test_without_plan_keeps_legacy_default(tmp_path):
    """No plan, no profile → the conservative default (batch 8) is unchanged."""
    rag = ArchillesRAG(db_path=str(tmp_path / "db"), skip_model=True)
    assert rag.batch_size == 8
    assert rag.profile_name is None
