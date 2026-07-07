#!/usr/bin/env python3
"""
ARCHILLES MCP Server Entry Point

Starts the Calibre MCP Server with stdio transport for Claude Desktop integration.
"""

# CRITICAL: Configure logging FIRST - before ANY other imports.
# Libraries (e.g. calibre_mcp.server) call logging.basicConfig() at module level.
# If we let them run first, our own basicConfig() becomes a NO-OP and logs never
# reach the file handler. By configuring logging here with explicit handlers we
# also guarantee that ALL log output goes to sys.stderr, never to stdout, which
# keeps the stdout channel clean for JSON-RPC (MCP protocol).
import sys
import logging
from pathlib import Path

_log_file = Path.home() / ".archilles" / "mcp_server.log"
_log_file.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(str(_log_file), mode='a'),
        logging.StreamHandler(sys.stderr),  # explicit stderr - never stdout
    ],
)
logger = logging.getLogger(__name__)

# Redirect stdout to stderr AFTER logging is configured but BEFORE further imports.
# This catches any stray print() calls in third-party libraries loaded at import time
# so they cannot corrupt the JSON-RPC stream on stdout.
_original_stdout = sys.stdout
sys.stdout = sys.stderr

import asyncio
import json
import threading

# Repo-Wurzel auf den Pfad — kanonische Import-Wurzel ist `src.*` (Review 5.14)
sys.path.insert(0, str(Path(__file__).parent))

from src.calibre_mcp.server import CalibreMCPServer, create_mcp_tools
from src.calibre_mcp.unified_server import UnifiedMCPServer, create_unified_tools

# Restore stdout for JSON-RPC communication
sys.stdout = _original_stdout


TOOL_MAP = {
    'get_book_annotations': 'get_book_annotations_tool',
    'search_annotations': 'search_annotations_tool',
    'list_annotated_books': 'list_annotated_books_tool',
    'compute_annotation_hash': 'compute_hash_tool',
    'detect_duplicates': 'detect_duplicates_tool',
    'get_book_details': 'get_book_details_tool',
    'get_doublette_tag_instruction': 'get_doublette_tag_instruction_tool',
    'export_bibliography': 'export_bibliography_tool',
    'list_books_by_author': 'list_books_by_author_tool',
    'list_tags': 'list_tags_tool',
    'search_books_with_citations': 'search_books_with_citations_tool',
    'set_research_interests': 'set_research_interests_tool',
    'watchdog_scan': 'watchdog_scan_tool',
}


def _start_preload(server, enabled: bool) -> threading.Thread | None:
    """Warm the RAG stack in a background daemon thread (unless disabled).

    Keeps the stdio/HTTP loop responsive during startup: ``initialize`` and
    ``tools/list`` answer immediately while models load. Returns the thread
    (for tests), or None when preloading is disabled.
    """
    if not enabled:
        logger.info("Model preload disabled by config")
        return None
    thread = threading.Thread(
        target=server.preload, name="model-preload", daemon=True
    )
    thread.start()
    logger.info("Model preload started in background thread")
    return thread


def _dispatch_tool(server, tool_name: str, params: dict) -> dict:
    """Dispatch a tool call synchronously. Safe to run in a thread pool.

    ``server`` is either a :class:`CalibreMCPServer` (legacy single-source
    mode) or a :class:`UnifiedMCPServer` (multi-source mode). Tools that
    only exist on the legacy server (``get_doublette_tag_instruction``)
    return a structured error in unified mode rather than raising
    AttributeError.
    """
    method_name = TOOL_MAP.get(tool_name)
    if not method_name:
        return {'error': f'Unknown tool: {tool_name}'}
    method = getattr(server, method_name, None)
    if method is None:
        return {'error': f'Tool {tool_name!r} is not available in this server mode'}
    try:
        return method(**params)
    except Exception as e:
        logger.error(f"Error in tool {tool_name}: {e}", exc_info=True)
        return {'error': str(e)}


async def handle_request(server, method: str, params: dict) -> dict:
    """Handle an MCP request by dispatching to the appropriate server method."""
    return _dispatch_tool(server, method, params)


