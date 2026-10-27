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

Re-running on a newer export is safe: chat_sync recognizes notes it wrote
before (and web clips of the same chat) and only adds what is new.
"""

import json
import sys
import argparse
from datetime import datetime
from pathlib import Path
from typing import Optional

from chat_sync import (
    ChatConversation,
    ChatMessage,
    add_sync_arguments,
    content_id,
    run_sync,
)
from vault_import import format_date, select_conversations


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
            "id": msg.get("uuid") or content_id(role, msg.get("created_at"), text_parts[0]),
            "role": "user" if role == "human" else "assistant",
            "text": "\n\n".join(text_parts),
            "timestamp": created,
        })

    return messages


def to_conversation(conversation: dict) -> ChatConversation:
    """Convert one Claude export entry into a :class:`ChatConversation`."""
    messages = [
        ChatMessage(m["id"], m["role"], m["text"], m["timestamp"])
        for m in extract_messages(conversation)
    ]
    created = parse_iso_date(conversation.get("created_at"))
    return ChatConversation(
        provider="claude",
        chat_id=conversation.get("uuid") or content_id(conversation.get("created_at"),
                                                       conversation.get("name")),
        title=conversation.get("name", "").strip() or "Untitled",
        messages=messages,
        assistant_label="**Claude:**",
        authors="Claude",
        source_platform="claude.ai",
        created=created,
        updated=parse_iso_date(conversation.get("updated_at")),
        summary=conversation.get("summary", "").strip(),
    )


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
    add_sync_arguments(parser)

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

    print(f"\nSyncing {len(conversations)} conversations...")
    run_sync([to_conversation(c) for c in conversations], args)


if __name__ == "__main__":
    main()
