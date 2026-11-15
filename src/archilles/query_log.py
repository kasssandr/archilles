"""The query log: what was asked of the library, kept on this machine.

The server log counts tool calls and never held their text, so the queries a
client actually sent were gone the moment they were answered -- and with them
the only honest record of how the library is used. Measurements had to be
designed around invented questions instead.

Off unless the master config says ``"query_log": true``. A tool that promises
to keep a library private does not start recording its owner's questions on
its own. When on, every tool call appends one JSON line to
``query_log.jsonl`` beside the master config: the tool, its arguments, how
long it took, and for searches which passages came back. The file never
leaves the machine; nothing reads it but the person who owns it.

The passages are logged by where they stand (source, title, page), not by
their text: the log is meant to be read years later against an index that has
been rebuilt since, and a place in a book outlives a chunk.
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

__all__ = ["QueryLog", "FILE_NAME"]

logger = logging.getLogger(__name__)

FILE_NAME = "query_log.jsonl"

# Result keys that carry the list of passages, in the order they are tried.
_HIT_KEYS = ("raw_results", "results")


def _hits(result: dict) -> list[dict] | None:
    """The passages of a search result, reduced to rank and place."""
    for key in _HIT_KEYS:
        rows = result.get(key)
        if not isinstance(rows, list):
            continue
        hits = []
        for position, row in enumerate(rows, start=1):
            if not isinstance(row, dict):
                continue
            meta = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
            hit = {"rank": row.get("rank", position)}
            if row.get("source") is not None:
                hit["source"] = row["source"]
            hit.update({k: v for k, v in meta.items() if v is not None})
            score = row.get("similarity", row.get("score"))
            if score is not None:
                hit["score"] = score
            hits.append(hit)
        return hits
    return None


class QueryLog:
    """Appends one JSON line per tool call. Safe to call from several threads."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.Lock()

    def record(self, tool: str, arguments: dict, result: Any, seconds: float) -> None:
        """Write one call. Never raises: a full disk must not fail a search."""
        try:
            entry: dict[str, Any] = {
                "ts": datetime.now().astimezone().isoformat(timespec="seconds"),
                "tool": tool,
                "arguments": arguments,
                "seconds": round(seconds, 3),
            }
            if isinstance(result, dict):
                if "error" in result:
                    entry["error"] = str(result["error"])
                if "num_results" in result:
                    entry["num_results"] = result["num_results"]
                hits = _hits(result)
                if hits is not None:
                    entry["hits"] = hits
            line = json.dumps(entry, ensure_ascii=False, default=str)
            with self._lock:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with open(self.path, "a", encoding="utf-8") as f:
                    f.write(line + "\n")
        except Exception as e:  # noqa: BLE001 -- logging must never break a call
            logger.warning("Query log not written: %s", e)