async def stdio_server(server, tools: list[dict]):
    """
    Run an MCP server using stdio transport.

    Reads JSON-RPC requests from stdin and writes responses to stdout.
    """
    logger.info("Starting ARCHILLES MCP Server (stdio mode)")

    # Ensure line-buffered mode (important on Windows)
    if hasattr(sys.stdin, 'reconfigure'):
        sys.stdin.reconfigure(line_buffering=True)
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(line_buffering=True)

    logger.info(f"Registered {len(tools)} tools")
    for tool in tools:
        logger.info(f"  - {tool['name']}: {tool['description'][:50]}...")

    request_id = None
    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                break

            request = json.loads(line.strip())
            request_id = request.get('id')
            method = request.get('method')
            logger.info(f"Received request: {method or 'unknown'}")

            # Notifications have no id and need no response
            if request_id is None:
                if method != 'notifications/initialized':
                    logger.warning(f"Received notification: {method}")
                else:
                    logger.info("Client sent initialized notification")
                continue

            if method == 'initialize':
                response = {
                    'jsonrpc': '2.0',
                    'id': request_id,
                    'result': {
                        'protocolVersion': '2024-11-05',
                        'capabilities': {'tools': {}},
                        'serverInfo': {'name': server.instance_name, 'version': '1.0.0'}
                    }
                }
            elif method == 'tools/list':
                response = {
                    'jsonrpc': '2.0',
                    'id': request_id,
                    'result': {'tools': tools}
                }
            elif method == 'tools/call':
                tool_name = request['params']['name']
                tool_params = request['params'].get('arguments', {})
                result = await handle_request(server, tool_name, tool_params)

                is_error = isinstance(result, dict) and 'error' in result
                content = [{'type': 'text', 'text': json.dumps(result, indent=2, ensure_ascii=False)}]
                result_payload = {'content': content}
                if is_error:
                    result_payload['isError'] = True

                response = {'jsonrpc': '2.0', 'id': request_id, 'result': result_payload}
            else:
                response = {
                    'jsonrpc': '2.0',
                    'id': request_id,
                    'error': {'code': -32601, 'message': f'Method not found: {method}'}
                }

            sys.stdout.write(json.dumps(response) + '\n')
            sys.stdout.flush()
            logger.info(f"Sent response for request {request_id}")

        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
            continue
        except Exception as e:
            logger.error(f"Error processing request: {e}", exc_info=True)
            error_id = request_id if request_id is not None else -1
            error_response = {
                'jsonrpc': '2.0',
                'id': error_id,
                'error': {'code': -32603, 'message': str(e)}
            }
            sys.stdout.write(json.dumps(error_response) + '\n')
            sys.stdout.flush()


