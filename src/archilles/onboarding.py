"""The logic behind the web UI's setup page.

Setting up a library means: register it as a source in the master config,
decide once how its tags steer indexing, pick the indexing mode and languages,
choose a cadence -- and from then on let the routines (watchdog) do the work.
On an empty index the routine is the initial indexing: phase A stubs every
book within minutes, phase B drains the full text.

Everything here writes only ARCHILLES' own configuration files. The library
itself is read through read-only connections (Calibre, Zotero) or adapters;
nothing in this module writes to it.

Where each setting lives (the readers decide this, not the page):

* master config ``~/.archilles/config.json`` -- source entry, ``priority_tags``,
  ``schedule`` (read by ``run_routine.py``)
* ``<library>/.archilles/config.json`` -- ``excluded_tags``,
  ``metadata_only_tags``, ``mode``, ``languages`` (read by the watchdog and
  ``batch_index`` through the ``config.get_*`` getters)
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

from src.archilles.config import (
    CURRENT_CONFIG_VERSION,
    load_master_config,
    master_config_path,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
RUNNER = REPO_ROOT / "scripts" / "run_routine.py"

# Wait for a running routine instead of skipping (same value the installer uses).
WAIT_FOR_LOCK_S = 7200

# How long a "run now" console stays open after the run, matching the
# scheduler wrappers: a window that closes itself cannot be resurrected by
# Windows' "restore apps after restart".
RUN_NOW_HOLD_S = 900


# ── Tag landscape ──────────────────────────────────────────────────


def tag_landscape(library_path: Path, adapter: str) -> list[tuple[str, int]]:
    """All tags of a library with the number of works carrying each, most used first."""
    library_path = Path(library_path)
    if adapter == "calibre":
        from src.archilles.sqlite_ro import connect_readonly

        conn = connect_readonly(library_path / "metadata.db")
        try:
            rows = conn.execute(
                "SELECT tags.name, COUNT(books.id) FROM tags "
                "JOIN books_tags_link ON tags.id = books_tags_link.tag "
                "JOIN books ON books_tags_link.book = books.id "
                "GROUP BY tags.id"
            ).fetchall()
        finally:
            conn.close()
        counts = Counter({str(name): int(n) for name, n in rows})
    else:
        from src.adapters import create_adapter

        counts = Counter()
        for doc in create_adapter(library_path, adapter).list_works():
            counts.update(set(doc.tags))
    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0].lower()))


# ── Config files ───────────────────────────────────────────────────


def _write_json_atomically(path: Path, data: dict) -> None:
    """Write *data* to *path*, keeping the previous version as ``<name>.bak``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
        if path.exists():
            shutil.copy2(path, path.with_name(path.name + ".bak"))
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def load_master_raw(path: Path | None = None) -> dict:
    """The master config as a plain dict, or an empty skeleton if there is none.

    Raw rather than :class:`MasterConfig` so that saving it back keeps every
    key -- including ones this page does not know about.
    """
    cfg_path = path or master_config_path()
    if not cfg_path.exists():
        return {"version": CURRENT_CONFIG_VERSION, "sources": []}
    with open(cfg_path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    if not isinstance(raw, dict):
        raise ValueError(f"Master config {cfg_path} is not a JSON object")
    raw.setdefault("sources", [])
    return raw


def find_source(raw: dict, name: str) -> dict | None:
    return next((s for s in raw.get("sources", []) if s.get("name") == name), None)


def upsert_source(raw: dict, name: str, updates: dict) -> dict:
    """Merge *updates* into the source *name*, creating it if needed.

    A value of ``None`` removes the key; keys not mentioned stay untouched.
    The first source ever added becomes ``default_source``.
    """
    entry = find_source(raw, name)
    if entry is None:
        entry = {"name": name}
        raw.setdefault("sources", []).append(entry)
    for key, value in updates.items():
        if value is None:
            entry.pop(key, None)
        else:
            entry[key] = value
    if not raw.get("default_source"):
        raw["default_source"] = name
    return raw


def save_master_raw(raw: dict, path: Path | None = None) -> Path:
    """Validate *raw* exactly as the readers will, then write it.

    The candidate goes through :func:`load_master_config` first, so a broken
    config is refused here instead of breaking the MCP server and every
    routine on their next start.
    """
    cfg_path = path or master_config_path()
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    fd, probe = tempfile.mkstemp(dir=cfg_path.parent, suffix=".probe.json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(raw, f, ensure_ascii=False)
        load_master_config(Path(probe))
    finally:
        Path(probe).unlink(missing_ok=True)
    _write_json_atomically(cfg_path, raw)
    return cfg_path


def library_config_path(library_path: Path) -> Path:
    return Path(library_path) / ".archilles" / "config.json"


def load_library_raw(library_path: Path) -> dict:
    """``<library>/.archilles/config.json`` as a dict (``{}`` if absent)."""
    path = library_config_path(library_path)
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    if not isinstance(raw, dict):
        raise ValueError(f"{path} is not a JSON object")
    return raw


def update_library_config(library_path: Path, updates: dict) -> Path:
    """Merge *updates* into the library config; ``None`` removes a key."""
    raw = load_library_raw(library_path)
    for key, value in updates.items():
        if value is None:
            raw.pop(key, None)
        else:
            raw[key] = value
    path = library_config_path(library_path)
    _write_json_atomically(path, raw)
    return path


# ── Routine status ─────────────────────────────────────────────────


def routine_status(library_path: Path, source_name: str) -> dict:
    """Last run per marker plus the newest history record of *source_name*."""
    archilles_dir = Path(library_path) / ".archilles"
    markers = {}
    for marker in sorted(archilles_dir.glob("last_routine_run*.txt")):
        label = marker.stem.removeprefix("last_routine_run").lstrip("_") or "run"
        try:
            markers[label] = marker.read_text(encoding="utf-8").strip()
        except OSError:
            continue
    last = None
    history = archilles_dir / "routine_history.jsonl"
    if history.exists():
        with history.open(encoding="utf-8") as f:
            for line in f:
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if record.get("source") == source_name:
                    last = record
    return {"markers": markers, "last_run": last}


# ── Scheduler tasks (Windows) ──────────────────────────────────────


def task_names(source_name: str, adapter: str) -> list[str]:
    """Task Scheduler names for a source: one task, plus phase B for Calibre."""
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", source_name).strip("-") or "source"
    base = f"Archilles-Routine-{slug}"
    return [base, f"{base}-B"] if adapter == "calibre" else [base]


def _ps_quote(value: str) -> str:
    """A PowerShell single-quoted string literal."""
    return "'" + value.replace("'", "''") + "'"


def build_register_script(
    source_name: str,
    adapter: str,
    python: str | None = None,
    repo_root: Path = REPO_ROOT,
) -> str:
    """PowerShell that registers the source's routine tasks (idempotent).

    Same task shape as ``install_scheduled_routines.ps1`` -- at logon, delayed,
    current user, no admin rights -- with one difference: no ``--frequency``.
    The cadence is read from the master config on every run, so changing it
    on the setup page needs no re-registration.
    """
    python = python or sys.executable
    runner = repo_root / "scripts" / "run_routine.py"
    base_args = f'"{runner}" --source "{source_name}" --wait-for-lock {WAIT_FOR_LOCK_S}'
    names = task_names(source_name, adapter)
    # (name, arguments, logon delay, time limit in hours; 0 = unlimited)
    tasks = []
    if adapter == "calibre":
        tasks.append((names[0], base_args + " --phase A", "PT5M", 8,
                      f"ARCHILLES {source_name}: phase A (metadata stubs, changes)"))
        tasks.append((names[1], base_args + " --phase B", "PT25M", 0,
                      f"ARCHILLES {source_name}: phase B (full-text backlog, no time limit)"))
    else:
        tasks.append((names[0], base_args, "PT5M", 8,
                      f"ARCHILLES {source_name}: routine ({adapter})"))

    lines = [
        '$ErrorActionPreference = "Stop"',
        "$user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name",
        "$principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited",
    ]
    for name, arguments, delay, hours, description in tasks:
        lines += [
            "$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd "
            "-AllowStartIfOnBatteries -DontStopIfGoingOnBatteries "
            f"-ExecutionTimeLimit (New-TimeSpan -Hours {hours})",
            f"$action = New-ScheduledTaskAction -Execute {_ps_quote(python)} "
            f"-Argument {_ps_quote(arguments)} -WorkingDirectory {_ps_quote(str(repo_root))}",
            "$trigger = New-ScheduledTaskTrigger -AtLogOn -User $user",
            f"$trigger.Delay = {_ps_quote(delay)}",
            f"if (Get-ScheduledTask -TaskName {_ps_quote(name)} -ErrorAction SilentlyContinue) "
            f"{{ Unregister-ScheduledTask -TaskName {_ps_quote(name)} -Confirm:$false }}",
            f"Register-ScheduledTask -TaskName {_ps_quote(name)} -Description {_ps_quote(description)} "
            "-Action $action -Trigger $trigger -Settings $settings -Principal $principal | Out-Null",
            f"Write-Output {_ps_quote('registered: ' + name)}",
        ]
    return "\n".join(lines) + "\n"


def _run_powershell(script: str) -> subprocess.CompletedProcess:
    # A file rather than -Command: multi-line blocks over stdin are fragile.
    # utf-8-sig, because Windows PowerShell 5.1 reads a BOM-less file as ANSI
    # and would mangle non-ASCII paths.
    fd, path = tempfile.mkstemp(suffix=".ps1")
    os.close(fd)
    try:
        Path(path).write_text(script, encoding="utf-8-sig")
        return subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive",
             "-ExecutionPolicy", "Bypass", "-File", path],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=120,
        )
    finally:
        Path(path).unlink(missing_ok=True)


