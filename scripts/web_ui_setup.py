"""Setup page of the web UI: add a library, decide its settings once, start its routine.

Rendering only -- what is read and written, and where, lives in
:mod:`src.archilles.onboarding`.
"""

import sys
from pathlib import Path

import streamlit as st

from src.adapters import detect_adapter_type
from src.archilles import onboarding
from src.archilles.config import (
    VALID_SCHEDULES,
    get_excluded_tags,
    get_languages,
    get_metadata_only_tags,
    get_mode,
)
from src.archilles.i18n import MESSAGES, OCR_CODES, t

ADAPTERS = ["calibre", "zotero", "obsidian", "folder"]
MODES = ["auto", "light", "full-local", "full-external"]
_NEW = "__new__"


@st.cache_data(ttl=300, show_spinner=False)
def _tag_landscape(library_path: str, adapter: str) -> list[tuple[str, int]]:
    return onboarding.tag_landscape(Path(library_path), adapter)


@st.cache_resource(show_spinner=False)
def _hardware_overview() -> tuple[str, str]:
    """Detected hardware and what ``auto`` resolves to on it."""
    from src.archilles import hardware
    from src.archilles.execution import plan
    from src.archilles.recipe import default_recipe

    hw = hardware.detect_hardware()
    return hw.summary(), plan(hw, default_recipe(), "auto").mode


def _pick_source(raw: dict, lang: str):
    """Source selector. Returns (name, library_path, adapter, entry, is_new) or None."""
    names = [s["name"] for s in raw.get("sources", []) if s.get("name")]
    options = names + [_NEW]
    # A widget's state can only be set before the widget exists, so a save
    # hands the source to select over to the next run.
    pending = st.session_state.pop("setup_pending_source", None)
    if pending in options:
        st.session_state["setup_source"] = pending
    if st.session_state.get("setup_source") not in options:
        st.session_state["setup_source"] = options[0]
    choice = st.selectbox(
        t("setup.source", lang), options, key="setup_source",
        format_func=lambda n: t("setup.new_source", lang) if n == _NEW else n,
    )

    if choice != _NEW:
        entry = onboarding.find_source(raw, choice)
        library_path = Path(entry["library_path"]).expanduser()
        adapter = entry.get("adapter") or detect_adapter_type(library_path)
        st.markdown(f"**{t('setup.path', lang)}:** `{library_path}` · "
                    f"**{t('setup.adapter', lang)}:** {adapter}")
        if not library_path.is_dir():
            st.error(t("setup.error_path_missing", lang).format(path=library_path))
            return None
        return choice, library_path, adapter, entry, False

    name = st.text_input(t("setup.name", lang), key="setup_new_name",
                         help=t("setup.help_name", lang)).strip()
    path_str = st.text_input(t("setup.path", lang), key="setup_new_path",
                             help=t("setup.help_path", lang)).strip().strip('"')
    if not name or not path_str:
        st.info(t("setup.hint_new_source", lang))
        return None
    if name in names:
        st.error(t("setup.error_name_taken", lang).format(name=name))
        return None
    library_path = Path(path_str).expanduser()
    if not library_path.is_dir():
        st.error(t("setup.error_path_missing", lang).format(path=library_path))
        return None
    detected = detect_adapter_type(library_path)
    adapter = st.selectbox(t("setup.adapter", lang), ADAPTERS,
                           index=ADAPTERS.index(detected), key="setup_new_adapter",
                           help=t("setup.help_adapter", lang).format(adapter=detected))
    return name, library_path, adapter, {}, True


def _render_routines(name: str, library_path: Path, adapter: str, lang: str) -> None:
    st.subheader(t("setup.section_routines", lang))

    status = onboarding.routine_status(library_path, name)
    if status["markers"]:
        for label, when in status["markers"].items():
            st.caption(t("setup.last_run", lang).format(label=label, when=when))
    else:
        st.caption(t("setup.never_run", lang))
    last = status["last_run"]
    if last:
        stats = ", ".join(f"{k}: {v}" for k, v in (last.get("stats") or {}).items()
                          if v not in (None, 0))
        st.caption(t("setup.last_result", lang).format(
            when=last.get("timestamp", "?"), code=last.get("exit_code", "?"),
            stats=stats or "–"))

    st.markdown(t("setup.run_now_text", lang))
    if st.button(t("setup.run_now", lang), key=f"setup_{name}_run"):
        try:
            onboarding.start_run_now(name, adapter)
        except OSError as e:
            st.error(t("setup.error_generic", lang).format(error=e))
        else:
            st.success(t("setup.run_started", lang))

    if sys.platform != "win32":
        st.caption(t("setup.scheduler_windows_only", lang))
        return

    mine = onboarding.task_names(name, adapter)
    st.markdown(t("setup.register_text", lang).format(tasks=", ".join(mine)))
    col_check, col_register = st.columns(2)
    tasks_key = f"setup_{name}_tasks"
    with col_check:
        if st.button(t("setup.check_tasks", lang), key=f"setup_{name}_check"):
            st.session_state[tasks_key] = onboarding.list_tasks()
    with col_register:
        if st.button(t("setup.register", lang), key=f"setup_{name}_register"):
            result = onboarding.register_tasks(name, adapter)
            if result.returncode == 0:
                st.success(t("setup.registered", lang).format(output=result.stdout.strip()))
            else:
                st.error(t("setup.error_generic", lang).format(
                    error=(result.stderr or result.stdout).strip()))
            st.session_state[tasks_key] = onboarding.list_tasks()

    tasks = st.session_state.get(tasks_key)
    if tasks is None:
        return
    if not tasks:
        st.caption(t("setup.no_tasks", lang))
        return
    st.dataframe(tasks, hide_index=True, use_container_width=True)
    others = [task["name"] for task in tasks
              if task["name"].startswith("Archilles-Routine") and task["name"] not in mine]
    if others:
        st.warning(t("setup.other_tasks_warning", lang).format(tasks=", ".join(others)))