async def sse_server(
    server,
    tools: list[dict],
    host: str = "127.0.0.1",
    port: int = 8765,
    auth_token: str | None = None,
    ssl_certfile: str | None = None,
    ssl_keyfile: str | None = None,
):
    """Run MCP server with SSE transport (for ChatGPT, Codex and other HTTP clients)."""
    import mcp.server as mcp_sdk
    import mcp.types as types
    from mcp.server.sse import SseServerTransport
    from starlette.applications import Starlette
    from starlette.requests import Request
    from starlette.responses import Response
    from starlette.routing import Mount, Route
    import uvicorn

    logger.info(f"Starting ARCHILLES MCP Server (SSE mode) on {host}:{port}")

    mcp_srv = mcp_sdk.Server(server.instance_name)

    sdk_tools = [
        types.Tool(
            name=t["name"],
            description=t["description"],
            inputSchema=t["inputSchema"],
        )
        for t in tools
    ]

    @mcp_srv.list_tools()
    async def list_tools():
        return sdk_tools

    @mcp_srv.call_tool()
    async def call_tool(name: str, arguments: dict | None):
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None, lambda: _dispatch_tool(server, name, arguments or {})
        )
        content = [
            types.TextContent(
                type="text",
                text=json.dumps(result, indent=2, ensure_ascii=False),
            )
        ]
        is_error = isinstance(result, dict) and 'error' in result
        return types.CallToolResult(content=content, isError=is_error)

    sse_transport = SseServerTransport("/messages/")
    init_options = mcp_srv.create_initialization_options()

    def _check_auth(request: Request) -> Response | None:
        if auth_token and request.headers.get("Authorization") != f"Bearer {auth_token}":
            return Response("Unauthorized", status_code=401)
        return None

    def _check_auth_scope(scope) -> Response | None:
        if not auth_token:
            return None
        headers = dict(scope.get("headers", []))
        auth_hdr = headers.get(b"authorization", b"").decode()
        if auth_hdr != f"Bearer {auth_token}":
            return Response("Unauthorized", status_code=401)
        return None

    async def handle_sse(request: Request):
        if (err := _check_auth(request)):
            return err
        async with sse_transport.connect_sse(
            request.scope, request.receive, request._send
        ) as (read_stream, write_stream):
            await mcp_srv.run(read_stream, write_stream, init_options)
        # Starlette's Route wrapper awaits the handler's return value as an ASGI
        # response, so we must return one even though the client has already
        # disconnected by the time we get here.
        return Response(status_code=204)

    async def messages_app(scope, receive, send):
        """ASGI wrapper for ``SseServerTransport.handle_post_message``.

        Mounted (not Routed) so Starlette does not wrap it with
        ``request_response()``: ``handle_post_message`` is already a full ASGI
        app that writes its response via ``send`` and returns ``None`` —
        letting Starlette's wrapper then ``await None(...)`` raises
        ``TypeError: 'NoneType' object is not callable`` on every POST.
        """
        if (err := _check_auth_scope(scope)):
            await err(scope, receive, send)
            return
        await sse_transport.handle_post_message(scope, receive, send)

    app = Starlette(
        routes=[
            Route("/sse", endpoint=handle_sse),
            Mount("/messages/", app=messages_app),
        ]
    )

    scheme = "https" if ssl_certfile else "http"
    logger.info(f"SSE endpoint: {scheme}://{host}:{port}/sse")
    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="warning",
        ssl_certfile=ssl_certfile or None,
        ssl_keyfile=ssl_keyfile or None,
    )
    userver = uvicorn.Server(config)
    try:
        await userver.serve()
    except OSError as e:
        if getattr(e, "errno", 0) in (98, 10048) or "address already in use" in str(e).lower():
            logger.error(f"Port {port} is already in use.")
            sys.stderr.write(f"\nERROR: Port {port} is already in use. Use --port to choose another.\n\n")
            sys.exit(1)
        raise


