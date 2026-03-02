#!/usr/bin/env python3
"""
import_ai_chats.py — Import AI chat exports into Calibre-ready HTML files

Converts exported conversations from ChatGPT, Gemini, Grok, Claude, and
Perplexity into HTML files with proper metadata, ready for Calibre import.

Usage:
    python scripts/import_ai_chats.py --source chatgpt --input export.zip
    python scripts/import_ai_chats.py --source chatgpt --input export.zip --add-to-calibre
    python scripts/import_ai_chats.py --source gemini  --input takeout.zip --output ./chats/
    python scripts/import_ai_chats.py --source claude  --input ~/exported_chats/  # folder of .md files
    python scripts/import_ai_chats.py --source chatgpt --input export.zip --dry-run

Export instructions per platform:
    ChatGPT    → Settings > Data Controls > Export data  →  ZIP file
    Gemini     → takeout.google.com > select Gemini      →  ZIP or TGZ
    Grok       → accounts.x.ai/data > Download           →  ZIP file
    Claude     → Browser extension (e.g. "AI Chat Exporter") → Markdown files
    Perplexity → Browser extension (e.g. "Save My Chatbot")  → Markdown files
"""

import argparse
import html as html_module
import json
import re
import subprocess
import sys
import zipfile
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ── Data classes ──────────────────────────────────────────────────────────────

class Message:
    def __init__(self, role: str, content: str, timestamp: Optional[datetime] = None):
        self.role = role        # 'user' | 'assistant'
        self.content = content
        self.timestamp = timestamp


class Conversation:
    def __init__(self, title: str, messages: list, platform: str,
                 created_at: Optional[datetime] = None):
        self.title = title
        self.messages = messages
        self.platform = platform
        self.created_at = created_at

    @property
    def display_title(self) -> str:
        t = (self.title or '').strip()
        if t:
            return t[:120]
        for msg in self.messages:
            if msg.role == 'user' and msg.content.strip():
                return msg.content.strip()[:80] + '…'
        return f"{self.platform} conversation"


# ── Platform parsers ──────────────────────────────────────────────────────────

class BaseParser(ABC):
    @abstractmethod
    def can_parse(self, path: Path) -> bool:
        ...

    @abstractmethod
    def parse(self, path: Path) -> list:
        ...


class ChatGPTParser(BaseParser):
    """
    Parses OpenAI ChatGPT export ZIP.
    The ZIP contains conversations.json with a tree-based mapping structure.
    Messages are reconstructed chronologically by create_time (more reliable
    than following the parent→child tree, which breaks on edited branches).
    """
    PLATFORM = 'ChatGPT'

    def can_parse(self, path: Path) -> bool:
        if path.is_file() and path.suffix == '.zip':
            with zipfile.ZipFile(path) as zf:
                return 'conversations.json' in zf.namelist()
        return path.is_dir() and (path / 'conversations.json').exists()

    def parse(self, path: Path) -> list:
        raw = self._read_json(path, 'conversations.json')
        return [c for c in (self._parse_one(d) for d in raw) if c and c.messages]

    def _read_json(self, path: Path, filename: str):
        if path.is_file():
            with zipfile.ZipFile(path) as zf:
                with zf.open(filename) as f:
                    return json.load(f)
        with open(path / filename, encoding='utf-8') as f:
            return json.load(f)

    def _parse_one(self, data: dict) -> Optional[Conversation]:
        title = data.get('title', '')
        ts = data.get('create_time')
        created_at = datetime.fromtimestamp(ts, tz=timezone.utc) if ts else None

        messages = []
        for node in data.get('mapping', {}).values():
            msg = node.get('message')
            if not msg:
                continue
            role = msg.get('author', {}).get('role', '')
            if role not in ('user', 'assistant'):
                continue
            parts = msg.get('content', {}).get('parts', [])
            content = '\n'.join(str(p) for p in parts if isinstance(p, str)).strip()
            if not content:
                continue
            msg_ts = msg.get('create_time')
            timestamp = datetime.fromtimestamp(msg_ts, tz=timezone.utc) if msg_ts else None
            messages.append(Message(role=role, content=content, timestamp=timestamp))

        messages.sort(key=lambda m: m.timestamp or datetime.min.replace(tzinfo=timezone.utc))
        return Conversation(title=title, messages=messages, platform=self.PLATFORM, created_at=created_at)


