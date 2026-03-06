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

## Other MCP Clients

Archilles should work with any MCP-compatible client (e.g., Cursor, VS Code with MCP extension). The configuration format may vary slightly. The key elements are always the same: point `command` to your Python executable, `args` to `mcp_server.py`, and set `ARCHILLES_LIBRARY_PATH`.

---

## Troubleshooting

See [Troubleshooting Guide →](TROUBLESHOOTING.md) for MCP-specific issues including:
- Tools not appearing in Claude Desktop
- "Tool ran without output" errors
- Library not found errors
- Slow first response (model loading)
