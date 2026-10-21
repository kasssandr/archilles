"""The setup page's logic: config writes, tag landscape, routine wiring.

The page is the new entry point for initial indexing, so the files it writes
are read by every routine and by the MCP server afterwards. What matters
most: it never loses keys it does not know, never writes a config the readers
would reject, and the scheduler tasks it registers follow the saved rhythm.
"""

import json
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

import scripts.run_routine as rr
from src.archilles import onboarding
from src.archilles.config import load_master_config


# ── Master config ──────────────────────────────────────────────────


class TestUpsertSource:
    def test_new_source_becomes_default_when_none_is_set(self):
        raw = {"version": 2, "sources": []}

        onboarding.upsert_source(raw, "calibre", {"library_path": "D:/Lib"})

        assert raw["default_source"] == "calibre"
        assert raw["sources"] == [{"name": "calibre", "library_path": "D:/Lib"}]

    def test_existing_default_is_kept(self):
        raw = {"default_source": "a", "sources": [{"name": "a", "library_path": "x"}]}

        onboarding.upsert_source(raw, "b", {"library_path": "y"})

        assert raw["default_source"] == "a"

    def test_keys_the_page_does_not_know_survive(self):
        raw = {"sources": [{"name": "lab", "library_path": "x",
                            "link_vault_script": "D:/link_vault.py"}]}

        onboarding.upsert_source(raw, "lab", {"schedule": "weekly"})

        entry = onboarding.find_source(raw, "lab")
        assert entry["link_vault_script"] == "D:/link_vault.py"
        assert entry["schedule"] == "weekly"

    def test_none_removes_a_key(self):
        raw = {"sources": [{"name": "c", "library_path": "x", "priority_tags": ["prio"]}]}

        onboarding.upsert_source(raw, "c", {"priority_tags": None})

        assert "priority_tags" not in onboarding.find_source(raw, "c")


class TestSaveMasterRaw:
    def test_round_trip_through_the_real_reader(self, tmp_path):
        path = tmp_path / "config.json"
        raw = onboarding.upsert_source(
            onboarding.load_master_raw(path), "calibre",
            {"library_path": str(tmp_path), "adapter": "calibre", "schedule": "manual",
             "priority_tags": ["BBB"]},
        )

        onboarding.save_master_raw(raw, path)

        master = load_master_config(path)
        assert master.sources[0].schedule == "manual"
        assert master.sources[0].priority_tags == ["BBB"]

    def test_invalid_config_is_refused_and_nothing_written(self, tmp_path):
        path = tmp_path / "config.json"
        path.write_text('{"sources": [{"name": "a", "library_path": "x"}]}', encoding="utf-8")
        before = path.read_text(encoding="utf-8")
        raw = onboarding.upsert_source(onboarding.load_master_raw(path), "a",
                                       {"schedule": "hourly"})

        with pytest.raises(ValueError):
            onboarding.save_master_raw(raw, path)

        assert path.read_text(encoding="utf-8") == before
        assert list(tmp_path.iterdir()) == [path]

    def test_previous_version_is_kept_as_backup(self, tmp_path):
        path = tmp_path / "config.json"
        path.write_text('{"sources": [{"name": "a", "library_path": "x"}]}', encoding="utf-8")
        raw = onboarding.upsert_source(onboarding.load_master_raw(path), "a",
                                       {"schedule": "weekly"})

        onboarding.save_master_raw(raw, path)

        backup = json.loads((tmp_path / "config.json.bak").read_text(encoding="utf-8"))
        assert "schedule" not in backup["sources"][0]

    def test_missing_file_yields_an_empty_skeleton(self, tmp_path):
        assert onboarding.load_master_raw(tmp_path / "nope.json")["sources"] == []


class TestLoadMasterConfigSchedule:
    def test_unknown_schedule_is_rejected(self, tmp_path):
        path = tmp_path / "config.json"
        path.write_text(json.dumps({"sources": [
            {"name": "a", "library_path": "x", "schedule": "hourly"}]}), encoding="utf-8")

        with pytest.raises(ValueError, match="schedule"):
            load_master_config(path)

    def test_schedule_is_optional(self, tmp_path):
        path = tmp_path / "config.json"
        path.write_text(json.dumps({"sources": [{"name": "a", "library_path": "x"}]}),
                        encoding="utf-8")

        assert load_master_config(path).sources[0].schedule is None


# ── Library config ─────────────────────────────────────────────────


class TestUpdateLibraryConfig:
    def test_merges_and_keeps_other_keys(self, tmp_path):
        (tmp_path / ".archilles").mkdir()
        cfg = tmp_path / ".archilles" / "config.json"
        cfg.write_text(json.dumps({"embedder": {"host": "h"}, "mode": "light"}),
                       encoding="utf-8")

        onboarding.update_library_config(tmp_path, {"mode": "auto",
                                                     "excluded_tags": ["exclude"]})

        data = json.loads(cfg.read_text(encoding="utf-8"))
        assert data == {"embedder": {"host": "h"}, "mode": "auto",
                        "excluded_tags": ["exclude"]}

    def test_creates_the_file_for_a_new_library(self, tmp_path):
        onboarding.update_library_config(tmp_path, {"languages": ["de", "en"]})

        data = json.loads((tmp_path / ".archilles" / "config.json").read_text(encoding="utf-8"))
        assert data == {"languages": ["de", "en"]}

    def test_none_removes_a_key(self, tmp_path):
        onboarding.update_library_config(tmp_path, {"mode": "light"})

        onboarding.update_library_config(tmp_path, {"mode": None})

        assert onboarding.load_library_raw(tmp_path) == {}


# ── Tag landscape ──────────────────────────────────────────────────


