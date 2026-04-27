"""Tests for create_unified_tools schema generation.

Focuses on the per-tool description boilerplate, where
``set_research_interests`` was previously misclassified as a generic
source-optional tool — its description claimed ``Default: <default_source>``
even though omitting ``source`` actually routes to the master file.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.calibre_mcp.unified_server import (
    _AGGREGATION_TOOLS,
    _SOURCE_OPTIONAL,
    create_unified_tools,
)


def _fake_base_tools():
    """Stand-in for create_mcp_tools(seed) — one entry per behaviour we care about."""
    base = {"type": "object", "properties": {"keywords": {"type": "array"}}}
    return [
        {"name": "search_books_with_citations", "description": "agg", "inputSchema": base},
        {"name": "get_book_details", "description": "single-source", "inputSchema": base},
        {"name": "set_research_interests", "description": "split", "inputSchema": base},
    ]


@pytest.fixture
def fake_server():
    """A UnifiedMCPServer-like mock with two sources and one Calibre source."""
    srv = MagicMock()
    srv.servers = {"cal1": MagicMock(), "cal2": MagicMock()}
    srv.source_names = ["cal1", "cal2"]
    srv.calibre_sources = ["cal1"]
    srv.default_source = "cal1"
    return srv


def _tool_by_name(tools, name):
    return next(t for t in tools if t["name"] == name)


def _source_description(tool):
    return tool["inputSchema"]["properties"]["source"]["description"]


def test_set_research_interests_in_source_optional_set():
    """set_research_interests is wired into the schema generator via _SOURCE_OPTIONAL."""
    assert "set_research_interests" in _SOURCE_OPTIONAL
    assert "set_research_interests" not in _AGGREGATION_TOOLS


def test_aggregation_tool_description_says_aggregate(fake_server):
    with patch(
        "src.calibre_mcp.unified_server.create_mcp_tools",
        return_value=_fake_base_tools(),
    ):
        tools = create_unified_tools(fake_server)
    desc = _source_description(_tool_by_name(tools, "search_books_with_citations"))
    assert "aggregate across all sources" in desc.lower()
    assert "default = aggregate" in desc.lower()


def test_get_book_details_description_advertises_default_source(fake_server):
    """For genuinely source-optional-with-default tools, the description must
    name the default source so omitting ``source`` is well-defined."""
    with patch(
        "src.calibre_mcp.unified_server.create_mcp_tools",
        return_value=_fake_base_tools(),
    ):
        tools = create_unified_tools(fake_server)
    desc = _source_description(_tool_by_name(tools, "get_book_details"))
    assert "Default: 'cal1'" in desc


def test_set_research_interests_description_does_not_lie_about_default(fake_server):
    """Regression for bug_009: the auto-generated description previously
    claimed ``Default: <default_source>`` even though omitting ``source`` in
    set_research_interests routes to the *master* file (a separate scope),
    not the default source's library. An LLM following that contract would
    silently store per-library updates in the master file.
    """
    with patch(
        "src.calibre_mcp.unified_server.create_mcp_tools",
        return_value=_fake_base_tools(),
    ):
        tools = create_unified_tools(fake_server)
    desc = _source_description(_tool_by_name(tools, "set_research_interests"))

    # Must NOT advertise a per-source default — that's the misleading part
    assert "Default: 'cal1'" not in desc
    assert "default:" not in desc.lower() or "default = aggregate" not in desc.lower()

    # Must mention the master file path so callers understand where omitted
    # source actually writes
    assert "master" in desc.lower()
    assert "research_interests.json" in desc.lower()


def test_set_research_interests_description_lists_available_sources(fake_server):
    """The description should still enumerate the valid source values for
    LLMs that DO want to scope to a specific library."""
    with patch(
        "src.calibre_mcp.unified_server.create_mcp_tools",
        return_value=_fake_base_tools(),
    ):
        tools = create_unified_tools(fake_server)
    desc = _source_description(_tool_by_name(tools, "set_research_interests"))
    assert "cal1" in desc
    assert "cal2" in desc
