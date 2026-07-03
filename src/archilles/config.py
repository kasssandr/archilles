"""
Shared configuration helpers.

Two independent configuration regimes coexist:

1. **Legacy single-source** (``get_library_path``, ``get_rag_db_path``,
   ``get_excluded_tags``) — driven by ``ARCHILLES_LIBRARY_PATH`` plus an
   optional ``<library>/.archilles/config.json``.  All existing scripts use
   this.

2. **Unified multi-source master config** (``MasterConfig``,
   ``load_master_config``, ``resolve_source_config``) — driven by
   ``~/.archilles/config.json`` (or ``$ARCHILLES_CONFIG_PATH``).  Used only
   by the unified MCP server.  When no master config is present the unified
   server falls back to the legacy single-source mode.

The two regimes do not overlap.  Scripts keep working unchanged.
"""

import json
import logging
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

# Environment variable names, checked in priority order
_ENV_VARS = ("ARCHILLES_LIBRARY_PATH", "CALIBRE_LIBRARY_PATH", "CALIBRE_LIBRARY")


def get_library_path(*, required: bool = True) -> Path | None:
    """Return the Calibre library path from environment variables.

    Checks ``ARCHILLES_LIBRARY_PATH``, then the legacy
    ``CALIBRE_LIBRARY_PATH`` and ``CALIBRE_LIBRARY`` fallbacks.

    Args:
        required: If *True* (default), print a helpful error message and
            ``sys.exit(1)`` when no variable is set.  If *False*, return
            *None* instead.
    """
    for var in _ENV_VARS:
        value = os.environ.get(var)
        if value:
            return Path(value)

    if not required:
        return None

    print("\n" + "=" * 60)
    print("ERROR: Library path not set")
    print("=" * 60 + "\n")
    print("Please set one of these environment variables:\n")
    print("  Windows (PowerShell):")
    print('    $env:ARCHILLES_LIBRARY_PATH = "C:\\path\\to\\Library"\n')
    print("  Linux/macOS:")
    print('    export ARCHILLES_LIBRARY_PATH="/path/to/Library"\n')
    print("  Legacy: CALIBRE_LIBRARY_PATH is also accepted.\n")
    sys.exit(1)


def get_rag_db_path(library_path: Path | None = None) -> str:
    """Return the RAG database path, reading config.json if present."""
    if library_path is None:
        library_path = get_library_path()

    config_path = library_path / ".archilles" / "config.json"
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        custom = config.get("rag_db_path")
        if custom:
            return str(Path(custom) if os.path.isabs(custom) else library_path / custom)

    return str(library_path / ".archilles" / "rag_db")


# Tags that exclude a Calibre book from indexing. ``exclude`` is the only
# universal convention shipped by default; users with language- or
# workflow-specific tags (e.g. ``draft``, ``Übersetzung``) add them through
# ``.archilles/config.json`` via the ``excluded_tags`` key.
DEFAULT_EXCLUDED_TAGS: list[str] = ['exclude']


def get_excluded_tags(library_path: Path | None = None) -> list[str]:
    """Return the list of Calibre tags that exclude a book from indexing.

    Reads ``excluded_tags`` from ``.archilles/config.json`` if present;
    the config value **replaces** the defaults (symmetric with
    ``rag_db_path``). Falls back to :data:`DEFAULT_EXCLUDED_TAGS`
    (``['exclude']``) when no config file or key is present, or when no
    library path is configured at all.

    Passing ``library_path=None`` (the default) means "no library context";
    the function then returns the defaults instead of resolving via
    ``get_library_path()`` — that older behaviour would call ``sys.exit(1)``
    if no environment variable was set, which is a hostile failure mode for
    callers that already explicitly opted out of requiring a library
    (e.g. ``get_library_path(required=False)``).

    Example ``config.json``::

        {
          "excluded_tags": ["exclude", "draft", "Übersetzung"]
        }
    """
    if library_path is None:
        return list(DEFAULT_EXCLUDED_TAGS)

    config_path = library_path / ".archilles" / "config.json"
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        custom = config.get("excluded_tags")
        if isinstance(custom, list):
            return [str(t) for t in custom]

    return list(DEFAULT_EXCLUDED_TAGS)


# Languages the system operates in. ``languages[0]`` is the operator/interface
# language that drives user-visible output (CLI, web UI, markdown export); the
# whole list is the corpus language set used for language-dependent data (OCR
# codes, keyword lists, …), consumed incrementally by later i18n stages.
# Prompts to the LLM standardise on English regardless of this setting.
DEFAULT_LANGUAGES: list[str] = ['en']


