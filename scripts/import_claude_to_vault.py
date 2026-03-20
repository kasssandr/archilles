#!/usr/bin/env python3
"""
Import Claude conversations into an Obsidian vault (Archilles Lab).

Converts Claude's conversations.json export into Markdown files
with YAML frontmatter, organized by month in the KI-Chats folder.

Thinking blocks and tool_use/tool_result are omitted — only the
final text output is preserved. File attachments are noted inline.

Usage:
    python import_claude_to_vault.py conversations.json D:/Archilles-Lab
    python import_claude_to_vault.py conversations.json D:/Archilles-Lab --limit 10
    python import_claude_to_vault.py conversations.json D:/Archilles-Lab --interactive
    python import_claude_to_vault.py conversations.json D:/Archilles-Lab --dry-run
"""

import json
import re
import sys
import argparse
from datetime import datetime
from pathlib import Path
from typing import Optional


def slugify(text: str, max_length: int = 50) -> str:
    """Convert text to a filesystem-safe slug."""
    text = text.lower().strip()
    replacements = {
        "ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss",
        "Ä": "Ae", "Ö": "Oe", "Ü": "Ue",
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = text.strip("-")
    if len(text) > max_length:
        text = text[:max_length].rstrip("-")
    return text or "untitled"


def parse_iso_date(iso_str: Optional[str]) -> Optional[datetime]:
    """Parse ISO 8601 timestamp string to datetime."""
    if not iso_str:
        return None
    try:
        return datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def format_date(dt: Optional[datetime]) -> str:
    """Format datetime as YYYY-MM-DD."""
    return dt.strftime("%Y-%m-%d") if dt else "unknown"


def get_month_folder(dt: Optional[datetime]) -> str:
    """Get YYYY-MM folder name from datetime."""
    return dt.strftime("%Y-%m") if dt else "undated"


def extract_messages(conversation: dict) -> list[dict]:
    """Extract messages from Claude conversation format.

    Filters out thinking, tool_use, and tool_result blocks.
    Only text blocks are preserved. File attachments are noted.
    """
    messages = []

    for msg in conversation.get("chat_messages", []):
        role = msg.get("sender", "unknown")
        if role not in ("human", "assistant"):
            continue

        # Collect text blocks only (skip thinking, tool_use, tool_result, token_budget)
        text_parts = []
        for block in msg.get("content", []):
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text":
                text = block.get("text", "").strip()
                if text:
                    text_parts.append(text)

        # Note file attachments
        files = msg.get("files", [])
        if files:
            file_names = [f.get("file_name", "?") for f in files if isinstance(f, dict)]
            if file_names:
                text_parts.append(
                    "*Anhänge: " + ", ".join(f"`{n}`" for n in file_names) + "*"
                )

        attachments = msg.get("attachments", [])
        if attachments:
            att_names = [
                a.get("file_name") or a.get("name", "?")
                for a in attachments if isinstance(a, dict)
            ]
            if att_names:
                text_parts.append(
                    "*Anhänge: " + ", ".join(f"`{n}`" for n in att_names) + "*"
                )

        if not text_parts:
            continue

        created = parse_iso_date(msg.get("created_at"))

        messages.append({
            "role": "user" if role == "human" else "assistant",
            "text": "\n\n".join(text_parts),
            "timestamp": created,
        })

    return messages


def conversation_to_markdown(conversation: dict) -> tuple[str, str, str]:
    """Convert a single conversation to Markdown with frontmatter.

    Returns:
        (filename, markdown_content, month_folder)
    """
    title = conversation.get("name", "").strip() or "Untitled"
    summary = conversation.get("summary", "").strip()

    created = parse_iso_date(conversation.get("created_at"))
    updated = parse_iso_date(conversation.get("updated_at"))

    date_str = format_date(created)
    month_folder = get_month_folder(created)
    slug = slugify(title)
    filename = f"{date_str}_claude_{slug}.md"

    messages = extract_messages(conversation)
    if not messages:
        return filename, "", month_folder

    # Build frontmatter
    tags = ["chat-protokoll", "KI-generiert"]
    safe_title = title.replace('"', "'")

    frontmatter_lines = [
        "---",
        f'title: "{safe_title}"',
        "authors: [Claude]",
        f"tags: [{', '.join(tags)}]",
        "type: chat",
        "source_llm: claude",
        "source_platform: claude.ai",
        f"created: {date_str}",
    ]
    if updated:
        frontmatter_lines.append(f"modified: {format_date(updated)}")
    frontmatter_lines.append(f"message_count: {len(messages)}")
    frontmatter_lines.append("---")

    # Build body
    body_lines = [f"# {title}", ""]

    if summary:
        body_lines.append(f"> {summary[:500]}")
        body_lines.append("")
        body_lines.append("---")
        body_lines.append("")

    for msg in messages:
        role_label = "**User:**" if msg["role"] == "user" else "**Claude:**"
        body_lines.append(role_label)
        body_lines.append("")
        body_lines.append(msg["text"])
        body_lines.append("")
        body_lines.append("---")
        body_lines.append("")

    markdown = "\n".join(frontmatter_lines) + "\n\n" + "\n".join(body_lines)
    return filename, markdown, month_folder


def preview_conversations(conversations: list[dict]) -> None:
    """Print a numbered list of conversations for interactive selection."""
    print(f"\n{'#':>4}  {'Date':10}  {'Msgs':>5}  Title")
    print("-" * 70)
    for i, conv in enumerate(conversations):
        title = (conv.get("name") or "Untitled")[:45]
        created = parse_iso_date(conv.get("created_at"))
        date_str = format_date(created)
        msgs = len(extract_messages(conv))
        print(f"{i:4d}  {date_str:10}  {msgs:5d}  {title}")


def interactive_select(conversations: list[dict]) -> list[dict]:
    """Let user pick conversations interactively."""
    preview_conversations(conversations)
    print(f"\nTotal: {len(conversations)} conversations")
    print("Enter numbers to import (comma-separated), ranges (3-7), or 'all':")
    print("Example: 0,3,5-10,15")

    selection = input("> ").strip()

    if selection.lower() == "all":
        return conversations

    indices = set()
    for part in selection.split(","):
        part = part.strip()
        if "-" in part:
            start, end = part.split("-", 1)
            indices.update(range(int(start), int(end) + 1))
        else:
            indices.add(int(part))

    return [conversations[i] for i in sorted(indices) if 0 <= i < len(conversations)]


def main():
    parser = argparse.ArgumentParser(
        description="Import Claude conversations into an Obsidian vault"
    )
    parser.add_argument(
        "input_file",
        type=Path,
        help="Path to conversations.json from Claude export"
    )
    parser.add_argument(
        "vault_path",
        type=Path,
        help="Path to the Obsidian vault (e.g., D:\\Archilles-Lab)"
    )
    parser.add_argument(
        "--output-folder",
        type=str,
        default="KI-Chats",
        help="Subfolder in vault for chat imports (default: KI-Chats)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of conversations to import (most recent first)"
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Interactively select which conversations to import"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be imported without writing files"
    )
    parser.add_argument(
        "--min-messages",
        type=int,
        default=2,
        help="Skip conversations with fewer messages (default: 2)"
    )

    args = parser.parse_args()

    if not args.input_file.exists():
        print(f"Error: {args.input_file} not found")
        sys.exit(1)

    if not args.vault_path.exists():
        print(f"Error: Vault path {args.vault_path} not found")
        sys.exit(1)

    # Load conversations
    print(f"Loading {args.input_file}...")
    with open(args.input_file, "r", encoding="utf-8") as f:
        conversations = json.load(f)

    print(f"Found {len(conversations)} conversations")

    # Sort by creation time (most recent first)
    conversations.sort(
        key=lambda c: c.get("created_at") or "",
        reverse=True
    )

    # Filter empty and short conversations
    conversations = [
        c for c in conversations
        if len(extract_messages(c)) >= args.min_messages
    ]
    print(f"After filtering (>= {args.min_messages} messages): {len(conversations)}")

    # Interactive selection or limit
    if args.interactive:
        conversations = interactive_select(conversations)
    elif args.limit:
        conversations = conversations[:args.limit]

    if not conversations:
        print("No conversations selected.")
        return

    print(f"\nImporting {len(conversations)} conversations...")

    # Convert and write
    output_base = args.vault_path / args.output_folder
    written = 0
    skipped = 0

    for conv in conversations:
        filename, markdown, month_folder = conversation_to_markdown(conv)

        if not markdown.strip():
            skipped += 1
            continue

        output_dir = output_base / month_folder
        output_path = output_dir / filename

        # Handle duplicates
        if output_path.exists():
            stem = output_path.stem
            for i in range(2, 100):
                alt_path = output_dir / f"{stem}-{i}.md"
                if not alt_path.exists():
                    output_path = alt_path
                    break

        if args.dry_run:
            title = (conv.get("name") or "Untitled")[:50]
            msgs = len(extract_messages(conv))
            print(f"  [DRY RUN] {output_path.relative_to(args.vault_path)}  ({msgs} msgs)  {title}")
        else:
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path.write_text(markdown, encoding="utf-8")
            written += 1

    if args.dry_run:
        print(f"\nDry run complete. Would write {len(conversations) - skipped} files.")
    else:
        print(f"\nDone. Written: {written}, Skipped (empty): {skipped}")
        print(f"Output: {output_base}")


if __name__ == "__main__":
    main()
