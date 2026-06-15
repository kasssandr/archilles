"""Tests for the shared vault-import helpers (finding 8.12)."""

from datetime import datetime

import pytest

from scripts.vault_import import (
    slugify,
    format_date,
    get_month_folder,
    make_filename,
    parse_selection,
    select_conversations,
    render_markdown,
)


# ── slugify ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text,expected", [
    ("Hello World", "hello-world"),
    ("Über Größe", "ueber-groesse"),
    ("Äpfel & Öl", "aepfel-oel"),
    ("  spaces  ", "spaces"),
    ("!!!", "untitled"),
    ("", "untitled"),
    ("a/b\\c:d", "a-b-c-d"),
])
def test_slugify(text, expected):
    assert slugify(text) == expected


def test_slugify_truncates_without_trailing_hyphen():
    out = slugify("word " * 20, max_length=10)
    assert len(out) <= 10
    assert not out.endswith("-")


# ── date helpers ────────────────────────────────────────────────────────

def test_format_date():
    assert format_date(datetime(1951, 3, 2)) == "1951-03-02"
    assert format_date(None) == "unknown"


def test_get_month_folder():
    assert get_month_folder(datetime(1951, 3, 2)) == "1951-03"
    assert get_month_folder(None) == "undated"


def test_make_filename():
    assert make_filename("2020-01-15", "claude", "My Chat!") == "2020-01-15_claude_my-chat.md"


# ── parse_selection ─────────────────────────────────────────────────────

@pytest.mark.parametrize("sel,count,expected", [
    ("all", 3, [0, 1, 2]),
    ("ALL", 2, [0, 1]),
    ("0", 5, [0]),
    ("0,2,4", 5, [0, 2, 4]),
    ("1-3", 5, [1, 2, 3]),
    ("0,3,5-7", 10, [0, 3, 5, 6, 7]),
    ("2,2,2", 5, [2]),            # dedup
    ("0,99", 3, [0]),            # out-of-range filtered
    ("1, ,3,", 5, [1, 3]),       # empty parts ignored (trailing comma safe)
])
def test_parse_selection(sel, count, expected):
    assert parse_selection(sel, count) == expected


# ── select_conversations (interactive) ──────────────────────────────────

def _describe(conv):
    return (conv["date"], conv["n"], conv["title"])


def test_select_conversations_subset(monkeypatch, capsys):
    convs = [{"date": "2020-01-01", "n": 3, "title": f"Chat {i}"} for i in range(5)]
    monkeypatch.setattr("builtins.input", lambda _="": "0,2-3")
    picked = select_conversations(convs, _describe)
    assert picked == [convs[0], convs[2], convs[3]]
    # preview table was printed
    assert "Title" in capsys.readouterr().out


def test_select_conversations_all(monkeypatch):
    convs = [{"date": "2020-01-01", "n": 1, "title": "A"},
             {"date": "2020-01-02", "n": 2, "title": "B"}]
    monkeypatch.setattr("builtins.input", lambda _="": "all")
    assert select_conversations(convs, _describe) == convs


# ── render_markdown ─────────────────────────────────────────────────────

def test_render_markdown_basic():
    fm = ["---", "title: \"X\"", "source_llm: claude", "---"]
    messages = [
        {"role": "user", "text": "Hi"},
        {"role": "assistant", "text": "Hello"},
    ]
    md = render_markdown(fm, "X", messages, "**Claude:**")
    assert md.startswith("---\ntitle: \"X\"\nsource_llm: claude\n---\n\n# X\n")
    assert "**User:**\n\nHi\n" in md
    assert "**Claude:**\n\nHello\n" in md
    assert md.count("---") >= 3  # frontmatter delimiters + message separators


def test_render_markdown_summary_blockquote():
    md = render_markdown(["---", "---"], "T", [], "**Claude:**", summary="A summary")
    assert "> A summary" in md


def test_render_markdown_summary_truncated():
    long = "x" * 600
    md = render_markdown(["---", "---"], "T", [], "**Claude:**", summary=long)
    assert "> " + "x" * 500 in md
    assert "x" * 501 not in md
