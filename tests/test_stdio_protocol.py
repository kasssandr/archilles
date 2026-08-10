"""Protocol handling of the hand-written stdio JSON-RPC loop.

The stdio path does not use the MCP SDK — it speaks JSON-RPC directly — so
protocol compliance is ours to keep. MCP 2026-07-28 removed the
initialize/initialized handshake: modern clients put protocol version, client
info and capabilities in ``_meta`` on every request. ARCHILLES serves both
eras from the same process, so these tests pin down both.
"""

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp_server import (  # noqa: E402
    ERR_INVALID_PARAMS,
    ERR_METHOD_NOT_FOUND,
    ERR_UNSUPPORTED_PROTOCOL_VERSION,
    LATEST_LEGACY_PROTOCOL_VERSION,
    META_CLIENT_CAPABILITIES,
    META_CLIENT_INFO,
    META_PROTOCOL_VERSION,
    META_SERVER_INFO,
    MODERN_PROTOCOL_VERSIONS,
    SUPPORTED_PROTOCOL_VERSIONS,
    build_response,
    is_modern_request,
    negotiate_protocol_version,
)

TOOLS = [
    {
        "name": "list_tags",
        "description": "List all tags in the library",
        "inputSchema": {"type": "object", "properties": {}},
    }
]


@pytest.fixture
def server():
    srv = MagicMock()
    srv.instance_name = "archilles-test"
    srv.list_tags_tool = MagicMock(return_value={"tags": ["History", "Fiction"]})
    return srv


def _modern_meta(version=MODERN_PROTOCOL_VERSIONS[0], **extra):
    meta = {
        META_PROTOCOL_VERSION: version,
        META_CLIENT_CAPABILITIES: {},
        META_CLIENT_INFO: {"name": "TestClient", "version": "1.0.0"},
    }
    meta.update(extra)
    return meta


def _request(method, request_id=1, params=None, modern=False):
    params = dict(params or {})
    if modern:
        params["_meta"] = params.get("_meta", _modern_meta())
    req = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params:
        req["params"] = params
    return req


# ---------------------------------------------------------------------------
# Era detection
# ---------------------------------------------------------------------------

class TestEraDetection:
    def test_meta_protocol_version_marks_modern(self):
        assert is_modern_request(_request("tools/list", modern=True))

    def test_absent_meta_marks_legacy(self):
        assert not is_modern_request(_request("tools/list"))

    def test_unrelated_meta_keys_do_not_mark_modern(self):
        # progressToken is a legacy _meta key and says nothing about the era.
        req = _request("tools/list", params={"_meta": {"progressToken": "abc"}})
        assert not is_modern_request(req)

    def test_missing_params_is_not_modern(self):
        assert not is_modern_request({"jsonrpc": "2.0", "id": 1, "method": "x"})


# ---------------------------------------------------------------------------
# Version negotiation (legacy initialize)
# ---------------------------------------------------------------------------

class TestNegotiateProtocolVersion:
    @pytest.mark.parametrize("version", ["2025-11-25", "2025-06-18", "2024-11-05"])
    def test_supported_version_is_echoed(self, version):
        assert negotiate_protocol_version(version) == version

    def test_unknown_version_falls_back_to_newest_legacy(self):
        assert negotiate_protocol_version("1900-01-01") == LATEST_LEGACY_PROTOCOL_VERSION

    def test_missing_version_falls_back_to_newest_legacy(self):
        assert negotiate_protocol_version(None) == LATEST_LEGACY_PROTOCOL_VERSION

    def test_modern_version_is_not_offered_to_a_legacy_client(self):
        # A legacy client sending initialize cannot speak a handshake-free
        # revision, so we must never answer one.
        assert negotiate_protocol_version("2026-07-28") == LATEST_LEGACY_PROTOCOL_VERSION