async def streamable_http_server(
    server,
    tools: list[dict],
    host: str = "127.0.0.1",
    port: int = 8765,
    auth_token: str | None = None,
    ssl_certfile: str | None = None,
    ssl_keyfile: str | None = None,
):
    """Run MCP server with Streamable HTTP transport (for ChatGPT Desktop and modern MCP clients)."""
    import uuid
    import anyio
    import mcp.server as mcp_sdk
    import mcp.types as types
    from mcp.server.streamable_http import StreamableHTTPServerTransport
    from starlette.applications import Starlette
    from starlette.routing import Mount
    import uvicorn

    logger.info(f"Starting ARCHILLES MCP Server (Streamable HTTP mode) on {host}:{port}")

    mcp_srv = mcp_sdk.Server(server.instance_name)

    sdk_tools = [
        types.Tool(
            name=t["name"],
            description=t["description"],
            inputSchema=t["inputSchema"],
        )
        for t in tools
    ]

    @mcp_srv.list_tools()
    async def list_tools():
        return sdk_tools

    @mcp_srv.call_tool()
    async def call_tool(name: str, arguments: dict | None):
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None, lambda: _dispatch_tool(server, name, arguments or {})
        )
        content = [
            types.TextContent(
                type="text",
                text=json.dumps(result, indent=2, ensure_ascii=False),
            )
        ]
        is_error = isinstance(result, dict) and "error" in result
        return types.CallToolResult(content=content, isError=is_error)

    init_options = mcp_srv.create_initialization_options()

    async def mcp_endpoint(scope, receive, send):
        if auth_token:
            headers = dict(scope.get("headers", []))
            auth_hdr = headers.get(b"authorization", b"").decode()
            if auth_hdr != f"Bearer {auth_token}":
                await send({"type": "http.response.start", "status": 401,
                            "headers": [(b"content-type", b"text/plain")]})
                await send({"type": "http.response.body", "body": b"Unauthorized", "more_body": False})
                return
        transport = StreamableHTTPServerTransport(mcp_session_id=str(uuid.uuid4()))
        async with transport.connect() as (read_stream, write_stream):
            async with anyio.create_task_group() as tg:
                tg.start_soon(mcp_srv.run, read_stream, write_stream, init_options)
                await transport.handle_request(scope, receive, send)
                tg.cancel_scope.cancel()

    app = Starlette(routes=[Mount("/mcp", app=mcp_endpoint)])

    scheme = "https" if ssl_certfile else "http"
    logger.info(f"MCP endpoint: {scheme}://{host}:{port}/mcp")

    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="warning",
        ssl_certfile=ssl_certfile or None,
        ssl_keyfile=ssl_keyfile or None,
    )
    userver = uvicorn.Server(config)
    try:
        await userver.serve()
    except OSError as e:
        if getattr(e, "errno", 0) in (98, 10048) or "address already in use" in str(e).lower():
            logger.error(f"Port {port} is already in use.")
            sys.stderr.write(f"\nERROR: Port {port} is already in use. Use --port to choose another.\n\n")
            sys.exit(1)
        raise