def register_tasks(source_name: str, adapter: str) -> subprocess.CompletedProcess:
    return _run_powershell(build_register_script(source_name, adapter))


def list_tasks() -> list[dict]:
    """Every registered ``Archilles-*`` task with its state and arguments."""
    result = _run_powershell(
        "$OutputEncoding = [Console]::OutputEncoding = [System.Text.Encoding]::UTF8\n"
        "@(Get-ScheduledTask -TaskName 'Archilles-*' -ErrorAction SilentlyContinue | "
        "ForEach-Object { [pscustomobject]@{ name = $_.TaskName; state = [string]$_.State; "
        "arguments = (($_.Actions | ForEach-Object { $_.Arguments }) -join ' ') } }) "
        "| ConvertTo-Json -Compress\n"
    )
    out = result.stdout.strip()
    if result.returncode != 0 or not out:
        return []
    data = json.loads(out)
    return data if isinstance(data, list) else [data]


# ── Run now ────────────────────────────────────────────────────────


def build_run_now_commands(
    source_name: str, adapter: str, python: str | None = None,
) -> list[list[str]]:
    """The forced routine runs that make up "run now", in order.

    For Calibre that is phase A, then phase B: on an empty index exactly the
    initial indexing (stubs for everything, then the full text, which can
    take days and stops cleanly on CTRL+C).
    """
    python = python or sys.executable
    base = [python, str(RUNNER), "--source", source_name, "--force",
            "--wait-for-lock", str(WAIT_FOR_LOCK_S)]
    if adapter == "calibre":
        return [base + ["--phase", "A"], base + ["--phase", "B"]]
    return [base]


def start_run_now(source_name: str, adapter: str) -> None:
    """Start "run now" detached, in its own visible console window on Windows."""
    commands = build_run_now_commands(source_name, adapter)
    if sys.platform == "win32":
        chain = " & ".join(subprocess.list2cmdline(c) for c in commands)
        # The outer quotes are stripped by cmd /c, leaving the chain intact.
        cmdline = f'cmd /c "{chain} & timeout /t {RUN_NOW_HOLD_S}"'
        subprocess.Popen(cmdline, cwd=str(REPO_ROOT),
                         creationflags=subprocess.CREATE_NEW_CONSOLE)
    else:
        import shlex

        chain = " ; ".join(shlex.join(c) for c in commands)
        subprocess.Popen(["sh", "-c", chain], cwd=str(REPO_ROOT),
                         start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