def _calibre_library(path: Path) -> Path:
    conn = sqlite3.connect(path / "metadata.db")
    conn.executescript("""
        CREATE TABLE books (id INTEGER PRIMARY KEY);
        CREATE TABLE tags (id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE books_tags_link (book INTEGER, tag INTEGER);
        INSERT INTO books VALUES (1), (2), (3);
        INSERT INTO tags VALUES (1, 'BBB'), (2, 'exclude'), (3, 'orphan');
        INSERT INTO books_tags_link VALUES (1, 1), (2, 1), (3, 2), (99, 3);
    """)
    conn.commit()
    conn.close()
    return path


class TestTagLandscape:
    def test_calibre_counts_books_per_tag_most_used_first(self, tmp_path):
        lib = _calibre_library(tmp_path)

        assert onboarding.tag_landscape(lib, "calibre") == [("BBB", 2), ("exclude", 1)]

    def test_other_adapters_count_works_from_the_adapter(self, tmp_path, monkeypatch):
        works = [SimpleNamespace(tags=["a", "b"]), SimpleNamespace(tags=["a"]),
                 SimpleNamespace(tags=["a", "a"])]
        import src.adapters as adapters
        monkeypatch.setattr(adapters, "create_adapter",
                            lambda path, kind: SimpleNamespace(list_works=lambda: works))

        assert onboarding.tag_landscape(tmp_path, "zotero") == [("a", 3), ("b", 1)]


# ── Routine status ─────────────────────────────────────────────────


class TestRoutineStatus:
    def test_markers_and_newest_record_of_this_source(self, tmp_path):
        d = tmp_path / ".archilles"
        d.mkdir()
        (d / "last_routine_run_phaseA.txt").write_text("2026-10-20T10:00", encoding="utf-8")
        (d / "routine_history.jsonl").write_text(
            json.dumps({"source": "calibre", "exit_code": 0}) + "\n"
            + "not json\n"
            + json.dumps({"source": "other", "exit_code": 9}) + "\n"
            + json.dumps({"source": "calibre", "exit_code": 3}) + "\n",
            encoding="utf-8",
        )

        status = onboarding.routine_status(tmp_path, "calibre")

        assert status["markers"] == {"phaseA": "2026-10-20T10:00"}
        assert status["last_run"]["exit_code"] == 3

    def test_a_library_that_never_ran(self, tmp_path):
        assert onboarding.routine_status(tmp_path, "x") == {"markers": {}, "last_run": None}


# ── Scheduler tasks and run now ────────────────────────────────────


class TestRegisterScript:
    def test_calibre_gets_phase_a_and_an_unlimited_phase_b(self):
        script = onboarding.build_register_script("calibre", "calibre", python="py.exe")

        assert "'Archilles-Routine-calibre'" in script
        assert "'Archilles-Routine-calibre-B'" in script
        assert "--phase A" in script and "--phase B" in script
        assert "New-TimeSpan -Hours 0" in script

    def test_tasks_carry_no_fixed_frequency(self):
        """The rhythm is read from the master config on every run, so a
        changed rhythm needs no re-registration."""
        script = onboarding.build_register_script("zotero", "zotero", python="py.exe")

        assert "--frequency" not in script
        assert "--phase" not in script

    def test_apostrophes_are_escaped_for_powershell(self):
        script = onboarding.build_register_script("x", "folder", python="C:/Tom's/py.exe")

        assert "'C:/Tom''s/py.exe'" in script

    def test_task_names_are_slugged(self):
        assert onboarding.task_names("my lib!", "folder") == ["Archilles-Routine-my-lib"]


class TestRunNow:
    def test_calibre_runs_phase_a_then_b_forced(self):
        cmds = onboarding.build_run_now_commands("calibre", "calibre", python="py")

        assert [c[c.index("--phase") + 1] for c in cmds] == ["A", "B"]
        assert all("--force" in c for c in cmds)

    def test_other_adapters_run_once(self):
        cmds = onboarding.build_run_now_commands("lab", "obsidian", python="py")

        assert len(cmds) == 1 and "--phase" not in cmds[0]


# ── run_routine follows the saved schedule ─────────────────────────


class TestResolveFrequency:
    def test_explicit_flag_wins(self):
        assert rr._resolve_frequency("weekly", "manual") == "weekly"

    def test_schedule_applies_without_flag(self):
        assert rr._resolve_frequency(None, "weekly") == "weekly"

    def test_daily_when_unset_everywhere(self):
        assert rr._resolve_frequency(None, None) == "daily"


class TestManualSchedule:
    @pytest.fixture
    def library(self, tmp_path, monkeypatch):
        lib = tmp_path / "lib"
        (lib / ".archilles").mkdir(parents=True)
        source = SimpleNamespace(
            name="lab", library_path=str(lib), adapter="obsidian",
            priority_tags=None, priority_collections=None, schedule="manual",
        )
        monkeypatch.setattr(rr, "load_master_config",
                            lambda: SimpleNamespace(sources=[source]))
        return lib

    def test_scheduled_run_is_skipped_and_logged(self, library, monkeypatch):
        def no_lock(*a, **k):
            raise AssertionError("a manual schedule must not reach the lock")
        monkeypatch.setattr(rr.runtime_lock, "acquire", no_lock)
        monkeypatch.setattr(sys, "argv", ["run_routine.py", "--source", "lab"])

        assert rr.main() == 0

        log = (library / ".archilles" / "routine.log").read_text(encoding="utf-8")
        assert "schedule=manual" in log

    def test_forced_run_goes_ahead(self, library, monkeypatch):
        monkeypatch.setattr(rr.runtime_lock, "acquire", lambda name, wait_s=0: False)
        monkeypatch.setattr(sys, "argv", ["run_routine.py", "--source", "lab", "--force"])

        assert rr.main() == 1  # reached the lock, which this test holds closed