class TestLegacyInitialize:
    def test_echoes_client_version(self, server):
        resp = build_response(
            server, TOOLS, _request("initialize", params={"protocolVersion": "2025-06-18"})
        )
        assert resp["result"]["protocolVersion"] == "2025-06-18"

    def test_reports_server_identity_and_tools_capability(self, server):
        resp = build_response(
            server, TOOLS, _request("initialize", params={"protocolVersion": "2025-11-25"})
        )
        assert resp["result"]["capabilities"] == {"tools": {}}
        assert resp["result"]["serverInfo"]["name"] == "archilles-test"

    def test_legacy_result_carries_no_modern_fields(self, server):
        resp = build_response(
            server, TOOLS, _request("initialize", params={"protocolVersion": "2024-11-05"})
        )
        assert "resultType" not in resp["result"]
        assert "_meta" not in resp["result"]

    def test_initialize_is_unknown_to_modern_clients(self, server):
        resp = build_response(server, TOOLS, _request("initialize", modern=True))
        assert resp["error"]["code"] == ERR_METHOD_NOT_FOUND


# ---------------------------------------------------------------------------
# Statelessness: no handshake required
# ---------------------------------------------------------------------------

class TestNoHandshakeRequired:
    def test_modern_tools_list_without_initialize(self, server):
        resp = build_response(server, TOOLS, _request("tools/list", modern=True))
        assert resp["result"]["tools"] == TOOLS

    def test_modern_tools_call_without_initialize(self, server):
        resp = build_response(
            server,
            TOOLS,
            _request("tools/call", params={"name": "list_tags", "arguments": {}}, modern=True),
        )
        payload = json.loads(resp["result"]["content"][0]["text"])
        assert payload == {"tags": ["History", "Fiction"]}
        assert "isError" not in resp["result"]

    def test_legacy_tools_list_without_initialize(self, server):
        # Legacy clients are not required to have completed a handshake either;
        # the loop never tracked it.
        resp = build_response(server, TOOLS, _request("tools/list"))
        assert resp["result"]["tools"] == TOOLS

    def test_repeated_calls_are_independent(self, server):
        first = build_response(server, TOOLS, _request("tools/list", request_id=1, modern=True))
        second = build_response(server, TOOLS, _request("tools/list", request_id=2, modern=True))
        assert first["result"]["tools"] == second["result"]["tools"]
        assert (first["id"], second["id"]) == (1, 2)


# ---------------------------------------------------------------------------
# Modern result shape
# ---------------------------------------------------------------------------

class TestModernResultShape:
    def test_result_declares_complete_result_type(self, server):
        resp = build_response(server, TOOLS, _request("tools/list", modern=True))
        assert resp["result"]["resultType"] == "complete"

    def test_result_identifies_the_server(self, server):
        resp = build_response(server, TOOLS, _request("tools/list", modern=True))
        assert resp["result"]["_meta"][META_SERVER_INFO]["name"] == "archilles-test"

    def test_unknown_meta_keys_are_ignored(self, server):
        meta = _modern_meta(**{
            "traceparent": "00-0af7651916cd43dd8448eb211c80319c-00f067aa0ba902b7-01",
            "com.example/custom": {"anything": True},
        })
        resp = build_response(server, TOOLS, _request("tools/list", params={"_meta": meta}))
        assert resp["result"]["tools"] == TOOLS


# ---------------------------------------------------------------------------
# Modern metadata validation
# ---------------------------------------------------------------------------

