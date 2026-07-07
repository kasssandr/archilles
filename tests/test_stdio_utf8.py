"""UTF-8 enforcement on the stdio transport.

On Windows, Python decodes stdin with the locale code page (cp1252) while
MCP clients send UTF-8: a query like 'Straßengewalt' arrived in the server
as 'StraÃŸengewalt', corrupting every non-ASCII (read: every German) query
before it reached the search engine.
"""

import mcp_server


class _FakeStream:
    def __init__(self):
        self.reconfigured_with = None

    def reconfigure(self, **kwargs):
        self.reconfigured_with = kwargs


class _StreamWithoutReconfigure:
    pass


class TestReconfigureStdioUtf8:
    def test_sets_utf8_and_line_buffering(self):
        stdin, stdout = _FakeStream(), _FakeStream()

        mcp_server._reconfigure_stdio_utf8(stdin, stdout)

        for stream in (stdin, stdout):
            assert stream.reconfigured_with is not None
            assert stream.reconfigured_with.get("encoding") == "utf-8"
            assert stream.reconfigured_with.get("line_buffering") is True

    def test_invalid_bytes_must_not_kill_the_read_loop(self):
        stdin, _ = _FakeStream(), None
        mcp_server._reconfigure_stdio_utf8(stdin)
        assert stdin.reconfigured_with.get("errors") == "replace"

    def test_streams_without_reconfigure_are_tolerated(self):
        mcp_server._reconfigure_stdio_utf8(_StreamWithoutReconfigure())  # no raise
