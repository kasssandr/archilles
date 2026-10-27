#!/usr/bin/env python3
"""
Import Grok conversations into an Obsidian vault (Archilles Lab).

Converts Grok's prod-grok-backend.json export into Markdown files
with YAML frontmatter, organized by month in the KI-Chats folder.

Usage:
    python import_grok_to_vault.py prod-grok-backend.json D:/MyVault
    python import_grok_to_vault.py prod-grok-backend.json D:/MyVault --limit 10
    python import_grok_to_vault.py prod-grok-backend.json D:/MyVault --interactive
    python import_grok_to_vault.py prod-grok-backend.json D:/MyVault --dry-run

Re-running on a newer export is safe: chat_sync recognizes notes it wrote
before (and web clips of the same chat) and only adds what is new.
"""

import json
import re
import sys
import argparse
from datetime import datetime, timezone
from pathlib import Path

from chat_sync import (
    ChatConversation,
    ChatMessage,
    add_sync_arguments,
    content_id,
    run_sync,
)
from vault_import import select_conversations


def parse_grok_timestamp(ts) -> datetime:
    """Parse Grok's various timestamp formats.
    
    Grok uses either:
    - ISO string: "2026-03-15T09:44:29.870913Z"
    - MongoDB-style: {"$date": {"$numberLong": "1773567869891"}}
    """
    if isinstance(ts, str):
        # ISO format
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            return datetime.now(timezone.utc)
    elif isinstance(ts, dict):
        # MongoDB {"$date": {"$numberLong": "..."}}
        try:
            date_val = ts.get("$date", {})
            if isinstance(date_val, dict):
                ms = int(date_val.get("$numberLong", 0))
            elif isinstance(date_val, (int, float)):
                ms = int(date_val)
            else:
                ms = int(date_val)
            return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
        except (ValueError, TypeError):
            return datetime.now(timezone.utc)
    return datetime.now(timezone.utc)


def clean_grok_tags(text: str) -> str:
    """Remove Grok's internal rendering tags (citations, cards etc.)."""
    # Remove <grok:render ...> ... </grok:render> including content (inline citations like " 12 ")
    text = re.sub(r"<grok:render[^>]*>.*?</grok:render>", "", text, flags=re.DOTALL)
    # Remove self-closing <grok:render ... />
    text = re.sub(r"<grok:render[^/]*/\s*>", "", text)
    # Remove any remaining unclosed <grok:...> tags
    text = re.sub(r"</?grok:[^>]*>", "", text)
    # Clean up resulting double spaces
    text = re.sub(r"  +", " ", text)
    return text.strip()


def extract_messages(conv_data: dict) -> list[dict]:
    """Extract messages from a Grok conversation."""
    responses = conv_data.get("responses", [])
    messages = []
    
    for resp_wrapper in responses:
        resp = resp_wrapper.get("response", {})
        sender = resp.get("sender", "unknown")
        text = resp.get("message", "")
        
        if not text or not text.strip():
            continue
        
        # Clean Grok's internal tags
        text = clean_grok_tags(text)
        
        if not text.strip():
            continue
        
        # Normalize role
        if sender in ("human", "user"):
            role = "user"
        elif sender in ("assistant", "grok"):
            role = "assistant"
        else:
            continue  # skip system messages etc.
        
        create_time = resp.get("create_time")
        model = resp.get("model", "")
        
        messages.append({
            "id": (_grok_id(resp.get("_id")) or _grok_id(resp.get("id"))
                   or content_id(role, create_time, text[:200])),
            "role": role,
            "text": text.strip(),
            "timestamp": create_time,
            "model": model,
        })
    
    return messages


def _grok_id(value) -> str:
    """Grok ids come as plain strings or MongoDB-style ``{"$oid": ...}``."""
    if isinstance(value, dict):
        value = value.get("$oid")
    return str(value) if value else ""


def to_conversation(conv_data: dict) -> ChatConversation:
    """Convert one Grok export entry into a :class:`ChatConversation`."""
    conv_meta = conv_data.get("conversation", {})
    title = conv_meta.get("title") or "Untitled Grok Chat"
    create_time = conv_meta.get("create_time")
    modify_time = conv_meta.get("modify_time")
    created = parse_grok_timestamp(create_time) if create_time else None

    raw = extract_messages(conv_data)
    model = next((m["model"] for m in raw if m["role"] == "assistant" and m.get("model")), "")
    messages = [
        ChatMessage(m["id"], m["role"], m["text"],
                    parse_grok_timestamp(m["timestamp"]) if m["timestamp"] else None)
        for m in raw
    ]
    return ChatConversation(
        provider="grok",
        chat_id=(_grok_id(conv_meta.get("id")) or _grok_id(conv_meta.get("_id"))
                 or content_id(create_time, title)),
        title=title,
        messages=messages,
        assistant_label="**Grok:**",
        authors="Grok",
        source_platform="grok.com",
        created=created,
        updated=parse_grok_timestamp(modify_time) if modify_time else None,
        model=model,
    )


def _describe(conv_data: dict) -> tuple[str, int, str]:
    meta = conv_data.get("conversation", {})
    cts = meta.get("create_time", "")
    date_str = parse_grok_timestamp(cts).strftime("%Y-%m-%d") if cts else "unknown"
    return date_str, len(extract_messages(conv_data)), meta.get("title", "Untitled")


def main():
    parser = argparse.ArgumentParser(
        description="Import Grok conversations into an Obsidian vault"
    )
    parser.add_argument(
        "input_file",
        type=Path,
        help="Path to prod-grok-backend.json from Grok export"
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
        data = json.load(f)
    
    conversations = data.get("conversations", [])
    print(f"Found {len(conversations)} conversations")
    
    # Sort by creation time (most recent first)
    def get_create_time(c):
        ct = c.get("conversation", {}).get("create_time", "")
        if ct:
            return parse_grok_timestamp(ct)
        return datetime.min.replace(tzinfo=timezone.utc)
    
    conversations.sort(key=get_create_time, reverse=True)
    
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
