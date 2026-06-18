"""Regression tests for PromptBuilder.expand_chunk_context priority.

Small-to-Big retrieval: when a child chunk carries a ``parent_id``, the parent
section (the structural ~2048-token "Big" context) must be preferred over the
pre-computed ±500-char ``window_text``. window_text remains the fallback for the
flat index (chunks without a parent).
"""
from src.archilles.engine.prompting import PromptBuilder


class _FakeStore:
    def __init__(self, parents):
        self._parents = parents  # id -> chunk dict

    def get_by_id(self, chunk_id):
        return self._parents.get(chunk_id)


class _FakeRag:
    def __init__(self, parents=None):
        self.store = _FakeStore(parents or {})


def _pb(parents=None):
    return PromptBuilder(_FakeRag(parents))


def test_parent_text_preferred_over_window_text():
    """A child with a resolvable parent_id gets the parent section, not window_text."""
    parent_text = "PARENT SECTION CONTENT " * 50
    pb = _pb({"p1": {"text": parent_text}})
    chunk = "small child chunk"
    window = chunk + " surrounded by some pre-computed window context " * 3
    out = pb.expand_chunk_context(chunk, {"window_text": window, "parent_id": "p1"})
    assert out == parent_text


def test_window_text_when_no_parent():
    """Flat index (no parent_id): window_text is used when longer than the chunk."""
    pb = _pb()
    chunk = "child"
    window = "child with lots of surrounding window context here"
    out = pb.expand_chunk_context(chunk, {"window_text": window, "parent_id": ""})
    assert out == window


def test_fallback_to_window_when_parent_missing():
    """parent_id present but not in store -> fall back to window_text."""
    pb = _pb({})  # store has no parents
    chunk = "child"
    window = "child plus surrounding window context"
    out = pb.expand_chunk_context(chunk, {"window_text": window, "parent_id": "missing"})
    assert out == window


def test_parent_empty_text_falls_back_to_window():
    """A parent row with empty text must not shadow window_text."""
    pb = _pb({"p1": {"text": ""}})
    chunk = "child"
    window = "child with window context around it"
    out = pb.expand_chunk_context(chunk, {"window_text": window, "parent_id": "p1"})
    assert out == window


def test_returns_chunk_when_nothing_available():
    """No parent, no usable window_text -> original chunk."""
    pb = _pb()
    chunk = "just the chunk text"
    out = pb.expand_chunk_context(chunk, {"window_text": "", "parent_id": ""})
    assert out == chunk
