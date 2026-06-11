"""Regression tests for the P1 fixes from the 2026-06-10 code review.

Each test corresponds to a numbered finding in
docs/internal/CODE_REVIEW_2026-06-10.md and is written so that it FAILS
on the pre-fix code and passes after the fix.

Findings covered:
    1.11 duplicate chunk IDs on re-indexing without prior delete
    8.7  hash reads and delete decisions based on a 100-row window
    4.2  additive research boost drowning RRF-scale scores
    8.2  min_similarity applied to RRF scores in hybrid mode
    4.1  min_similarity vs. reranker scale; explicit bounded activation
    4.3  search_with_citations bypassing the reranker
    8.4  exact_phrase results without score_type marker
    5.4  cross-source merge comparing incomparable raw scores
    2.2  substring keyword matching in section classification
    2.3  contradictory introduction handling (TOC vs. page heuristic)
    2.8  roman numeral regex matching the English word "I"
    4.5  research boost matching substrings ("Kant" boosts "Kantine")
    6.2  TOC marker filter dropping highlights via substrings
    6.1  write_annotations dropping highlights WITH text
    1.2  filters must act as PRE-filter, not post-ANN-cutoff filter
"""

import numpy as np
import pytest


def _store(tmp_path):
    from src.storage.lancedb_store import LanceDBStore

    return LanceDBStore(db_path=str(tmp_path / "db"))


def _chunks(book_id, n, prefix="v1"):
    return [
        {"id": f"{book_id}_chunk_{i}", "text": f"{prefix} chunk {i}", "book_id": book_id}
        for i in range(n)
    ]


def _emb(n):
    return np.random.rand(n, 8).astype(np.float32)


# ── 1.11: re-adding the same chunk IDs must not create duplicates ────────

class TestDuplicateChunkIds:
    def test_readd_same_ids_does_not_duplicate(self, tmp_path):
        """Re-indexing without prior delete silently doubled every chunk."""
        store = _store(tmp_path)
        book_id = "Author_Title_7"

        store.add_chunks(_chunks(book_id, 3, "v1"), _emb(3))
        store.add_chunks(_chunks(book_id, 3, "v2"), _emb(3))

        rows = store.get_by_book_id(book_id)
        assert len(rows) == 3

    def test_readd_replaces_with_newest_text(self, tmp_path):
        """On ID collision the newer write must win (upsert semantics)."""
        store = _store(tmp_path)
        book_id = "Author_Title_7"

        store.add_chunks(_chunks(book_id, 2, "v1"), _emb(2))
        store.add_chunks(_chunks(book_id, 2, "v2"), _emb(2))

        rows = store.get_by_book_id(book_id)
        assert sorted(r["text"] for r in rows) == ["v2 chunk 0", "v2 chunk 1"]

    def test_new_ids_still_append(self, tmp_path):
        """The guard must not break normal incremental adds."""
        store = _store(tmp_path)
        book_id = "Author_Title_7"

        store.add_chunks(_chunks(book_id, 2), _emb(2))
        extra = [{"id": f"{book_id}_annot_0", "text": "note", "book_id": book_id}]
        store.add_chunks(extra, _emb(1))

        assert len(store.get_by_book_id(book_id)) == 3

    def test_other_books_untouched(self, tmp_path):
        """Upserting one book must not affect another book's chunks."""
        store = _store(tmp_path)

        store.add_chunks(_chunks("Book_A_1", 2), _emb(2))
        store.add_chunks(_chunks("Book_B_2", 2), _emb(2))
        store.add_chunks(_chunks("Book_A_1", 2, "v2"), _emb(2))

        assert len(store.get_by_book_id("Book_A_1")) == 2
        assert len(store.get_by_book_id("Book_B_2")) == 2
        assert all(
            r["text"].startswith("v1") for r in store.get_by_book_id("Book_B_2")
        )


# ── 1.11(b): inventory tool for pre-existing duplicates ──────────────────

