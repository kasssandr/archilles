"""Tests for chat_sync: re-importing chat exports into a vault without duplicates."""

import sys
from datetime import datetime
from pathlib import Path

import pytest

from scripts.chat_sync import (
    END_MARKER,
    START_MARKER,
    ChatConversation,
    ChatMessage,
    Syncer,
    VaultIndex,
    chat_id_from_url,
    duplicate_groups,
    parse_note,
    prefix_end,
    provider_from_url,
    read_note,
    set_keys,
)

CHAT_ID = "0b6c3a52-7f4e-4d1a-9c55-2f9e8d7a6b10"

# Distinct, long enough texts so fingerprints can tell the messages apart.
TEXTS = [
    "Wie hängen Bundestheologie und Blutsverwandtschaft in der Spätantike zusammen?",
    "Die Bundestheologie verschiebt Zugehörigkeit von der Abstammung zur Verpflichtung, "
    "und genau darin liegt ihr Bruch mit dem Clan.",
    "Welche Quellen belegen diesen Übergang im vierten Jahrhundert am deutlichsten?",
    "Vor allem die Kanones der Synoden und die Briefe der Kirchenväter zeigen, "
    "wie Verwandtschaft durch Taufpatenschaft ersetzt wird.",
    "Gibt es dazu Gegenpositionen in der neueren Forschung zur Familie?",
    "Ja, einige Historiker betonen die Kontinuität der Hausgemeinschaft "
    "und lesen die Patenschaft als Erweiterung, nicht als Ersatz.",
    "Fasse die beiden Positionen bitte knapp in einer Gegenüberstellung zusammen.",
    "Erstens Bruch durch Verpflichtung, zweitens Kontinuität durch Erweiterung; "
    "beide stützen sich auf dieselben Synodalakten.",
]


def conversation(n: int, chat_id: str = CHAT_ID, ids=None) -> ChatConversation:
    ids = ids or [f"m{i}" for i in range(n)]
    messages = [
        ChatMessage(ids[i], "user" if i % 2 == 0 else "assistant", TEXTS[i])
        for i in range(n)
    ]
    return ChatConversation(
        provider="claude", chat_id=chat_id, title="Bund und Blut", messages=messages,
        assistant_label="**Claude:**", authors="Claude", source_platform="claude.ai",
        created=datetime(2026, 9, 1), updated=datetime(2026, 9, 2),
    )


def sync(vault: Path, conv: ChatConversation, **kw):
    syncer = Syncer(vault, now=datetime(2026, 10, 27, 12, 0, 0), **kw)
    return syncer.sync([conv])


def only(result, kind=None):
    actions = [a for a in result.actions if a.kind != "unchanged"] if kind is None else \
        [a for a in result.actions if a.kind == kind]
    assert len(actions) == 1, result.actions
    return actions[0]


@pytest.fixture
def vault(tmp_path):
    (tmp_path / ".obsidian").mkdir()
    return tmp_path


# ── ids and frontmatter ─────────────────────────────────────────────────

@pytest.mark.parametrize("url,provider,chat_id", [
    (f"https://claude.ai/chat/{CHAT_ID}", "claude", CHAT_ID),
    ("https://chatgpt.com/c/67a1b2c3-0000-8000-9000-abcdef012345", "chatgpt",
     "67a1b2c3-0000-8000-9000-abcdef012345"),
    ("https://chatgpt.com/g/g-abc-scholar/c/6801-aa", "chatgpt", "6801-aa"),
    ("https://www.perplexity.ai/search/was-ist-bund-Ab3_xYz?s=c", "perplexity", "was-ist-bund-Ab3_xYz"),
    ("https://example.org/article", "", ""),
])
def test_ids_from_urls(url, provider, chat_id):
    assert provider_from_url(url) == provider
    assert chat_id_from_url(url) == chat_id


def test_set_keys_keeps_other_lines_verbatim():
    lines = ['title: "Mein Titel"', "tags:", "  - eigene", "modified: 2026-01-01"]
    out = set_keys(lines, {"modified": "2026-10-27", "chat_id": CHAT_ID, "chat_body_hash": ""})
    assert out[:3] == lines[:3]
    assert out[3] == "modified: 2026-10-27"
    assert f"chat_id: {CHAT_ID}" in out
    assert 'chat_body_hash: ""' in out


