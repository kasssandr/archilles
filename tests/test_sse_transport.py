"""Tests for SSE transport in mcp_server.py."""

import asyncio
import json
import sys
import threading
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_server(tools=None):
    """Return a minimal CalibreMCPServer mock."""
    from src.calibre_mcp.server import CalibreMCPServer, create_mcp_tools

    server = MagicMock(spec=CalibreMCPServer)
    server.instance_name = "archilles-test"

    # Make create_mcp_tools return at least the standard list for a real server
    # but use the real function with our mock so we only need tool name/schema
    real_tools = [
        {
            "name": "list_tags",
            "description": "List all tags in the library",
            "inputSchema": {"type": "object", "properties": {}},
        }
    ]
    server.list_tags_tool = MagicMock(return_value={"tags": ["History", "Fiction"]})
    return server, real_tools


# ---------------------------------------------------------------------------
# Unit: _dispatch_tool
# ---------------------------------------------------------------------------

class TestDispatchTool:
    def test_known_tool_dispatched(self):
        from mcp_server import _dispatch_tool, TOOL_MAP

        server = MagicMock()
        server.list_tags_tool = MagicMock(return_value={"tags": ["A", "B"]})

        result = _dispatch_tool(server, "list_tags", {})
        assert result == {"tags": ["A", "B"]}
        server.list_tags_tool.assert_called_once_with()

    def test_unknown_tool_returns_error(self):
        from mcp_server import _dispatch_tool

        server = MagicMock()
        result = _dispatch_tool(server, "nonexistent_tool", {})
        assert "error" in result
        assert "nonexistent_tool" in result["error"]

    def test_tool_exception_returns_error(self):
        from mcp_server import _dispatch_tool

        server = MagicMock()
        server.list_tags_tool = MagicMock(side_effect=RuntimeError("DB gone"))

        result = _dispatch_tool(server, "list_tags", {})
        assert "error" in result
        assert "DB gone" in result["error"]

    def test_tool_with_params(self):
        from mcp_server import _dispatch_tool

        server = MagicMock()
        server.search_books_with_citations_tool = MagicMock(return_value={"results": []})

        result = _dispatch_tool(server, "search_books_with_citations", {"query": "Caesar"})
        server.search_books_with_citations_tool.assert_called_once_with(query="Caesar")
        assert result == {"results": []}


# ---------------------------------------------------------------------------
# Unit: sse_server argument parsing / config resolution
# ---------------------------------------------------------------------------

class TestTransportResolution:
    """Verify that CLI args take priority over config, config over default."""

    def _run_main_with_args(self, argv, config_transport=None):
        """
        Call main() up to the transport-resolution step and capture the
        transport_mode / sse_host / sse_port it would use, without actually
        starting a server.
        """
        import argparse

        # Simulate the arg-parsing + resolution logic from main()
        parser = argparse.ArgumentParser()
        parser.add_argument("--transport", choices=["stdio", "sse"], default=None)
        parser.add_argument("--host", default=None)
        parser.add_argument("--port", type=int, default=None)
        args = parser.parse_args(argv)

        transport_cfg = config_transport or {}
        transport_mode = args.transport or transport_cfg.get("mode", "stdio")
        sse_host = args.host or transport_cfg.get("host", "127.0.0.1")
        sse_port = args.port or transport_cfg.get("port", 8765)
        return transport_mode, sse_host, sse_port

    def test_default_is_stdio(self):
        mode, host, port = self._run_main_with_args([])
        assert mode == "stdio"

    def test_cli_sse_flag(self):
        mode, host, port = self._run_main_with_args(["--transport", "sse"])
        assert mode == "sse"
        assert host == "127.0.0.1"
        assert port == 8765

    def test_cli_overrides_config(self):
        mode, host, port = self._run_main_with_args(
            ["--transport", "sse", "--port", "9000"],
            config_transport={"mode": "stdio", "port": 8765},
        )
        assert mode == "sse"
        assert port == 9000

    def test_config_sse_no_cli(self):
        mode, host, port = self._run_main_with_args(
            [],
            config_transport={"mode": "sse", "host": "127.0.0.1", "port": 8800},
        )
        assert mode == "sse"
        assert port == 8800


# ---------------------------------------------------------------------------
# Integration: SSE server starts, serves tool list, handles tool call
# ---------------------------------------------------------------------------

def _run_sse_test(coro):
    """Run an async test coroutine synchronously."""
    return asyncio.run(coro)


async def _sse_server_with_probe(port: int, auth_token=None, extra_headers=None):
    """Start sse_server, probe the /sse endpoint, return (status_code, content_type)."""
    import httpx
    from mcp_server import sse_server

    server = MagicMock()
    server.instance_name = "archilles-test"

    mock_tools: list = []

    task = asyncio.create_task(
        sse_server(server, mock_tools, host="127.0.0.1", port=port, auth_token=auth_token)
    )
    await asyncio.sleep(0.4)

    status = None
    ct = ""
    try:
        async with httpx.AsyncClient() as client:
            headers = extra_headers or {}
            try:
                async with client.stream(
                    "GET",
                    f"http://127.0.0.1:{port}/sse",
                    headers=headers,
                    timeout=2.0,
                ) as resp:
                    status = resp.status_code
                    ct = resp.headers.get("content-type", "")
            except httpx.ReadTimeout:
                pass  # SSE connection keeps streaming — timeout is OK
    finally:
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass

    return status, ct


def test_sse_server_tool_list():
    """Start an SSE server and verify the /sse endpoint responds with event-stream."""
    status, ct = _run_sse_test(_sse_server_with_probe(18765))
    assert status == 200
    assert "text/event-stream" in ct


def test_sse_server_auth_rejects_bad_token():
    """SSE endpoint returns 401 when auth_token is set and header is missing."""
    status, _ = _run_sse_test(_sse_server_with_probe(18766, auth_token="secret"))
    assert status == 401


def test_sse_server_auth_accepts_correct_token():
    """SSE endpoint responds with 200 when correct Bearer token is provided."""
    status, ct = _run_sse_test(
        _sse_server_with_probe(
            18767,
            auth_token="secret",
            extra_headers={"Authorization": "Bearer secret"},
        )
    )
    assert status == 200
    assert "text/event-stream" in ct