class TestDuplicateInventory:
    def test_summarize_no_duplicates(self):
        from scripts.find_duplicate_chunks import summarize_duplicates

        rows = [
            {"id": "A_chunk_0", "book_id": "A"},
            {"id": "A_chunk_1", "book_id": "A"},
            {"id": "B_chunk_0", "book_id": "B"},
        ]
        report = summarize_duplicates(rows)
        assert report["total_rows"] == 3
        assert report["duplicate_ids"] == 0
        assert report["excess_rows"] == 0
        assert report["books"] == {}

    def test_summarize_counts_duplicates_per_book(self):
        from scripts.find_duplicate_chunks import summarize_duplicates

        rows = [
            {"id": "A_chunk_0", "book_id": "A"},
            {"id": "A_chunk_0", "book_id": "A"},  # 1 excess
            {"id": "A_chunk_1", "book_id": "A"},
            {"id": "B_chunk_0", "book_id": "B"},
            {"id": "B_chunk_0", "book_id": "B"},  # triple -> 2 excess
            {"id": "B_chunk_0", "book_id": "B"},
        ]
        report = summarize_duplicates(rows)
        assert report["total_rows"] == 6
        assert report["duplicate_ids"] == 2
        assert report["excess_rows"] == 3
        assert report["books"]["A"] == {"duplicate_ids": 1, "excess_rows": 1}
        assert report["books"]["B"] == {"duplicate_ids": 1, "excess_rows": 2}

    def test_scan_store_finds_legacy_duplicates(self, tmp_path):
        """Integration: duplicates created by the pre-fix code path
        (plain table.add, bypassing the upsert guard) must be found."""
        from scripts.find_duplicate_chunks import scan_table

        store = _store(tmp_path)
        store.add_chunks(_chunks("Book_A_1", 2), _emb(2))
        # Recreate the legacy duplicate state: append all rows verbatim
        store.table.add(store.table.to_pandas())

        report = scan_table(store.table)
        assert report["total_rows"] == 4
        assert report["duplicate_ids"] == 2
        assert report["excess_rows"] == 2
        assert report["books"]["Book_A_1"]["excess_rows"] == 2


# ── 8.7: book state must not depend on a 100-row window ──────────────────

class TestWindowlessBookState:
    def test_get_book_state_sees_past_100_rows(self, tmp_path):
        """Pre-fix code read hashes from get_by_book_id(limit=100) — for books
        with >100 chunks the annotation hash was often outside the window,
        causing pointless re-embedding on every scan (and, before the upsert
        guard, duplicate accumulation)."""
        from src.archilles.constants import ChunkType

        store = _store(tmp_path)
        chunks = [
            {"id": f"B_chunk_{i}", "text": f"c{i}", "book_id": "B",
             "chunk_type": ChunkType.CONTENT, "metadata_hash": "meta123",
             "format": "pdf"}
            for i in range(110)
        ]
        chunks += [
            {"id": f"B_annot_{i}", "text": f"a{i}", "book_id": "B",
             "chunk_type": ChunkType.ANNOTATION, "annotation_hash": "annot456"}
            for i in range(3)
        ]
        store.add_chunks(chunks, _emb(113))

        state = store.get_book_state("B")
        assert state["total"] == 113
        assert state["has_content"] is True
        assert state["content_count"] == 110
        assert state["metadata_hash"] == "meta123"
        assert state["annotation_hash"] == "annot456"  # outside any 100-row window
        assert state["format"] == "pdf"

    def test_get_book_state_unknown_book(self, tmp_path):
        store = _store(tmp_path)
        store.add_chunks(_chunks("Other_1", 1), _emb(1))

        state = store.get_book_state("Missing")
        assert state["total"] == 0
        assert state["has_content"] is False
        assert state["metadata_hash"] == ""
        assert state["annotation_hash"] == ""


class _FakeModel:
    """Embedding stand-in so the smart-update path runs without BGE-M3."""

    def encode(self, text, **kwargs):
        if isinstance(text, list):
            return np.random.rand(len(text), 8).astype(np.float32)
        return np.random.rand(8).astype(np.float32)


