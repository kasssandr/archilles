"""
Automatic language detection for text chunks.

Uses langdetect library to identify languages (ISO 639-1 codes).
Optimized for academic texts in multiple languages.
"""

from typing import Optional, List, Dict
import logging

try:
    from langdetect import detect, detect_langs, LangDetectException
    LANGDETECT_AVAILABLE = True
except ImportError:
    LANGDETECT_AVAILABLE = False

logger = logging.getLogger(__name__)


class LanguageDetector:
    """
    Detect language of text chunks.

    Returns ISO 639-1 codes (e.g., 'en', 'de', 'la', 'grc') or
    ISO 639-3 for ancient languages.
    """

    # Common languages in Tom's library
    LANGUAGE_NAMES = {
        'en': 'English',
        'de': 'German',
        'fr': 'French',
        'la': 'Latin',
        'it': 'Italian',
        'es': 'Spanish',
        'grc': 'Ancient Greek',
        'he': 'Hebrew',
        'ar': 'Arabic',
    }

    @classmethod
    def detect(cls, text: str, min_confidence: float = 0.9) -> Optional[str]:
        """
        Detect language of text.

        Args:
            text: Text to analyze
            min_confidence: Minimum confidence threshold (0-1)

        Returns:
            ISO 639-1/3 language code or None if uncertain
        """
        if not LANGDETECT_AVAILABLE:
            logger.debug("langdetect not available, skipping language detection")
            return None

        if not text or len(text.strip()) < 50:
            # Too short for reliable detection
            return None

        try:
            # Get probabilities for all detected languages
            lang_probs = detect_langs(text)

            if not lang_probs:
                return None

            # Get most likely language
            top_lang = lang_probs[0]

            # Only return if confidence is high enough
            if top_lang.prob >= min_confidence:
                return top_lang.lang
            else:
                logger.debug(
                    f"Language detection uncertain: {top_lang.lang} "
                    f"({top_lang.prob:.2f} < {min_confidence})"
                )
                return None

        except LangDetectException as e:
            logger.debug(f"Language detection failed: {e}")
            return None

    @classmethod
    def detect_with_confidence(cls, text: str) -> Optional[Dict[str, float]]:
        """
        Detect language with confidence scores for all candidates.

        Args:
            text: Text to analyze

        Returns:
            Dict with 'language' and 'confidence', or None
        """
        if not LANGDETECT_AVAILABLE:
            return None

        if not text or len(text.strip()) < 50:
            return None

        try:
            lang_probs = detect_langs(text)
            if not lang_probs:
                return None

            top_lang = lang_probs[0]
            return {
                'language': top_lang.lang,
                'confidence': top_lang.prob,
                'alternatives': [
                    {'language': lp.lang, 'confidence': lp.prob}
                    for lp in lang_probs[1:3]  # Top 3 alternatives
                ]
            }
        except LangDetectException:
            return None

    @classmethod
    def detect_for_chunks(
        cls,
        chunks: List[Dict],
        min_confidence: float = 0.9
    ) -> List[Dict]:
        """
        Add language detection to chunks.

        Args:
            chunks: List of chunks with 'text' key
            min_confidence: Minimum confidence threshold

        Returns:
            Same chunks with 'language' added to metadata
        """
        if not LANGDETECT_AVAILABLE:
            logger.warning(
                "langdetect not installed. Language filtering won't work. "
                "Install with: pip install langdetect"
            )
            return chunks

        for chunk in chunks:
            text = chunk.get('text', '')
            lang = cls.detect(text, min_confidence=min_confidence)

            if lang:
                # Add to metadata
                if 'metadata' not in chunk:
                    chunk['metadata'] = {}
                chunk['metadata']['language'] = lang

        return chunks

    @classmethod
    def is_available(cls) -> bool:
        """Check if language detection is available."""
        return LANGDETECT_AVAILABLE

    @classmethod
    def get_language_name(cls, code: str) -> str:
        """
        Get human-readable language name from code.

        Args:
            code: ISO 639-1/3 language code

        Returns:
            Language name or the code itself
        """
        return cls.LANGUAGE_NAMES.get(code, code.upper())