def get_languages(library_path: Path | None = None) -> list[str]:
    """Return the configured language list from ``.archilles/config.json``.

    ``languages[0]`` is the operator/interface language; the whole list is the
    corpus language set. The config value **replaces** the default (symmetric
    with ``excluded_tags``). Falls back to :data:`DEFAULT_LANGUAGES`
    (``['en']``) when there is no library context, no config file, no/empty/
    invalid ``languages`` key, or the file cannot be parsed. Non-string and
    blank entries are dropped.

    Example ``config.json``::

        {
          "languages": ["de", "en", "la"]
        }
    """
    if library_path is None:
        return list(DEFAULT_LANGUAGES)

    config_path = library_path / ".archilles" / "config.json"
    if not config_path.exists():
        return list(DEFAULT_LANGUAGES)

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except (json.JSONDecodeError, OSError):
        return list(DEFAULT_LANGUAGES)

    custom = config.get("languages") if isinstance(config, dict) else None
    if isinstance(custom, list):
        langs = [x for x in custom if isinstance(x, str) and x.strip()]
        if langs:
            return langs

    return list(DEFAULT_LANGUAGES)


# Calibre tag marking a book as a known duplicate (finding 5.18 — replaces the
# hard-coded German "Doublette"). Configurable so users can keep their own tag.
DEFAULT_DUPLICATE_TAG = "duplicate"


def get_duplicate_tag(library_path: Path | None = None) -> str:
    """Return the Calibre tag that marks a book as a known duplicate.

    Reads ``duplicate_tag`` from ``<library>/.archilles/config.json``; falls
    back to :data:`DEFAULT_DUPLICATE_TAG` (``"duplicate"``) when there is no
    library context, no config file/key, or the file cannot be parsed. Users
    who tagged duplicates in another language set this key (e.g. ``"Doublette"``).
    """
    if library_path is None:
        return DEFAULT_DUPLICATE_TAG

    config_path = library_path / ".archilles" / "config.json"
    if not config_path.exists():
        return DEFAULT_DUPLICATE_TAG

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except (json.JSONDecodeError, OSError):
        return DEFAULT_DUPLICATE_TAG

    val = config.get("duplicate_tag") if isinstance(config, dict) else None
    return val if isinstance(val, str) and val.strip() else DEFAULT_DUPLICATE_TAG


# Hardware-Tiers-V2 (§7): the single user-facing variable. ``auto`` lets plan()
# derive the sensible path from the detected hardware; the explicit modes
# (light/full-local/full-external) override it. Stored as ``mode`` in
# ``.archilles/config.json``; the CLI ``--mode`` flag overrides the config.
DEFAULT_MODE = "auto"


def get_mode(library_path: Path | None = None) -> str:
    """Return the configured indexing mode from ``.archilles/config.json``.

    One of ``auto``/``light``/``full-local``/``full-external`` (the values
    accepted by :func:`src.archilles.execution.plan`). The reader is lenient:
    a missing config, missing/blank/non-string ``mode``, an unknown value, or
    an unparseable file all fall back to :data:`DEFAULT_MODE` (``"auto"``).
    Guarding here matters because ``plan()`` itself raises ``ValueError`` on an
    invalid mode — a config typo must not crash an indexing run.
    """
    if library_path is None:
        return DEFAULT_MODE

    config_path = library_path / ".archilles" / "config.json"
    if not config_path.exists():
        return DEFAULT_MODE

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except (json.JSONDecodeError, OSError):
        return DEFAULT_MODE

    from src.archilles.execution import VALID_MODES

    val = config.get("mode") if isinstance(config, dict) else None
    if isinstance(val, str) and val in VALID_MODES:
        return val
    return DEFAULT_MODE


# Built-in defaults for the embed-prepared embedder; mirror the argparse
# defaults of the ``embed`` CLI command.
_EMBEDDER_DEFAULTS = {
    "mode": "local",
    "host": None,
    "port": 8000,
    "token": None,
    "batch_size": 100,
    "use_gzip": True,
}


