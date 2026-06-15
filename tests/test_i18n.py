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
        assert i18n.t("label.relevance", "en") == "Relevance"

    def test_german(self):
        assert i18n.t("label.relevance", "de") == "Relevanz"

    def test_default_language_is_english(self):
        assert i18n.t("label.relevance") == "Relevance"

    def test_unknown_language_falls_back_to_english(self):
        assert i18n.t("export.title", "fr") == i18n.MESSAGES["en"]["export.title"]

    def test_missing_key_returns_the_key(self):
        assert i18n.t("does.not.exist", "en") == "does.not.exist"

    def test_builtin_bundles_have_identical_keys(self):
        # English and German are both shipped as complete built-ins; their key
        # sets must match exactly (no key only in one). Catches typos and
        # forgotten translations.
        assert set(i18n.MESSAGES["en"]) == set(i18n.MESSAGES["de"])


class TestWebUiKeys:
    """The web UI strings (Etappe 3) resolve in both built-in languages and
    keep their format placeholders intact."""

    def test_generic_labels(self):
        assert i18n.t("label.author", "de") == "Autor"
        assert i18n.t("label.author", "en") == "Author"
        assert i18n.t("label.page", "de") == "Seite"
        assert i18n.t("label.chapter", "en") == "Chapter"

    def test_webui_chrome(self):
        assert i18n.t("webui.tab_search", "de") == "🔍 Suche"
        assert i18n.t("webui.tab_search", "en") == "🔍 Search"
        assert i18n.t("webui.search_settings", "de") == "Sucheinstellungen"
        assert i18n.t("webui.index_status", "en") == "Index Status"

    def test_placeholder_formatting(self):
        # Keys with placeholders must format cleanly in both languages.
        de = i18n.t("webui.results_found", "de").format(n=3, query="Freiheit")
        assert "3" in de and "Freiheit" in de
        en = i18n.t("webui.books_indexed_summary", "en").format(n=12, chunks="1,000")
        assert "12" in en and "1,000" in en
        assert i18n.t("webui.parent_chunk", "de").format(id="abc") == "Eltern-Chunk (abc):"

    def test_unknown_language_falls_back(self):
        assert i18n.t("webui.button_search", "fr") == "🔍 Search"


class TestCorpusData:
    """Corpus-language data (Etappe 5): OCR codes, stop words, TOC keywords,
    dialogue markers, locales — derived from the languages list."""

    def test_ocr_language_joins_active(self):
        assert i18n.get_ocr_language(["de", "en"]) == "deu+eng"
        assert i18n.get_ocr_language(["la", "de"]) == "lat+deu"
        assert i18n.get_ocr_language(["en"]) == "eng"

    def test_ocr_language_fallbacks(self):
        assert i18n.get_ocr_language([]) == "eng"
        assert i18n.get_ocr_language(None) == "eng"
        assert i18n.get_ocr_language(["xx"]) == "eng"  # unknown ISO code

    def test_ocr_language_dedups(self):
        assert i18n.get_ocr_language(["en", "en"]) == "eng"

    def test_stopwords_are_language_scoped(self):
        # finding 8.3: a single mixed set let German 'die' drop English "die".
        en = i18n.get_stopwords(["en"])
        de = i18n.get_stopwords(["de"])
        assert "the" in en and "die" not in en
        assert "die" in de and "the" not in de

    def test_stopwords_union(self):
        both = i18n.get_stopwords(["de", "en"])
        assert "the" in both and "die" in both

    def test_stopwords_none_is_all(self):
        all_sw = i18n.get_stopwords(None)
        assert {"the", "die", "le", "et"} <= all_sw  # en, de, fr, la

    def test_locale(self):
        assert i18n.get_locale(["de"]) == "de-DE"
        assert i18n.get_locale(["en", "de"]) == "en-US"
        assert i18n.get_locale(None) == "en-US"
        assert i18n.get_locale(["xx"]) == "en-US"

    def test_toc_keywords_union_all_languages(self):
        kw = i18n.get_toc_keywords()
        assert "chapter" in kw and "kapitel" in kw
        front = i18n.get_toc_front_matter_keywords()
        assert "preface" in front and "vorwort" in front

    def test_dialogue_markers_drop_private_name(self):
        markers = i18n.get_dialogue_user_markers()
        assert "tom" not in markers  # finding 3.19: private name removed
        assert "nutzer" in markers and "user" in markers

    def test_dialogue_markers_language_scoped(self):
        en = i18n.get_dialogue_user_markers(["en"])
        assert "user" in en and "nutzer" not in en


class TestEngineCorpusIntegration:
    """ArchillesRAG derives OCR language and the query stop-word set from the
    `languages` constructor argument (findings 2.33, 8.3)."""

    @staticmethod
    def _rag(tmp_path, **kw):
        from src.archilles.engine import ArchillesRAG
        return ArchillesRAG(db_path=str(tmp_path / "db"), skip_model=True, **kw)

    def test_stop_words_language_scoped(self, tmp_path):
        rag = self._rag(tmp_path, languages=["en"])
        assert "the" in rag.stop_words and "der" not in rag.stop_words

    def test_stop_words_union(self, tmp_path):
        rag = self._rag(tmp_path, languages=["de", "en"])
        assert "the" in rag.stop_words and "der" in rag.stop_words

    def test_default_languages_keep_all_stop_words(self, tmp_path):
        # No languages → all known stop words (legacy behaviour, no break).
        rag = self._rag(tmp_path)
        assert {"the", "der", "le"} <= rag.stop_words

    def test_dialogue_default_markers_have_no_private_name(self):
        from src.archilles.chunkers.dialogue import DEFAULT_USER_MARKERS
        assert "tom" not in DEFAULT_USER_MARKERS
        assert "nutzer" in DEFAULT_USER_MARKERS


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


class TestPrintResultsI18n:
    """CLI search output (Searcher.print_results) follows the operator
    language via ``t()``; defaults to English."""

    @staticmethod
    def _rag(tmp_path):
        from src.archilles.engine import ArchillesRAG
        return ArchillesRAG(db_path=str(tmp_path / "db"), skip_model=True)

    @staticmethod
    def _results():
        return [{
            'rank': 1,
            'similarity': 0.95,  # > 0.8 -> "very high" / "sehr hoch"
            'text': 'A test sentence.',
            'metadata': {'book_title': 'Test Book', 'page_number': 42},
        }]

    def test_german(self, tmp_path, capsys):
        self._rag(tmp_path).print_results(self._results(), query_text="", lang="de")
        out = capsys.readouterr().out
        assert "TREFFER" in out
        assert "Relevanz:" in out
        assert "sehr hoch" in out
        assert "PDF S." in out

    def test_english(self, tmp_path, capsys):
        self._rag(tmp_path).print_results(self._results(), query_text="", lang="en")
        out = capsys.readouterr().out
        assert "RESULTS" in out
        assert "Relevance:" in out
        assert "very high" in out
        assert "PDF p." in out
        assert "Relevanz" not in out

    def test_defaults_to_english(self, tmp_path, capsys):
        self._rag(tmp_path).print_results(self._results(), query_text="")
        out = capsys.readouterr().out
        assert "RESULTS" in out and "Relevance:" in out

    def test_empty_results_localised(self, tmp_path, capsys):
        self._rag(tmp_path).print_results([], lang="de")
        out = capsys.readouterr().out
        assert "Keine Ergebnisse" in out
