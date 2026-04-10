"""
Dialogue-aware chunker for chat/Q&A Markdown exports.

Activation: set ``chunking_strategy: dialogue`` in the note's YAML frontmatter.
The pipeline checks this field automatically for ``.md``/``.markdown`` files.

Chunking unit: one user prompt + the following LLM response (an "exchange").
Long LLM responses are split at paragraph boundaries; each continuation chunk
repeats the user prompt as a context header so it remains self-contained.

Supported turn-marker formats (in order of detection precedence):
    **User:**          bold with colon-inside  (ChatGPT, Grok, Gemini exports)
    **User**:          bold with colon-outside
    User:              plain colon on its own line
"""

import re
import logging
from dataclasses import dataclass
from typing import List, Optional

from src.archilles.constants import ChunkType
from .base import TextChunker, TextChunk, ChunkerConfig

logger = logging.getLogger(__name__)

# ── Default speaker sets ────────────────────────────────────────

DEFAULT_USER_MARKERS: frozenset[str] = frozenset({
    "user", "tom", "human", "nutzer", "ich",
})

DEFAULT_LLM_MARKERS: frozenset[str] = frozenset({
    "chatgpt", "grok", "gemini", "claude", "assistant",
    "copilot", "perplexity", "mistral", "llama", "deepseek",
    "chatbot", "ai", "bot",
})

# ── Turn-marker regex patterns ──────────────────────────────────

# **Speaker:** or **Speaker**: (bold, colon inside or outside the stars)
_BOLD_TURN = re.compile(
    r'(?m)^(?:\*\*([^*:]+):\*\*|\*\*([^*]+)\*\*:)\s*',
)

# **[SPEAKER]** on its own line — Perplexity export format
_BRACKET_TURN = re.compile(
    r'(?m)^\*\*\[([A-Z][A-Z0-9 _]{0,30})\]\*\*\s*$',
)

# Plain "Speaker:" on its own line (no bold) — used as fallback
_PLAIN_TURN = re.compile(
    r'(?m)^([A-Za-z][A-Za-z0-9 ]{0,30}):\s*$',
)


@dataclass
class _Turn:
    speaker: str       # normalised lowercase
    raw_speaker: str   # original label, for display in chunks
    content: str       # text belonging to this turn (stripped)


def _parse_turns(text: str) -> List[_Turn]:
    """Split *text* into turns.  Returns [] if no turn markers found."""
    # Try bold format first (most specific → fewest false positives)
    matches = list(_BOLD_TURN.finditer(text))
    bracket = False
    if not matches:
        matches = list(_BRACKET_TURN.finditer(text))
        bracket = bool(matches)
    if not matches:
        matches = list(_PLAIN_TURN.finditer(text))
    if not matches:
        return []

    turns: List[_Turn] = []
    for i, m in enumerate(matches):
        if bracket:
            # **[SPEAKER]** — single capture group, title-case for display
            raw = m.group(1).strip()
            raw_display = raw.title()
        else:
            # Group 1 = colon-inside (**Speaker:**), group 2 = colon-outside (**Speaker**:)
            # Group 1 also used for plain "Speaker:" pattern
            raw = (m.group(1) or m.group(2) or "").strip()
            raw_display = raw
        content_start = m.end()
        content_end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        content = text[content_start:content_end].strip()
        if raw:
            turns.append(_Turn(
                speaker=raw.lower(),
                raw_speaker=raw_display,
                content=content,
            ))
    return turns


def _group_exchanges(
    turns: List[_Turn],
    user_markers: frozenset[str],
) -> List[tuple[str, str, str]]:
    """Group turns into (user_content, llm_raw_speaker, llm_content) triples.

    Rules:
    - User turns accumulate until a non-user speaker appears.
    - That non-user turn (LLM) closes the exchange.
    - Consecutive LLM turns without an interleaved user turn are each their
      own exchange with an empty user_content.
    - Trailing user turns without a response become an exchange with empty
      llm_content (edge case, e.g. file cut off mid-conversation).
    """
    exchanges: List[tuple[str, str, str]] = []
    pending_user: List[str] = []

    for turn in turns:
        if turn.speaker in user_markers:
            pending_user.append(turn.content)
        else:
            user_content = "\n\n".join(pending_user)
            exchanges.append((user_content, turn.raw_speaker, turn.content))
            pending_user = []

    # Flush any trailing user turn(s) without a response
    if pending_user:
        exchanges.append(("\n\n".join(pending_user), "", ""))

    return exchanges


def _split_paragraphs(text: str, max_tokens: int, estimate_fn) -> List[str]:
    """Split *text* into parts each fitting in *max_tokens*, at paragraph breaks."""
    paragraphs = [p.strip() for p in re.split(r'\n{2,}', text) if p.strip()]
    if not paragraphs:
        return [text] if text.strip() else []

    parts: List[str] = []
    current_parts: List[str] = []
    current_tokens = 0

    for para in paragraphs:
        para_tokens = estimate_fn(para)
        if current_tokens + para_tokens > max_tokens and current_parts:
            parts.append("\n\n".join(current_parts))
            current_parts = [para]
            current_tokens = para_tokens
        else:
            current_parts.append(para)
            current_tokens += para_tokens

    if current_parts:
        parts.append("\n\n".join(current_parts))

    return parts