class GeminiParser(BaseParser):
    """
    Parses Google Takeout export containing Gemini conversation JSON files.
    Files are located in a 'gemini/conversations/' subfolder within the ZIP.
    """
    PLATFORM = 'Gemini'

    def can_parse(self, path: Path) -> bool:
        if path.is_file() and path.suffix == '.zip':
            try:
                with zipfile.ZipFile(path) as zf:
                    return any('gemini' in n.lower() and n.endswith('.json') for n in zf.namelist())
            except Exception:
                return False
        return path.is_dir() and any(path.rglob('gemini/**/*.json'))

    def parse(self, path: Path) -> list:
        conversations = []
        for data in self._iter_json(path):
            conv = self._parse_one(data)
            if conv and conv.messages:
                conversations.append(conv)
        return conversations

    def _iter_json(self, path: Path):
        if path.is_file() and path.suffix == '.zip':
            with zipfile.ZipFile(path) as zf:
                for name in zf.namelist():
                    if 'gemini' in name.lower() and name.endswith('.json'):
                        with zf.open(name) as f:
                            yield json.load(f)
        else:
            for p in sorted((path / 'gemini').rglob('*.json')):
                with open(p, encoding='utf-8') as f:
                    yield json.load(f)

    def _parse_one(self, data: dict) -> Optional[Conversation]:
        created_str = data.get('createdTime', '')
        try:
            created_at = datetime.fromisoformat(created_str.replace('Z', '+00:00'))
        except Exception:
            created_at = None

        messages = [
            Message(
                role='user' if m.get('role') == 'user' else 'assistant',
                content=m.get('content', '').strip()
            )
            for m in data.get('messages', [])
            if m.get('content', '').strip()
        ]
        title = data.get('title') or data.get('id', '')
        return Conversation(title=title, messages=messages, platform=self.PLATFORM, created_at=created_at)


class GrokParser(BaseParser):
    """
    Parses Grok export ZIP from accounts.x.ai/data.
    Note: Grok exports may contain binary/hex-encoded data — this parser
    handles the standard JSON format; use grok-export-decoder for raw exports.
    """
    PLATFORM = 'Grok'

    def can_parse(self, path: Path) -> bool:
        if not (path.is_file() and path.suffix == '.zip'):
            return False
        try:
            with zipfile.ZipFile(path) as zf:
                for name in zf.namelist():
                    if name.endswith('.json'):
                        with zf.open(name) as f:
                            data = json.load(f)
                            if 'conversations' in data:
                                return True
        except Exception:
            pass
        return False

    def parse(self, path: Path) -> list:
        data = self._read_json(path)
        return [c for c in (self._parse_one(d) for d in data.get('conversations', [])) if c and c.messages]

    def _read_json(self, path: Path) -> dict:
        with zipfile.ZipFile(path) as zf:
            for name in zf.namelist():
                if name.endswith('.json'):
                    with zf.open(name) as f:
                        return json.load(f)
        raise ValueError(f"No JSON found in {path}")

    def _parse_one(self, data: dict) -> Optional[Conversation]:
        ts = data.get('timestamp')
        created_at = datetime.fromtimestamp(ts, tz=timezone.utc) if ts else None
        messages = []
        for m in data.get('messages', []):
            role = 'user' if m.get('role') == 'user' else 'assistant'
            content = m.get('content', '').strip()
            if not content:
                continue
            msg_ts = m.get('timestamp')
            timestamp = datetime.fromtimestamp(msg_ts, tz=timezone.utc) if msg_ts else None
            messages.append(Message(role=role, content=content, timestamp=timestamp))
        return Conversation(title=data.get('id', ''), messages=messages,
                            platform=self.PLATFORM, created_at=created_at)


