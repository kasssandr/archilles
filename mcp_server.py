#!/usr/bin/env python3
"""
ARCHILLES MCP Server Entry Point

Starts the Calibre MCP Server with stdio transport for Claude Desktop integration.
"""

# CRITICAL: Redirect stdout to stderr BEFORE any imports
# This prevents print() statements from RAG/libraries from corrupting JSON-RPC
import sys
_original_stdout = sys.stdout
sys.stdout = sys.stderr

import asyncio
import json
import logging
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from calibre_mcp.server import CalibreMCPServer, create_mcp_tools

# Restore stdout for JSON-RPC communication
sys.stdout = _original_stdout

# Configure logging to file (not stdout, as that's used for MCP communication)
log_file = Path.home() / ".archilles" / "mcp_server.log"
log_file.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    filename=str(log_file),
    filemode='a'
)
logger = logging.getLogger(__name__)


async def handle_request(server: CalibreMCPServer, method: str, params: dict) -> dict:
    """
    Handle an MCP request by calling the appropriate server method.

    Args:
        server: The CalibreMCPServer instance
        method: The tool method name
        params: The parameters for the method

    Returns:
        Result dictionary
    """
    try:
        # Map tool names to server methods
        tool_map = {
            'get_book_annotations': server.get_book_annotations_tool,
            'search_annotations': server.search_annotations_tool,
            'list_annotated_books': server.list_annotated_books_tool,
            'compute_annotation_hash': server.compute_hash_tool,
            'index_annotations': server.index_annotations_tool,
            'get_index_stats': server.get_index_stats_tool,
            'detect_duplicates': server.detect_duplicates_tool,
            'get_book_details': server.get_book_details_tool,
            'get_doublette_tag_instruction': server.get_doublette_tag_instruction_tool,
            'export_bibliography': server.export_bibliography_tool,
            'search_books_with_citations': server.search_books_with_citations_tool,
        }

        if method in tool_map:
            result = tool_map[method](**params)
            return result
        else:
            return {'error': f'Unknown method: {method}'}

    except Exception as e:
        logger.error(f"Error handling request {method}: {e}", exc_info=True)
        return {'error': str(e)}


async def stdio_server(server: CalibreMCPServer):
    """
    Run an MCP server using stdio transport.

    Reads JSON-RPC requests from stdin and writes responses to stdout.
    """
    logger.info("Starting ARCHILLES MCP Server (stdio mode)")

    # Get tool definitions
    tools = create_mcp_tools(server)

    # Send server info on startup
    server_info = {
        'jsonrpc': '2.0',
        'method': 'server/info',
        'params': {
            'name': 'archilles',
            'version': '1.0.0',
            'capabilities': {
                'tools': tools
            }
        }
    }

    # Log available tools
    logger.info(f"Registered {len(tools)} tools")
    for tool in tools:
        logger.info(f"  - {tool['name']}: {tool['description'][:50]}...")

    # Process requests from stdin
    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                break

            request = json.loads(line.strip())
            logger.info(f"Received request: {request.get('method', 'unknown')}")

            # Handle different request types
            request_id = request.get('id')
            method = request.get('method')

            # Handle notifications (no id, no response needed)
            if request_id is None:
                if method == 'notifications/initialized':
                    logger.info("Client sent initialized notification")
                else:
                    logger.warning(f"Received notification: {method}")
                continue

            if method == 'initialize':
                response = {
                    'jsonrpc': '2.0',
                    'id': request_id,
                    'result': {
                        'protocolVersion': '2024-11-05',
                        'capabilities': {
                            'tools': {}
                        },
                        'serverInfo': {
                            'name': 'archilles',
                            'version': '1.0.0'
                        }
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

                # MCP spec requires result.content array with text/image items
                # Check if tool returned an error
                if isinstance(result, dict) and 'error' in result:
                    response = {
                        'jsonrpc': '2.0',
                        'id': request_id,
                        'result': {
                            'content': [{'type': 'text', 'text': json.dumps(result, indent=2, ensure_ascii=False)}],
                            'isError': True
                        }
                    }
                else:
                    response = {
                        'jsonrpc': '2.0',
                        'id': request_id,
                        'result': {
                            'content': [{'type': 'text', 'text': json.dumps(result, indent=2, ensure_ascii=False)}]
                        }
                    }
            else:
                response = {
                    'jsonrpc': '2.0',
                    'id': request_id,
                    'error': {
                        'code': -32601,
                        'message': f'Method not found: {method}'
                    }
                }

            # Send response
            sys.stdout.write(json.dumps(response) + '\n')
            sys.stdout.flush()
            logger.info(f"Sent response for request {request_id}")

        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
            # Don't send error response - client will timeout and retry
            continue
        except Exception as e:
            logger.error(f"Error processing request: {e}", exc_info=True)
            # Try to extract id from request, fallback to -1 if not available
            error_id = -1
            if 'request' in locals() and isinstance(request, dict):
                error_id = request.get('id', -1)

            error_response = {
                'jsonrpc': '2.0',
                'id': error_id,
                'error': {
                    'code': -32603,
                    'message': str(e)
                }
            }
            sys.stdout.write(json.dumps(error_response) + '\n')
            sys.stdout.flush()


def main():
    """Main entry point."""
    import os

    # Determine library path from environment or default
    # This makes the tool portable across different installations
    default_library = os.getenv('CALIBRE_LIBRARY_PATH', 'D:/Calibre-Bibliothek')

    # Load configuration from .archilles folder within library
    config_path = Path(default_library) / ".archilles" / "config.json"
    config = {}

    if config_path.exists():
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            logger.info(f"Loaded config from {config_path}")
        except Exception as e:
            logger.warning(f"Failed to load config: {e}")

    # Get library path (config overrides environment/default)
    library_path = config.get('calibre_library_path', default_library)

    # Derive paths relative to library - ensures consistency between MCP server and CLI tools
    archilles_dir = Path(library_path) / ".archilles"

    # RAG database for fulltext search (PDF/EPUB chunks)
    default_rag_path = str(archilles_dir / "rag_db")
    rag_db_path = os.getenv('RAG_DB_PATH') or config.get('rag_db_path', default_rag_path)

    # ChromaDB for annotations (highlights/notes)
    default_chroma_path = str(archilles_dir / "chroma_db")
    chroma_persist_dir = config.get('chroma_persist_dir', default_chroma_path)

    logger.info(f"Library path: {library_path}")
    logger.info(f"RAG database path: {rag_db_path}")
    logger.info(f"ChromaDB path: {chroma_persist_dir}")

    # Initialize server
    server = CalibreMCPServer(
        library_path=library_path,
        annotations_dir=None,  # Will auto-detect
        enable_semantic_search=True,
        chroma_persist_dir=chroma_persist_dir,
        rag_db_path=rag_db_path
    )

    logger.info(f"Server initialized with library: {config.get('calibre_library_path', 'D:/Calibre-Bibliothek')}")
    logger.info(f"Semantic search enabled: {server.enable_semantic_search}")

    # Run stdio server
    asyncio.run(stdio_server(server))


if __name__ == '__main__':
    main()