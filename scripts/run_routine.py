#!/usr/bin/env python3
"""
ARCHILLES Routine Runner — generic wrapper for scheduled watchdog/batch_index
runs across all configured sources.

Per-source tool selection
-------------------------
Calibre adapter        → ``scripts/watchdog.py --json`` (real watchdog with
                         hash-based metadata/annotation diff)
Other adapters         → ``scripts/batch_index.py --all --skip-existing``
                         (finds new documents only — no hash diff yet)

Marker logic
------------
A marker file ``<library>/.archilles/last_routine_run.txt`` is written on
successful completion.  On the next invocation the runner skips when:

* ``--frequency daily``  and the marker is dated today, or
* ``--frequency weekly`` and the marker falls in the same ISO calendar week.

Use ``--force`` to ignore the marker and ``--dry-run`` to print the planned
command without executing.

Usage
-----
    python scripts/run_routine.py --source archilles-lab --frequency daily
    python scripts/run_routine.py --source archilles-zotero --frequency weekly
    python scripts/run_routine.py --source archilles --frequency daily --force
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.archilles.config import load_master_config


def _should_skip(marker: Path, frequency: str, now: datetime) -> tuple[bool, str | None]:
    if not marker.exists():
        return False, None
    try:
        last_iso = marker.read_text(encoding="utf-8").strip()
        last = datetime.fromisoformat(last_iso)
    except Exception:
        return False, None
    if frequency == "daily" and last.date() == now.date():
        return True, last_iso
    if frequency == "weekly" and last.isocalendar()[:2] == now.isocalendar()[:2]:
        return True, last_iso
    return False, None


def _append_history(history_file: Path, record: dict) -> None:
    history_file.parent.mkdir(parents=True, exist_ok=True)
    with history_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


_LOCK_FILE = Path.home() / ".archilles" / "routine.lock"
_LOCK_MAX_AGE_S = 9 * 3600


def _acquire_lock(script_name: str, wait_s: int = 0) -> bool:
    """Try to acquire the global lock.

    If wait_s > 0, polls every 60 s until the lock is free or the timeout
    expires — tasks that fire simultaneously at login will serialize naturally
    rather than being skipped for the day.
    """
    poll_interval = 300
    deadline = time.time() + wait_s
    while True:
        locked = False
        if _LOCK_FILE.exists():
            try:
                if time.time() - _LOCK_FILE.stat().st_mtime < _LOCK_MAX_AGE_S:
                    locked = True
                    info = _LOCK_FILE.read_text(encoding="utf-8").strip()
            except OSError:
                pass

        if not locked:
            _LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
            _LOCK_FILE.write_text(
                f"{script_name}  PID={os.getpid()}  seit={datetime.now().isoformat()}",
                encoding="utf-8",
            )
            return True

        if time.time() >= deadline:
            print(f"SKIP — Routine-Lock nach {wait_s}s Wartezeit noch belegt: {info}",
                  file=sys.stderr)
            return False

        remaining = int(deadline - time.time())
        print(f"  Warte auf Lock ({remaining}s verbleibend): {info}", file=sys.stderr)
        time.sleep(poll_interval)


def _release_lock() -> None:
    try:
        _LOCK_FILE.unlink(missing_ok=True)
    except OSError:
        pass


def _build_command(adapter: str) -> list[str]:
    if adapter in ("calibre", "zotero"):
        # watchdog.py auto-detects library type via zotero.sqlite vs metadata.db
        return [sys.executable, str(REPO_ROOT / "scripts" / "watchdog.py"), "--json"]
    return [
        sys.executable,
        str(REPO_ROOT / "scripts" / "batch_index.py"),
        "--all",
        "--skip-existing",
    ]


def _parse_stats(stdout: str, adapter: str) -> dict:
    """Best-effort extraction of counters from tool stdout."""
    if adapter == "calibre":
        # watchdog --json prints progress lines BEFORE the final JSON dump;
        # extract the last top-level JSON object by scanning from the end.
        s = stdout.rstrip()
        if not s.endswith("}"):
            return {}
        depth = 0
        start = -1
        for i in range(len(s) - 1, -1, -1):
            ch = s[i]
            if ch == "}":
                depth += 1
            elif ch == "{":
                depth -= 1
                if depth == 0:
                    start = i
                    break
        if start < 0:
            return {}
        try:
            data = json.loads(s[start:])
            return {
                "scanned": data.get("scanned"),
                "new_books": len(data.get("new_books", [])),
                "metadata_changed": len(data.get("metadata_changed", [])),
                "annotations_changed": len(data.get("annotations_changed", [])),
                "delta_updates": data.get("delta_updates", 0),
                "errors": len(data.get("errors", [])),
            }
        except Exception:
            return {}
    stats: dict = {}
    for key, pat in (
        ("indexed",  r"Successfully indexed:\s+(\d+)"),
        ("failed",   r"Failed:\s+(\d+)"),
        ("skipped",  r"Skipped:\s+(\d+)"),
    ):
        m = re.search(pat, stdout)
        if m:
            stats[key] = int(m.group(1))
    return stats


def main() -> int:
    parser = argparse.ArgumentParser(
        description="ARCHILLES routine runner (scheduler-friendly wrapper).",
    )
    parser.add_argument("--source", required=True,
                        help="Source name from master config (e.g. 'archilles-lab')")
    parser.add_argument("--frequency", required=True, choices=["daily", "weekly"])
    parser.add_argument("--force", action="store_true",
                        help="Ignore marker and run unconditionally")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print plan and exit (no subprocess, no marker update)")
    parser.add_argument("--wait-for-lock", type=int, default=0, metavar="SECONDS",
                        help="Poll for the global lock up to SECONDS before giving up "
                             "(default: 0 = skip immediately if locked). "
                             "Recommended value for OnLogon tasks: 7200")
    args = parser.parse_args()

    master = load_master_config()
    if master is None:
        print("Keine Master-Config gefunden. Erwartet unter ~/.archilles/config.json.",
              file=sys.stderr)
        return 2

    src = next((s for s in master.sources if s.name == args.source), None)
    if src is None:
        names = [s.name for s in master.sources]
        print(f"Unbekannte Source '{args.source}'. Verfügbar: {names}", file=sys.stderr)
        return 2

    library_path = Path(src.library_path)
    archilles_dir = library_path / ".archilles"
    archilles_dir.mkdir(parents=True, exist_ok=True)
    marker = archilles_dir / "last_routine_run.txt"
    log_file = archilles_dir / "routine.log"
    history_file = archilles_dir / "routine_history.jsonl"

    now = datetime.now().astimezone()
    skip, last_iso = (False, None) if args.force else _should_skip(marker, args.frequency, now)
    if skip:
        msg = (f"[{now.isoformat()}] {args.source}: SKIP "
               f"(last run {last_iso}, frequency={args.frequency})")
        print(msg)
        with log_file.open("a", encoding="utf-8") as f:
            f.write(msg + "\n")
        return 0

    adapter = src.adapter or "calibre"
    cmd = _build_command(adapter)
    env = os.environ.copy()
    env["ARCHILLES_LIBRARY_PATH"] = str(library_path)

    if args.dry_run:
        print(f"DRY-RUN — würde ausführen: {' '.join(cmd)}\n"
              f"  ARCHILLES_LIBRARY_PATH={library_path}")
        return 0

    if not _acquire_lock(f"run_routine({args.source})", wait_s=args.wait_for_lock):
        return 1
    try:
        start = datetime.now().astimezone()
        print(f"[{start.isoformat()}] {args.source}: {' '.join(cmd)}")
        with log_file.open("a", encoding="utf-8") as f:
            f.write(f"\n=== {start.isoformat()} {args.source} START ===\n")
            f.write(f"cmd: {' '.join(cmd)}\n")

        try:
            proc = subprocess.run(
                cmd, env=env, cwd=str(REPO_ROOT),
                capture_output=True, text=True, encoding="utf-8",
                timeout=8 * 3600,
            )
        except subprocess.TimeoutExpired:
            end = datetime.now().astimezone()
            record = {
                "timestamp": start.isoformat(), "source": args.source,
                "adapter": adapter, "frequency": args.frequency,
                "exit_code": -1, "duration_s": (end - start).total_seconds(),
                "error": "timeout (>8h)", "stats": {},
            }
            _append_history(history_file, record)
            with log_file.open("a", encoding="utf-8") as f:
                f.write(f"=== {end.isoformat()} TIMEOUT ===\n")
            return 124

        end = datetime.now().astimezone()
        duration = (end - start).total_seconds()

        with log_file.open("a", encoding="utf-8") as f:
            f.write(proc.stdout or "")
            if proc.stderr:
                f.write("\n--- stderr ---\n" + proc.stderr)
            f.write(f"\n=== {end.isoformat()} EXIT={proc.returncode} dur={duration:.1f}s ===\n")

        sys.stdout.write(proc.stdout or "")
        if proc.stderr:
            sys.stderr.write(proc.stderr)

        record = {
            "timestamp": start.isoformat(), "source": args.source,
            "adapter": adapter, "frequency": args.frequency,
            "exit_code": proc.returncode, "duration_s": round(duration, 1),
            "stats": _parse_stats(proc.stdout or "", adapter),
        }
        _append_history(history_file, record)

        if proc.returncode == 0:
            marker.write_text(end.isoformat(), encoding="utf-8")

        return proc.returncode
    finally:
        _release_lock()


if __name__ == "__main__":
    sys.exit(main())
