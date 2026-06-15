"""
Global routine-lock for Archilles automations.

A single file-based mutex at ``~/.archilles/routine.lock`` serialises any
process that needs exclusive access to the shared GPU / LanceDB / Calibre
SQLite resources — scheduled watchdogs, vault-linker, status-mail, and
future tenants like the news agent.

Design
------
* **Lockfile content:** a short human-readable line ``"{script_name}  PID=…
  since=ISO"``.  Reading it shows you which automation currently holds the
  lock and since when.
* **Heartbeat:** a daemon thread refreshes the lockfile's mtime every
  :data:`HEARTBEAT_INTERVAL_S` seconds via ``os.utime`` (atomic — never
  recreates a stray file if the lock was just released).
* **Stale recovery:** if the mtime has not been refreshed within
  :data:`STALE_AFTER_S` (1 h), the next acquirer reclaims the lock.  This
  covers the case where a previous holder crashed without releasing.
* **Wait-and-poll:** acquirers pass ``wait_s`` to wait for a busy lock to
  free up.  Scheduled tasks pass 2 h so OnLogon triggers serialise rather
  than skip the day.

Usage
-----
High-level (recommended): the context manager handles heartbeat lifecycle.

.. code-block:: python

    from archilles.runtime_lock import routine_lock

    with routine_lock("news-agent(heavy)", wait_s=1800) as acquired:
        if not acquired:
            sys.exit(1)
        do_gpu_work()

Low-level (for legacy try/finally patterns):

.. code-block:: python

    import threading
    from archilles import runtime_lock

    if not runtime_lock.acquire("script-name", wait_s=7200):
        return 1
    stop = threading.Event()
    runtime_lock.start_heartbeat(stop)
    try:
        do_work()
    finally:
        stop.set()
        runtime_lock.release()
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterator

logger = logging.getLogger(__name__)

# ── Public constants ────────────────────────────────────────────────────

#: Path to the shared lockfile.  Override at import time if you need a
#: different location for testing or per-user isolation.
LOCK_FILE: Path = Path.home() / ".archilles" / "routine.lock"

#: How often a live holder refreshes the lockfile mtime.
HEARTBEAT_INTERVAL_S: int = 300

#: How long the lockfile mtime may stay unrefreshed before the next
#: acquirer treats it as stale and reclaims it.  Must be larger than
#: :data:`HEARTBEAT_INTERVAL_S` by a comfortable margin so a delayed
#: heartbeat doesn't trigger false stealing.  1 h is also large enough to
#: tolerate occasional non-heartbeating tenants (legacy short-lived
#: scripts that haven't been migrated yet).
STALE_AFTER_S: int = 3600

#: How often :func:`acquire` re-checks a busy lock while waiting.
_POLL_INTERVAL_S: int = 300


# ── Low-level API ───────────────────────────────────────────────────────


def acquire(script_name: str, wait_s: int = 0) -> bool:
    """Try to acquire the global routine lock.

    Parameters
    ----------
    script_name
        Short identifier written into the lockfile so other processes can
        see who holds it (e.g. ``"run_routine(archilles)"``).
    wait_s
        How long to wait for a busy lock to free up.  ``0`` (default)
        means "fail fast"; positive values poll every
        :data:`_POLL_INTERVAL_S` seconds until the timeout elapses.

    Returns
    -------
    bool
        ``True`` if the lock was acquired; ``False`` if ``wait_s`` ran
        out while the lock stayed busy.

    Notes
    -----
    A returned ``True`` does *not* start the heartbeat — callers must
    either use :func:`start_heartbeat` directly (low-level) or, better,
    wrap the work in :func:`routine_lock` (high-level).  A long-running
    holder without heartbeat risks having its lock reclaimed after
    :data:`STALE_AFTER_S`.
    """
    deadline = time.time() + wait_s
    info = ""
    while True:
        busy = False
        if LOCK_FILE.exists():
            try:
                if time.time() - LOCK_FILE.stat().st_mtime < STALE_AFTER_S:
                    busy = True
                    info = LOCK_FILE.read_text(encoding="utf-8").strip()
            except OSError:
                pass

        if not busy:
            LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
            LOCK_FILE.write_text(
                f"{script_name}  PID={os.getpid()}  since={datetime.now().isoformat()}",
                encoding="utf-8",
            )
            return True

        if time.time() >= deadline:
            logger.warning(
                "Routine lock still held after %ss wait: %s", wait_s, info
            )
            print(
                f"SKIP — routine lock still held after {wait_s}s wait: {info}",
                file=sys.stderr,
            )
            return False

        remaining = int(deadline - time.time())
        logger.info("Waiting for routine lock (%ss left): %s", remaining, info)
        print(
            f"  Waiting for lock ({remaining}s left): {info}", file=sys.stderr
        )
        time.sleep(_POLL_INTERVAL_S)


def release() -> None:
    """Remove the lockfile.  Safe to call when the lock is not held."""
    try:
        LOCK_FILE.unlink(missing_ok=True)
    except OSError:
        pass


def start_heartbeat(stop_event: threading.Event) -> threading.Thread:
    """Refresh the lockfile mtime every :data:`HEARTBEAT_INTERVAL_S` seconds.

    The returned thread is a daemon — it does not need to be joined, and
    it terminates when the program exits.  Set ``stop_event`` when the
    caller wants to stop refreshing early (e.g. just before
    :func:`release`).

    Uses ``os.utime`` rather than ``Path.touch`` so a heartbeat tick that
    races with :func:`release` cannot resurrect a zombie lockfile.
    """

    def _beat() -> None:
        while not stop_event.wait(HEARTBEAT_INTERVAL_S):
            try:
                os.utime(LOCK_FILE, None)
            except OSError:
                # FileNotFoundError when the lock was already released —
                # nothing to do, the heartbeat will simply tick again.
                pass

    t = threading.Thread(target=_beat, daemon=True, name="routine-lock-heartbeat")
    t.start()
    return t


# ── High-level context manager ──────────────────────────────────────────


@contextmanager
def routine_lock(script_name: str, *, wait_s: int = 0) -> Iterator[bool]:
    """Acquire the lock for the duration of a ``with`` block.

    Yields ``True`` if the lock was acquired (heartbeat thread is then
    running) or ``False`` if ``wait_s`` ran out.  In both cases the
    block executes; check the yielded value to decide whether to do
    work or bail out early:

    .. code-block:: python

        with routine_lock("my-script", wait_s=600) as got_it:
            if not got_it:
                return  # busy — try again later
            do_protected_work()

    On exit (normal or via exception), the heartbeat is stopped and the
    lockfile removed.
    """
    acquired = acquire(script_name, wait_s=wait_s)
    stop = threading.Event()
    if acquired:
        start_heartbeat(stop)
    try:
        yield acquired
    finally:
        stop.set()
        if acquired:
            release()
