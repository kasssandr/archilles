"""End-to-end integration tests: parse → match → output pipeline."""

from pathlib import Path

from src.calibre_mcp.annotation_providers.kindle_provider import KindleProvider
from src.calibre_mcp.book_matcher import BookMatcher

FIXTURES = Path(__file__).parent / "fixtures"

CALIBRE_BOOKS = [
    {"calibre_id": 1, "title": "Die Blechtrommel", "author": "Günter Grass"},
    {
        "calibre_id": 4,
        "title": "The Structure of Scientific Revolutions",
        "author": "Thomas S. Kuhn",
    },
]


def test_kindle_to_matcher_pipeline():
    """Full pipeline: parse Kindle clippings -> match to Calibre books."""
    provider = KindleProvider()
    annotations = provider.extract(str(FIXTURES / "my_clippings_en.txt"))
    assert len(annotations) == 3

    items = [
        {"title": a.book_title, "author": a.book_author, "annotation": a}
        for a in annotations
    ]

    matcher = BookMatcher(CALIBRE_BOOKS)
    matched, unmatched = matcher.match_batch(items)

    assert len(matched) == 3
    assert all(m["calibre_id"] == 4 for m in matched)
    assert len(unmatched) == 0


def test_german_clippings_pipeline():
    """German Kindle clippings match correctly."""
    provider = KindleProvider()
    annotations = provider.extract(str(FIXTURES / "my_clippings_de.txt"))
    assert len(annotations) == 2

    items = [
        {"title": a.book_title, "author": a.book_author, "annotation": a}
        for a in annotations
    ]

    matcher = BookMatcher(CALIBRE_BOOKS)
    matched, unmatched = matcher.match_batch(items)

    assert len(matched) == 2
    assert all(m["calibre_id"] == 1 for m in matched)


def test_mixed_match_unmatched():
    """Some annotations match, some don't."""
    provider = KindleProvider()
    de_annotations = provider.extract(str(FIXTURES / "my_clippings_de.txt"))
    en_annotations = provider.extract(str(FIXTURES / "my_clippings_en.txt"))

    all_annotations = de_annotations + en_annotations
    items = [
        {"title": a.book_title, "author": a.book_author, "annotation": a}
        for a in all_annotations
    ]

    # Only Blechtrommel in Calibre, not Kuhn
    matcher = BookMatcher([CALIBRE_BOOKS[0]])
    matched, unmatched = matcher.match_batch(items)

    assert len(matched) == 2  # Die Blechtrommel entries
    assert len(unmatched) == 3  # Kuhn entries


def test_unmatched_review_queue(tmp_path):
    """Unmatched annotations are written to review queue JSON."""
    provider = KindleProvider()
    annotations = provider.extract(str(FIXTURES / "my_clippings_en.txt"))

    items = [
        {"title": a.book_title, "author": a.book_author}
        for a in annotations
    ]

    # Empty Calibre library -> nothing matches
    matcher = BookMatcher([])
    review_file = tmp_path / "unmatched.json"
    matched, unmatched = matcher.match_batch(items, unmatched_path=review_file)

    assert len(matched) == 0
    assert len(unmatched) == 3
    assert review_file.exists()


def test_registry_integration():
    """Test that KindleProvider works through the registry."""
    from src.calibre_mcp.annotation_providers import create_default_registry

    registry = create_default_registry()
    assert "kindle" in registry.available
    assert "pdf" in registry.available
    assert "calibre_viewer" in registry.available

    # Extract via registry
    results = registry.extract_all(
        str(FIXTURES / "my_clippings_en.txt"), source="kindle"
    )
    assert len(results) == 3
    assert results[0].source == "kindle"