def test_parse_note_roundtrip_crlf(tmp_path):
    text = "---\r\ntitle: x\r\n---\r\n\r\nBody\r\n"
    note = parse_note(tmp_path / "a.md", text)
    assert note.newline == "\r\n"
    assert note.frontmatter == {"title": "x"}
    assert note.body == "\nBody\n"


# ── first import and plain re-import ────────────────────────────────────

def test_first_import_creates_note_with_sync_state(vault):
    action = only(sync(vault, conversation(4)))
    assert action.kind == "created"
    note = read_note(action.path)
    assert action.path.parent == vault / "KI-Chats" / "2026-09"
    assert note.frontmatter["chat_id"] == CHAT_ID
    assert note.frontmatter["chat_url"] == f"https://claude.ai/chat/{CHAT_ID}"
    assert note.frontmatter["chat_last_message"] == "m3"
    assert note.frontmatter["message_count"] == 4
    assert START_MARKER in note.body and END_MARKER in note.body
    assert TEXTS[3] in note.body


def test_same_export_again_changes_nothing(vault):
    path = only(sync(vault, conversation(4))).path
    before = path.read_bytes()
    result = sync(vault, conversation(4))
    assert [a.kind for a in result.actions] == ["unchanged"]
    assert path.read_bytes() == before
    assert len(list(vault.rglob("*.md"))) == 1


def test_dry_run_writes_nothing(vault):
    result = sync(vault, conversation(4), dry_run=True)
    assert only(result).kind == "created"
    assert not list(vault.rglob("*.md"))


# ── case 1: chat continued since the export ─────────────────────────────

def test_continued_chat_untouched_note_is_regenerated(vault):
    path = only(sync(vault, conversation(4))).path
    action = only(sync(vault, conversation(6)))
    assert action.kind == "updated"
    note = read_note(path)
    assert note.frontmatter["chat_last_message"] == "m5"
    assert TEXTS[5] in note.body
    assert note.body.count(START_MARKER) == 1
    # Still untouched: the next continuation regenerates again.
    assert only(sync(vault, conversation(8))).kind == "updated"


# ── case 2: note edited in Obsidian ─────────────────────────────────────