class DialogueChunker(TextChunker):
    """Chunks chat/dialogue Markdown by user→LLM exchange units.

    Each chunk corresponds to one complete exchange (user prompt + LLM response).
    When an LLM response exceeds *max_exchange_tokens*, it is split at paragraph
    boundaries and the user prompt is prepended to every continuation chunk so
    each chunk remains semantically self-contained.

    Activated automatically by :class:`~src.archilles.pipeline.ModularPipeline`
    when the document's YAML frontmatter contains::

        chunking_strategy: dialogue
    """

    def __init__(
        self,
        config: Optional[ChunkerConfig] = None,
        user_markers: Optional[frozenset[str]] = None,
        llm_markers: Optional[frozenset[str]] = None,
        max_exchange_tokens: int = 800,
        repeat_prompt_on_split: bool = True,
        prompt_header_max_tokens: int = 150,
    ):
        super().__init__(config)
        self.user_markers = (
            frozenset(m.lower() for m in user_markers)
            if user_markers is not None
            else DEFAULT_USER_MARKERS
        )
        self.llm_markers = (
            frozenset(m.lower() for m in llm_markers)
            if llm_markers is not None
            else DEFAULT_LLM_MARKERS
        )
        self.max_exchange_tokens = max_exchange_tokens
        self.repeat_prompt_on_split = repeat_prompt_on_split
        # Max tokens the user-prompt header may occupy when prepended to split
        # continuation chunks.  Long prompts are truncated with an ellipsis.
        self.prompt_header_max_tokens = prompt_header_max_tokens

    # ── Interface ───────────────────────────────────────────────

    @property
    def name(self) -> str:
        return "dialogue"

    @property
    def description(self) -> str:
        return "Chunks chat/dialogue Markdown by user→LLM exchange units"

    def chunk(self, text: str, source_file: str = "") -> List[TextChunk]:
        """Split *text* into exchange-based chunks."""
        turns = _parse_turns(text)

        if not turns:
            logger.debug("No turn markers found in %s — falling back to single chunk", source_file)
            # Return empty so pipeline falls through to semantic chunker
            return []

        exchanges = _group_exchanges(turns, self.user_markers)
        chunks: List[TextChunk] = []
        chunk_idx = 0

        for exchange_idx, (user_content, llm_speaker, llm_content) in enumerate(exchanges):
            # Skip empty exchanges (e.g. double user-turns with no LLM response captured)
            if not user_content and not llm_content:
                continue

            exchange_text = self._format_exchange(user_content, llm_speaker, llm_content)
            base_meta = {
                "chunk_type": ChunkType.EXCHANGE,
                "exchange_index": exchange_idx,
                "user_prompt_preview": (user_content or llm_content)[:120].replace("\n", " "),
                "turn_count": 1,
            }

            if self.estimate_tokens(exchange_text) <= self.max_exchange_tokens:
                chunks.append(TextChunk(
                    text=exchange_text,
                    chunk_index=chunk_idx,
                    source_file=source_file,
                    metadata=base_meta,
                ))
                chunk_idx += 1
            else:
                # Split long LLM response at paragraph boundaries
                user_header = self._format_user_header(user_content, llm_speaker)
                header_tokens = self.estimate_tokens(user_header)
                available = max(self.max_exchange_tokens - header_tokens, 50)

                parts = _split_paragraphs(llm_content, available, self.estimate_tokens)
                if not parts:
                    parts = [llm_content]

                for part_idx, part in enumerate(parts):
                    if self.repeat_prompt_on_split or part_idx == 0:
                        chunk_text = user_header + part
                    else:
                        label = f"**{llm_speaker}:** (Forts.)" if llm_speaker else "(Forts.)"
                        chunk_text = f"{label}\n{part}"

                    chunks.append(TextChunk(
                        text=chunk_text,
                        chunk_index=chunk_idx,
                        source_file=source_file,
                        metadata={**base_meta, "part_index": part_idx},
                    ))
                    chunk_idx += 1

        logger.debug(
            "DialogueChunker: %d exchanges → %d chunks (%s)",
            len(exchanges), len(chunks), source_file,
        )
        return chunks

    # ── Helpers ─────────────────────────────────────────────────

    @staticmethod
    def _format_exchange(user_content: str, llm_speaker: str, llm_content: str) -> str:
        parts: List[str] = []
        if user_content:
            parts.append(f"**User:**\n{user_content}")
        if llm_content:
            label = f"**{llm_speaker}:**" if llm_speaker else "**Assistant:**"
            parts.append(f"{label}\n{llm_content}")
        return "\n\n".join(parts)

    def _format_user_header(self, user_content: str, llm_speaker: str) -> str:
        """Build the repeated-prompt prefix for split chunks.

        If the user prompt exceeds *prompt_header_max_tokens*, it is truncated
        at a word boundary and an ellipsis is appended.  This ensures that long
        user prompts don't crowd out the LLM-response content in continuation
        chunks.
        """
        llm_label = f"**{llm_speaker}:**" if llm_speaker else "**Assistant:**"
        if not user_content:
            return f"{llm_label}\n"

        truncated = self._truncate_to_tokens(user_content, self.prompt_header_max_tokens)
        return f"**User:**\n{truncated}\n\n{llm_label}\n"

    def _truncate_to_tokens(self, text: str, max_tokens: int) -> str:
        """Truncate *text* to *max_tokens*, breaking at a word boundary."""
        if self.estimate_tokens(text) <= max_tokens:
            return text
        # Approximate character limit (estimate_tokens uses ~4 chars/token)
        char_limit = max_tokens * 4
        truncated = text[:char_limit]
        # Break at the last space to avoid splitting mid-word
        last_space = truncated.rfind(' ')
        if last_space > char_limit // 2:
            truncated = truncated[:last_space]
        return truncated.rstrip() + " […]"