class TestSmartUpdateUnconditionalDelete:
    def _rag(self, tmp_path):
        from src.archilles.engine import ArchillesRAG

        rag = ArchillesRAG(db_path=str(tmp_path / "db"), skip_model=True)
        rag.embedding_model = _FakeModel()
        return rag

    def _seed(self, store):
        from src.archilles.constants import ChunkType

        chunks = [
            {"id": "B_chunk_0", "text": "content", "book_id": "B",
             "chunk_type": ChunkType.CONTENT, "metadata_hash": "meta123",
             "format": "pdf"},
            {"id": "B_comment_0", "text": "old comment", "book_id": "B",
             "chunk_type": ChunkType.CALIBRE_COMMENT, "metadata_hash": "meta123"},
        ]
        chunks += [
            {"id": f"B_annot_{i}", "text": f"old annot {i}", "book_id": "B",
             "chunk_type": ChunkType.ANNOTATION, "annotation_hash": "old"}
            for i in range(3)
        ]
        store.add_chunks(chunks, _emb(5))

    def test_annotation_update_replaces_all_old_chunks(self, tmp_path):
        """Pre-fix: the delete was guarded by the (possibly blind) window view
        -> no delete, but re-add -> one extra copy per routine run."""
        from src.archilles.constants import ChunkType

        rag = self._rag(tmp_path)
        self._seed(rag.store)

        state = rag.store.get_book_state("B")
        rag._update_metadata_only(
            "B", {"title": "T"}, "meta123", state,
            annotations=[{"highlighted_text": "neu", "type": "highlight"}],
            annotation_hash="new",
        )

        rows = rag.store.get_by_book_id("B", limit=1000)
        annots = [c for c in rows if c["chunk_type"] == ChunkType.ANNOTATION]
        assert len(annots) == 1
        assert "neu" in annots[0]["text"]

    def test_annotation_delete_does_not_depend_on_state_view(self, tmp_path):
        """Even a blind state (no annotation info) must not skip the delete."""
        from src.archilles.constants import ChunkType

        rag = self._rag(tmp_path)
        self._seed(rag.store)

        blind = rag.store.get_book_state("B")
        blind["annotation_hash"] = ""

        rag._update_metadata_only(
            "B", {"title": "T"}, "meta123", blind,
            annotations=[{"highlighted_text": "neu", "type": "highlight"}],
            annotation_hash="new",
        )

        rows = rag.store.get_by_book_id("B", limit=1000)
        annots = [c for c in rows if c["chunk_type"] == ChunkType.ANNOTATION]
        assert len(annots) == 1

    def test_comment_update_deletes_stale_comment(self, tmp_path):
        """meta_changed without new comments must remove the old comment chunk."""
        from src.archilles.constants import ChunkType

        rag = self._rag(tmp_path)
        self._seed(rag.store)

        state = rag.store.get_book_state("B")
        rag._update_metadata_only("B", {"title": "T"}, "meta999", state)

        rows = rag.store.get_by_book_id("B", limit=1000)
        comments = [c for c in rows if c["chunk_type"] == ChunkType.CALIBRE_COMMENT]
        assert comments == []
        # content chunks stay untouched
        assert [c for c in rows if c["chunk_type"] == ChunkType.CONTENT]


# ── 4.2: research boost must not drown RRF-scale scores ──────────────────

class TestResearchBoostScale:
    def test_boost_is_multiplicative(self):
        """Pre-fix: +0.15 per keyword on RRF scores (~0.016) meant a single
        keyword match outweighed the search relevance ~10x."""
        from src.retriever.research_boost import apply_research_boost

        results = [
            {"text": "highly relevant, no keyword", "score": 0.032},
            {"text": "weak hit mentioning Kant", "score": 0.016},
        ]
        boosted = apply_research_boost(results, ["kant"], boost_factor=0.15)

        assert boosted[0]["text"] == "highly relevant, no keyword"
        assert boosted[1]["score"] == pytest.approx(0.016 * 1.15)

    def test_boost_operates_on_rerank_score_when_present(self):
        """After reranking, rerank_score governs the order — boosting the
        stale RRF score would silently discard the reranker's work."""
        from src.retriever.research_boost import apply_research_boost

        results = [
            {"text": "no keyword", "score": 0.01, "rerank_score": 0.90},
            {"text": "kant appears", "score": 0.02, "rerank_score": 0.85},
        ]
        boosted = apply_research_boost(results, ["kant"], boost_factor=0.15)

        assert boosted[0]["text"] == "kant appears"  # 0.85*1.15 > 0.90
        assert boosted[0]["rerank_score"] == pytest.approx(0.85 * 1.15)
        assert boosted[0]["score"] == pytest.approx(0.02)  # untouched


# ── 8.2 / 4.1: min_similarity must only apply to bounded scales ──────────