class TestModernMetaValidation:
    def test_unsupported_version_is_rejected_with_supported_list(self, server):
        meta = _modern_meta(version="1900-01-01")
        resp = build_response(server, TOOLS, _request("tools/list", params={"_meta": meta}))
        error = resp["error"]
        assert error["code"] == ERR_UNSUPPORTED_PROTOCOL_VERSION
        assert error["data"]["requested"] == "1900-01-01"
        assert error["data"]["supported"] == list(SUPPORTED_PROTOCOL_VERSIONS)

    def test_legacy_version_in_modern_meta_is_rejected(self, server):
        # 2025-11-25 has no per-request _meta; announcing it there is a
        # protocol error, not a downgrade we can honour.
        meta = _modern_meta(version="2025-11-25")
        resp = build_response(server, TOOLS, _request("tools/list", params={"_meta": meta}))
        assert resp["error"]["code"] == ERR_UNSUPPORTED_PROTOCOL_VERSION

    def test_missing_client_capabilities_is_invalid_params(self, server):
        meta = _modern_meta()
        del meta[META_CLIENT_CAPABILITIES]
        resp = build_response(server, TOOLS, _request("tools/list", params={"_meta": meta}))
        assert resp["error"]["code"] == ERR_INVALID_PARAMS

    def test_client_info_is_optional(self, server):
        meta = _modern_meta()
        del meta[META_CLIENT_INFO]
        resp = build_response(server, TOOLS, _request("tools/list", params={"_meta": meta}))
        assert "error" not in resp


# ---------------------------------------------------------------------------
# server/discover
# ---------------------------------------------------------------------------

class TestServerDiscover:
    def test_lists_supported_versions_and_capabilities(self, server):
        resp = build_response(server, TOOLS, _request("server/discover", modern=True))
        result = resp["result"]
        assert result["supportedVersions"] == list(SUPPORTED_PROTOCOL_VERSIONS)
        assert result["capabilities"] == {"tools": {}}
        assert result["_meta"][META_SERVER_INFO]["name"] == "archilles-test"

    def test_answers_a_dual_era_probe_without_meta(self, server):
        # The stdio backward-compatibility probe may arrive before the client
        # knows our era; answering it is what identifies us as modern.
        resp = build_response(server, TOOLS, _request("server/discover"))
        assert MODERN_PROTOCOL_VERSIONS[0] in resp["result"]["supportedVersions"]


# ---------------------------------------------------------------------------
# Errors, notifications, tool dispatch
# ---------------------------------------------------------------------------

class TestErrorsAndNotifications:
    def test_notification_gets_no_response(self, server):
        assert build_response(
            server, TOOLS, {"jsonrpc": "2.0", "method": "notifications/initialized"}
        ) is None

    def test_unknown_method_is_method_not_found(self, server):
        resp = build_response(server, TOOLS, _request("resources/list", modern=True))
        assert resp["error"]["code"] == ERR_METHOD_NOT_FOUND

    def test_tools_call_without_name_is_invalid_params(self, server):
        resp = build_response(server, TOOLS, _request("tools/call", params={}, modern=True))
        assert resp["error"]["code"] == ERR_INVALID_PARAMS

    def test_unknown_tool_is_reported_as_tool_error(self, server):
        # A tool that does not exist is a tool-level failure, not a protocol
        # one: the model should see it and be able to correct itself.
        resp = build_response(
            server, TOOLS, _request("tools/call", params={"name": "nope"}, modern=True)
        )
        assert resp["result"]["isError"] is True
        assert "error" not in resp

    def test_failing_tool_is_reported_as_tool_error(self, server):
        server.list_tags_tool = MagicMock(side_effect=RuntimeError("index unavailable"))
        resp = build_response(
            server, TOOLS, _request("tools/call", params={"name": "list_tags"}, modern=True)
        )
        assert resp["result"]["isError"] is True
        assert "index unavailable" in resp["result"]["content"][0]["text"]

    def test_response_echoes_request_id(self, server):
        resp = build_response(server, TOOLS, _request("tools/list", request_id="abc", modern=True))
        assert resp["id"] == "abc"

    def test_non_ascii_tool_output_survives_serialisation(self, server):
        server.list_tags_tool = MagicMock(return_value={"tags": ["Straßengewalt"]})
        resp = build_response(
            server, TOOLS, _request("tools/call", params={"name": "list_tags"}, modern=True)
        )
        assert "Straßengewalt" in resp["result"]["content"][0]["text"]