def resolve_embedder_settings(cli: dict, cfg: dict) -> dict:
    """Merge CLI overrides over config-file values over built-in defaults.

    Precedence per key: ``cli`` (value is not None) > ``cfg`` (key present and
    not None) > built-in default. ``cli`` carries an explicit ``False`` for
    ``use_gzip`` when ``--no-gzip`` was passed, which correctly wins as a
    non-None value.

    Returns kwargs for ``ArchillesRAG.embed_prepared``:
    ``mode, host, port, token, batch_size, use_gzip``.

    Raises:
        ValueError: if the resolved ``mode`` is not ``"local"`` or ``"remote"``.
    """
    out = {}
    for key, default in _EMBEDDER_DEFAULTS.items():
        cli_val = cli.get(key)
        if cli_val is not None:
            out[key] = cli_val
        elif cfg.get(key) is not None:
            out[key] = cfg[key]
        else:
            out[key] = default

    if out["mode"] not in ("local", "remote"):
        raise ValueError(
            f"Invalid embedder mode: {out['mode']!r} "
            "(expected 'local' or 'remote')"
        )
    return out


def get_embedder_config(library_path: Path | None = None) -> dict:
    """Return the ``embedder`` block from ``<library>/.archilles/config.json``.

    Returns ``{}`` when there is no library context, no config file, no
    ``embedder`` block, the block is not an object, or the file cannot be
    parsed. The block is optional — its absence means "use built-in defaults".
    """
    if library_path is None:
        return {}

    config_path = library_path / ".archilles" / "config.json"
    if not config_path.exists():
        return {}

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}

    block = config.get("embedder") if isinstance(config, dict) else None
    return block if isinstance(block, dict) else {}


# ───────────────────────────────────────────────────────────────────
# Unified multi-source master config (v2)
# ───────────────────────────────────────────────────────────────────

CURRENT_CONFIG_VERSION = 2


@dataclass
class SourceConfig:
    """One source entry inside a :class:`MasterConfig`.

    Fields left as ``None`` inherit from the master globals during resolution.
    ``library_path`` and ``name`` are mandatory; everything else is optional
    and may also be overridden by a library-local ``.archilles/config.json``.
    """

    name: str
    library_path: Path
    adapter: str | None = None
    rag_db_path: str | None = None
    excluded_tags: list[str] | None = None
    # Tags whose books are indexed first (group 0 in _index_priority_key).
    # Substring match, case-insensitive — e.g. ["prio", "favorites"].
    priority_tags: list[str] | None = None
    linked_attachment_base: Path | None = None
    enable_reranking: bool | None = None
    reranker_device: str | None = None


@dataclass
class MasterConfig:
    """Top-level configuration for the unified MCP server.

    Globals (``transport``, ``citation``, ``enable_reranking``,
    ``reranker_device``) live here because one server process can only honour
    one value each.  Per-source overrides for the ranking knobs are accepted
    so a user can keep e.g. a CPU-only adapter in a GPU-default setup.
    """

    sources: list[SourceConfig] = field(default_factory=list)
    default_source: str | None = None
    transport: dict = field(default_factory=dict)
    enable_reranking: bool = False
    reranker_device: str = "cpu"
    citation: dict = field(default_factory=dict)
    version: int = CURRENT_CONFIG_VERSION


def master_config_path() -> Path:
    """Resolve the master config path.

    Order: ``$ARCHILLES_CONFIG_PATH`` env var → ``~/.archilles/config.json``.
    The path is returned even when the file does not yet exist; callers are
    responsible for ``.exists()`` checks.
    """
    env = os.environ.get("ARCHILLES_CONFIG_PATH")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".archilles" / "config.json"


def master_archilles_dir() -> Path:
    """Directory holding master-level shared metadata (config, research interests).

    Returns the parent of :func:`master_config_path` — defaults to
    ``~/.archilles/`` and follows ``$ARCHILLES_CONFIG_PATH`` when set.
    The directory is not created here; callers that intend to write should
    do so themselves.
    """
    return master_config_path().parent


