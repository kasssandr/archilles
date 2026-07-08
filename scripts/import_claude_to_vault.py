#!/usr/bin/env python3
"""
Import Claude conversations into an Obsidian vault (Archilles Lab).

Converts Claude's conversations.json export into Markdown files
with YAML frontmatter, organized by month in the KI-Chats folder.

Thinking blocks and tool_use/tool_result are omitted — only the
final text output is preserved. File attachments are noted inline.

Usage:
    python import_claude_to_vault.py conversations.json D:/MyVault
    python import_claude_to_vault.py conversations.json D:/MyVault --limit 10
    python import_claude_to_vault.py conversations.json D:/MyVault --interactive
    python import_claude_to_vault.py conversations.json D:/MyVault --dry-run
"""

import json
import sys
import argparse
from datetime import datetime
from pathlib import Path
from typing import Optional

from vault_import import (
    format_date,
    get_month_folder,
    make_filename,
    render_markdown,
    select_conversations,
)


def parse_iso_date(iso_str: Optional[str]) -> Optional[datetime]:
    """Parse ISO 8601 timestamp string to datetime."""
    if not iso_str:
        return None
    try:
        return datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


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
    filename = make_filename(date_str, "claude", title)

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

    markdown = render_markdown(
        frontmatter_lines, title, messages, "**Claude:**", summary=summary
    )
    return filename, markdown, month_folder


def _describe(conv: dict) -> tuple[str, int, str]:
    created = parse_iso_date(conv.get("created_at"))
    return format_date(created), len(extract_messages(conv)), conv.get("name") or "Untitled"


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
        help="Path to the Obsidian vault (e.g., D:\\MyVault)"
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
        conversations = select_conversations(conversations, _describe)
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