class MarkdownParser(BaseParser):
    """
    Generic Markdown parser for Claude and Perplexity exports.

    Both platforms lack official bulk export; browser extensions (e.g.
    "AI Chat Exporter", "Save My Chatbot") export conversations as .md files
    in the common format:

        # Conversation Title
        **User:** message text
        **Assistant:** response text

    Point --input at a folder containing these .md files.
    """
    USER_PATTERN = re.compile(r'^\*\*(?:User|Human|You)\*\*[:\s]*', re.IGNORECASE)
    ASSISTANT_PATTERN = re.compile(r'^\*\*(?:Assistant|Claude|Perplexity|AI)\*\*[:\s]*', re.IGNORECASE)

    def __init__(self, platform: str):
        self.PLATFORM = platform

    def can_parse(self, path: Path) -> bool:
        if path.is_dir():
            return any(path.glob('*.md'))
        return path.suffix == '.md'

    def parse(self, path: Path) -> list:
        files = sorted(path.glob('*.md')) if path.is_dir() else [path]
        return [c for c in (self._parse_file(f) for f in files) if c and c.messages]

    def _parse_file(self, path: Path) -> Optional[Conversation]:
        lines = path.read_text(encoding='utf-8').splitlines()
        title = path.stem
        if lines and lines[0].startswith('#'):
            title = lines[0].lstrip('#').strip()
            lines = lines[1:]

        messages = []
        current_role = None
        current_lines = []

        def flush():
            if current_role:
                content = '\n'.join(current_lines).strip()
                if content:
                    messages.append(Message(role=current_role, content=content))

        for line in lines:
            if self.USER_PATTERN.match(line):
                flush()
                current_role = 'user'
                current_lines = [self.USER_PATTERN.sub('', line).strip()]
            elif self.ASSISTANT_PATTERN.match(line):
                flush()
                current_role = 'assistant'
                current_lines = [self.ASSISTANT_PATTERN.sub('', line).strip()]
            else:
                current_lines.append(line)
        flush()

        return Conversation(title=title, messages=messages, platform=self.PLATFORM)


