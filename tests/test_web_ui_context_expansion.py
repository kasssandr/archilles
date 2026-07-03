"""Tests for the Web-UI context-expansion priority (review 2026-07-03,
finding 5.5).

``render_result`` checked ``window_text`` first and only fell back to the
parent chunk — the reverse of the 2026-06-18 decision and of
``expand_chunk_context`` (engine/prompting.py:331-339), which prefers the
parent chunk (the whole structural Small-to-Big section) over window_text.
Since hierarchical children *keep* their window_text, the old order meant
the parent chunk was effectively never shown in the UI.
"""

from scripts.web_ui import _resolve_expanded_context


class TestResolveExpandedContext:
    def test_parent_preferred_over_window_text(self):
        result = _resolve_expanded_context(
            text="short",
            window_text="a much longer surrounding window of text",
            parent={"text": "the full structural parent section"},
        )

        assert result == ("parent", "the full structural parent section")

    def test_falls_back_to_window_text_when_no_parent(self):
        result = _resolve_expanded_context(
            text="short",
            window_text="a much longer surrounding window of text",
            parent=None,
        )

        assert result == ("window", "a much longer surrounding window of text")

    def test_falls_back_to_window_text_when_parent_has_no_text(self):
        result = _resolve_expanded_context(
            text="short",
            window_text="a much longer surrounding window of text",
            parent={"text": ""},
        )

        assert result == ("window", "a much longer surrounding window of text")

    def test_window_text_not_used_when_not_longer_than_chunk(self):
        result = _resolve_expanded_context(
            text="a fairly long original chunk of text",
            window_text="shorter",
            parent=None,
        )

        assert result is None

    def test_none_when_nothing_available(self):
        assert _resolve_expanded_context("text", "", None) is None