class TestMinSimilarityScales:
    def test_hybrid_rrf_results_not_filtered(self):
        """Pre-fix: hybrid mode filtered RRF scores (~0.016) against a
        cosine-style threshold — anything >0.1 silently emptied results."""
        from src.archilles.engine import ArchillesRAG

        results = [{"score": 0.016}, {"score": 0.032}]
        out = ArchillesRAG._apply_min_similarity(results, 0.3, "hybrid")
        assert out == results

    def test_semantic_results_filtered(self):
        from src.archilles.engine import ArchillesRAG

        results = [{"score": 0.8}, {"score": 0.2}]
        out = ArchillesRAG._apply_min_similarity(results, 0.5, "semantic")
        assert out == [{"score": 0.8}]

    def test_rerank_filter_passes_results_without_rerank_score(self):
        """If the reranker silently failed, results carry only RRF scores —
        filtering those against min_similarity would empty the list."""
        from src.service.archilles_service import _filter_by_rerank_score

        results = [{"score": 0.016}, {"rerank_score": 0.7}, {"rerank_score": 0.2}]
        out = _filter_by_rerank_score(results, 0.5)
        assert out == [{"score": 0.016}, {"rerank_score": 0.7}]


# ── 4.1: reranker must produce a bounded, version-independent scale ──────

class TestRerankerBoundedActivation:
    def test_explicit_sigmoid_activation_passed(self, monkeypatch):
        """sentence-transformers changed the default activation across major
        versions (logits vs. sigmoid). Pin it explicitly to sigmoid so
        rerank_score is always 0-1."""
        import sentence_transformers

        captured = {}

        class _FakeCE:
            def __init__(self, name, **kwargs):
                captured.update(kwargs)
                self.device = "cpu"

        monkeypatch.setattr(sentence_transformers, "CrossEncoder", _FakeCE)
        from src.retriever.reranker import CrossEncoderReranker

        rr = CrossEncoderReranker(device="cpu")
        assert rr._ensure_loaded()
        act = captured.get("activation_fn") or captured.get("default_activation_function")
        assert act is not None and "Sigmoid" in type(act).__name__


# ── 4.3: search_with_citations must use the reranker when enabled ────────

class _FakeRagForService:
    def __init__(self):
        self.query_kwargs = None

    def query(self, **kwargs):
        self.query_kwargs = kwargs
        results = [
            {"text": "a", "score": 0.016, "metadata": {"book_id": "A"}},
            {"text": "b", "score": 0.015, "metadata": {"book_id": "B"}},
            {"text": "c", "score": 0.014, "metadata": {"book_id": "C"}},
        ]
        return results[: kwargs.get("top_k", 10)]

    def create_claude_prompt(self, results, query_text, expand_context=False,
                             citation_config=None):
        return {"system": "s", "user": "u"}


class _FakeReranker:
    def __init__(self):
        self.called = False

    def rerank(self, query, results, top_k=10):
        self.called = True
        for i, r in enumerate(results):
            r["rerank_score"] = 0.9 - i * 0.1
        return results[:top_k]


class TestCitationPathReranking:
    def test_search_with_citations_reranks_when_enabled(self, tmp_path):
        from src.service.archilles_service import ArchillesService

        svc = ArchillesService(db_path=str(tmp_path), enable_reranking=True)
        svc._rag = _FakeRagForService()
        svc._reranker = _FakeReranker()

        out = svc.search_with_citations("query", top_k=2,
                                        boost_research_interests=False)

        assert svc._reranker.called, "citation path skipped the reranker"
        assert out["num_results"] == 2
        # Candidate fetch must be broader than top_k (like search() does)
        assert svc._rag.query_kwargs["top_k"] > 2

    def test_search_with_citations_works_without_reranker(self, tmp_path):
        from src.service.archilles_service import ArchillesService

        svc = ArchillesService(db_path=str(tmp_path), enable_reranking=False)
        svc._rag = _FakeRagForService()

        out = svc.search_with_citations("query", top_k=2,
                                        boost_research_interests=False)
        assert out["num_results"] == 2


# ── 8.4: exact_phrase results must carry a score_type marker ──────────────