# ── HTML rendering ────────────────────────────────────────────────────────────

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="author" content="{platform}">
<meta name="date" content="{date_iso}">
<title>{title_escaped}</title>
<style>
  body {{ font-family: Georgia, serif; max-width: 820px; margin: 2em auto;
         padding: 0 1.2em; color: #1a1a1a; line-height: 1.6; }}
  h1   {{ font-size: 1.35em; border-bottom: 1px solid #ddd; padding-bottom: .4em; }}
  .meta {{ color: #888; font-size: .85em; margin-bottom: 2em; }}
  .message {{ margin: 1.4em 0; }}
  .role {{ font-weight: bold; font-size: .8em; text-transform: uppercase;
           letter-spacing: .06em; margin-bottom: .25em; }}
  .user      .role {{ color: #1a4f8a; }}
  .assistant .role {{ color: #1a6e35; }}
  .content {{ white-space: pre-wrap; }}
  pre  {{ background: #f5f5f5; padding: .8em 1em; border-radius: 4px;
         overflow-x: auto; font-size: .88em; }}
  code {{ background: #f0f0f0; padding: .1em .3em; border-radius: 3px;
         font-size: .9em; font-family: monospace; }}
  pre code {{ background: none; padding: 0; }}
  hr   {{ border: none; border-top: 1px solid #eee; margin: 1.8em 0; }}
</style>
</head>
<body>
<h1>{title_escaped}</h1>
<p class="meta">Platform: {platform} &nbsp;·&nbsp; {date_display}</p>
{body}
</body>
</html>"""


def _text_to_html(text: str) -> str:
    """Escape HTML in plain text, preserving fenced code blocks."""
    segments = re.split(r'(```(?:\w+)?\n?[\s\S]*?```)', text)
    parts = []
    for i, seg in enumerate(segments):
        if i % 2 == 1:
            m = re.match(r'```(\w*)\n?([\s\S]*?)```', seg)
            if m:
                lang = html_module.escape(m.group(1))
                code = html_module.escape(m.group(2).rstrip())
                cls = f' class="language-{lang}"' if lang else ''
                parts.append(f'<pre><code{cls}>{code}</code></pre>')
        else:
            escaped = html_module.escape(seg)
            # Inline code: backticks survive html.escape unchanged
            escaped = re.sub(r'`([^`\n]+)`',
                             lambda m2: f'<code>{html_module.escape(m2.group(1))}</code>',
                             escaped)
            parts.append(escaped)
    return ''.join(parts)


def conversation_to_html(conv: Conversation) -> str:
    date_iso = conv.created_at.strftime('%Y-%m-%d') if conv.created_at else ''
    date_display = conv.created_at.strftime('%Y-%m-%d') if conv.created_at else 'unknown date'

    blocks = []
    for msg in conv.messages:
        label = 'You' if msg.role == 'user' else conv.platform
        blocks.append(
            f'<div class="message {msg.role}">\n'
            f'  <div class="role">{html_module.escape(label)}</div>\n'
            f'  <div class="content">{_text_to_html(msg.content)}</div>\n'
            f'</div>'
        )

    return _HTML_TEMPLATE.format(
        title_escaped=html_module.escape(conv.display_title),
        platform=html_module.escape(conv.platform),
        date_iso=date_iso,
        date_display=date_display,
        body='\n<hr>\n'.join(blocks),
    )


def safe_filename(title: str, max_len: int = 80) -> str:
    name = re.sub(r'[\\/:*?"<>|]', '_', title)
    return re.sub(r'\s+', ' ', name).strip()[:max_len] or 'conversation'


# ── Calibre integration ───────────────────────────────────────────────────────

def add_to_calibre(html_path: Path, conv: Conversation,
                   library_path: Optional[str] = None) -> bool:
    tags = ['AI-Chat', conv.platform]
    if conv.created_at:
        tags.append(conv.created_at.strftime('%Y-%m'))

    cmd = ['calibredb', 'add', str(html_path),
           '--title', conv.display_title,
           '--author', conv.platform,
           '--tags', ','.join(tags)]
    if library_path:
        cmd += ['--library-path', library_path]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.returncode == 0
    except FileNotFoundError:
        print('  ⚠️  calibredb not found — import HTML files into Calibre manually')
        return False


# ── Parser registry ───────────────────────────────────────────────────────────

PARSERS = {
    'chatgpt':    ChatGPTParser(),
    'gemini':     GeminiParser(),
    'grok':       GrokParser(),
    'claude':     MarkdownParser(platform='Claude'),
    'perplexity': MarkdownParser(platform='Perplexity'),
}


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description='Import AI chat exports into Calibre-ready HTML files.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__)

    ap.add_argument('--source', required=True, choices=list(PARSERS),
                    help='Source platform')
    ap.add_argument('--input', required=True, type=Path,
                    help='Export file (ZIP/TGZ) or folder of Markdown files')
    ap.add_argument('--output', type=Path, default=Path('./ai_chat_import'),
                    help='Output directory for HTML files (default: ./ai_chat_import)')
    ap.add_argument('--add-to-calibre', action='store_true',
                    help='Import HTML files directly into Calibre via calibredb')
    ap.add_argument('--library-path',
                    help='Calibre library path (uses Calibre default if omitted)')
    ap.add_argument('--dry-run', action='store_true',
                    help='Preview what would be imported without writing files')
    args = ap.parse_args()

    if not args.input.exists():
        print(f'❌ Not found: {args.input}')
        sys.exit(1)

    platform_parser = PARSERS[args.source]
    if not platform_parser.can_parse(args.input):
        print(f'❌ Input does not look like a {args.source} export: {args.input}')
        sys.exit(1)

    print(f'📥 Parsing {args.source} export: {args.input}')
    conversations = platform_parser.parse(args.input)
    print(f'   Found {len(conversations)} conversations\n')

    if not conversations:
        return

    if not args.dry_run:
        args.output.mkdir(parents=True, exist_ok=True)

    imported = errors = 0
    for conv in conversations:
        date_str = conv.created_at.strftime('%Y-%m-%d') if conv.created_at else '????-??-??'

        if args.dry_run:
            print(f'  [{date_str}] {conv.display_title[:70]} ({len(conv.messages)} messages)')
            continue

        filename = safe_filename(f'{conv.platform} - {conv.display_title}') + '.html'
        out_path = args.output / filename
        out_path.write_text(conversation_to_html(conv), encoding='utf-8')

        if args.add_to_calibre:
            if add_to_calibre(out_path, conv, args.library_path):
                print(f'  ✅ [{date_str}] {conv.display_title[:60]}')
                imported += 1
            else:
                print(f'  ⚠️  [{date_str}] {conv.display_title[:55]} (saved, not imported)')
                errors += 1
        else:
            print(f'  💾 [{date_str}] {out_path.name}')
            imported += 1

    if not args.dry_run:
        print(f'\n{"="*55}')
        print(f'  Conversations processed: {imported + errors}')
        if errors:
            print(f'  Calibre import errors:   {errors}')
        if not args.add_to_calibre:
            print(f'\n  📂 HTML files saved to: {args.output}')
            print(f'  → Drag folder into Calibre, or run:')
            print(f'     calibredb add "{args.output}" --recurse')


if __name__ == '__main__':
    main()
