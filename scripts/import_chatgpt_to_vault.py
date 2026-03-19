#!/usr/bin/env python3
"""
Import ChatGPT conversations into an Obsidian vault (Archilles Lab).

Converts ChatGPT's conversations.json export into Markdown files
with YAML frontmatter, organized by month in the KI-Chats folder.

Usage:
    python import_chatgpt_to_vault.py conversations.json D:\Archilles-Lab
    python import_chatgpt_to_vault.py conversations.json D:\Archilles-Lab --limit 10
    python import_chatgpt_to_vault.py conversations.json D:\Archilles-Lab --interactive
    python import_chatgpt_to_vault.py conversations.json D:\Archilles-Lab --dry-run
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
    # German umlauts
    replacements = {
        "ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss",
        "Ä": "Ae", "Ö": "Oe", "Ü": "Ue",
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    # Replace non-alphanumeric with hyphens
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = text.strip("-")
    # Truncate
    if len(text) > max_length:
        text = text[:max_length].rstrip("-")
    return text or "untitled"


def format_timestamp(unix_ts: Optional[float]) -> Optional[str]:
    """Convert Unix timestamp to ISO date string."""
    if not unix_ts:
        return None
    try:
        return datetime.fromtimestamp(unix_ts).strftime("%Y-%m-%d")
    except (ValueError, OSError):
        return None


def format_datetime(unix_ts: Optional[float]) -> Optional[str]:
    """Convert Unix timestamp to ISO datetime string."""
    if not unix_ts:
        return None
    try:
        return datetime.fromtimestamp(unix_ts).strftime("%Y-%m-%dT%H:%M:%S")
    except (ValueError, OSError):
        return None


def get_month_folder(unix_ts: Optional[float]) -> str:
    """Get YYYY-MM folder name from timestamp."""
    if not unix_ts:
        return "undated"
    try:
        return datetime.fromtimestamp(unix_ts).strftime("%Y-%m")
    except (ValueError, OSError):
        return "undated"


def extract_messages(conversation: dict) -> list[dict]:
    """Extract messages from ChatGPT conversation format.
    
    ChatGPT uses a tree structure (mapping) rather than a flat list.
    We follow the chain from root to leaves.
    """
    mapping = conversation.get("mapping", {})
    if not mapping:
        return []
    
    # Find root node (no parent)
    root_id = None
    for node_id, node in mapping.items():
        if node.get("parent") is None:
            root_id = node_id
            break
    
    if not root_id:
        return []
    
    # Walk the tree following the last child at each level
    messages = []
    current_id = root_id
    visited = set()
    
    while current_id and current_id not in visited:
        visited.add(current_id)
        node = mapping.get(current_id, {})
        msg = node.get("message")
        
        if msg and msg.get("content", {}).get("parts"):
            role = msg.get("author", {}).get("role", "unknown")
            # Skip system messages
            if role in ("user", "assistant"):
                parts = msg["content"]["parts"]
                text_parts = [p for p in parts if isinstance(p, str) and p.strip()]
                if text_parts:
                    messages.append({
                        "role": role,
                        "text": "\n\n".join(text_parts),
                        "timestamp": msg.get("create_time"),
                    })
        
        # Follow children (take the last one — ChatGPT's "current" branch)
        children = node.get("children", [])
        current_id = children[-1] if children else None
    
    return messages


def conversation_to_markdown(conversation: dict) -> tuple[str, str, str]:
    """Convert a single conversation to Markdown with frontmatter.
    
    Returns:
        (filename, markdown_content, month_folder)
    """
    title = conversation.get("title", "Untitled")
    create_time = conversation.get("create_time")
    update_time = conversation.get("update_time")
    
    date_str = format_timestamp(create_time) or "unknown"
    month_folder = get_month_folder(create_time)
    slug = slugify(title)
    filename = f"{date_str}_chatgpt_{slug}.md"
    
    # Extract messages
    messages = extract_messages(conversation)
    
    if not messages:
        return filename, "", month_folder
    
    # Detect dominant model (if available)
    model_slug = conversation.get("default_model_slug", "")
    
    # Build frontmatter
    tags = ["chat-protokoll", "KI-generiert"]
    
    # Try to detect topic-related tags from title
    # (kept minimal — user can add tags later in Obsidian)
    
    safe_title = title.replace('"', "'")  # Avoid YAML breakage from nested quotes
    
    frontmatter_lines = [
        "---",
        f'title: "{safe_title}"',
        "authors: [ChatGPT]",
        f"tags: [{', '.join(tags)}]",
        "type: chat",
        "source_llm: chatgpt",
        "source_platform: chatgpt.com",
    ]
    if model_slug:
        frontmatter_lines.append(f"model: {model_slug}")
    frontmatter_lines.append(f"created: {date_str}")
    if update_time:
        frontmatter_lines.append(f"modified: {format_timestamp(update_time)}")
    frontmatter_lines.append(f"message_count: {len(messages)}")
    frontmatter_lines.append("---")
    
    # Build body
    body_lines = [f"# {title}", ""]
    
    for msg in messages:
        role_label = "**User:**" if msg["role"] == "user" else "**ChatGPT:**"
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
        title = conv.get("title", "Untitled")[:45]
        date_str = format_timestamp(conv.get("create_time")) or "unknown"
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
            title = conv.get("title", "Untitled")[:50]
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
