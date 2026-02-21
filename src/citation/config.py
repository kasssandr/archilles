"""Citation style configuration for ARCHILLES.

Design goals
------------
1. **Minimal now**: a dataclass + a dict of prompt fragments is all we need
   today, because Claude handles the actual formatting.
2. **CSL-ready**: the ``csl_style`` field stores the canonical CSL style ID
   (e.g. "chicago-author-date") so that citeproc-py can be wired in later
   without changing the config schema.
3. **Zotero-compatible**: the CSL style IDs used here are the same IDs used
   by Zotero's style repository, ensuring a seamless handover when the
   Zotero backend is added (see ROADMAP.md).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Style registry
# ---------------------------------------------------------------------------
# Each entry maps a short key to:
#   - label:       human-readable name (shown in setup / config)
#   - csl_style:   canonical CSL style ID (for future citeproc-py use)
#   - locale_hint: typical locale (user can override)
#   - prompt_de:   German instruction fragment for the RAG system prompt
#   - prompt_en:   English instruction fragment for the RAG system prompt
#   - example:     one-line example so the user knows what they get

CITATION_STYLES: Dict[str, Dict[str, str]] = {
    "chicago-author-date": {
        "label": "Chicago (Author-Date)",
        "csl_style": "chicago-author-date-17th-edition",
        "locale_hint": "en-US",
        "prompt_de": (
            "Formatiere die Literaturliste im Chicago-Stil (Author-Date, 17. Auflage). "
            "Beispiel: Müller, Anna. 2019. *Titel des Buches*. Berlin: Verlag."
        ),
        "prompt_en": (
            "Format the bibliography in Chicago style (Author-Date, 17th edition). "
            "Example: Mueller, Anna. 2019. *Book Title*. Berlin: Publisher."
        ),
        "example": "Müller, Anna. 2019. *Titel*. Berlin: Verlag.",
    },
    "chicago-note": {
        "label": "Chicago (Notes & Bibliography)",
        "csl_style": "chicago-note-bibliography-17th-edition",
        "locale_hint": "en-US",
        "prompt_de": (
            "Formatiere die Literaturliste im Chicago-Stil (Notes & Bibliography, 17. Auflage). "
            "Verwende Fußnoten-Notation mit vollständiger Erstnennung. "
            "Beispiel: Anna Müller, *Titel des Buches* (Berlin: Verlag, 2019), 42."
        ),
        "prompt_en": (
            "Format the bibliography in Chicago style (Notes & Bibliography, 17th edition). "
            "Use footnote notation with full first citation. "
            "Example: Anna Mueller, *Book Title* (Berlin: Publisher, 2019), 42."
        ),
        "example": "Anna Müller, *Titel* (Berlin: Verlag, 2019), 42.",
    },
    "apa7": {
        "label": "APA 7th Edition",
        "csl_style": "apa-7th-edition",
        "locale_hint": "en-US",
        "prompt_de": (
            "Formatiere die Literaturliste nach APA (7. Auflage). "
            "Beispiel: Müller, A. (2019). *Titel des Buches*. Verlag."
        ),
        "prompt_en": (
            "Format the bibliography in APA style (7th edition). "
            "Example: Mueller, A. (2019). *Book title*. Publisher."
        ),
        "example": "Müller, A. (2019). *Titel*. Verlag.",
    },
    "harvard": {
        "label": "Harvard",
        "csl_style": "harvard-cite-them-right",
        "locale_hint": "en-GB",
        "prompt_de": (
            "Formatiere die Literaturliste im Harvard-Stil. "
            "Beispiel: Müller, A. (2019) *Titel des Buches*. Berlin: Verlag."
        ),
        "prompt_en": (
            "Format the bibliography in Harvard style. "
            "Example: Mueller, A. (2019) *Book title*. Berlin: Publisher."
        ),
        "example": "Müller, A. (2019) *Titel*. Berlin: Verlag.",
    },
    "mla9": {
        "label": "MLA 9th Edition",
        "csl_style": "modern-language-association",
        "locale_hint": "en-US",
        "prompt_de": (
            "Formatiere die Literaturliste nach MLA (9. Auflage). "
            "Beispiel: Müller, Anna. *Titel des Buches*. Verlag, 2019."
        ),
        "prompt_en": (
            "Format the bibliography in MLA style (9th edition). "
            "Example: Mueller, Anna. *Book Title*. Publisher, 2019."
        ),
        "example": "Müller, Anna. *Titel*. Verlag, 2019.",
    },
    "ieee": {
        "label": "IEEE",
        "csl_style": "ieee",
        "locale_hint": "en-US",
        "prompt_de": (
            "Formatiere die Literaturliste im IEEE-Stil mit nummerierten Referenzen. "
            "Beispiel: [1] A. Müller, *Titel des Buches*. Berlin: Verlag, 2019."
        ),
        "prompt_en": (
            "Format the bibliography in IEEE style with numbered references. "
            "Example: [1] A. Mueller, *Book Title*. Berlin: Publisher, 2019."
        ),
        "example": "[1] A. Müller, *Titel*. Berlin: Verlag, 2019.",
    },
}

# Default style when nothing is configured
DEFAULT_STYLE = "chicago-author-date"
DEFAULT_LOCALE = "de-DE"


# ---------------------------------------------------------------------------
# Configuration dataclass
# ---------------------------------------------------------------------------

@dataclass
class CitationConfig:
    """User's citation preferences.

    Attributes:
        style:   key into CITATION_STYLES (e.g. "apa7", "chicago-note")
        locale:  BCP-47 locale tag (e.g. "de-DE", "en-US")
        csl_path: optional path to a custom .csl file (for future use)

    The ``style`` field doubles as the lookup key for prompt fragments
    *and* as the base for resolving the canonical CSL style ID when
    citeproc-py is available.
    """

    style: str = DEFAULT_STYLE
    locale: str = DEFAULT_LOCALE
    csl_path: Optional[str] = None

    def __post_init__(self) -> None:
        if self.style not in CITATION_STYLES:
            logger.warning(
                "Unknown citation style %r, falling back to %r",
                self.style,
                DEFAULT_STYLE,
            )
            self.style = DEFAULT_STYLE

    # -- Convenience helpers -------------------------------------------------

    @property
    def label(self) -> str:
        """Human-readable style name."""
        return CITATION_STYLES[self.style]["label"]

    @property
    def csl_style_id(self) -> str:
        """Canonical CSL style ID (for citeproc-py / Zotero)."""
        return CITATION_STYLES[self.style]["csl_style"]

    @property
    def prompt_fragment(self) -> str:
        """Localized prompt instruction for the current style."""
        lang = self.locale.split("-")[0]
        key = "prompt_de" if lang == "de" else "prompt_en"
        return CITATION_STYLES[self.style][key]

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for config.json."""
        d: Dict[str, Any] = {
            "style": self.style,
            "locale": self.locale,
        }
        if self.csl_path:
            d["csl_path"] = self.csl_path
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CitationConfig":
        """Deserialize from config.json ``citation`` section."""
        return cls(
            style=data.get("style", DEFAULT_STYLE),
            locale=data.get("locale", DEFAULT_LOCALE),
            csl_path=data.get("csl_path"),
        )


# ---------------------------------------------------------------------------
# Prompt generation
# ---------------------------------------------------------------------------

def format_bibliography_instruction(cfg: CitationConfig) -> str:
    """Build the bibliography instruction block for the RAG system prompt.

    This is injected into rule 5 of the system prompt so that Claude
    formats the bibliography in the user's preferred style.
    """
    return cfg.prompt_fragment
