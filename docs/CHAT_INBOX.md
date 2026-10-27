# Chat Inbox: Filing AI Chats into an Obsidian Vault

Conversations with Claude, ChatGPT, Gemini, Perplexity and others are worth keeping
when they carry research, and noise when they don't. The chat inbox keeps an archive
of them in an Obsidian vault without hand-written frontmatter: every new chat lands in
one folder, Claude sorts trivial from substantive and proposes title, summary and tags,
you decide in a single review note, and the routine files and indexes the rest.

Script: `scripts/chat_inbox.py`. It runs as the first step of the vault's routine.

---

## How it works

```
Web Clipper note ─┐
Claude export ────┼─► KI-Chats/_Eingang ─► review note ─► KI-Chats/YYYY-MM/   (ticked)
ChatGPT export ───┘   (not indexed)        (you tick)     KI-Chats/_Verworfen (unticked)
```

Each routine run does two things, in this order:

1. **File** — if the review note is ticked as done, the ticked chats move to
   `KI-Chats/YYYY-MM/<date>_<platform>_<slug>.md`, with the title, summary and tags
   from the review note written into their frontmatter. Unticked chats move to
   `KI-Chats/_Verworfen/`. Nothing is deleted.
2. **Scan** — new chats in the inbox are prepared:
   - Exports (`conversations.json` or the export ZIP from Claude or ChatGPT) are
     unpacked into one note per conversation. Conversations the vault already holds
     are skipped. The processed export moves to `.archilles/chat_exports/`.
   - The frontmatter of every inbox note is brought to the shared schema (below).
   - Claude (`claude -p`, the Haiku model, on your Claude subscription — no API key)
     reads each chat and proposes keep or trivial, a title, a two-sentence summary
     and tags taken from the tags the vault already uses.
   - The result is written to the review note `_INBOX/KI-Chat-Review.md`.

The routine then indexes the vault as usual. Filed chats are found by search; the
inbox, the rejected folder and the review note are not.

---

## Setup

### 1. Switch it on for the vault

In `~/.archilles/config.json`, add a `chat_inbox` block to the vault's source:

```json
{
  "name": "my-vault",
  "adapter": "obsidian",
  "path": "D:\\MyVault",
  "chat_inbox": {"lang": "de"}
}
```

`lang` sets the language of the review note and of the proposed titles and summaries
(`en` or `de`). An empty block `{}` uses English.

### 2. Keep the inbox out of the index

In the vault's `.archilles/config.json`, add to `exclude_patterns`:

```json
"exclude_patterns": [
  "KI-Chats/_Eingang/*",
  "KI-Chats/_Verworfen/*",
  "_INBOX/KI-Chat-Review.md"
]
```

### 3. Claude Code

The triage calls the `claude` command line tool. It must be installed and logged in.
Without it, run the script with `--no-triage`: the chats are still listed for review,
just without proposals.

### 4. Obsidian Web Clipper template (optional)

To clip chats straight into the inbox, import this template in the Web Clipper
settings (*Templates → Import*). It opens automatically on the chat sites listed
under `triggers`.

```json
{
  "schemaVersion": "0.1.0",
  "name": "KI-Chat",
  "behavior": "create",
  "noteContentFormat": "{{content}}",
  "properties": [
    {"name": "title", "value": "{{title}}", "type": "text"},
    {"name": "type", "value": "chat", "type": "text"},
    {"name": "source", "value": "{{url}}", "type": "text"},
    {"name": "created", "value": "{{date|date:\"YYYY-MM-DD\"}}", "type": "date"}
  ],
  "triggers": [
    "https://claude.ai/",
    "https://chatgpt.com/",
    "https://gemini.google.com/",
    "https://www.perplexity.ai/",
    "https://grok.com/",
    "https://notebook.google.com/",
    "https://search.brave.com/ask",
    "/^https:\\/\\/www\\.google\\.com\\/search\\?.*udm=50/"
  ],
  "noteNameFormat": "{{date|date:\"YYYY-MM-DD\"}} {{title|safe_name}}",
  "path": "KI-Chats/_Eingang"
}
```

Keeping `source` matters: the platform is read from the URL, and the URL is what
recognises a chat that is already in the archive.

---

## Daily use

1. **Collect.** Clip a chat with the Web Clipper, or drop a platform export into
   `KI-Chats/_Eingang`. Notes moved there by hand work too.
2. **Run.** The routine runs at logon. To start it now: web UI → **⚙️ Setup** → pick
   the vault in the **Library** list at the top → **▶️ Run now**.
3. **Review.** Open `_INBOX/KI-Chat-Review.md` in Obsidian (Live Preview or Reading
   view, so the checkboxes are clickable):
   - Ticked chats go into the archive, unticked ones are set aside. *Suggestions* come
     ticked, *Probably trivial* unticked; change either.
   - Title, summary and tags can be edited right in the note.
   - Chats Claude could not assess are listed under *Not pre-sorted* and retried on
     the next run.
4. **Release.** Tick **Review done** at the top of the note.
5. **Run again.** The next run files the chats and indexes them.

### Duplicates

Exports are checked against the archive automatically. Clipped notes are checked by
their `source` URL — a clip without a URL, or a chat already in the archive under a
different URL, is not recognised. Untick it in the review.

---

## Frontmatter schema

Every chat note — new or archived — uses these keys, in this order:

```yaml
title: ...
type: chat
source_llm: claude        # claude, chatgpt, gemini, perplexity, grok, notebooklm, …
model: ...
source: https://...       # the chat's URL
authors: [...]
created: YYYY-MM-DD
modified: YYYY-MM-DD
description: ...          # the summary
chunking_strategy: ...
message_count: ...
tags: [...]
```

Other keys are kept after these. Older variants are mapped onto the schema (German
keys such as `titel`/`datum`, `date`, `author`, platform names in any spelling); the
platform is taken from the URL or the file name when it is missing.

To bring an existing archive to the schema:

```bash
python scripts/chat_inbox.py normalize D:\MyVault           # dry run: what would change
python scripts/chat_inbox.py normalize D:\MyVault --apply   # write it
```

Only frontmatter is rewritten; the chat text and line endings stay as they are.
Notes it cannot settle (two platforms in one note, contradicting dates) are reported,
not changed. Commit the vault before `--apply` if it is under version control.

---

## Command line

```bash
python scripts/chat_inbox.py run   D:\MyVault --lang de   # file, then scan (what the routine does)
python scripts/chat_inbox.py scan  D:\MyVault --no-triage # list new chats without asking Claude
python scripts/chat_inbox.py apply D:\MyVault             # file a finished review only
```

Options: `--chats-folder` (default `KI-Chats`), `--inbox-folder` (`_Eingang`),
`--rejected-folder` (`_Verworfen`), `--review-note` (`_INBOX/KI-Chat-Review.md`),
`--model` (`haiku`).

---

## Limits

- A conversation that continues after it was filed is not updated in the archive.
- Edits to notes already in the index are not picked up by the routine yet: it adds new
  notes and removes deleted ones, but does not re-index changed ones. This affects
  every Obsidian vault, not only the chat archive.
- Gemini Notebook (formerly NotebookLM) has no export; clip its chats instead.