def test_exact_phrase_results_have_score_type(tmp_path):
    """exact_phrase scores are raw occurrence counts — downstream consumers
    can only treat them correctly if the scale is labelled."""
    from src.archilles.engine import ArchillesRAG

    rag = ArchillesRAG(db_path=str(tmp_path / "db"), skip_model=True)
    rag.store.add_chunks(
        [{"id": "B_chunk_0", "text": "Sein und Zeit ist ein Hauptwerk.",
          "book_id": "B", "chunk_type": "content"}],
        _emb(1),
    )
    rag.store.create_fts_index()

    results = rag._exact_phrase_search("Sein und Zeit", top_k=5)
    assert results, "exact phrase not found"
    assert results[0]["score_type"] == "exact_phrase"


# ── 5.4: cross-source merge must not compare raw RRF scores ──────────────

class TestCrossSourceMerge:
    def test_interleaves_by_rank_when_scores_incomparable(self):
        """RRF scores from separate LanceDB instances are not comparable —
        pre-fix the raw-score sort put every result of the 'louder' source
        above all results of the other."""
        from src.calibre_mcp.unified_server import merge_source_results

        cal = [
            {"text": "a1", "score": 0.030, "rank": 1, "source": "calibre"},
            {"text": "a2", "score": 0.029, "rank": 2, "source": "calibre"},
        ]
        zot = [
            {"text": "b1", "score": 0.016, "rank": 1, "source": "zotero"},
            {"text": "b2", "score": 0.015, "rank": 2, "source": "zotero"},
        ]
        merged = merge_source_results([("calibre", cal), ("zotero", zot)], top_k=4)

        assert {merged[0]["text"], merged[1]["text"]} == {"a1", "b1"}
        assert {merged[2]["text"], merged[3]["text"]} == {"a2", "b2"}
        assert [r["rank"] for r in merged] == [1, 2, 3, 4]

    def test_uses_rerank_score_when_all_results_reranked(self):
        """Cross-encoder scores are query-document specific and therefore
        comparable across sources — they take precedence."""
        from src.calibre_mcp.unified_server import merge_source_results

        cal = [{"text": "a1", "score": 0.030, "rerank_score": 0.7, "rank": 1}]
        zot = [{"text": "b1", "score": 0.010, "rerank_score": 0.9, "rank": 1}]
        merged = merge_source_results([("calibre", cal), ("zotero", zot)], top_k=2)

        assert merged[0]["text"] == "b1"
        assert merged[0]["rank"] == 1

    def test_truncates_to_top_k(self):
        from src.calibre_mcp.unified_server import merge_source_results

        cal = [{"text": f"a{i}", "score": 0.03, "rank": i} for i in range(1, 6)]
        merged = merge_source_results([("calibre", cal)], top_k=3)
        assert len(merged) == 3


# ── Wortgrenzen-Familie: 2.2 / 2.3 / 2.8 / 4.5 / 6.2 ─────────────────────

class TestWordBoundaryHelper:
    def test_contains_keyword_respects_word_boundaries(self):
        from src.archilles.text_match import contains_keyword

        assert contains_keyword("Notes on method", ["notes"])
        assert not contains_keyword("Banknotes of the empire", ["notes"])
        assert not contains_keyword("The Geneva protocol", ["toc"])
        assert contains_keyword("Table of Contents", ["table of contents"])
        assert not contains_keyword("Der Vorteil des Zweifels", ["teil"])
        assert not contains_keyword("Indexikalität als Begriff", ["index"])
        assert contains_keyword("Index", ["index"])

    def test_count_keyword_matches(self):
        from src.archilles.text_match import count_keyword_matches

        assert count_keyword_matches("Kant und Hegel", ["kant", "hegel"]) == 2
        assert count_keyword_matches("Die Kantine", ["kant"]) == 0


