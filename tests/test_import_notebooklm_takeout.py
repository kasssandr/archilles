"""Tests for the NotebookLM Takeout importer's chat parser."""

from scripts.import_notebooklm_takeout import _parse_chat_history_html


def test_chat_history_reads_oldest_turn_first(tmp_path):
    # Takeout writes the newest exchange first, each answer above its question.
    html = tmp_path / "Chat Session - x.html"
    html.write_text(
        "MODEL: <p>Second answer</p>\n"
        "USER: <p>Second question</p>\n"
        "MODEL: <p>First answer</p>\n"
        "USER: <p>First question</p>\n",
        encoding="utf-8",
    )

    md = _parse_chat_history_html(html)

    assert md.split("\n\n") == [
        "**User:**\nFirst question",
        "**Gemini:**\nFirst answer",
        "**User:**\nSecond question",
        "**Gemini:**\nSecond answer",
    ]
