"""Tests for the Hardware-Tiers-V2 wiring in the watchdog (Etappe 4).

Part 1 — _load_rag is plan-aware: it resolves the same mode→plan() path as
scripts/batch_index so newly indexed titles inherit the recipe's chunk schema
instead of the old flat default ("neue Titel werden flach indexiert").

Part 2 — full-external trickle: in full-external mode the watchdog indexes new
titles provisionally light (flat, local) and marks their chunks pending_external
for a later external batch embed (§12).
"""

from pathlib import Path
from unittest.mock import patch

import pytest

from src.archilles.hardware import HardwareProfile
from src.archilles.watchdog import WatchdogScanner

# Reuse the in-memory Calibre helpers from the main watchdog test module.
from tests.test_watchdog import _add_book, _create_calibre_db


@pytest.fixture
def calibre_library(tmp_path):
    _create_calibre_db(tmp_path)
    return tmp_path


def _caps(*, cuda=False, mps=False, vram_gb=None):
    return HardwareProfile(
        cpu_cores=8, ram_gb=32.0, gpu_available=cuda or mps,
        gpu_name="synthetic", vram_gb=vram_gb,
        cuda_available=cuda, mps_available=mps,
    )


def _scanner(tmp_path: Path) -> WatchdogScanner:
    return WatchdogScanner(
        library_path=tmp_path,
        db_path=str(tmp_path / ".archilles" / "rag_db"),
        archilles_dir=tmp_path / ".archilles",
    )


class _RecordingRAG:
    """Stand-in for ArchillesRAG that records constructor kwargs (no model load)."""

    last_kwargs: dict = {}

    def __init__(self, **kwargs):
        _RecordingRAG.last_kwargs = kwargs


def _load_with(tmp_path, *, mode, hw):
    scanner = _scanner(tmp_path)
    with patch("src.archilles.config.get_mode", return_value=mode), \
         patch("src.archilles.hardware.detect_hardware", return_value=hw), \
         patch("src.archilles.engine.ArchillesRAG", _RecordingRAG):
        scanner._load_rag()
    return _RecordingRAG.last_kwargs


class TestLoadRagIsPlanAware:
    def test_full_local_passes_hierarchical_plan(self, tmp_path):
        kw = _load_with(tmp_path, mode="full-local", hw=_caps(cuda=True, vram_gb=24))
        assert kw["hierarchical"] is True
        assert kw["execution_plan"].mode == "full-local"
        assert kw["execution_plan"].batch_size == 64  # gpu-large

    def test_light_passes_flat(self, tmp_path):
        kw = _load_with(tmp_path, mode="light", hw=_caps(cuda=True, vram_gb=24))
        assert kw["hierarchical"] is False
        assert kw["execution_plan"].mode == "light"

    def test_auto_capable_is_hierarchical(self, tmp_path):
        kw = _load_with(tmp_path, mode="auto", hw=_caps(cuda=True, vram_gb=24))
        assert kw["hierarchical"] is True
        assert kw["execution_plan"].mode == "full-local"

    def test_auto_weak_is_flat(self, tmp_path):
        kw = _load_with(tmp_path, mode="auto", hw=_caps())  # cpu-only
        assert kw["hierarchical"] is False
        assert kw["execution_plan"].mode == "light"

    def test_full_external_forces_flat_provisional(self, tmp_path):
        """full-external has no local hierarchical path on the watchdog: the new
        title is indexed flat (provisional light), embed_local stays False."""
        kw = _load_with(tmp_path, mode="full-external", hw=_caps(cuda=True, vram_gb=4))
        assert kw["hierarchical"] is False
        assert kw["execution_plan"].embed_local is False


class TestZoteroLoadRagIsPlanAware:
    """The Zotero scanner shares the same flat-default gap — align it too."""

    def test_zotero_full_local_passes_hierarchical_plan(self, tmp_path):
        from src.archilles.watchdog import ZoteroWatchdogScanner

        scanner = ZoteroWatchdogScanner(
            library_path=tmp_path,
            db_path=str(tmp_path / ".archilles" / "rag_db"),
            archilles_dir=tmp_path / ".archilles",
        )
        with patch("src.archilles.config.get_mode", return_value="full-local"), \
             patch("src.archilles.hardware.detect_hardware",
                   return_value=_caps(cuda=True, vram_gb=24)), \
             patch("src.archilles.engine.ArchillesRAG", _RecordingRAG):
            scanner._load_rag()
        assert _RecordingRAG.last_kwargs["hierarchical"] is True
        assert _RecordingRAG.last_kwargs["execution_plan"].mode == "full-local"


class _FakeStore:
    def __init__(self):
        self.marked: list[str] = []

    def mark_pending_external(self, book_id: str) -> int:
        self.marked.append(book_id)
        return 1


