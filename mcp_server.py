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

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from calibre_mcp.server import CalibreMCPServer, create_mcp_tools

# Restore stdout for JSON-RPC communication
sys.stdout = _original_stdout


TOOL_MAP = {
    'get_book_annotations': 'get_book_annotations_tool',
    'search_annotations': 'search_annotations_tool',
    'list_annotated_books': 'list_annotated_books_tool',
    'compute_annotation_hash': 'compute_hash_tool',
    'index_annotations': 'index_annotations_tool',
    'get_index_stats': 'get_index_stats_tool',
    'detect_duplicates': 'detect_duplicates_tool',
    'get_book_details': 'get_book_details_tool',
    'get_doublette_tag_instruction': 'get_doublette_tag_instruction_tool',
    'export_bibliography': 'export_bibliography_tool',
    'list_books_by_author': 'list_books_by_author_tool',
    'list_tags': 'list_tags_tool',
    'search_books_with_citations': 'search_books_with_citations_tool',
    'set_research_interests': 'set_research_interests_tool',
}


async def handle_request(server: CalibreMCPServer, method: str, params: dict) -> dict:
    """Handle an MCP request by dispatching to the appropriate server method."""
    try:
        method_name = TOOL_MAP.get(method)
        if not method_name:
            return {'error': f'Unknown method: {method}'}
        return getattr(server, method_name)(**params)
    except Exception as e:
        logger.error(f"Error handling request {method}: {e}", exc_info=True)
        return {'error': str(e)}


async def stdio_server(server: CalibreMCPServer):
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

    tools = create_mcp_tools(server)
    logger.info(f"Registered {len(tools)} tools")
    for tool in tools:
        logger.info(f"  - {tool['name']}: {tool['description'][:50]}...")

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
                        'serverInfo': {'name': 'archilles', 'version': '1.0.0'}
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
            error_id = request.get('id', -1) if 'request' in locals() and isinstance(request, dict) else -1
            error_response = {
                'jsonrpc': '2.0',
                'id': error_id,
                'error': {'code': -32603, 'message': str(e)}
            }
            sys.stdout.write(json.dumps(error_response) + '\n')
            sys.stdout.flush()


def main():
    """Main entry point."""
    import os

    # Check for CALIBRE_LIBRARY_PATH - required for portable installation
    library_path = os.getenv('CALIBRE_LIBRARY_PATH')

    if not library_path:
        logger.error("CALIBRE_LIBRARY_PATH environment variable not set")
        sys.stderr.write("\n" + "="*60 + "\n")
        sys.stderr.write("ERROR: CALIBRE_LIBRARY_PATH not set\n")
        sys.stderr.write("="*60 + "\n\n")
        sys.stderr.write("Please set the environment variable to your Calibre library:\n\n")
        sys.stderr.write("  Windows (PowerShell):\n")
        sys.stderr.write('    $env:CALIBRE_LIBRARY_PATH = "C:\\path\\to\\Calibre-Library"\n\n')
        sys.stderr.write("  Linux/macOS:\n")
        sys.stderr.write('    export CALIBRE_LIBRARY_PATH="/path/to/Calibre-Library"\n\n')
        sys.stderr.write("  Claude Desktop (claude_desktop_config.json):\n")
        sys.stderr.write('    "env": {"CALIBRE_LIBRARY_PATH": "/path/to/Calibre-Library"}\n\n')
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

    library_path = config.get('calibre_library_path', library_path)
    archilles_dir = Path(library_path) / ".archilles"

    rag_db_path = os.getenv('RAG_DB_PATH') or config.get('rag_db_path', str(archilles_dir / "rag_db"))
    chroma_persist_dir = config.get('chroma_persist_dir', str(archilles_dir / "chroma_db"))

    logger.info(f"Library path: {library_path}")
    logger.info(f"RAG database path: {rag_db_path}")
    logger.info(f"ChromaDB path: {chroma_persist_dir}")

    enable_reranking = config.get('enable_reranking', False)
    reranker_device = config.get('reranker_device', 'cpu')
    if enable_reranking:
        logger.info(f"Cross-encoder reranking enabled (device: {reranker_device})")

    from citation.config import CitationConfig
    citation_config = CitationConfig.from_dict(config.get('citation', {}))
    logger.info(f"Citation style: {citation_config.label} (locale: {citation_config.locale})")

    server = CalibreMCPServer(
        library_path=library_path,
        annotations_dir=None,
        enable_semantic_search=True,
        chroma_persist_dir=chroma_persist_dir,
        rag_db_path=rag_db_path,
        enable_reranking=enable_reranking,
        reranker_device=reranker_device,
        citation_config=citation_config,
    )

    logger.info(f"Server initialized with library: {library_path}")
    logger.info(f"Semantic search enabled: {server.enable_semantic_search}")
    asyncio.run(stdio_server(server))


if __name__ == '__main__':
    main()