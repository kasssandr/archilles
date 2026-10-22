"""Tests for the chat inbox (scripts/chat_inbox.py)."""

import json
from pathlib import Path
from types import SimpleNamespace

from scripts.chat_inbox import (
    Item,
    Layout,
    VaultIndex,
    cmd_apply,
    cmd_scan,
    normalize_file,
    normalize_frontmatter,
    parse_review,
    read_note,
    render_review,
    triage,
)


def _layout(vault: Path) -> Layout:
    args = SimpleNamespace(vault=vault, chats_folder="KI-Chats", inbox_folder="_Eingang",
                           rejected_folder="_Verworfen", review_note="_INBOX/KI-Chat-Review.md")
    return Layout.from_args(args)


def _quiet(*_args, **_kwargs):
    pass


# ── normalize_frontmatter ───────────────────────────────────────────────

def test_web_clipper_leftovers_are_cleaned():
    fm, warnings = normalize_frontmatter({
        "title": "Spinoza", "source": "https://www.google.com/search?q=x&udm=50",
        "author": "Gemini", "published": None, "created": "2026-10-01",
        "description": "Suchen Sie ganz privat im Web. Nützliche Ergebnisse",
        "tags": ["clippings"],
    }, "2026-10-01_Gemini_Spinoza")
    assert fm["source_llm"] == "gemini"
    assert fm["type"] == "chat"
    assert fm["authors"] == ["Gemini"]
    assert "author" not in fm and "published" not in fm and "description" not in fm
    assert fm["tags"] == []
    assert warnings == []


def test_german_keys_map_without_overwriting():
    fm, _ = normalize_frontmatter({"titel": "Hermes", "datum": "2026-09-29",
                                   "art": "Zusammenfassung", "date": "2020-01-01",
                                   "created": "2026-09-30"}, "x")
    assert fm["title"] == "Hermes"
    assert fm["description"] == "Zusammenfassung"
    assert fm["created"] == "2026-09-30"
    assert fm["datum"] == "2026-09-29" and fm["date"] == "2020-01-01"


def test_platform_aliases_and_model():
    fm, _ = normalize_frontmatter({"source_llm": "chatgpt.com"}, "x")
    assert fm["source_llm"] == "chatgpt"
    fm, _ = normalize_frontmatter({"source_llm": "Gemini 3.7 Flash Thinking"}, "x")
    assert fm["source_llm"] == "gemini"
    assert fm["model"] == "Gemini 3.7 Flash Thinking"


def test_platform_from_filename():
    fm, _ = normalize_frontmatter({}, "2025-08-05_Theurgie_als_Kontrollgruppe_(ChatGPT)")
    assert fm["source_llm"] == "chatgpt"
    assert fm["title"] == "Theurgie als Kontrollgruppe (ChatGPT)"
    fm, _ = normalize_frontmatter({}, "2026-03-16_perplexity_foren-suche")
    assert fm["source_llm"] == "perplexity"
    assert fm["title"] == "foren-suche"


def test_ambiguities_only_warn():
    fm, warnings = normalize_frontmatter(
        {"source_llm": "grok, notebooklm, perplexity", "created": "2026-09-14"}, "x")
    assert fm["source_llm"] == "grok, notebooklm, perplexity"
    assert any("several platforms" in w for w in warnings)

    fm, warnings = normalize_frontmatter(
        {"source_llm": "chatgpt", "tags": ["grok", "PDF"], "created": "2026-09-22"},
        "2026-09-21_ChatGPT_x")
    assert fm["tags"] == ["grok", "PDF"]
    assert any("other platforms" in w for w in warnings)
    assert any("differs from created" in w for w in warnings)


# ── normalize_file ──────────────────────────────────────────────────────

def test_body_is_kept_byte_for_byte_with_crlf(tmp_path):
    body = "\r\n**User:**\r\n\r\nFrage *mit* Umlauten: äöü\r\n"
    path = tmp_path / "2026-03-01_claude_x.md"
    path.write_bytes(("---\r\ntitle: \"X\"\r\ntags: [a, b]\r\nsource_platform: claude.ai\r\n"
                      "source_llm: claude\r\n---" + body).encode("utf-8"))
    result = normalize_file(path, write=True)
    assert result.changed
    raw = path.read_bytes().decode("utf-8")
    assert raw.endswith(body)
    assert "\n" not in raw.replace("\r\n", "")
    assert "source_platform" not in raw
    assert "tags:\r\n  - a\r\n  - b" in raw
    assert normalize_file(path, write=True).changed is False


