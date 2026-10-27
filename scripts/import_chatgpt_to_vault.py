#!/usr/bin/env python3
"""
Import ChatGPT conversations into an Obsidian vault (Archilles Lab).

Converts ChatGPT's conversations.json export into Markdown files
with YAML frontmatter, organized by month in the KI-Chats folder.

Usage:
    python import_chatgpt_to_vault.py conversations.json D:/MyVault
    python import_chatgpt_to_vault.py conversations.json D:/MyVault --limit 10
    python import_chatgpt_to_vault.py conversations.json D:/MyVault --interactive
    python import_chatgpt_to_vault.py conversations.json D:/MyVault --dry-run

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
from vault_import import select_conversations


def format_timestamp(unix_ts: Optional[float]) -> Optional[str]:
    """Convert Unix timestamp to ISO date string."""
    if not unix_ts:
        return None
    try:
        return datetime.fromtimestamp(unix_ts).strftime("%Y-%m-%d")
    except (ValueError, OSError):
        return None


def to_datetime(unix_ts: Optional[float]) -> Optional[datetime]:
    """Convert a Unix timestamp to a datetime (None if missing or invalid)."""
    if not unix_ts:
        return None
    try:
        return datetime.fromtimestamp(unix_ts)
    except (ValueError, OSError, TypeError):
        return None


def _current_branch(mapping: dict, current_node: Optional[str]) -> list[str]:
    """Node ids of the branch the chat shows, root first.

    The export names the visible leaf in ``current_node``; walking its parents
    gives the branch the user actually continued. Older exports without it
    fall back to following the last child from the root.
    """
    if current_node in mapping:
        path, seen = [], set()
        node_id = current_node
        while node_id and node_id not in seen:
            seen.add(node_id)
            path.append(node_id)
            node_id = mapping.get(node_id, {}).get("parent")
        return path[::-1]

    root_id = next((nid for nid, node in mapping.items() if node.get("parent") is None), None)
    path, seen = [], set()
    node_id = root_id
    while node_id and node_id not in seen:
        seen.add(node_id)
        path.append(node_id)
        children = mapping.get(node_id, {}).get("children", [])
        node_id = children[-1] if children else None
    return path


def extract_messages(conversation: dict) -> list[dict]:
    """Extract messages from ChatGPT conversation format.

    ChatGPT uses a tree structure (mapping) rather than a flat list; edited
    prompts and regenerated answers are branches. We take the visible one.
    """
    mapping = conversation.get("mapping", {})
    if not mapping:
        return []

    path = _current_branch(mapping, conversation.get("current_node"))

    messages = []
    for node_id in path:
        node = mapping.get(node_id, {})
        msg = node.get("message")
        if not (msg and msg.get("content", {}).get("parts")):
            continue
        role = msg.get("author", {}).get("role", "unknown")
        # Skip system and tool messages
        if role not in ("user", "assistant"):
            continue
        parts = msg["content"]["parts"]
        text_parts = [p for p in parts if isinstance(p, str) and p.strip()]
        if text_parts:
            messages.append({
                "id": msg.get("id") or node_id,
                "role": role,
                "text": "\n\n".join(text_parts),
                "timestamp": msg.get("create_time"),
            })

    return messages


def to_conversation(conversation: dict) -> ChatConversation:
    """Convert one ChatGPT export entry into a :class:`ChatConversation`."""
    create_time = conversation.get("create_time")
    update_time = conversation.get("update_time")
    messages = [
        ChatMessage(m["id"], m["role"], m["text"], to_datetime(m["timestamp"]))
        for m in extract_messages(conversation)
    ]
    return ChatConversation(
        provider="chatgpt",
        chat_id=(conversation.get("conversation_id") or conversation.get("id")
                 or content_id(create_time, conversation.get("title"))),
        title=conversation.get("title") or "Untitled",
        messages=messages,
        assistant_label="**ChatGPT:**",
        authors="ChatGPT",
        source_platform="chatgpt.com",
        created=to_datetime(create_time),
        updated=to_datetime(update_time),
        model=conversation.get("default_model_slug") or "",
    )


def _describe(conv: dict) -> tuple[str, int, str]:
    date_str = format_timestamp(conv.get("create_time")) or "unknown"
    return date_str, len(extract_messages(conv)), conv.get("title", "Untitled")


def main():
    parser = argparse.ArgumentParser(
        description="Import ChatGPT conversations into an Obsidian vault"
    )
    parser.add_argument(
        "input_file",
        type=Path,
        help="Path to conversations.json from ChatGPT export"
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
    
    # Validate inputs
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
        key=lambda c: c.get("create_time") or 0,
        reverse=True
    )
    
    # Filter by minimum message count
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