def _edit(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert old in text
    path.write_text(text.replace(old, new), encoding="utf-8")


def test_edited_note_not_continued_stays_as_is(vault):
    path = only(sync(vault, conversation(4))).path
    _edit(path, TEXTS[1], TEXTS[1] + "\n\nMeine Anmerkung: das gilt nur für den Westen des Reiches.")
    before = path.read_bytes()
    assert [a.kind for a in sync(vault, conversation(4)).actions] == ["unchanged"]
    assert path.read_bytes() == before


def test_additions_kept_and_new_messages_appended(vault):
    path = only(sync(vault, conversation(4))).path
    remark = "Meine Anmerkung: das gilt nur für den Westen des Reiches, nicht für Byzanz."
    _edit(path, TEXTS[1], TEXTS[1] + "\n\n" + remark)

    action = only(sync(vault, conversation(6)))
    assert action.kind == "appended"
    assert "1 own paragraphs kept" in action.detail
    text = path.read_text(encoding="utf-8")
    assert remark in text
    assert text.index(TEXTS[3]) < text.index(TEXTS[4]) < text.index(END_MARKER)
    assert "<!-- archilles:chat:continued 2026-10-27 -->" in text
    assert read_note(path).frontmatter["chat_last_message"] == "m5"


def test_cosmetic_edits_and_deletions_survive(vault):
    path = only(sync(vault, conversation(6))).path
    # Restructure: a heading of one's own, and the superfluous exchange removed.
    _edit(path, "**User:**\n\n" + TEXTS[0], "## Ausgangsfrage\n\n**User:**\n\n" + TEXTS[0])
    _edit(path, "**User:**\n\n" + TEXTS[4] + "\n\n---\n\n**Claude:**\n\n" + TEXTS[5] + "\n\n---\n", "")

    action = only(sync(vault, conversation(8)))
    assert action.kind == "appended"
    assert "form only" in action.detail
    text = path.read_text(encoding="utf-8")
    assert "## Ausgangsfrage" in text
    assert TEXTS[4] not in text and TEXTS[5] not in text   # deletion respected
    assert TEXTS[6] in text and TEXTS[7] in text           # continuation added


def test_user_frontmatter_survives_owned_keys_update(vault):
    path = only(sync(vault, conversation(4))).path
    _edit(path, "tags: [chat-protokoll, KI-generiert]", "tags: [chat-protokoll, Bund, eigene]")
    _edit(path, 'title: "Bund und Blut"', 'title: "Bund statt Blut"')
    sync(vault, conversation(6))
    fm = read_note(path).frontmatter
    assert fm["tags"] == ["chat-protokoll", "Bund", "eigene"]
    assert fm["title"] == "Bund statt Blut"
    assert fm["message_count"] == 6


def test_backup_written_before_change(vault):
    path = only(sync(vault, conversation(4))).path
    original = path.read_text(encoding="utf-8")
    sync(vault, conversation(6))
    backups = list((vault / ".archilles" / "chat-sync-backup").rglob("*.md"))
    assert len(backups) == 1
    assert backups[0].read_text(encoding="utf-8") == original


# ── history changed upstream (edited prompt, other branch) ──────────────

def test_upstream_branch_change_untouched_note_regenerated(vault):
    path = only(sync(vault, conversation(4))).path
    branched = conversation(4, ids=["m0", "m1", "x2", "x3"])
    assert only(sync(vault, branched)).kind == "updated"
    assert read_note(path).frontmatter["chat_last_message"] == "x3"


def test_upstream_branch_change_edited_note_appends_after_prefix(vault):
    path = only(sync(vault, conversation(4))).path
    _edit(path, TEXTS[1], TEXTS[1] + "\n\nEine eigene Randbemerkung mit genug Worten darin.")
    branched = conversation(6, ids=["x0", "x1", "x2", "x3", "x4", "x5"])
    action = only(sync(vault, branched))
    assert action.kind == "appended"
    text = path.read_text(encoding="utf-8")
    assert text.count(TEXTS[0]) == 1 and TEXTS[5] in text


def test_upstream_branch_change_scattered_note_is_conflict(vault):
    path = only(sync(vault, conversation(6))).path
    for i in (0, 1, 2, 3):
        _edit(path, TEXTS[i], "Ganz eigener Ersatztext ohne jede Übereinstimmung Nummer " + str(i))
    before = path.read_bytes()
    branched = conversation(8, ids=[f"x{i}" for i in range(8)])
    assert only(sync(vault, branched)).kind == "conflict"
    assert path.read_bytes() == before


# ── notes without sync state: web clips and old imports ─────────────────

def _clip(vault: Path, name: str, body: str, chat_id: str = CHAT_ID) -> Path:
    path = vault / "Lab-Inbox" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n"
        'title: "Bund und Blut - Claude"\n'
        f'source: "https://claude.ai/chat/{chat_id}"\n'
        "tags:\n  - clippings\n"
        "---\n" + body, encoding="utf-8")
    return path


def test_fragmentary_clip_rebuilt_with_own_paragraphs(vault):
    own = "Wichtig für Kapitel drei: die Patenschaft als juristische Fiktion lesen."
    path = _clip(vault, "Bund und Blut.md",
                 "\nCopy\n\n" + TEXTS[5] + "\n\nRetry\n\n" + own + "\n")
    action = only(sync(vault, conversation(8)))
    assert action.kind == "rebuilt"
    text = path.read_text(encoding="utf-8")
    assert all(t in text for t in TEXTS)
    assert "## Eigene Ergänzungen (aus dem Clip)" in text
    assert own in text
    assert "Retry" not in text
    fm = read_note(path).frontmatter
    assert fm["tags"] == ["clippings"]
    assert fm["chat_last_message"] == "m7"
    assert list((vault / ".archilles" / "chat-sync-backup").rglob("Bund und Blut.md"))
    # From now on it is a managed, untouched note.
    assert [a.kind for a in sync(vault, conversation(8)).actions] == ["unchanged"]


def test_clip_holding_a_prefix_is_adopted(vault):
    body = "\n" + "\n\n".join(TEXTS[:4]) + "\n"
    path = _clip(vault, "Bund.md", body)
    action = only(sync(vault, conversation(8)))
    assert action.kind == "adopted"
    assert "held 4/8" in action.detail
    text = path.read_text(encoding="utf-8")
    assert text.count(TEXTS[0]) == 1 and TEXTS[7] in text
    assert [a.kind for a in sync(vault, conversation(8)).actions] == ["unchanged"]


