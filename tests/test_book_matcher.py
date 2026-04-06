"""Tests for BookMatcher fuzzy title+author matching."""

import json
from pathlib import Path

from src.calibre_mcp.book_matcher import BookMatcher, MatchResult, normalize, _strip_edition_suffix

SAMPLE_BOOKS = [
    {"calibre_id": 1, "title": "Die Blechtrommel", "author": "Günter Grass"},
    {"calibre_id": 2, "title": "Der Prozess", "author": "Franz Kafka"},
    {
        "calibre_id": 3,
        "title": "Faust: Der Tragödie erster Teil",
        "author": "Johann Wolfgang von Goethe",
    },
    {
        "calibre_id": 4,
        "title": "The Structure of Scientific Revolutions",
        "author": "Thomas S. Kuhn",
    },
    {"calibre_id": 5, "title": "Sapiens", "author": "Yuval Noah Harari"},
]


# ── normalize ───────────────────────────────────────────────────────


def test_normalize_basic():
    assert normalize("  Günter Grass  ") == "gunter grass"


def test_normalize_accents():
    assert normalize("François") == "francois"


def test_normalize_punctuation():
    assert normalize("Faust: Der Tragödie") == "faust der tragodie"


def test_normalize_empty():
    assert normalize("") == ""


# ── _strip_edition_suffix ───────────────────────────────────────────


def test_strip_german_edition():
    assert _strip_edition_suffix("Die Blechtrommel (German Edition)") == "Die Blechtrommel"


def test_strip_kindle_edition():
    assert _strip_edition_suffix("The Process (Kindle Edition)") == "The Process"


def test_strip_no_suffix():
    assert _strip_edition_suffix("Normal Title") == "Normal Title"


# ── Exact match ─────────────────────────────────────────────────────


def test_exact_match_title_and_author():
    m = BookMatcher(SAMPLE_BOOKS)
    result = m.match("Die Blechtrommel", "Günter Grass")
    assert result is not None
    assert result.calibre_id == 1
    assert result.match_type == "exact"
    assert result.score == 100.0


def test_exact_match_case_insensitive():
    m = BookMatcher(SAMPLE_BOOKS)
    result = m.match("die blechtrommel")
    assert result is not None
    assert result.calibre_id == 1
    assert result.match_type == "exact"


def test_exact_match_without_accents():
    m = BookMatcher(SAMPLE_BOOKS)
    result = m.match("Die Blechtrommel", "Gunter Grass")
    assert result is not None
    assert result.calibre_id == 1


# ── Fuzzy match ─────────────────────────────────────────────────────


def test_fuzzy_match_edition_suffix():
    m = BookMatcher(SAMPLE_BOOKS)
    result = m.match("Die Blechtrommel (German Edition)", "Grass, Günter")
    assert result is not None
    assert result.calibre_id == 1


def test_fuzzy_match_partial_title():
    m = BookMatcher(SAMPLE_BOOKS)
    result = m.match(
        "Structure of Scientific Revolutions", "Thomas Kuhn"
    )
    assert result is not None
    assert result.calibre_id == 4


# ── No match ────────────────────────────────────────────────────────


def test_no_match_below_threshold():
    m = BookMatcher(SAMPLE_BOOKS, fuzzy_threshold=95.0)
    result = m.match("Completely Different Book Title Here")
    assert result is None


def test_no_match_empty_title():
    m = BookMatcher(SAMPLE_BOOKS)
    result = m.match("")
    assert result is None


# ── Batch matching ──────────────────────────────────────────────────


def test_match_batch_splits_correctly():
    m = BookMatcher(SAMPLE_BOOKS)
    items = [
        {"title": "Die Blechtrommel", "author": "Günter Grass", "text": "h1"},
        {"title": "Unknown Book XYZ", "author": "Nobody", "text": "h2"},
        {"title": "Sapiens", "author": "Yuval Noah Harari", "text": "h3"},
    ]
    matched, unmatched = m.match_batch(items)
    assert len(matched) == 2
    assert matched[0]["calibre_id"] == 1
    assert matched[1]["calibre_id"] == 5
    assert len(unmatched) == 1
    assert unmatched[0]["title"] == "Unknown Book XYZ"


def test_match_batch_writes_unmatched_json(tmp_path):
    m = BookMatcher(SAMPLE_BOOKS)
    items = [
        {"title": "Unknown Book", "author": "Nobody", "text": "h1"},
    ]
    out_file = tmp_path / "unmatched.json"
    matched, unmatched = m.match_batch(items, unmatched_path=out_file)
    assert len(unmatched) == 1
    assert out_file.exists()
    data = json.loads(out_file.read_text(encoding="utf-8"))
    assert len(data) == 1
    assert data[0]["title"] == "Unknown Book"


def test_match_batch_no_file_when_all_matched(tmp_path):
    m = BookMatcher(SAMPLE_BOOKS)
    items = [{"title": "Sapiens", "author": "Harari"}]
    out_file = tmp_path / "unmatched.json"
    matched, unmatched = m.match_batch(items, unmatched_path=out_file)
    assert len(matched) == 1
    assert len(unmatched) == 0
    assert not out_file.exists()
