# MCP Integration Guide

> **Status**: Documentation in progress

## What is MCP?

The [Model Context Protocol](https://modelcontextprotocol.io/) (MCP) is a standardized way for AI assistants to access external tools and data sources.

Archilles implements an MCP server, allowing Claude and other MCP-compatible assistants to search your Calibre library directly.

## Setup for Claude Desktop

> **Coming soon**: Detailed Claude Desktop configuration

### Prerequisites

- Claude Desktop installed
- Archilles indexed library

### Configuration

```json
{
  "mcpServers": {
    "archilles": {
      "command": "python",
      "args": ["/path/to/archilles/mcp_server.py"],
      "env": {
        "CALIBRE_LIBRARY": "/path/to/your/Calibre Library"
      }
    }
  }
}
```

## Available Tools

### `search_library`

Search your Calibre library semantically.

**Parameters**:
- `query` (string): Search query
- `mode` (string): "semantic", "keyword", or "hybrid" (default)
- `language` (string, optional): Filter by language
- `tag_filter` (array, optional): Filter by Calibre tags

**Example**:
```
Claude, search my library for discussions of medieval trade routes
```

### `list_books`

> **Coming soon**

### `get_book_info`

> **Coming soon**

## Usage Examples

> **Coming soon**: Practical examples of using Archilles through Claude

## Troubleshooting

See [TROUBLESHOOTING.md](TROUBLESHOOTING.md) for MCP-specific issues.

## Other MCP Clients

Archilles should work with any MCP-compatible client. Configuration may vary.

---

For technical details about the MCP implementation, see [ARCHITECTURE.md](ARCHITECTURE.md).