def _legacy(vault: Path, name: str, n: int) -> Path:
    """A note as the importers wrote it before chat_sync: no id, no markers."""
    path = vault / "KI-Chats" / "2026-09" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "".join(
        f"{'**User:**' if i % 2 == 0 else '**Claude:**'}\n\n{TEXTS[i]}\n\n---\n\n" for i in range(n))
    path.write_text(
        '---\ntitle: "Bund und Blut"\nauthors: [Claude]\ntype: chat\nsource_llm: claude\n'
        f"created: 2026-09-01\nmessage_count: {n}\n---\n\n# Bund und Blut\n\n" + body,
        encoding="utf-8")
    return path


def test_legacy_import_matched_by_fingerprint_and_continued(vault):
    path = _legacy(vault, "2026-09-01_claude_bund-und-blut.md", 4)
    action = only(sync(vault, conversation(6)))
    assert action.kind == "adopted"
    assert "fingerprint" in action.detail
    fm = read_note(path).frontmatter
    assert fm["chat_id"] == CHAT_ID
    assert TEXTS[5] in path.read_text(encoding="utf-8")
    assert len(VaultIndex(vault).notes) == 1


def test_legacy_duplicates_reported_not_deleted(vault):
    first = _legacy(vault, "2026-09-01_claude_bund-und-blut.md", 4)
    second = _legacy(vault, "2026-09-01_claude_bund-und-blut-2.md", 6)
    result = sync(vault, conversation(6))
    adopted = only(result, "adopted")
    duplicate = only(result, "duplicate")
    assert adopted.path == second          # the fuller note carries on
    assert duplicate.path == first
    assert first.exists()


def test_unrelated_note_not_matched(vault):
    other = vault / "KI-Chats" / "andere.md"
    other.parent.mkdir(parents=True)
    other.write_text("---\ntype: chat\nsource_llm: claude\n---\n\n"
                     "Ein völlig anderes Gespräch über Wetter, Gärten und die Bahn im Herbst.\n",
                     encoding="utf-8")
    assert only(sync(vault, conversation(4))).kind == "created"


def test_clip_of_another_chat_never_matched_by_fingerprint(vault):
    _clip(vault, "Fremd.md", "\n" + "\n\n".join(TEXTS[:4]) + "\n",
          chat_id="11111111-2222-3333-4444-555555555555")
    assert only(sync(vault, conversation(4))).kind == "created"


def test_duplicate_groups_finds_double_clips(vault):
    _clip(vault, "A.md", "\nText\n")
    _clip(vault, "B.md", "\nText\n")
    groups = duplicate_groups(VaultIndex(vault))
    assert len(groups) == 1 and len(groups[0]) == 2


def test_prefix_end():
    assert prefix_end([True, True, False, False]) == 1
    assert prefix_end([True, False, True, True]) == 3
    assert prefix_end([False, False, False, True]) is None
    assert prefix_end([False, False]) is None


# ── ChatGPT: the visible branch ─────────────────────────────────────────

def test_chatgpt_follows_current_node(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    sys.modules.pop("import_chatgpt_to_vault", None)
    import import_chatgpt_to_vault as chatgpt

    def node(nid, parent, children, role=None, text=None):
        msg = {"id": nid, "author": {"role": role}, "content": {"parts": [text]}} if role else None
        return {"id": nid, "parent": parent, "children": children, "message": msg}

    conv = {
        "id": "c1", "title": "T", "create_time": 1_760_000_000, "current_node": "a1",
        "mapping": {
            "root": node("root", None, ["u1"]),
            "u1": node("u1", "root", ["a1", "a2"], "user", "Frage"),
            "a1": node("a1", "u1", [], "assistant", "Antwort eins"),
            "a2": node("a2", "u1", [], "assistant", "Antwort zwei"),
        },
    }
    result = chatgpt.to_conversation(conv)
    assert result.chat_id == "c1"
    assert [m.id for m in result.messages] == ["u1", "a1"]
    del conv["current_node"]
    assert [m.id for m in chatgpt.to_conversation(conv).messages] == ["u1", "a2"]


# ── indexing ignores the sync markers ───────────────────────────────────

def test_txt_extractor_drops_sync_markers(vault):
    from src.extractors.txt_extractor import TXTExtractor
    path = only(sync(vault, conversation(4))).path
    _edit(path, END_MARKER, "<!-- archilles:chat:continued 2026-10-27 -->\n" + END_MARKER)
    text = "\n".join(c["text"] for c in TXTExtractor().extract(path).chunks)
    assert "archilles:chat" not in text
    assert TEXTS[3] in text