def test_invalid_yaml_is_repaired(tmp_path):
    path = tmp_path / "n.md"
    path.write_bytes(b"---\ntitle: 'Britain's Escape Plan', MMT\nsource_llm: chatgpt\n---\nBody\n")
    result = normalize_file(path, write=True)
    assert "invalid YAML, parsed leniently" in result.warnings
    note = read_note(path)
    assert note.repaired is False
    assert note.fm["title"] == "'Britain's Escape Plan', MMT"
    assert note.body == "Body\n"


def test_note_without_frontmatter_gets_one(tmp_path):
    path = tmp_path / "2026-01-02_grok_frage.md"
    path.write_text("Nur Text\n", encoding="utf-8")
    normalize_file(path, write=True)
    note = read_note(path)
    assert note.fm["source_llm"] == "grok" and str(note.fm["created"]) == "2026-01-02"
    assert note.body.strip() == "Nur Text"


# ── review note ─────────────────────────────────────────────────────────

def test_review_round_trip_keeps_user_edits():
    items = [
        Item(stem="a", title="Erster", platform="claude", created="2026-10-21", words=1200,
             description="Worum es geht.", tags=["BBB", "Karolinger"]),
        Item(stem="b", title="Wetter", platform="chatgpt", created="2026-10-20",
             keep=False, trivial=True),
        Item(stem="c", title="Ungeprüft", triaged=False),
    ]
    text = render_review(items, "de", "KI-Chats/_Verworfen")
    done, parsed = parse_review(text, "de")
    assert done is False
    assert [(i.stem, i.keep, i.trivial, i.triaged) for i in parsed] == [
        ("a", True, False, True), ("c", True, False, False), ("b", False, True, True)]
    assert parsed[0].words == 1200 and parsed[0].created == "2026-10-21"

    edited = (text.replace("- [ ] **Review abgeschlossen", "- [x] **Review abgeschlossen")
                  .replace("**Erster**", "**Erster, besser**")
                  .replace("Tags: BBB, Karolinger", "Tags: BBB, #Merowinger")
                  .replace("- [x] **Erster", "- [ ] **Erster"))
    done, parsed = parse_review(edited, "de")
    first = next(i for i in parsed if i.stem == "a")
    assert done is True
    assert first.title == "Erster, besser" and first.keep is False
    assert first.tags == ["BBB", "Merowinger"]
    assert first.description == "Worum es geht."


# ── triage ──────────────────────────────────────────────────────────────

def test_triage_maps_ids_and_survives_failed_batch(tmp_path):
    notes = []
    for n in range(3):
        path = tmp_path / f"n{n}.md"
        path.write_text(f"---\ntitle: T{n}\n---\nText {n}\n", encoding="utf-8")
        notes.append((path, read_note(path)))
    prompts = []

    def runner(prompt):
        prompts.append(prompt)
        if len(prompts) == 2:
            return None
        return [{"id": "c0", "keep": False, "title": "Neu", "description": "D", "tags": ["x"]}]

    verdicts = triage(notes, ["BBB"], runner, batch_size=2, log=_quiet)
    assert set(verdicts) == {"n0"}
    assert verdicts["n0"]["title"] == "Neu"
    assert "BBB" in prompts[0] and "Text 1" in prompts[0]


# ── scan / apply ────────────────────────────────────────────────────────

CLAUDE_EXPORT = [
    {"uuid": "u-1", "name": "Königtum", "summary": "", "created_at": "2026-06-02T10:00:00Z",
     "updated_at": "2026-06-02T11:00:00Z", "chat_messages": [
        {"sender": "human", "content": [{"type": "text", "text": "Frage"}], "created_at": "2026-06-02T10:00:00Z"},
        {"sender": "assistant", "content": [{"type": "text", "text": "Antwort"}], "created_at": "2026-06-02T10:01:00Z"},
    ]},
    {"uuid": "u-2", "name": "Kurz", "summary": "", "created_at": "2026-06-03T10:00:00Z",
     "updated_at": "2026-06-03T10:00:00Z", "chat_messages": [
        {"sender": "human", "content": [{"type": "text", "text": "Hallo"}], "created_at": "2026-06-03T10:00:00Z"},
    ]},
]


def _runner(prompt):
    import re
    return [{"id": cid, "keep": True, "title": "Germanisches Königtum",
             "description": "Kurz gefasst.", "tags": ["BBB"]}
            for cid in re.findall(r'<conversation id="(c\d+)"', prompt)]