class TestSectionClassificationBoundaries:
    def test_toc_title_banknotes_not_back_matter(self):
        """2.2: 'notes' in 'Banknotes' classified chapters as back_matter,
        silently excluding them from default search."""
        from src.extractors.pdf_extractor import PDFExtractor
        from src.archilles.constants import SectionType

        assert PDFExtractor._section_type_from_toc_title("A History of Banknotes") is None
        assert (PDFExtractor._section_type_from_toc_title("Notes")
                == SectionType.BACK_MATTER)

    def test_page_heuristic_banknotes_stays_main(self):
        from src.extractors.pdf_extractor import PDFExtractor
        from src.archilles.constants import SectionType

        ext = PDFExtractor()
        page = "Banknotes and credit in early modern Europe\n" + "Text. " * 50
        assert ext._detect_section_type(page, 50, 300) == SectionType.MAIN_CONTENT

    def test_epub_protocol_chapter_not_front_matter(self):
        """2.2: 'toc' in 'protocol' made EPUB chapters front_matter."""
        from src.extractors.epub_extractor import EPUBExtractor
        from src.archilles.constants import SectionType

        assert (EPUBExtractor._detect_section_type("The Geneva Protocol")
                == SectionType.MAIN_CONTENT)
        assert (EPUBExtractor._detect_section_type("TOC")
                == SectionType.FRONT_MATTER)

    def test_introduction_page_stays_main_content(self):
        """2.3: TOC keywords deliberately treat introductions as main content
        ('inhaltlich relevant') — the page heuristic must agree, otherwise
        TOC-less PDFs lose their introduction from search."""
        from src.extractors.pdf_extractor import PDFExtractor
        from src.archilles.constants import SectionType

        ext = PDFExtractor()
        page = "Introduction\n" + "This study examines historical sources. " * 20
        assert ext._detect_section_type(page, 10, 300) == SectionType.MAIN_CONTENT

    def test_english_pronoun_i_not_front_matter(self):
        """2.8: the roman numeral regex matched the English word 'I'."""
        from src.extractors.pdf_extractor import PDFExtractor
        from src.archilles.constants import SectionType

        ext = PDFExtractor()
        page = "I have always thought that the question deserves study.\n" \
               + "More prose follows here without any special markers. " * 10
        assert ext._detect_section_type(page, 2, 300) == SectionType.MAIN_CONTENT

    def test_standalone_roman_label_still_front_matter(self):
        from src.extractors.pdf_extractor import PDFExtractor
        from src.archilles.constants import SectionType

        ext = PDFExtractor()
        page = "iv\nNeutral prose without special markers follows here."
        assert ext._detect_section_type(page, 2, 300) == SectionType.FRONT_MATTER


class TestTocMarkerBoundaries:
    def test_vorteil_highlight_not_dropped(self):
        """6.2: 'teil' in 'Vorteil' silently dropped short highlights."""
        from src.calibre_mcp.annotations import is_toc_marker

        ann = {"highlighted_text": "Der Vorteil des Zweifels", "notes": ""}
        assert not is_toc_marker(ann)

    def test_real_chapter_marker_still_dropped(self):
        from src.calibre_mcp.annotations import is_toc_marker

        ann = {"highlighted_text": "Kapitel 3: Die Anfänge der Stadt", "notes": ""}
        assert is_toc_marker(ann)


class TestResearchBoostBoundaries:
    def test_kant_does_not_boost_kantine(self):
        """4.5: substring matching boosted 'Kantine' for keyword 'Kant'."""
        from src.retriever.research_boost import apply_research_boost

        results = [{"text": "Die Kantine war geschlossen", "score": 0.02}]
        boosted = apply_research_boost(results, ["Kant"], boost_factor=0.15)
        assert boosted[0]["score"] == pytest.approx(0.02)

    def test_kant_still_boosts_kant(self):
        from src.retriever.research_boost import apply_research_boost

        results = [{"text": "Kant und die Aufklärung", "score": 0.02}]
        boosted = apply_research_boost(results, ["Kant"], boost_factor=0.15)
        assert boosted[0]["score"] == pytest.approx(0.02 * 1.15)


# ── 6.1: highlights WITH text must be persisted ───────────────────────────

class _FakeEmbedder:
    def embed_batch(self, texts):
        class _Result:
            pass

        result = _Result()
        result.embeddings = np.random.rand(len(texts), 8).astype(np.float32)
        return result


@pytest.fixture
def annotation_env(tmp_path):
    """Minimal Calibre metadata.db + seeded LanceDB for write_annotations."""
    import sqlite3

    lib = tmp_path / "library"
    lib.mkdir()
    con = sqlite3.connect(lib / "metadata.db")
    con.executescript(
        """
        CREATE TABLE books (id INTEGER PRIMARY KEY, title TEXT);
        CREATE TABLE tags (id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE books_tags_link (id INTEGER PRIMARY KEY, book INTEGER, tag INTEGER);
        CREATE TABLE languages (id INTEGER PRIMARY KEY, lang_code TEXT);
        CREATE TABLE books_languages_link (id INTEGER PRIMARY KEY, book INTEGER, lang_code INTEGER);
        """
    )
    con.execute("INSERT INTO books (id, title) VALUES (7, 'Testbuch')")
    con.commit()
    con.close()

    store = _store(tmp_path)
    store.add_chunks(_chunks("seed_1", 1), _emb(1))  # table must exist
    return lib, tmp_path / "db", store


