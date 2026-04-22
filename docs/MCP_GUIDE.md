# MCP Integration Guide

How to connect Archilles to Claude Desktop and use your library through natural language.

---

## What is MCP?

The [Model Context Protocol](https://modelcontextprotocol.io/) (MCP) lets AI assistants like Claude access external tools directly. With Archilles' MCP server running, Claude Desktop can search your Calibre library, retrieve your annotations, and generate citation-ready passages—all from a natural conversation.

This is the **primary way to use Archilles**. The command-line interface exists for indexing and administration; MCP is where the research experience happens.

---

## Prerequisites

1. Archilles installed and configured ([Installation Guide →](INSTALLATION.md))
2. At least a few books indexed (`python scripts/rag_demo.py stats` shows chunks > 0)
3. [Claude Desktop](https://claude.ai/download) installed

---

## Configuration

### Step 1: Find Your Claude Desktop Config File

| Platform | Location |
|----------|----------|
| **Windows** | `%APPDATA%\Claude\claude_desktop_config.json` |
| **macOS** | `~/Library/Application Support/Claude/claude_desktop_config.json` |

If the file doesn't exist yet, create it.

### Step 2: Add Archilles to the Config

Open the file and add the `archilles` entry under `mcpServers`:

**Windows:**
```json
{
  "mcpServers": {
    "archilles": {
      "command": "C:\\Users\\YourName\\archilles\\venv\\Scripts\\python.exe",
      "args": ["C:\\Users\\YourName\\archilles\\mcp_server.py"],
      "env": {
        "ARCHILLES_LIBRARY_PATH": "D:\\My Calibre Library"
      }
    }
  }
}
```

**macOS / Linux:**
```json
{
  "mcpServers": {
    "archilles": {
      "command": "/Users/yourname/archilles/venv/bin/python",
      "args": ["/Users/yourname/archilles/mcp_server.py"],
      "env": {
        "ARCHILLES_LIBRARY_PATH": "/Users/yourname/Calibre Library"
      }
    }
  }
}
```

> **Use the full path to your virtual environment's Python.** Using just `python` or `python3` may not find the right interpreter or Archilles' installed packages.

> **Use forward slashes or escaped backslashes in JSON.** `"D:\\My Calibre Library"` and `"D:/My Calibre Library"` both work on Windows.

### Step 3: Restart Claude Desktop

Close Claude Desktop completely and reopen it. On first start with the new config, the MCP server loads and establishes the connection. Look for the Archilles tools icon (a hammer/wrench symbol) in the Claude Desktop interface.

### Step 4: Verify Connection

In Claude Desktop, ask:
```
What tools do you have available?
```

You should see the Archilles tools listed. If not, see [Troubleshooting →](TROUBLESHOOTING.md).

---

## Available Tools

Archilles exposes the following tools to Claude:

| Tool | What it does |
|------|-------------|
| `search_books_with_citations` | **Main search tool.** Finds relevant passages across all indexed books with citation-ready output (author, title, year, page/chapter). |
| `search_annotations` | Searches your personal highlights, notes, and Calibre comments using the same hybrid search. |
| `list_annotated_books` | Lists all books that have indexed annotations or comments. |
| `get_book_annotations` | Retrieves all annotations for a specific book. |
| `get_book_details` | Returns full metadata for a Calibre book by its ID. |
| `list_tags` | Lists all your Calibre tags with book counts. |
| `export_bibliography` | Exports a bibliography in BibTeX, RIS, Chicago, APA, or other formats. |
| `detect_duplicates` | Finds duplicate books in your library (by title+author, ISBN, or exact title). |
| `compute_annotation_hash` | Technical tool for checking annotation state. |
| `get_doublette_tag_instruction` | Workflow helper for tagging duplicate books in Calibre. |

You don't need to call these tools directly — just ask Claude in natural language and it will use the right tool automatically.

---

## Usage Examples

### Find Passages on a Topic

```
Search my books for discussions of political legitimacy in early modern Europe.
```

```
Find passages about the hard problem of consciousness in my philosophy books.
```

```
What do my sources say about medieval trade routes between the Mediterranean and Northern Europe?
```

### Filter by Language or Tag

```
Search my books for "Rex" but only in Latin texts.
```

```
Find discussions of monetary policy, but only in books tagged "Economics".
```

### Search Your Annotations

```
What did I highlight about consciousness?
```

```
Search my annotations for notes about Hannah Arendt's theory of power.
```

```
Show me everything I've marked in books about the Reformation.
```

### Find Exact Quotes

```
Find the exact quote "in necessariis unitas" in my books.
```

### Compare Sources

```
Search my books for what Arendt writes about power, then search again for what Foucault writes. Compare the two positions based on the passages you find.
```

### Export and Cite

```
Find the five most relevant passages about feudalism in my history books and export them as a BibTeX bibliography.
```

---

## Tips for Better Results

**Be specific:** Instead of "political theory", ask "legitimacy of royal authority in 13th-century France".

**Mention the tool if needed:** "Search my *annotations* for..." vs. "Search my *books* for..." to direct Claude to the right tool.

**Use language filters for mixed libraries:** If you have texts in multiple languages, add "in German texts only" or "in Latin" to narrow results.

**For exact terms:** Latin phrases, proper names, and technical terminology work best with a keyword-style query. Claude will use hybrid search by default, which handles both.

**For exact phrases:** Ask Claude to use the `--exact` mode: "Find the exact phrase 'der kategorische Imperativ' in my books."

---

## Log File

The MCP server writes logs to:

```
~/.archilles/mcp_server.log
```

On Windows: `C:\Users\YourName\.archilles\mcp_server.log`

Check this file if something isn't working — it captures all startup errors, search queries, and any exceptions.

---

## Remote MCP Clients (SSE Transport)

Claude Desktop spawns the MCP server as a subprocess and communicates over **stdio**. Other clients — ChatGPT Desktop, OpenAI Codex, Cursor, VS Code, and any tool that expects a URL rather than a command — communicate over **HTTP/SSE** instead.

Archilles supports both. The SSE mode runs a local HTTP server that any MCP-compatible client can connect to by URL.

### Starting the SSE Server

```bash
# Default: localhost on port 8765
python mcp_server.py --transport sse

# Custom port (e.g. for a second instance)
python mcp_server.py --transport sse --port 8766
```

The server binds exclusively to `127.0.0.1` — it is never reachable from other machines.

Once running, the server is available at:
- **SSE endpoint:** `http://127.0.0.1:8765/sse`
- **Message endpoint:** `http://127.0.0.1:8765/messages/`

### Connecting ChatGPT Desktop

1. Open ChatGPT Desktop → Settings → Connected apps / MCP servers
2. Add a new server and enter the SSE URL: `http://127.0.0.1:8765/sse`
3. Save. ChatGPT will list all Archilles tools and you can use them in any conversation.

### Connecting via Config File (SSE Mode)

You can also set the SSE transport permanently in `.archilles/config.json` inside your Calibre library, so you don't need to pass `--transport sse` every time:

```json
{
  "adapter": "calibre",
  "library_path": "D:\\Calibre-Bibliothek",
  "instance_name": "archilles-bib",
  "transport": {
    "mode": "sse",
    "host": "127.0.0.1",
    "port": 8765
  }
}
```

CLI flags take priority over the config file. `--transport stdio` always starts in stdio mode regardless of config.

### Optional Authentication

If you want a shared secret (useful when multiple users share a machine), add `auth_token` to the transport block:

```json
{
  "transport": {
    "mode": "sse",
    "host": "127.0.0.1",
    "port": 8765,
    "auth_token": "your-shared-secret"
  }
}
```

Clients must then include the header `Authorization: Bearer your-shared-secret` with every request. If no token is set, all localhost requests are accepted.

### Running Multiple Instances in Parallel

Each Archilles instance (e.g. one for your main library, one for a work archive) can run simultaneously — one over stdio, one over SSE, or both over SSE on different ports:

```bash
# Instance 1: Claude Desktop uses stdio (no change to its config)
# Instance 2: second library over SSE on port 8766
ARCHILLES_LIBRARY_PATH="D:\Work-Archive" python mcp_server.py --transport sse --port 8766
```

### Port Already in Use

If port 8765 is taken, the server exits with a clear message:

```
ERROR: Port 8765 is already in use. Use --port to choose another.
```

Pick any free port and pass it via `--port`.

### Windows Firewall

On first start, Windows may show a firewall dialog asking whether to allow Python network access. Since the server only binds to `127.0.0.1`, you can safely click **"Allow access"** — it never accepts connections from outside your machine. If you click "Block", SSE mode will not work; open Windows Firewall settings and add an exception for your Python executable.

### stdio vs. SSE — Which to Use?

| Client | Transport |
|--------|-----------|
| Claude Desktop | **stdio** (keep existing config) |
| ChatGPT Desktop | SSE |
| OpenAI Codex | SSE |
| Cursor / VS Code MCP extension | SSE |
| Any client that expects a URL | SSE |

Do **not** switch Claude Desktop to SSE — it only supports stdio and will stop working if you change its config.

---

## Troubleshooting

See [Troubleshooting Guide →](TROUBLESHOOTING.md) for MCP-specific issues including:
- Tools not appearing in Claude Desktop
- "Tool ran without output" errors
- Library not found errors
- Slow first response (model loading)