def render_setup_tab(lang: str) -> None:
    st.header(t("setup.title", lang))
    st.markdown(t("setup.intro", lang))

    flash = st.session_state.pop("setup_flash", None)
    if flash:
        st.success(flash)

    try:
        raw = onboarding.load_master_raw()
    except (ValueError, OSError) as e:
        st.error(t("setup.error_master", lang).format(error=e))
        return

    picked = _pick_source(raw, lang)
    if picked is None:
        return
    name, library_path, adapter, entry, is_new = picked

    def key(field: str) -> str:
        return f"setup_{name}_{field}"

    # ── Tags ──
    st.subheader(t("setup.section_tags", lang))
    try:
        with st.spinner(t("setup.loading_tags", lang)):
            tags = _tag_landscape(str(library_path), adapter)
    except Exception as e:
        st.warning(t("setup.error_tags", lang).format(error=e))
        tags = []
    counts = dict(tags)

    current_prio = list(entry.get("priority_tags") or [])
    current_excl = get_excluded_tags(library_path)
    # Only the Calibre scanner honours metadata-only tags.
    current_meta = get_metadata_only_tags(library_path) if adapter == "calibre" else []
    options = sorted(set(counts) | set(current_prio) | set(current_excl) | set(current_meta),
                     key=lambda tag: (-counts.get(tag, 0), tag.lower()))

    def label(tag: str) -> str:
        return f"{tag} ({counts.get(tag, 0)})"

    with st.expander(t("setup.tag_overview", lang).format(n=len(tags))):
        st.dataframe([{t("label.tags", lang): n, t("setup.works", lang): c} for n, c in tags],
                     hide_index=True, use_container_width=True)

    prio = None
    if adapter in ("calibre", "zotero"):
        prio = st.multiselect(t("setup.priority_tags", lang), options, default=current_prio,
                              format_func=label, key=key("prio"),
                              help=t("setup.help_priority_tags", lang))
    excl = st.multiselect(t("setup.excluded_tags", lang), options, default=current_excl,
                          format_func=label, key=key("excl"),
                          help=t("setup.help_excluded_tags", lang))
    meta = None
    if adapter == "calibre":
        meta = st.multiselect(t("setup.metadata_only_tags", lang), options, default=current_meta,
                              format_func=label, key=key("meta"),
                              help=t("setup.help_metadata_only_tags", lang))
    clash = set(prio or []) & set(excl)
    if clash:
        st.warning(t("setup.warning_prio_excluded", lang).format(tags=", ".join(sorted(clash))))

    # ── Mode and languages ──
    st.subheader(t("setup.section_mode", lang))
    hw_summary, auto_mode = _hardware_overview()
    st.caption(hw_summary.replace("\n", " · "))
    current_mode = get_mode(library_path)
    mode = st.radio(t("setup.mode", lang), MODES, index=MODES.index(current_mode),
                    key=key("mode"),
                    format_func=lambda m: t(f"setup.mode_{m}", lang).format(auto=auto_mode))
    if mode == "full-external":
        st.warning(t("setup.mode_external_warning", lang))

    langs = get_languages(library_path)
    ui_options = sorted(MESSAGES)
    ui_lang = st.selectbox(t("setup.ui_language", lang), ui_options,
                           index=ui_options.index(langs[0]) if langs[0] in ui_options else 0,
                           key=key("ui_lang"))
    corpus = st.multiselect(t("setup.corpus_languages", lang),
                            sorted(set(OCR_CODES) | set(langs)), default=langs,
                            key=key("corpus"), help=t("setup.help_corpus_languages", lang))

    # ── Schedule ──
    st.subheader(t("setup.section_schedule", lang))
    schedules = list(VALID_SCHEDULES)
    current_schedule = entry.get("schedule") or "daily"
    schedule = st.radio(t("setup.schedule", lang), schedules,
                        index=schedules.index(current_schedule), horizontal=True,
                        key=key("schedule"),
                        format_func=lambda s: t(f"setup.schedule_{s}", lang))
    st.caption(t("setup.help_schedule", lang))

    # ── Save ──
    if st.button(t("setup.save", lang), type="primary", key=key("save")):
        source_updates = {"library_path": str(library_path), "adapter": adapter,
                          "schedule": schedule}
        if prio is not None:
            source_updates["priority_tags"] = prio or None
        library_updates = {
            "excluded_tags": excl,
            "mode": mode,
            "languages": [ui_lang] + [code for code in corpus if code != ui_lang],
        }
        if meta is not None:
            library_updates["metadata_only_tags"] = meta
        try:
            master_path = onboarding.save_master_raw(
                onboarding.upsert_source(raw, name, source_updates))
            library_cfg = onboarding.update_library_config(library_path, library_updates)
        except (ValueError, OSError) as e:
            st.error(t("setup.error_generic", lang).format(error=e))
        else:
            st.session_state["setup_flash"] = t("setup.saved", lang).format(
                master=master_path, library=library_cfg)
            st.session_state["setup_pending_source"] = name
            st.rerun()

    if is_new:
        st.caption(t("setup.hint_save_first", lang))
        return
    st.divider()
    _render_routines(name, library_path, adapter, lang)
