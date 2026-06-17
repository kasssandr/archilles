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
| `list_books_by_author` | Lists all titles by an author straight from Calibre metadata (partial match, optional tag/year filter). The reliable way to find articles and short texts whose author name never appears in the indexed full text. |
| `list_tags` | Lists all your Calibre tags with book counts. |
| `export_bibliography` | Exports a bibliography in BibTeX, RIS, Chicago, APA, or other formats. |
| `detect_duplicates` | Finds duplicate books in your library (by title+author, ISBN, or exact title). |
| `set_research_interests` | Registers project keywords that get a relevance boost in every subsequent search — no re-indexing, switch focus between projects in seconds. |
| `watchdog_scan` | Scans the Calibre library for metadata/annotation changes and new titles, updating the index delta (Calibre-only). See [Keeping Your Index in Sync](#keeping-your-index-in-sync). |
| `compute_annotation_hash` | Technical tool for checking annotation state. |
| `get_doublette_tag_instruction` | Workflow helper for tagging duplicate books in Calibre. |

That is the full set of 13 tools exposed by the single-library server. You don't need to call these tools directly — just ask Claude in natural language and it will use the right tool automatically.

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

**For exact phrases:** Ask for an exact-match search and Claude switches to keyword mode: "Find the exact phrase 'der kategorische Imperativ' in my books." (The `--exact` flag exists on the `rag_demo.py` CLI; over MCP the same effect comes from a keyword-style query.)

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

### ChatGPT Desktop — Current Status and Limitation

**ChatGPT Desktop does not currently support local MCP servers.** The app blocks connections to `localhost` and `127.0.0.1` at the application level, regardless of protocol (HTTP or HTTPS). This is a deliberate policy decision by OpenAI: ChatGPT's MCP integration is designed for publicly reachable remote servers, not local processes.

Archilles supports the modern Streamable HTTP transport (`--transport streamable-http`, MCP spec March 2025), which is technically correct for ChatGPT — once OpenAI allows local servers, the connection should work without any further changes on the Archilles side. Until then, there are two options:

#### Option A: Tunnel (ngrok / Cloudflare Tunnel)

A tunnel exposes your local Archilles server under a public HTTPS URL that ChatGPT accepts.

```bash
# ngrok (requires a free account at ngrok.com)
ngrok http 8765

# or: Cloudflare Tunnel (requires cloudflared to be installed)
cloudflared tunnel --url http://localhost:8765
```

The tunnel prints a URL such as `https://abc123.ngrok-free.app`. Use that URL in ChatGPT Desktop:

1. Start Archilles: `python mcp_server.py --transport streamable-http`
2. Start the tunnel and copy the URL
3. ChatGPT Desktop → Settings → Connected apps / MCP servers → add new server
4. Enter the URL: `https://<tunnel-id>.ngrok-free.app/mcp`

**Privacy note:** With a tunnel, all search queries and results — including excerpts from your books and notes — pass through a third-party server (ngrok or Cloudflare). For researchers working with sensitive sources, unpublished materials, or archival documents, this is a meaningful trade-off. For those working exclusively with published, non-sensitive material, the risk is low.

**Authentication strongly recommended:** If you use a tunnel, set an `auth_token` in your transport config so that anyone who discovers the tunnel URL cannot access your library:

```json
{
  "transport": {
    "mode": "streamable-http",
    "host": "127.0.0.1",
    "port": 8765,
    "auth_token": "your-secret-token"
  }
}
```

#### Option B: Wait

If OpenAI adds localhost support in a future version of ChatGPT Desktop, Archilles will work without any changes — just start with `--transport streamable-http` and enter `https://localhost:8765/mcp` in ChatGPT.

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

| Client | Transport | URL |
|--------|-----------|-----|
| Claude Desktop | **stdio** (keep existing config) | — |
| Cursor / VS Code MCP extension | SSE or Streamable HTTP | `http://127.0.0.1:8765/sse` or `/mcp` |
| OpenAI Codex CLI | Streamable HTTP | `http://127.0.0.1:8765/mcp` |
| ChatGPT Desktop | ⚠ not supported (local servers blocked) | — |
| Any HTTP-based client | SSE or Streamable HTTP | see above |

`--transport sse` uses the classic SSE transport (`/sse` + `/messages/`). `--transport streamable-http` uses the modern Streamable HTTP transport (`/mcp`, single endpoint for GET and POST) per MCP spec March 2025.

Do **not** switch Claude Desktop to SSE — it only supports stdio and will stop working if you change its config.

---

## Keeping Your Index in Sync

Once your library is indexed, every book you edit, every tag you change, every highlight you add in Calibre is a divergence between Calibre and LanceDB. The **Watchdog** (`scripts/watchdog.py`) closes that gap for **Calibre**: a fast scan that detects metadata and annotation changes via hash comparison, updates the LanceDB delta, and queues genuinely new books for the next batch-index run.

After the first scan has seeded its annotation-signature cache, subsequent scans typically finish in a few seconds on a library of a few thousand titles — they reopen only the books whose file signature changed. The first scan itself is slower, because each PDF with embedded highlights is opened once to seed the cache. You only need to run the watchdog periodically — **daily or weekly is enough for most users; monthly is fine for libraries that don't change often**. Hourly schedules are overkill unless you're actively curating in Calibre all day.

> **For Zotero and Obsidian/folder sources** the hash-based watchdog does not yet exist — `watchdog_scan` is currently Calibre-only. The unified scheduled-routines layer (Option E below) covers all three sources by running the appropriate tool per adapter, but for non-Calibre sources it only finds *new* documents, not metadata edits on already-indexed ones. Generalising the watchdog is on the roadmap; until then, the routines layer is the recommended path for Zotero and Obsidian.

### Option A: Claude Routine (easiest if you use Claude)

The MCP server exposes the scan as a tool called `watchdog_scan`. In Claude Desktop, create a Routine that calls it on your preferred schedule (Settings → Routines → New Routine → "Run tool `watchdog_scan`" → pick an interval). No shell, no scheduler, no configuration files.

> Note: `watchdog_scan` is Calibre-only. If your unified config also includes Zotero or an Obsidian vault, those sources are not covered by this tool — use Option E for full multi-source coverage.

### Option B: Windows Task Scheduler

For users who don't run Claude, or who prefer the OS-level scheduler:

1. Open **Task Scheduler** (Win+R → `taskschd.msc`)
2. **Create Basic Task…** → name it "Archilles Watchdog"
3. **Trigger:** Daily (or Weekly / Monthly) at a quiet hour — e.g. 03:00 when you're not using the PC
4. **Action:** Start a program
   - **Program/script:** `C:\Path\To\Python\python.exe`
   - **Arguments:** `C:\Path\To\archilles\scripts\watchdog.py --json`
   - **Start in:** `C:\Path\To\archilles`
5. On the final page, tick **"Open the Properties dialog when I click Finish"**, then under **Actions → Edit** add the environment variable via the **Run whether user is logged on or not** option, or supply it inline by wrapping the command in a small batch file:

   ```bat
   @echo off
   set ARCHILLES_LIBRARY_PATH=D:\Your-Library
   "C:\Path\To\Python\python.exe" "C:\Path\To\archilles\scripts\watchdog.py" --json >> "%TEMP%\archilles_watchdog.log" 2>&1
   ```

   Then point the task at the `.bat` file instead of `python.exe` directly.

The scan writes a human-readable log to `<library>/.archilles/watchdog.log` regardless — the `%TEMP%` redirect above only captures the task's own stdout/stderr for debugging.

### Option C: cron (Linux / macOS)

```cron
# Every night at 03:00
0 3 * * * ARCHILLES_LIBRARY_PATH="/home/you/Calibre-Library" /usr/bin/python3 /home/you/archilles/scripts/watchdog.py --json >> /home/you/archilles-watchdog.log 2>&1

# Once a week on Sundays at 04:00
0 4 * * 0 ARCHILLES_LIBRARY_PATH="/home/you/Calibre-Library" /usr/bin/python3 /home/you/archilles/scripts/watchdog.py --json >> /home/you/archilles-watchdog.log 2>&1
```

Run `crontab -e` to edit your personal crontab. Use `which python3` and `which python` to find the correct interpreter path.

### Option D: launchd (macOS, the native way)

Create `~/Library/LaunchAgents/org.archilles.watchdog.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>                <string>org.archilles.watchdog</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/python3</string>
    <string>/Users/you/archilles/scripts/watchdog.py</string>
    <string>--json</string>
  </array>
  <key>EnvironmentVariables</key>
  <dict>
    <key>ARCHILLES_LIBRARY_PATH</key>
    <string>/Users/you/Calibre-Library</string>
  </dict>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>               <integer>3</integer>
    <key>Minute</key>             <integer>0</integer>
  </dict>
  <key>StandardOutPath</key>      <string>/tmp/archilles-watchdog.log</string>
  <key>StandardErrorPath</key>    <string>/tmp/archilles-watchdog.log</string>
</dict>
</plist>
```

Load it with `launchctl load ~/Library/LaunchAgents/org.archilles.watchdog.plist`. To remove it later, `launchctl unload …` then delete the file.

### Option E: Unified Scheduled Routines (multi-source, Windows)

If your `~/.archilles/config.json` lists more than one source — Calibre, Zotero, an Obsidian vault — the helper `scripts/run_routine.py` covers all of them with a single wrapper. It picks the right tool per adapter (`watchdog.py` for Calibre, `batch_index.py --all --skip-existing` for Zotero and folder/Obsidian), self-throttles via per-library marker files, and writes a structured history that a weekly mailer can summarise.

Install all five tasks at once:

```powershell
powershell.exe -ExecutionPolicy Bypass -File C:\Path\To\archilles\scripts\install_scheduled_routines.ps1
```

This registers (idempotently, no admin rights):

| Task | Trigger / Delay | Frequency in script |
|------|-----------------|---------------------|
| `Archilles-Routine-Calibre` | OnLogon + 5 min | daily |
| `Archilles-Routine-Lab` | OnLogon + 5 min | daily |
| `Archilles-Routine-Zotero` | OnLogon + 5 min | weekly |
| `Archilles-Status-Mail` | OnLogon + 10 min | weekly (first logon of new ISO week) |
| `Archilles-Vault-Linker` | OnLogon + 30 min | monthly + hard-gated on Lab routine |

The trigger fires at every logon; the script decides per run whether work is due (a single marker file in `<library>/.archilles/last_routine_run.txt` makes this idempotent). Missed triggers because the machine was off are picked up at the next logon.

The status mail requires a Gmail App Password in `~/.archilles/secrets.env` (key `GMAIL_APP_PASSWORD`); recipient and sender are hard-coded in the script — adjust before first use if you forked the repo.

Uninstall:

```powershell
Get-ScheduledTask -TaskName 'Archilles-*' | Unregister-ScheduledTask -Confirm:$false
```

For the architectural background and the explicit scope (what the routines layer does *not* do — namely metadata-diff for non-Calibre sources, which is reserved for a future watchdog generalisation), see [ADR-025](DECISIONS.md#adr-025-scheduled-routines--pragmatischer-schritt-a-vor-watchdog-generalisierung-mai-2026) and [ARCHITECTURE.md §8](ARCHITECTURE.md).

### What the Watchdog Actually Does

Each run produces a structured JSON report (with `--json`) and appends a human-readable summary to `<library>/.archilles/watchdog.log`:

| Category | What triggers it | What happens |
|----------|------------------|--------------|
| **New books** | Book exists in Calibre but not in LanceDB | Written to `index_queue.json` for the next `batch_index.py` run |
| **Metadata changed** | Title / author / tags / comments / publisher edited in Calibre | LanceDB updated in place (~1–3 s per book, no re-embedding) |
| **Annotations changed** | Highlights or notes added / removed / edited | Annotation chunks re-indexed for the affected book |
| **Unchanged** | No hash difference | Skipped (the common case) |

New books are queued rather than indexed on the spot because embedding them takes ~90 s per book — you don't want your nightly scan to hold your machine for hours. Run `python scripts/batch_index.py` on your own schedule to drain the queue.

The script exits with code `0` on success, `1` if any book failed — so external monitors can treat non-zero exits as a paging signal.

### Choosing an Interval

| How often you edit Calibre | Suggested schedule |
|----------------------------|--------------------|
| Daily research, frequent tagging / annotating | **Daily** (e.g. 03:00) |
| Steady curation, a few edits per week | **Weekly** (e.g. Sunday 04:00) |
| Mostly static collection, occasional additions | **Monthly** (e.g. 1st of the month) |
| Active re-organisation session | Trigger manually: `python scripts/watchdog.py` |

Intervals shorter than "daily" rarely help — metadata edits aren't time-critical, and running the scan more often doesn't speed up the next `batch_index.py` for new books.

---

## Troubleshooting

See [Troubleshooting Guide →](TROUBLESHOOTING.md) for MCP-specific issues including:
- Tools not appearing in Claude Desktop
- "Tool ran without output" errors
- Library not found errors
- Slow first response (model loading)