class _FakeRAG:
    def __init__(self):
        self.store = _FakeStore()
        self.indexed: list[str] = []

    def index_book(self, path, book_id, force=False, phase='phase2'):
        self.indexed.append(book_id)
        return {'book_id': book_id, 'chunks_indexed': 3}


class TestProvisionalLightMarking:
    """In full-external mode, Phase 3 new titles are indexed provisionally light
    (flat, local) and marked pending_external for a later external batch embed."""

    def _run(self, calibre_library, *, mode, hw):
        scanner = WatchdogScanner(
            library_path=calibre_library,
            db_path=str(calibre_library / ".archilles" / "rag_db"),
            archilles_dir=calibre_library / ".archilles",
        )
        scanner._load_indexed_hashes = lambda: {}          # book is "new"
        scanner._annotation_changed = lambda file_path, stored_hash: False
        fake = _FakeRAG()
        scanner._load_rag = lambda: fake
        with patch("src.archilles.config.get_mode", return_value=mode), \
             patch("src.archilles.hardware.detect_hardware", return_value=hw):
            scanner.scan(dry_run=False, queue_new=False, index_new=True)
        return fake

    def test_full_external_marks_new_title(self, calibre_library):
        _add_book(calibre_library, 1, "New Title", authors=["A"], with_file="x.epub")
        fake = self._run(calibre_library, mode="full-external",
                         hw=_caps(cuda=True, vram_gb=4))
        assert fake.indexed == ["1"]
        assert fake.store.marked == ["1"]

    def test_full_local_does_not_mark(self, calibre_library):
        _add_book(calibre_library, 1, "New Title", authors=["A"], with_file="x.epub")
        fake = self._run(calibre_library, mode="full-local",
                         hw=_caps(cuda=True, vram_gb=24))
        assert fake.indexed == ["1"]
        assert fake.store.marked == []  # embed_local → no provisional marker

    def test_metadata_only_stub_not_marked(self, calibre_library):
        """A phase1 metadata stub is not 'provisional light content' — it is
        upgraded via the fulltext path, not the external-embed path."""
        _add_book(calibre_library, 1, "Stub", authors=["A"], with_file="x.epub")
        scanner = WatchdogScanner(
            library_path=calibre_library,
            db_path=str(calibre_library / ".archilles" / "rag_db"),
            archilles_dir=calibre_library / ".archilles",
        )
        scanner._load_indexed_hashes = lambda: {}
        scanner._annotation_changed = lambda file_path, stored_hash: False
        fake = _FakeRAG()
        scanner._load_rag = lambda: fake
        with patch("src.archilles.config.get_mode", return_value="full-external"), \
             patch("src.archilles.hardware.detect_hardware",
                   return_value=_caps(cuda=True, vram_gb=4)):
            scanner.scan(dry_run=False, queue_new=False, index_metadata_only=True)
        assert fake.store.marked == []


class TestProvisionalLightMarkingPhase4:
    """Phase 4 (--index-fulltext-pending) drains phase1 stubs into full content.
    Under full-external that content is flat/provisional and must be marked too."""

    def _run_fulltext(self, calibre_library, *, mode, hw):
        from src.archilles.watchdog import (
            _calibre_metadata_for_hash, _compute_metadata_hash,
        )
        stored = _compute_metadata_hash(
            _calibre_metadata_for_hash(calibre_library)[101]
        )
        scanner = WatchdogScanner(
            library_path=calibre_library,
            db_path=str(calibre_library / ".archilles" / "rag_db"),
            archilles_dir=calibre_library / ".archilles",
        )
        scanner._load_indexed_hashes = lambda: {
            101: {"book_id": "101", "metadata_hash": stored,
                  "annotation_hash": "", "has_content": False},  # phase1 stub
        }
        scanner._annotation_changed = lambda file_path, stored_hash: False
        fake = _FakeRAG()
        scanner._load_rag = lambda: fake
        with patch("src.archilles.config.get_mode", return_value=mode), \
             patch("src.archilles.hardware.detect_hardware", return_value=hw):
            scanner.scan(dry_run=False, queue_new=False,
                         index_fulltext_pending=True)
        return fake

    def test_full_external_marks_drained_stub(self, calibre_library):
        _add_book(calibre_library, 101, "Stub", authors=["A"], with_file="x.epub")
        fake = self._run_fulltext(calibre_library, mode="full-external",
                                  hw=_caps(cuda=True, vram_gb=4))
        assert fake.indexed == ["101"]
        assert fake.store.marked == ["101"]

    def test_full_local_does_not_mark_drained_stub(self, calibre_library):
        _add_book(calibre_library, 101, "Stub", authors=["A"], with_file="x.epub")
        fake = self._run_fulltext(calibre_library, mode="full-local",
                                  hw=_caps(cuda=True, vram_gb=24))
        assert fake.indexed == ["101"]
        assert fake.store.marked == []
