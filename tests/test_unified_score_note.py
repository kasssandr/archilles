"""The merged search response labels its score scale.

RRF fusion scores live on a ~1/(60+rank) scale — the best possible hit
carries ~0.016. An MCP client reading them as cosine similarities
concludes "all results are noise" (exactly what happened in the first
Cowork test run). The response therefore says what the numbers mean.
"""

from types import SimpleNamespace

from src.calibre_mcp.unified_server import UnifiedMCPServer


def _inner_server(results):
    service = SimpleNamespace(
        search=lambda **kwargs: [dict(r) for r in results],
        build_claude_prompt=lambda **kwargs: {"system": "", "user": ""},
    )
    return SimpleNamespace(
        _ensure_rag_initialized=lambda: True,
        service=service,
        _archilles_dir=None,
        citation_config=None,
    )


def _make_unified(tmp_path, results):
    return UnifiedMCPServer(
        servers={"lib": _inner_server(results)},
        default_source="lib",
        master_dir=tmp_path,
    )


class TestScoreNote:
    def test_rrf_results_carry_score_note(self, tmp_path):
        results = [{"rank": 1, "score": 0.016, "text": "x", "metadata": {}}]
        server = _make_unified(tmp_path, results)

        response = server.search_books_with_citations_tool(query="q", top_k=3)

        assert "score_note" in response
        assert "RRF" in response["score_note"]

    def test_reranked_results_carry_no_score_note(self, tmp_path):
        results = [
            {"rank": 1, "score": 0.9, "rerank_score": 0.9, "text": "x", "metadata": {}}
        ]
        server = _make_unified(tmp_path, results)

        response = server.search_books_with_citations_tool(query="q", top_k=3)

        assert "score_note" not in response