def test_write_annotations_persists_highlights_with_text(annotation_env):
    """Pre-fix: only type=='note' was written — highlights with full text
    (e.g. from My Clippings.txt) were silently dropped, contradicting the
    documented behaviour ('Highlights without text are skipped')."""
    from src.archilles.annotation_providers.base import Annotation
    from src.calibre_mcp.annotation_writer import write_annotations

    lib, db_path, store = annotation_env
    matched = [
        {
            "calibre_id": 7,
            "calibre_title": "Testbuch",
            "calibre_author": "Anna Autor",
            "annotation": Annotation(
                source="kindle", type="highlight",
                text="Der markierte Satz aus dem Buch.",
            ),
        },
        {
            "calibre_id": 7,
            "calibre_title": "Testbuch",
            "calibre_author": "Anna Autor",
            "annotation": Annotation(
                source="kindle", type="note", text="Eine reine Notiz.",
            ),
        },
        {
            "calibre_id": 7,
            "calibre_title": "Testbuch",
            "calibre_author": "Anna Autor",
            "annotation": Annotation(
                source="kindle", type="bookmark", text="",  # no text -> skip
            ),
        },
    ]

    n_books, n_annots = write_annotations(
        matched, lib, db_path, embedder=_FakeEmbedder(), progress=lambda *_: None,
    )

    assert n_books == 1
    assert n_annots == 2
    # Fresh handle — the fixture's table reference predates the write
    rows = _store(lib.parent).get_by_book_id("7", limit=100)
    texts = sorted(r["text"] for r in rows)
    assert any("markierte Satz" in t for t in texts)
    assert any("reine Notiz" in t for t in texts)
    types = {r["annotation_type"] for r in rows}
    assert types == {"highlight", "note"}


def test_write_annotations_includes_attached_note(annotation_env):
    """A highlight with an attached user note must keep both parts."""
    from src.archilles.annotation_providers.base import Annotation
    from src.calibre_mcp.annotation_writer import write_annotations

    lib, db_path, store = annotation_env
    matched = [{
        "calibre_id": 7,
        "calibre_title": "Testbuch",
        "calibre_author": "Anna Autor",
        "annotation": Annotation(
            source="kindle", type="highlight",
            text="Markierter Text.", note="Mein Kommentar dazu.",
        ),
    }]

    write_annotations(matched, lib, db_path,
                      embedder=_FakeEmbedder(), progress=lambda *_: None)

    rows = _store(lib.parent).get_by_book_id("7", limit=100)
    assert len(rows) == 1
    assert "Markierter Text." in rows[0]["text"]
    assert "Mein Kommentar dazu." in rows[0]["text"]


# ── 1.2: filters must act as PRE-filter (not post-ANN-cutoff) ─────────────

def test_vector_search_filter_reaches_beyond_topk_window(tmp_path):
    """Searching WITHIN one book must return that book's chunks even when
    they are far from the query vector. A post-filter applied after the
    ANN top_k cutoff would return zero results here — older LanceDB
    versions did exactly that, which is why the version is pinned."""
    from src.storage.lancedb_store import LanceDBStore

    store = LanceDBStore(db_path=str(tmp_path / "db"))

    rng = np.random.default_rng(42)
    base = np.ones(8, dtype=np.float32)

    # 120 chunks of book A clustered tightly around the query vector …
    chunks_a = [
        {"id": f"A_chunk_{i}", "text": f"a{i}", "book_id": "A"} for i in range(120)
    ]
    emb_a = (base + rng.normal(0, 0.01, (120, 8))).astype(np.float32)

    # … and 2 chunks of book B, far away in vector space.
    chunks_b = [
        {"id": f"B_chunk_{i}", "text": f"b{i}", "book_id": "B"} for i in range(2)
    ]
    emb_b = (-base + rng.normal(0, 0.01, (2, 8))).astype(np.float32)

    store.add_chunks(chunks_a, emb_a)
    store.add_chunks(chunks_b, emb_b)

    results = store.vector_search(base, top_k=5, book_id="B")
    assert len(results) == 2
    assert {r["book_id"] for r in results} == {"B"}