def test_scan_imports_export_once_and_lists_it(tmp_path):
    layout = _layout(tmp_path)
    layout.inbox.mkdir(parents=True)
    (layout.inbox / "conversations.json").write_text(json.dumps(CLAUDE_EXPORT), encoding="utf-8")
    (layout.inbox / "Geklippt.md").write_text(
        "---\ntitle: Geklippt\nsource: https://claude.ai/share/abc\ncreated: 2026-10-21\n"
        "tags:\n  - clippings\n---\nText\n", encoding="utf-8")

    assert cmd_scan(layout, "de", _runner, no_triage=False, log=_quiet) == 2
    notes = sorted(p.name for p in layout.inbox.glob("*.md"))
    assert notes == ["2026-06-02_claude_koenigtum.md", "Geklippt.md"]
    imported = read_note(layout.inbox / "2026-06-02_claude_koenigtum.md")
    assert imported.fm["source"] == "https://claude.ai/chat/u-1"
    assert not (layout.inbox / "conversations.json").exists()
    assert list((tmp_path / ".archilles" / "chat_exports").iterdir())

    review = layout.review.read_text(encoding="utf-8")
    assert review.count("%%id:") == 2 and "Germanisches Königtum" in review

    # Same export again: nothing new, review untouched.
    (layout.inbox / "conversations.json").write_text(json.dumps(CLAUDE_EXPORT), encoding="utf-8")
    assert cmd_scan(layout, "de", _runner, no_triage=False, log=_quiet) == 0
    assert layout.review.read_text(encoding="utf-8") == review


def test_failed_triage_is_retried(tmp_path):
    layout = _layout(tmp_path)
    layout.inbox.mkdir(parents=True)
    (layout.inbox / "a.md").write_text("---\ntitle: A\n---\nText\n", encoding="utf-8")
    cmd_scan(layout, "de", lambda _p: None, no_triage=False, log=_quiet)
    _, items = parse_review(layout.review.read_text(encoding="utf-8"), "de")
    assert items[0].triaged is False
    assert cmd_scan(layout, "de", _runner, no_triage=False, log=_quiet) == 1
    _, items = parse_review(layout.review.read_text(encoding="utf-8"), "de")
    assert items[0].triaged is True and items[0].title == "Germanisches Königtum"


def test_apply_files_ticked_and_rejects_the_rest(tmp_path):
    layout = _layout(tmp_path)
    layout.inbox.mkdir(parents=True)
    for name, created in (("keep", "2026-06-02"), ("drop", "2026-06-03")):
        (layout.inbox / f"{name}.md").write_text(
            f"---\ntitle: {name}\nsource_llm: claude\nsource: https://claude.ai/chat/{name}\n"
            f"created: {created}\n---\nText\n", encoding="utf-8")
    cmd_scan(layout, "de", _runner, no_triage=True, log=_quiet)
    text = layout.review.read_text(encoding="utf-8")
    assert cmd_apply(layout, "de", log=_quiet) == 0          # not marked done yet

    text = (text.replace("- [ ] **Review", "- [x] **Review")
                .replace("- [x] **drop**", "- [ ] **drop**")
                .replace("**keep**", "**Königtum und Recht**"))
    text = text.replace("Tags: \n", "Tags: BBB\n")
    layout.review.write_text(text, encoding="utf-8")

    assert cmd_apply(layout, "de", log=_quiet) == 1
    filed = layout.chats / "2026-06" / "2026-06-02_claude_koenigtum-und-recht.md"
    note = read_note(filed)
    assert note.fm["title"] == "Königtum und Recht" and note.fm["tags"] == ["BBB"]
    assert (layout.rejected / "drop.md").exists()
    assert not list(layout.inbox.glob("*.md"))
    ledger = json.loads((tmp_path / ".archilles" / "chat_inbox.json").read_text(encoding="utf-8"))
    assert ledger["seen"]["https://claude.ai/chat/drop"]["decision"] == "rejected"
    assert "Nichts offen." in layout.review.read_text(encoding="utf-8")


def test_vault_index_ignores_untitled_stems():
    idx = VaultIndex(stems={"2026-05-01_claude_untitled"}, sources=set(),
                     date_titles={("2026-05-01", "untitled")})
    assert not idx.knows("2026-05-01_claude_untitled.md", "u", "2026-05-01", "Untitled")
    idx.stems.add("2026-05-01_claude_thema")
    assert idx.knows("2026-05-01_claude_thema.md", "u", "2026-05-01", "Thema")
