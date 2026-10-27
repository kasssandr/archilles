#!/usr/bin/env python3
"""
Import Gemini conversations from Google Takeout HTML into an Obsidian vault.

Google Takeout exports Gemini activity as a single HTML file ("Mein Aktivitaetsverlauf"
or "My Activity") with all prompts and responses in Material Design Lite layout.

Each entry is a content-cell div containing:
- "Eingegebener Prompt:" followed by user text
- A timestamp (e.g. "14.03.2026, 13:08:30 MEZ")
- Gemini's response as HTML

The script groups consecutive entries within a time window into conversations.

Usage:
    python import_gemini_to_vault.py "Mein Aktivitaetsverlauf.html" D:/MyVault
    python import_gemini_to_vault.py activity.html D:/MyVault --dry-run
    python import_gemini_to_vault.py activity.html D:/MyVault --interactive
    python import_gemini_to_vault.py activity.html D:/MyVault --limit 10

Re-running on a newer Takeout is safe: chat_sync recognizes notes it wrote
before (and web clips of the same chat, by fingerprint) and only adds what
is new.
"""

import re
import sys
import html as html_module
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from html.parser import HTMLParser
from typing import Optional

from chat_sync import ChatConversation, ChatMessage, add_sync_arguments, content_id, run_sync
from vault_import import format_date, select_conversations


class HTMLToText(HTMLParser):
    """Strip HTML tags, keep text."""
    def __init__(self):
        super().__init__()
        self._parts = []
        self._in_li = False
        self._ol_count = 0
        self._in_ol = False

    def handle_starttag(self, tag, attrs):
        if tag == "br":
            self._parts.append("\n")
        elif tag == "p":
            self._parts.append("\n\n")
        elif tag in ("strong", "b"):
            self._parts.append("**")
        elif tag in ("em", "i"):
            self._parts.append("*")
        elif tag in ("code", "pre"):
            self._parts.append("`")
        elif tag == "ol":
            self._in_ol = True
            self._ol_count = 0
        elif tag == "ul":
            self._in_ol = False
        elif tag == "li":
            if self._in_ol:
                self._ol_count += 1
                self._parts.append(f"\n{self._ol_count}. ")
            else:
                self._parts.append("\n- ")
        elif tag in ("h1", "h2", "h3"):
            level = int(tag[1])
            self._parts.append("\n\n" + "#" * level + " ")

    def handle_endtag(self, tag):
        if tag in ("strong", "b"):
            self._parts.append("**")
        elif tag in ("em", "i"):
            self._parts.append("*")
        elif tag in ("code", "pre"):
            self._parts.append("`")
        elif tag == "p":
            self._parts.append("\n")

    def handle_data(self, data):
        self._parts.append(data)

    def get_text(self) -> str:
        text = "".join(self._parts).strip()
        return re.sub(r"\n{3,}", "\n\n", text)


def html_to_text(html: str) -> str:
    if not html:
        return ""
    p = HTMLToText()
    try:
        p.feed(html)
        return p.get_text()
    except Exception:
        return re.sub(r"<[^>]+>", "", html).strip()


def plain_strip(html: str) -> str:
    return re.sub(r"<[^>]+>", "", html).strip()