def main():
    """Main entry point — picks unified or legacy single-source mode."""
    import argparse
    import os

    parser = argparse.ArgumentParser(description="ARCHILLES MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable-http"],
        default=None,
        help="Transport protocol (default: stdio, or from config.json)",
    )
    parser.add_argument("--host", default=None, help="SSE bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=None, help="SSE port (default: 8765)")
    parser.add_argument("--ssl-certfile", default=None, help="TLS certificate file (enables HTTPS)")
    parser.add_argument("--ssl-keyfile", default=None, help="TLS private key file (enables HTTPS)")
    args = parser.parse_args()

    # ── Mode selection: master config wins over legacy single-source ──
    from src.archilles.config import load_master_config, master_config_path

    try:
        master = load_master_config()
    except (ValueError, json.JSONDecodeError) as e:
        logger.error("Master config %s is malformed: %s", master_config_path(), e)
        sys.stderr.write(f"\nERROR: Master config malformed: {e}\n\n")
        sys.exit(1)

    if master is not None:
        server, tools, transport_cfg, preload_enabled = _init_unified(master)
    else:
        server, tools, transport_cfg, preload_enabled = _init_legacy_single_source()

    _start_preload(server, preload_enabled)

    # Resolve transport from CLI args → config → default (stdio)
    transport_mode = args.transport or transport_cfg.get("mode", "stdio")
    sse_host = args.host or transport_cfg.get("host", "127.0.0.1")
    sse_port = args.port or transport_cfg.get("port", 8765)
    sse_auth_token = transport_cfg.get("auth_token")
    sse_certfile = args.ssl_certfile or transport_cfg.get("ssl_certfile")
    sse_keyfile = args.ssl_keyfile or transport_cfg.get("ssl_keyfile")

    if transport_mode == "sse":
        logger.info(f"Transport: SSE ({sse_host}:{sse_port})")
        asyncio.run(sse_server(server, tools, sse_host, sse_port, sse_auth_token, sse_certfile, sse_keyfile))
    elif transport_mode == "streamable-http":
        logger.info(f"Transport: Streamable HTTP ({sse_host}:{sse_port})")
        asyncio.run(streamable_http_server(server, tools, sse_host, sse_port, sse_auth_token, sse_certfile, sse_keyfile))
    else:
        logger.info("Transport: stdio")
        asyncio.run(stdio_server(server, tools))


def _init_unified(master):
    """Build the unified multi-source server from a parsed master config."""
    server = UnifiedMCPServer.from_master_config(master)
    tools = create_unified_tools(server)
    logger.info(
        "Mode: unified (sources: %s, default: %r)",
        server.source_names, server.default_source,
    )
    return server, tools, dict(master.transport), master.preload_models


def _init_legacy_single_source():
    """Build the single-source server from ARCHILLES_LIBRARY_PATH + library config."""
    import os
    from src.archilles.config import master_config_path

    library_path = os.getenv('ARCHILLES_LIBRARY_PATH') or os.getenv('CALIBRE_LIBRARY_PATH')

    if not library_path:
        master_path = master_config_path()
        logger.error("Neither master config nor ARCHILLES_LIBRARY_PATH is set")
        sys.stderr.write("\n" + "=" * 60 + "\n")
        sys.stderr.write("ERROR: No configuration found\n")
        sys.stderr.write("=" * 60 + "\n\n")
        sys.stderr.write("Provide either:\n\n")
        sys.stderr.write(f"  A) Master config at {master_path} for multi-source mode, OR\n")
        sys.stderr.write("  B) Set ARCHILLES_LIBRARY_PATH for single-source mode:\n\n")
        sys.stderr.write("  Windows (PowerShell):\n")
        sys.stderr.write('    $env:ARCHILLES_LIBRARY_PATH = "C:\\path\\to\\Library"\n\n')
        sys.stderr.write("  Linux/macOS:\n")
        sys.stderr.write('    export ARCHILLES_LIBRARY_PATH="/path/to/Library"\n\n')
        sys.stderr.write("  Claude Desktop (claude_desktop_config.json):\n")
        sys.stderr.write('    "env": {"ARCHILLES_LIBRARY_PATH": "/path/to/Library"}\n\n')
        sys.stderr.flush()
        sys.exit(1)

    config_path = Path(library_path) / ".archilles" / "config.json"
    config = {}
    if config_path.exists():
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            logger.info(f"Loaded config from {config_path}")
        except Exception as e:
            logger.warning(f"Failed to load config: {e}")

    library_path = config.get('library_path', config.get('calibre_library_path', library_path))
    archilles_dir = Path(library_path) / ".archilles"
    instance_name = config.get('instance_name', 'archilles')

    rag_db_path = os.getenv('RAG_DB_PATH') or config.get('rag_db_path', str(archilles_dir / "rag_db"))

    adapter_type = config.get('adapter')  # None = auto-detect
    try:
        from src.adapters import create_adapter
        adapter = create_adapter(Path(library_path), adapter_type)
        logger.info(f"Adapter: {adapter.adapter_type} (instance: {instance_name})")
    except Exception as e:
        logger.warning(f"Could not create adapter: {e} — continuing without adapter")
        adapter = None

    logger.info(f"Library path: {library_path}")
    logger.info(f"Instance: {instance_name}")
    logger.info(f"RAG database path: {rag_db_path}")

    from src.archilles.config import resolve_enable_reranking
    enable_reranking = resolve_enable_reranking(config.get('enable_reranking'))
    reranker_device = config.get('reranker_device', 'cpu')
    if enable_reranking:
        logger.info(f"Cross-encoder reranking enabled (device: {reranker_device})")

    from src.citation.config import CitationConfig
    citation_config = CitationConfig.from_dict(config.get('citation', {}))
    logger.info(f"Citation style: {citation_config.label} (locale: {citation_config.locale})")

    server = CalibreMCPServer(
        library_path=library_path,
        annotations_dir=None,
        rag_db_path=rag_db_path,
        enable_reranking=enable_reranking,
        reranker_device=reranker_device,
        citation_config=citation_config,
        adapter=adapter,
        instance_name=instance_name,
    )
    logger.info(
        "Mode: legacy single-source — server %r (%s)",
        instance_name, adapter.adapter_type if adapter else "no adapter",
    )
    tools = create_mcp_tools(server)
    preload_enabled = bool(config.get("preload_models", True))
    return server, tools, config.get("transport", {}), preload_enabled


if __name__ == '__main__':
    main()