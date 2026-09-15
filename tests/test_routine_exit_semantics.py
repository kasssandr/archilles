"""A run that finished is not a run that died — and the exit code must say which.

Observed 2026-09-15: ``watchdog.py`` exited 1 both when a scan crashed and when
a single book merely failed to extract, and ``run_routine.py`` wrote its
"ran today" marker only on exit 0. So three unreadable ``.azw3`` files were
enough to make a completed Phase A look like a dead one: the marker stood
still and the routine re-ran on every logon of the same day.

The codes now separate the two cases. A book that cannot be extracted is a
property of that book, not a failure of the scan.
"""

import io
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import scripts.run_routine as rr
from src.archilles.watchdog import (
    COMPLETED_EXIT_CODES,
    EXIT_ABORTED,
    EXIT_OK,
    EXIT_PARTIAL,
    EXIT_USAGE,
    exit_code_for,
)


class TestExitCodeForResults:
    def test_a_clean_scan_is_ok(self):
        assert exit_code_for({"errors": []}) == EXIT_OK

    def test_individual_item_errors_are_partial_not_aborted(self):
        results = {"errors": [{"calibre_id": 9138, "error": "extraction failed"}]}
        assert exit_code_for(results) == EXIT_PARTIAL

    def test_a_scan_that_finished_is_distinguishable_from_one_that_died(self):
        assert EXIT_OK in COMPLETED_EXIT_CODES
        assert EXIT_PARTIAL in COMPLETED_EXIT_CODES
        assert EXIT_ABORTED not in COMPLETED_EXIT_CODES
        assert EXIT_USAGE not in COMPLETED_EXIT_CODES


class _FakeProc:
    """Just enough of Popen for run_routine: a pid, a stdout, a return code."""

    def __init__(self, returncode: int):
        self.pid = 4242
        self.stdout = io.StringIO("scan output\n")
        self._returncode = returncode

    def wait(self, timeout=None):
        return self._returncode

    def kill(self):  # pragma: no cover - only reached on a timeout
        pass


@pytest.fixture
def library(tmp_path, monkeypatch):
    lib = tmp_path / "lib"
    (lib / ".archilles").mkdir(parents=True)
    source = SimpleNamespace(
        name="archilles", library_path=str(lib), adapter="calibre",
        priority_tags=None, priority_collections=None,
    )
    monkeypatch.setattr(
        rr, "load_master_config", lambda: SimpleNamespace(sources=[source]))
    monkeypatch.setattr(rr.runtime_lock, "acquire", lambda name, wait_s=0: True)
    monkeypatch.setattr(rr.runtime_lock, "start_heartbeat", lambda ev: None)
    monkeypatch.setattr(rr.runtime_lock, "release", lambda: None)
    monkeypatch.setattr(
        rr.process_lifetime, "tie_child_to_parent", lambda pid: None)
    return lib


def _run_with_exit(monkeypatch, returncode: int) -> int:
    monkeypatch.setattr(
        rr.subprocess, "Popen", lambda *a, **kw: _FakeProc(returncode))
    monkeypatch.setattr(
        sys, "argv",
        ["run_routine.py", "--source", "archilles", "--frequency", "daily",
         "--phase", "A"],
    )
    return rr.main()


def _marker(lib: Path) -> Path:
    return lib / ".archilles" / "last_routine_run_phaseA.txt"


class TestTodaysRunMarker:
    def test_a_clean_run_counts_as_todays_run(self, library, monkeypatch):
        _run_with_exit(monkeypatch, EXIT_OK)

        assert _marker(library).exists()

    def test_a_run_with_unusable_books_still_counts_as_todays_run(
            self, library, monkeypatch):
        """The scan did its work; three unreadable books do not undo that."""
        _run_with_exit(monkeypatch, EXIT_PARTIAL)

        assert _marker(library).exists()

    def test_an_aborted_run_does_not_count_as_todays_run(
            self, library, monkeypatch):
        _run_with_exit(monkeypatch, EXIT_ABORTED)

        assert not _marker(library).exists()

    def test_a_usage_error_does_not_count_as_todays_run(
            self, library, monkeypatch):
        _run_with_exit(monkeypatch, EXIT_USAGE)

        assert not _marker(library).exists()


class TestWeeklyMailReadsTheSameCodes:
    @staticmethod
    def _row(exit_code: int) -> dict:
        return {
            "timestamp": "2026-09-15T23:38:52+02:00", "exit_code": exit_code,
            "duration_s": 12.0, "stats": {"errors": 3},
        }

    def test_a_partial_run_is_not_reported_as_a_failed_one(self):
        from scripts.weekly_status_mail import _format_source_block

        block = _format_source_block(
            "archilles", "calibre", Path("D:/lib"), [self._row(EXIT_PARTIAL)])

        assert "abgebrochen: 0" in block
        assert "Abgebrochene Läufe" not in block

    def test_an_aborted_run_is_reported(self):
        from scripts.weekly_status_mail import _format_source_block

        block = _format_source_block(
            "archilles", "calibre", Path("D:/lib"), [self._row(EXIT_ABORTED)])

        assert "abgebrochen: 1" in block
        assert "Abgebrochene Läufe" in block
