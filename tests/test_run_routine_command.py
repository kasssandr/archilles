"""Tests for _build_command's non-Calibre/Zotero fallback (review 2026-07-03,
finding 1.2).

The fallback command for other adapters (Obsidian Lab, Folder) hard-coded
``--profile minimal``. Per ``resolve_indexing_plan`` in batch_index.py,
``--profile`` bypasses mode/plan resolution entirely, so these libraries
were pinned to flat/minimal forever regardless of the configured ``mode`` —
exactly the "watchdog uses different presets" divergence ADR-028 set out to
remove. Dropping the flag lets mode/config decide (weak hardware still
resolves to light automatically via ``plan()``).
"""

from scripts.run_routine import _build_command


class TestNonCalibreZoteroFallback:
    def test_no_profile_override_for_obsidian_adapter(self):
        cmd = _build_command("obsidian")

        assert "--profile" not in cmd

    def test_no_profile_override_for_folder_adapter(self):
        cmd = _build_command("folder")

        assert "--profile" not in cmd

    def test_still_uses_batch_index_all_skip_existing(self):
        cmd = _build_command("obsidian")

        assert "batch_index.py" in cmd[1]
        assert "--all" in cmd
        assert "--skip-existing" in cmd
        assert "--non-interactive" in cmd

    def test_cleanup_orphans_included_for_path_keyed_adapters(self):
        """Deletes/renames in path-keyed sources (Obsidian, Folder) leave
        stale index entries; the routine must clean them up each run.
        Calibre/Zotero get the equivalent inside the watchdog scan."""
        assert "--cleanup-orphans" in _build_command("obsidian")
        assert "--cleanup-orphans" in _build_command("folder")


class TestCalibreZoteroUnaffected:
    def test_calibre_still_uses_watchdog(self):
        cmd = _build_command("calibre")

        assert "watchdog.py" in cmd[1]


class TestZoteroIndexNew:
    """Zotero has no A/B stub phase — the routine must index new items
    immediately (today it passes no index flag, so new_indexed stays 0)."""

    def test_build_command_zotero_indexes_new(self):
        cmd = _build_command("zotero", max_new=None)
        assert "--index-new" in cmd
        assert "--index-metadata-only" not in cmd
        assert "--index-fulltext-pending" not in cmd

    def test_build_command_zotero_passes_max_new(self):
        cmd = _build_command("zotero", max_new=25)
        assert "--max-new" in cmd
        assert "25" in cmd
