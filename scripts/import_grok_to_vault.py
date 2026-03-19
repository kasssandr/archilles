#!/usr/bin/env python3
"""
Import Grok conversations into an Obsidian vault (Archilles Lab).

Converts Grok's prod-grok-backend.json export into Markdown files
with YAML frontmatter, organized by month in the KI-Chats folder.

Usage:
    python import_grok_to_vault.py prod-grok-backend.json D:\Archilles-Lab
    python import_grok_to_vault.py prod-grok-backend.json D:\Archilles-Lab --limit 10
    python import_grok_to_vault.py prod-grok-backend.json D:\Archilles-Lab --interactive
    python import_grok_to_vault.py prod-grok-backend.json D:\Archilles-Lab --dry-run
"""

import json
import re
import sys
import argparse
from datetime import datetime, timezone
from pathlib import Path


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
            "role": role,
            "text": text.strip(),
            "timestamp": create_time,
            "model": model,
        })
    
    return messages


def conversation_to_markdown(conv_data: dict) -> tuple[str, str, str]:
    """Convert a single Grok conversation to Markdown with frontmatter.
    
    Returns:
        (filename, markdown_content, month_folder)
    """
    conv_meta = conv_data.get("conversation", {})
    title = conv_meta.get("title", "Untitled Grok Chat")
    create_time_str = conv_meta.get("create_time", "")
    modify_time_str = conv_meta.get("modify_time", "")
    
    # Parse creation time
    if create_time_str:
        dt = parse_grok_timestamp(create_time_str)
    else:
        dt = datetime.now(timezone.utc)
    
    date_str = dt.strftime("%Y-%m-%d")
    month_folder = dt.strftime("%Y-%m")
    
    # Extract messages
    messages = extract_messages(conv_data)
    
    if not messages:
        return "", "", ""
    
    # Detect model from first assistant message
    model = ""
    for msg in messages:
        if msg["role"] == "assistant" and msg.get("model"):
            model = msg["model"]
            break
    
    slug = slugify(title)
    filename = f"{date_str}_grok_{slug}.md"
    
    # Build frontmatter
    tags = ["chat-protokoll", "KI-generiert"]
    
    # Escape quotes in title for YAML
    safe_title = title.replace('"', "'")  # Avoid YAML breakage from nested quotes
    
    frontmatter_lines = [
        "---",
        f'title: "{safe_title}"',
        "authors: [Grok]",
        f"tags: [{', '.join(tags)}]",
        "type: chat",
        "source_llm: grok",
        "source_platform: grok.com",
    ]
    if model:
        frontmatter_lines.append(f"model: {model}")
    frontmatter_lines.append(f"created: {date_str}")
    if modify_time_str:
        modify_dt = parse_grok_timestamp(modify_time_str)
        frontmatter_lines.append(f"modified: {modify_dt.strftime('%Y-%m-%d')}")
    frontmatter_lines.append(f"message_count: {len(messages)}")
    frontmatter_lines.append("---")
    
    # Build body
    body_lines = [f"# {title}", ""]
    
    for msg in messages:
        role_label = "**User:**" if msg["role"] == "user" else "**Grok:**"
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
    for i, conv_data in enumerate(conversations):
        conv_meta = conv_data.get("conversation", {})
        title = conv_meta.get("title", "Untitled")[:45]
        create_time_str = conv_meta.get("create_time", "")
        if create_time_str:
            dt = parse_grok_timestamp(create_time_str)
            date_str = dt.strftime("%Y-%m-%d")
        else:
            date_str = "unknown"
        msgs = len(extract_messages(conv_data))
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
    
    for conv_data in conversations:
        filename, markdown, month_folder = conversation_to_markdown(conv_data)
        
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
            conv_meta = conv_data.get("conversation", {})
            title = conv_meta.get("title", "Untitled")[:50]
            msgs = len(extract_messages(conv_data))
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
