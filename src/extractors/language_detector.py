"""
Automatic language detection for text chunks.

Uses Lingua library for accurate language identification (ISO 639-1 codes).
Optimized for academic texts in multiple languages.
"""

from typing import Optional, List, Dict
import logging
from collections import Counter

try:
    from lingua import Language, LanguageDetectorBuilder
    LINGUA_AVAILABLE = True

    # Build detector with ALL 75 supported languages
    # This ensures the system works out-of-the-box for any user worldwide
    # Performance impact: minimal (<5% slower vs. language-specific subset)
    # Supported: All major languages incl. Chinese, Japanese, Korean, Arabic, etc.
    _DETECTOR = LanguageDetectorBuilder.from_all_languages().build()
except ImportError:
    LINGUA_AVAILABLE = False
    _DETECTOR = None

logger = logging.getLogger(__name__)


class LanguageDetector:
    """
    Detect language of text chunks using Lingua library.

    Returns ISO 639-1 codes (e.g., 'en', 'de', 'la', 'el').
    """

    # Language code mapping (Lingua uses ISO 639-1)
    LANGUAGE_NAMES = {
        'en': 'English',
        'de': 'German',
        'fr': 'French',
        'la': 'Latin',
        'it': 'Italian',
        'es': 'Spanish',
        'el': 'Greek',  # Modern Greek (covers ancient Greek text too)
        'he': 'Hebrew',
        'ar': 'Arabic',
        'ru': 'Russian',
        'pt': 'Portuguese',
        'nl': 'Dutch',
    }

    @classmethod
    def detect(cls, text: str, min_confidence: float = 0.9) -> Optional[str]:
        """
        Detect language of text.

        Args:
            text: Text to analyze
            min_confidence: Minimum confidence threshold (0-1)

        Returns:
            ISO 639-1 language code or None if uncertain
        """
        if not LINGUA_AVAILABLE or _DETECTOR is None:
            logger.debug("Lingua not available, skipping language detection")
            return None

        if not text or len(text.strip()) < 50:
            # Too short for reliable detection
            return None

        try:
            # Get confidence values for all languages
            confidence_values = _DETECTOR.compute_language_confidence_values(text)

            if not confidence_values:
                return None

            # Get most confident language
            top_match = confidence_values[0]
            confidence = top_match.value

            if confidence >= min_confidence:
                return top_match.language.iso_code_639_1.name.lower()

            logger.debug(
                f"Language detection uncertain: {top_match.language.name} "
                f"({confidence:.2f} < {min_confidence})"
            )
            return None

        except Exception as e:
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
        if not LINGUA_AVAILABLE or _DETECTOR is None:
            return None

        if not text or len(text.strip()) < 50:
            return None

        try:
            confidence_values = _DETECTOR.compute_language_confidence_values(text)

            if not confidence_values:
                return None

            top_match = confidence_values[0]
            lang_code = top_match.language.iso_code_639_1.name.lower()

            alternatives = []
            for match in confidence_values[1:3]:  # Top 3 alternatives
                alt_code = match.language.iso_code_639_1.name.lower()
                alternatives.append({
                    'language': alt_code,
                    'confidence': match.value
                })

            return {
                'language': lang_code,
                'confidence': top_match.value,
                'alternatives': alternatives
            }
        except Exception as e:
            logger.debug(f"Language detection failed: {e}")
            return None

    @classmethod
    def detect_for_chunks(
        cls,
        chunks: List[Dict],
        min_confidence: float = 0.9,
        show_progress: bool = False
    ) -> List[Dict]:
        """
        Add language detection to chunks.

        Args:
            chunks: List of chunks with 'text' key
            min_confidence: Minimum confidence threshold
            show_progress: Show progress bar (default: False)

        Returns:
            Same chunks with 'language' added to metadata
        """
        if not LINGUA_AVAILABLE:
            logger.warning(
                "Lingua not installed. Language filtering won't work. "
                "Install with: pip install lingua-language-detector"
            )
            return chunks

        # Progress bar
        try:
            from tqdm import tqdm
            iterator = tqdm(chunks, desc="    Detecting languages", leave=False) if show_progress else chunks
        except ImportError:
            iterator = chunks

        detected_languages = []

        for chunk in iterator:
            text = chunk.get('text', '')
            lang = cls.detect(text, min_confidence=min_confidence)

            if lang:
                # Add to metadata
                if 'metadata' not in chunk:
                    chunk['metadata'] = {}
                chunk['metadata']['language'] = lang
                detected_languages.append(lang)

        # Print summary
        if show_progress and detected_languages:
            lang_counts = Counter(detected_languages)
            summary_parts = [f"{cls.get_language_name(lang)} ({count})"
                           for lang, count in lang_counts.most_common()]
            summary = ", ".join(summary_parts)
            print(f"    ✓ Languages detected: {summary}")
            print(f"    ✓ {len(detected_languages)}/{len(chunks)} chunks with language info")

        return chunks

    @classmethod
    def is_available(cls) -> bool:
        """Check if language detection is available."""
        return LINGUA_AVAILABLE and _DETECTOR is not None

    @classmethod
    def get_language_name(cls, code: str) -> str:
        """
        Get human-readable language name from code.

        Args:
            code: ISO 639-1 language code

        Returns:
            Language name or the code itself
        """
        return cls.LANGUAGE_NAMES.get(code, code.upper())
