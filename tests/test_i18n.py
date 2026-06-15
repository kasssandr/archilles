"""Tests for the i18n foundation (P3 stage 1): config language resolution,
the ``t()`` message lookup, and its first consumers in the prompt/export path."""
import json
from pathlib import Path

from src.archilles import i18n
from src.archilles.config import DEFAULT_LANGUAGES, get_languages


def _write_config(library_path, cfg):
    d = library_path / ".archilles"
    d.mkdir(exist_ok=True)
    (d / "config.json").write_text(json.dumps(cfg), encoding="utf-8")


class TestGetLanguages:
    def test_no_library_context_returns_default(self):
        assert get_languages(None) == ["en"]
        assert get_languages(None) is not DEFAULT_LANGUAGES  # fresh copy

    def test_missing_config_returns_default(self, tmp_path):
        assert get_languages(tmp_path) == ["en"]

    def test_reads_languages_list(self, tmp_path):
        _write_config(tmp_path, {"languages": ["de", "en", "la"]})
        assert get_languages(tmp_path) == ["de", "en", "la"]

    def test_first_entry_is_operator_language(self, tmp_path):
        _write_config(tmp_path, {"languages": ["fr", "en"]})
        assert get_languages(tmp_path)[0] == "fr"

    def test_empty_list_falls_back(self, tmp_path):
        _write_config(tmp_path, {"languages": []})
        assert get_languages(tmp_path) == ["en"]

    def test_non_list_falls_back(self, tmp_path):
        _write_config(tmp_path, {"languages": "de"})
        assert get_languages(tmp_path) == ["en"]

    def test_drops_non_string_and_blank_entries(self, tmp_path):
        _write_config(tmp_path, {"languages": ["de", "", 3, "  ", "en"]})
        assert get_languages(tmp_path) == ["de", "en"]

    def test_broken_json_falls_back(self, tmp_path):
        d = tmp_path / ".archilles"
        d.mkdir()
        (d / "config.json").write_text("{ not valid json", encoding="utf-8")
        assert get_languages(tmp_path) == ["en"]


class TestTranslate:
    def test_english(self):
        assert i18n.t("export.relevance", "en") == "Relevance"

    def test_german(self):
        assert i18n.t("export.relevance", "de") == "Relevanz"

    def test_default_language_is_english(self):
        assert i18n.t("export.relevance") == "Relevance"

    def test_unknown_language_falls_back_to_english(self):
        assert i18n.t("export.title", "fr") == i18n.MESSAGES["en"]["export.title"]

    def test_missing_key_returns_the_key(self):
        assert i18n.t("does.not.exist", "en") == "does.not.exist"

    def test_german_bundle_keys_are_subset_of_english(self):
        # English is authoritative: every other-language key must exist in en,
        # otherwise t() could not fall back for it.
        missing = set(i18n.MESSAGES["de"]) - set(i18n.MESSAGES["en"])
        assert missing == set()


class TestSystemPromptStandardisedEnglish:
    """8.19: the LLM prompt is fixed to English (quality + maintainability),
    independent of the operator language."""

    def test_system_prompt_is_english(self):
        from src.archilles.engine.prompting import PromptBuilder
        sp = PromptBuilder.get_system_prompt()
        assert "academic research assistant" in sp
        assert "akademischer Forschungsassistent" not in sp
        assert "Du bist" not in sp

    def test_system_prompt_keeps_structure(self):
        from src.archilles.engine.prompting import PromptBuilder
        sp = PromptBuilder.get_system_prompt()
        assert "<system_instructions>" in sp
        assert "<rules>" in sp


class TestPromptMarkersAndExport:
    """XML markers/labels are English (Claude-facing); the markdown export
    follows the operator language via ``t()``."""

    @staticmethod
    def _rag(tmp_path):
        from src.archilles.engine import ArchillesRAG
        return ArchillesRAG(db_path=str(tmp_path / "db"), skip_model=True)

    @staticmethod
    def _results():
        return [{
            'rank': 1,
            'similarity': 0.75,
            'text': 'A test sentence about theology.',
            'metadata': {
                'author': 'Test Author',
                'book_title': 'Test Book',
                'year': 1958,
                'language': 'de',
                'page_number': 42,
            },
        }]

    def test_inline_metadata_markers_and_labels_are_english(self, tmp_path):
        rag = self._rag(tmp_path)
        inline = rag.prompt_builder._build_inline_metadata(
            self._results()[0]['metadata'], "doc_1"
        )
        assert inline.startswith("<<<SOURCE ID=doc_1>>>")
        assert "Author:" in inline and "Title:" in inline
        assert "Year:" in inline and "Page:" in inline and "Language:" in inline
        assert "<<<QUELLE" not in inline
        assert "Autor:" not in inline and "Seite:" not in inline

    def test_xml_meta_labels_and_end_marker_are_english(self, tmp_path):
        rag = self._rag(tmp_path)
        # <content> is XML-escaped, so assert on substrings that survive escaping
        xml = rag.prompt_builder.format_results_as_xml(self._results(), "theology")
        assert "Author:" in xml and "Title:" in xml and "Page:" in xml
        assert "Autor:" not in xml and "Seite:" not in xml and "Titel:" not in xml
        assert "END SOURCE" in xml
        assert "ENDE QUELLE" not in xml

    def test_export_uses_german_labels(self, tmp_path):
        rag = self._rag(tmp_path)
        out = str(tmp_path / "de.md")
        rag.export_to_markdown(self._results(), "theology", out, lang="de")
        text = Path(out).read_text(encoding="utf-8")
        assert "Suchergebnisse" in text
        assert "Relevanz:" in text

    def test_export_uses_english_labels(self, tmp_path):
        rag = self._rag(tmp_path)
        out = str(tmp_path / "en.md")
        rag.export_to_markdown(self._results(), "theology", out, lang="en")
        text = Path(out).read_text(encoding="utf-8")
        assert "Search Results" in text
        assert "Relevance:" in text
        assert "Suchergebnisse" not in text

    def test_export_defaults_to_english(self, tmp_path):
        rag = self._rag(tmp_path)
        out = str(tmp_path / "def.md")
        rag.export_to_markdown(self._results(), "theology", out)
        text = Path(out).read_text(encoding="utf-8")
        assert "Search Results" in text