def parse_timestamp(text: str) -> Optional[datetime]:
    # German: "14.03.2026, 13:08:30 MEZ"
    m = re.search(r"(\d{2})\.(\d{2})\.(\d{4}),?\s+(\d{2}):(\d{2}):(\d{2})", text)
    if m:
        day, mon, year, h, mi, s = [int(x) for x in m.groups()]
        try:
            return datetime(year, mon, day, h, mi, s)
        except ValueError:
            pass
    # English: "Mar 14, 2026, 1:08:30 PM"
    m = re.search(
        r"(\w{3})\s+(\d{1,2}),?\s+(\d{4}),?\s+(\d{1,2}):(\d{2}):(\d{2})\s*(AM|PM)?",
        text, re.IGNORECASE
    )
    if m:
        month_map = {"jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,
                     "jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12}
        mon = month_map.get(m.group(1).lower()[:3], 1)
        day, year, h, mi, s = int(m.group(2)), int(m.group(3)), int(m.group(4)), int(m.group(5)), int(m.group(6))
        ampm = m.group(7)
        if ampm and ampm.upper() == "PM" and h < 12:
            h += 12
        elif ampm and ampm.upper() == "AM" and h == 12:
            h = 0
        try:
            return datetime(year, mon, day, h, mi, s)
        except ValueError:
            pass
    return None


def parse_gemini_html(html_path: Path) -> list[dict]:
    """Parse Takeout HTML into list of {prompt, response, timestamp} dicts."""
    text = html_path.read_text(encoding="utf-8")
    entries = []

    # Split by content-cell divs
    cells = re.split(
        r'<div\s+class="content-cell\s+mdl-cell\s+mdl-cell--6-col[^"]*">',
        text
    )

    for cell in cells[1:]:
        # Take content up to the closing div structure
        # (cells may contain nested divs, so we take a generous chunk)
        cell_content = cell[:cell.find('</div></div></div>')]  if '</div></div></div>' in cell else cell.split('</div>')[0]

        # Look for prompt marker
        prompt_match = re.search(
            r"(?:Eingegebener Prompt|Entered Prompt|Prompt entered)\s*:\s*(.*?)(?:\s*<br>)",
            cell_content, re.DOTALL | re.IGNORECASE
        )
        if not prompt_match:
            continue

        prompt_text = html_module.unescape(plain_strip(prompt_match.group(1))).strip()
        if not prompt_text:
            continue

        # Extract timestamp
        ts = parse_timestamp(cell_content)

        # Response: everything after the timestamp line
        # Find timestamp pattern followed by <br>
        ts_pattern = re.search(
            r"\d{2}\.\d{2}\.\d{4},?\s+\d{2}:\d{2}:\d{2}\s*\w*\s*<br>",
            cell_content
        )
        if not ts_pattern:
            ts_pattern = re.search(
                r"\w{3}\s+\d{1,2},?\s+\d{4},?\s+\d{1,2}:\d{2}:\d{2}\s*(?:AM|PM)?\s*\w*\s*<br>",
                cell_content, re.IGNORECASE
            )

        response_html = ""
        if ts_pattern:
            response_html = cell_content[ts_pattern.end():]
        else:
            after = cell_content[prompt_match.end():]
            parts = after.split("<br>", 1)
            if len(parts) > 1:
                response_html = parts[1]

        response_text = html_to_text(response_html).strip()

        entries.append({
            "prompt": prompt_text,
            "response": response_text,
            "timestamp": ts,
        })

    return entries


def group_into_conversations(entries: list[dict], gap_minutes: int = 30) -> list[dict]:
    """Group entries into conversations by time proximity."""
    if not entries:
        return []

    sorted_entries = sorted(entries, key=lambda e: e["timestamp"] or datetime.max)
    conversations = []
    current = []
    
    for entry in sorted_entries:
        if not current:
            current.append(entry)
            continue

        last_ts = current[-1]["timestamp"]
        this_ts = entry["timestamp"]

        if this_ts and last_ts and (this_ts - last_ts) > timedelta(minutes=gap_minutes):
            conversations.append(_finalize(current))
            current = [entry]
        else:
            current.append(entry)

    if current:
        conversations.append(_finalize(current))

    return conversations


def _finalize(entries: list[dict]) -> dict:
    first_prompt = entries[0]["prompt"]
    title = first_prompt[:80].strip()
    if len(first_prompt) > 80:
        title = title.rsplit(" ", 1)[0] + "..."

    messages = []
    for e in entries:
        messages.append({"role": "user", "text": e["prompt"], "timestamp": e["timestamp"]})
        if e["response"]:
            messages.append({"role": "assistant", "text": e["response"], "timestamp": e["timestamp"]})

    return {
        "title": title,
        "messages": messages,
        "timestamp": entries[0]["timestamp"],
        "last_timestamp": entries[-1]["timestamp"],
        "message_count": len(messages),
    }


def to_conversation(conv: dict) -> ChatConversation:
    """Convert one grouped Gemini conversation into a :class:`ChatConversation`.

    Takeout carries no conversation ids, so the id is derived from the first
    prompt and its time: a conversation continued later keeps its start, and
    with it its id.
    """
    ts = conv["timestamp"]
    messages = [
        ChatMessage(content_id(m["role"], m.get("timestamp"), m["text"][:200]), m["role"], m["text"])
        for m in conv["messages"]
    ]
    first_prompt = conv["messages"][0]["text"] if conv["messages"] else ""
    return ChatConversation(
        provider="gemini",
        chat_id=content_id(ts.isoformat() if ts else None, first_prompt[:200]),
        title=conv["title"],
        messages=messages,
        assistant_label="**Gemini:**",
        authors="Gemini",
        source_platform="gemini.google.com",
        created=ts,
        updated=conv.get("last_timestamp"),
    )


def _describe(conv: dict) -> tuple[str, int, str]:
    return format_date(conv["timestamp"]), conv["message_count"], conv["title"]


def main():
    ap = argparse.ArgumentParser(description="Import Gemini Takeout HTML into Obsidian vault")
    ap.add_argument("input_file", type=Path, help="Takeout HTML file")
    ap.add_argument("vault_path", type=Path, help="Obsidian vault path")
    ap.add_argument("--output-folder", default="KI-Chats")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--interactive", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--min-messages", type=int, default=2)
    ap.add_argument("--gap-minutes", type=int, default=30, help="Minutes between entries to split conversations (default: 30)")

    add_sync_arguments(ap)


    args = ap.parse_args()

    if not args.input_file.exists():
        print(f"Error: {args.input_file} not found"); sys.exit(1)
    if not args.vault_path.exists():
        print(f"Error: {args.vault_path} not found"); sys.exit(1)

    print(f"Parsing {args.input_file}...")
    entries = parse_gemini_html(args.input_file)
    print(f"Found {len(entries)} prompt/response entries")

    if not entries:
        print("No entries found. Check the HTML structure."); sys.exit(1)

    print(f"Grouping into conversations (gap: {args.gap_minutes} min)...")
    convs = group_into_conversations(entries, args.gap_minutes)
    print(f"Grouped into {len(convs)} conversations")

    convs = [c for c in convs if c["message_count"] >= args.min_messages]
    print(f"After filtering (>= {args.min_messages} messages): {len(convs)}")

    convs.sort(key=lambda c: c["timestamp"] or datetime.min, reverse=True)

    if args.interactive:
        convs = select_conversations(convs, _describe)
    elif args.limit:
        convs = convs[:args.limit]

    if not convs:
        print("No conversations selected."); return

    print(f"\nSyncing {len(convs)} conversations...")
    run_sync([to_conversation(c) for c in convs], args)


if __name__ == "__main__":
    main()