def load_master_config(path: Path | None = None) -> MasterConfig | None:
    """Load and validate the unified master config.

    Returns ``None`` if the file does not exist — the unified server treats
    this as legacy single-source mode.  Raises :class:`ValueError` for
    structural problems (missing fields, duplicate names, dangling
    ``default_source``); the JSON parser raises its own errors for malformed
    syntax.
    """
    cfg_path = path or master_config_path()
    if not cfg_path.exists():
        return None

    with open(cfg_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    sources_raw = raw.get("sources")
    if not isinstance(sources_raw, list) or not sources_raw:
        raise ValueError(f"Master config {cfg_path} has no sources")

    sources: list[SourceConfig] = []
    for src in sources_raw:
        if not isinstance(src, dict) or "name" not in src or "library_path" not in src:
            raise ValueError(
                f"Source entry missing 'name'/'library_path' in {cfg_path}: {src!r}"
            )
        excluded = src.get("excluded_tags")
        if excluded is not None and not isinstance(excluded, list):
            raise ValueError(
                f"Source '{src['name']}': excluded_tags must be a list, got {type(excluded).__name__}"
            )
        priority = src.get("priority_tags")
        if priority is not None and not isinstance(priority, list):
            raise ValueError(
                f"Source '{src['name']}': priority_tags must be a list, got {type(priority).__name__}"
            )
        linked = src.get("linked_attachment_base")
        sources.append(SourceConfig(
            name=str(src["name"]),
            library_path=Path(src["library_path"]).expanduser(),
            adapter=src.get("adapter"),
            rag_db_path=src.get("rag_db_path"),
            excluded_tags=[str(t) for t in excluded] if excluded is not None else None,
            priority_tags=[str(t) for t in priority] if priority is not None else None,
            linked_attachment_base=Path(linked).expanduser() if linked else None,
            enable_reranking=src.get("enable_reranking"),
            reranker_device=src.get("reranker_device"),
        ))

    names = [s.name for s in sources]
    duplicates = {n for n in names if names.count(n) > 1}
    if duplicates:
        raise ValueError(f"Duplicate source names in {cfg_path}: {sorted(duplicates)}")

    default_source = raw.get("default_source")
    if default_source is not None and default_source not in names:
        raise ValueError(
            f"default_source '{default_source}' not in sources {names} (in {cfg_path})"
        )

    return MasterConfig(
        sources=sources,
        default_source=default_source,
        transport=dict(raw.get("transport") or {}),
        enable_reranking=bool(raw.get("enable_reranking", False)),
        reranker_device=str(raw.get("reranker_device", "cpu")),
        citation=dict(raw.get("citation") or {}),
        version=int(raw.get("version", CURRENT_CONFIG_VERSION)),
    )


def resolve_source_config(master: MasterConfig, source_name: str) -> dict:
    """Return the effective config for one source.

    Override hierarchy (highest wins):

    1. ``<library_path>/.archilles/config.json`` — library-local override
    2. ``master.sources[name]``                  — per-source entry in master
    3. ``master.<global>``                       — global master fields
    4. built-in defaults

    The returned dict is flat and self-contained: ``library_path``,
    ``adapter``, ``rag_db_path`` (absolute), ``excluded_tags``,
    ``linked_attachment_base``, ``enable_reranking``, ``reranker_device``,
    ``citation``.  ``rag_db_path`` is always absolute by the time it is
    returned, so callers do not need to know about library-relative paths.
    """
    src = next((s for s in master.sources if s.name == source_name), None)
    if src is None:
        names = [s.name for s in master.sources]
        raise KeyError(f"Source {source_name!r} not in master config; have {names}")

    # Layer 3 + 2: master globals + per-source entry
    effective: dict = {
        "name": source_name,
        "library_path": src.library_path,
        "adapter": src.adapter,
        "rag_db_path": (
            src.rag_db_path
            if src.rag_db_path and os.path.isabs(src.rag_db_path)
            else str(src.library_path / (src.rag_db_path or ".archilles/rag_db"))
        ),
        "excluded_tags": (
            list(src.excluded_tags)
            if src.excluded_tags is not None
            else list(DEFAULT_EXCLUDED_TAGS)
        ),
        "linked_attachment_base": src.linked_attachment_base,
        "enable_reranking": (
            src.enable_reranking
            if src.enable_reranking is not None
            else master.enable_reranking
        ),
        "reranker_device": src.reranker_device or master.reranker_device,
        "citation": dict(master.citation),
    }

    # Layer 1: library-local override
    local_cfg = src.library_path / ".archilles" / "config.json"
    if local_cfg.exists():
        try:
            with open(local_cfg, "r", encoding="utf-8") as f:
                local = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Cannot read library-local config %s: %s", local_cfg, e)
            return effective

        if "adapter" in local:
            effective["adapter"] = local["adapter"]
        if "rag_db_path" in local:
            local_path = local["rag_db_path"]
            effective["rag_db_path"] = (
                local_path if os.path.isabs(local_path)
                else str(src.library_path / local_path)
            )
        if isinstance(local.get("excluded_tags"), list):
            effective["excluded_tags"] = [str(t) for t in local["excluded_tags"]]
        if "enable_reranking" in local:
            effective["enable_reranking"] = bool(local["enable_reranking"])
        if "reranker_device" in local:
            effective["reranker_device"] = str(local["reranker_device"])
        if isinstance(local.get("citation"), dict):
            merged = dict(effective["citation"])
            merged.update(local["citation"])
            effective["citation"] = merged

    return effective
