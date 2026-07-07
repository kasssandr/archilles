"""Watchdog runs must keep the search indexes covering what they wrote.

The watchdog paths index via ``rag.index_book()`` and never refreshed any
index — unlike batch_index/embed_prepared, which rebuild FTS after a run.
Weeks of phase-B runs left 1.2M of 1.56M rows unindexed, so every
keyword/hybrid query brute-force-scanned them (~5 min per search).
"""

from types import SimpleNamespace

from src.archilles.watchdog import _refresh_search_indexes


def _fake_rag(events, *, ensure_raises=False):
    def ensure_vector_index():
        events.append("ensure")
        if ensure_raises:
            raise RuntimeError("index backend down")
        return True

    def optimize_indexes():
        events.append("optimize")
        return True

    store = SimpleNamespace(
        ensure_vector_index=ensure_vector_index,
        optimize_indexes=optimize_indexes,
    )
    return SimpleNamespace(store=store)


def _results(delta=0, new=0, fulltext=0):
    return {
        "delta_updates": delta,
        "new_indexed": new,
        "fulltext_indexed": fulltext,
    }


class TestRefreshSearchIndexes:
    def test_refreshes_after_indexing_work(self):
        events = []
        _refresh_search_indexes(_fake_rag(events), _results(fulltext=3), dry_run=False)
        assert events == ["ensure", "optimize"]

    def test_skips_on_dry_run(self):
        events = []
        _refresh_search_indexes(_fake_rag(events), _results(fulltext=3), dry_run=True)
        assert events == []

    def test_skips_when_nothing_indexed(self):
        events = []
        _refresh_search_indexes(_fake_rag(events), _results(), dry_run=False)
        assert events == []

    def test_skips_without_rag(self):
        _refresh_search_indexes(None, _results(new=1), dry_run=False)  # must not raise

    def test_store_failure_does_not_raise(self):
        events = []
        _refresh_search_indexes(
            _fake_rag(events, ensure_raises=True), _results(delta=1), dry_run=False
        )
        assert events == ["ensure"]
