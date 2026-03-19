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
    python import_gemini_to_vault.py "Mein Aktivitaetsverlauf.html" D:\Archilles-Lab
    python import_gemini_to_vault.py activity.html D:\Archilles-Lab --dry-run
    python import_gemini_to_vault.py activity.html D:\Archilles-Lab --interactive
    python import_gemini_to_vault.py activity.html D:\Archilles-Lab --limit 10
"""

import re
import sys
import html as html_module
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from html.parser import HTMLParser
from typing import Optional


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


def slugify(text: str, max_length: int = 50) -> str:
    text = text.lower().strip()
    for k, v in {"ae": "ae", "oe": "oe", "ue": "ue", "ss": "ss",
                  "\u00e4": "ae", "\u00f6": "oe", "\u00fc": "ue", "\u00df": "ss"}.items():
        text = text.replace(k, v)
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = text.strip("-")
    if len(text) > max_length:
        text = text[:max_length].rstrip("-")
    return text or "untitled"


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
        messages.append({"role": "user", "text": e["prompt"]})
        if e["response"]:
            messages.append({"role": "assistant", "text": e["response"]})

    return {
        "title": title,
        "messages": messages,
        "timestamp": entries[0]["timestamp"],
        "message_count": len(messages),
    }


def conversation_to_markdown(conv: dict) -> tuple[str, str, str]:
    title = conv["title"]
    ts = conv["timestamp"]
    messages = conv["messages"]

    if not messages:
        return "", "", ""

    date_str = ts.strftime("%Y-%m-%d") if ts else "unknown"
    month_folder = ts.strftime("%Y-%m") if ts else "undated"
    slug = slugify(title)
    filename = f"{date_str}_gemini_{slug}.md"

    safe_title = title.replace('"', "'")  # Avoid YAML breakage from nested quotes

    frontmatter = "\n".join([
        "---",
        f'title: "{safe_title}"',
        "authors: [Gemini]",
        "tags: [chat-protokoll, KI-generiert]",
        "type: chat",
        "source_llm: gemini",
        "source_platform: gemini.google.com",
        f"created: {date_str}",
        f"message_count: {conv['message_count']}",
        "---",
    ])

    body = [f"# {title}", ""]
    for msg in messages:
        label = "**User:**" if msg["role"] == "user" else "**Gemini:**"
        body.extend([label, "", msg["text"], "", "---", ""])

    return filename, frontmatter + "\n\n" + "\n".join(body), month_folder


def preview_conversations(convs):
    print(f"\n{'#':>4}  {'Date':10}  {'Msgs':>5}  Title")
    print("-" * 70)
    for i, c in enumerate(convs):
        ts = c["timestamp"]
        d = ts.strftime("%Y-%m-%d") if ts else "unknown"
        print(f"{i:4d}  {d:10}  {c['message_count']:5d}  {c['title'][:45]}")


def interactive_select(convs):
    preview_conversations(convs)
    print(f"\nTotal: {len(convs)} conversations")
    print("Enter numbers (comma-separated), ranges (3-7), or 'all':")
    sel = input("> ").strip()
    if sel.lower() == "all":
        return convs
    indices = set()
    for part in sel.split(","):
        part = part.strip()
        if "-" in part:
            s, e = part.split("-", 1)
            indices.update(range(int(s), int(e) + 1))
        else:
            indices.add(int(part))
    return [convs[i] for i in sorted(indices) if 0 <= i < len(convs)]


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
        convs = interactive_select(convs)
    elif args.limit:
        convs = convs[:args.limit]

    if not convs:
        print("No conversations selected."); return

    print(f"\nImporting {len(convs)} conversations...")
    out_base = args.vault_path / args.output_folder
    written = skipped = 0

    for conv in convs:
        fn, md, mf = conversation_to_markdown(conv)
        if not md.strip():
            skipped += 1; continue

        out_dir = out_base / mf
        out_path = out_dir / fn

        if out_path.exists():
            stem = out_path.stem
            for i in range(2, 100):
                alt = out_dir / f"{stem}-{i}.md"
                if not alt.exists():
                    out_path = alt; break

        if args.dry_run:
            print(f"  [DRY RUN] {out_path.relative_to(args.vault_path)}  ({conv['message_count']} msgs)  {conv['title'][:50]}")
        else:
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path.write_text(md, encoding="utf-8")
            written += 1

    if args.dry_run:
        print(f"\nDry run complete. Would write {len(convs) - skipped} files.")
    else:
        print(f"\nDone. Written: {written}, Skipped: {skipped}")
        print(f"Output: {out_base}")


if __name__ == "__main__":
    main()
