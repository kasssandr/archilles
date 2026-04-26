"""
Unified MCP server — wraps multiple :class:`CalibreMCPServer` instances behind
a single process for the multi-source ARCHILLES configuration.

When a master config (``~/.archilles/config.json`` or ``$ARCHILLES_CONFIG_PATH``)
describes multiple sources (Calibre, Folder, Obsidian, Zotero, ...), this
server instantiates one inner server per source with its own adapter and
LanceDB, and routes tool calls:

- single-source tools dispatch via the ``source`` parameter (default =
  ``master.default_source``);
- aggregation tools (search, list-style) fan out across all sources in
  parallel and merge the results;
- Calibre-only tools are gated behind :pyattr:`UnifiedMCPServer.calibre_sources`.

The legacy single-source :class:`CalibreMCPServer` is left untouched —
``mcp_server.py`` chooses between the two depending on whether a master
config is present.

This module currently provides only the dispatcher skeleton. Tool methods
and the unified tool-schema generator live in a follow-up step.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from src.archilles.config import (
    MasterConfig,
    master_archilles_dir,
    resolve_source_config,
)
from src.calibre_mcp.server import CalibreMCPServer

logger = logging.getLogger(__name__)


class UnifiedMCPServer:
    """Multi-source dispatcher for ARCHILLES MCP tools.

    Parameters
    ----------
    servers:
        Mapping from source name to a fully-initialised inner server.
    default_source:
        Name of the source returned by :meth:`resolve_source` when called
        with ``source=None``. Must be a key in *servers*. If ``None`` and
        only one source is configured, that source becomes the default; if
        ``None`` with multiple sources, single-item tool calls without an
        explicit ``source`` argument will raise.
    master_dir:
        Directory holding master-level shared metadata (e.g.
        ``research_interests.json``).
    instance_name:
        Human-readable server name for ``serverInfo`` in MCP handshakes.
    """

    def __init__(
        self,
        servers: dict[str, CalibreMCPServer],
        default_source: Optional[str],
        master_dir: Path,
        instance_name: str = "archilles",
    ):
        if not servers:
            raise ValueError("UnifiedMCPServer requires at least one source")
        if default_source is not None and default_source not in servers:
            raise ValueError(
                f"default_source {default_source!r} not in {sorted(servers)}"
            )
        self.servers = servers
        # Implicit default when exactly one source is configured.
        if default_source is None and len(servers) == 1:
            default_source = next(iter(servers))
        self.default_source = default_source
        self.master_dir = master_dir
        self.instance_name = instance_name

    # ── Construction ─────────────────────────────────────────────────────

    @classmethod
    def from_master_config(cls, master: MasterConfig) -> "UnifiedMCPServer":
        """Build the unified server from a parsed :class:`MasterConfig`.

        Each source is resolved via :func:`resolve_source_config` (master
        globals → master.sources[name] → library-local override) and turned
        into a :class:`CalibreMCPServer`. Sources whose adapter fails to
        construct are logged and skipped, so a single misconfigured library
        does not bring down the whole server.
        """
        from src.adapters import create_adapter

        try:
            from citation.config import CitationConfig
        except ImportError:
            from src.citation.config import CitationConfig

        servers: dict[str, CalibreMCPServer] = {}
        for src in master.sources:
            cfg = resolve_source_config(master, src.name)
            try:
                adapter = create_adapter(cfg["library_path"], cfg["adapter"])
            except Exception as e:
                logger.error(
                    "Source %r: adapter construction failed (%s) — skipping",
                    src.name, e,
                )
                continue

            citation_config = CitationConfig.from_dict(cfg.get("citation") or {})
            servers[src.name] = CalibreMCPServer(
                library_path=str(cfg["library_path"]),
                annotations_dir=None,
                rag_db_path=cfg["rag_db_path"],
                enable_reranking=bool(cfg["enable_reranking"]),
                reranker_device=cfg["reranker_device"],
                citation_config=citation_config,
                adapter=adapter,
                instance_name=src.name,
            )
            logger.info(
                "Source %r ready: adapter=%s rag_db=%s",
                src.name, adapter.adapter_type, cfg["rag_db_path"],
            )

        if not servers:
            raise RuntimeError(
                "No source could be initialised — check master config and adapters"
            )

        # If master.default_source pointed at a source that failed to load,
        # demote it to None and let __init__ pick the implicit default.
        default = master.default_source if master.default_source in servers else None

        return cls(
            servers=servers,
            default_source=default,
            master_dir=master_archilles_dir(),
        )

    # ── Source resolution ────────────────────────────────────────────────

    def resolve_source(self, source: Optional[str]) -> CalibreMCPServer:
        """Pick a server for a single-source tool call.

        ``source=None`` returns the default source; passing an unknown name
        raises :class:`KeyError` with the list of available sources, so the
        caller can surface a helpful error to the LLM client.
        """
        if source is None:
            if self.default_source is None:
                raise KeyError(
                    f"This tool requires an explicit 'source' parameter; "
                    f"available: {sorted(self.servers)}"
                )
            return self.servers[self.default_source]
        if source not in self.servers:
            raise KeyError(
                f"Unknown source {source!r}; available: {sorted(self.servers)}"
            )
        return self.servers[source]

    def resolve_source_for_path(self, book_path: str) -> Optional[str]:
        """Find which source a filesystem path belongs to.

        Uses path-prefix matching against each source's ``library_path``.
        On nested libraries the longest-prefix match wins. Returns ``None``
        if no source covers the path; callers should treat that as a hard
        error and surface it to the user.
        """
        try:
            target = Path(book_path).resolve()
        except OSError:
            return None

        matches: list[tuple[int, str]] = []
        for name, server in self.servers.items():
            if server.library_path is None:
                continue
            try:
                root = server.library_path.resolve()
            except OSError:
                continue
            try:
                target.relative_to(root)
            except ValueError:
                continue
            matches.append((len(str(root)), name))

        if not matches:
            return None
        matches.sort(reverse=True)
        return matches[0][1]

    # ── Capability properties ────────────────────────────────────────────

    @property
    def calibre_sources(self) -> list[str]:
        """Names of sources whose adapter is Calibre.

        Used to gate Calibre-specific tools (``detect_duplicates``,
        ``watchdog_scan``) — these are only registered in the MCP tool list
        when at least one Calibre source is present.
        """
        return [
            name
            for name, srv in self.servers.items()
            if srv.adapter is not None and srv.adapter.adapter_type == "calibre"
        ]

    @property
    def source_names(self) -> list[str]:
        """Sorted list of all source names, for tool-schema enumerations."""
        return sorted(self.servers)
