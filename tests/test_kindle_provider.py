"""Tests for Kindle My Clippings.txt provider."""

from pathlib import Path

from src.calibre_mcp.annotation_providers.kindle_provider import (
    KindleProvider,
    _parse_clipping_date,
    _parse_meta_line,
)

FIXTURES = Path(__file__).parent / "fixtures"


# ── Date parsing ────────────────────────────────────────────────────


def test_parse_english_date():
    dt = _parse_clipping_date("March 15, 2026 10:23:45 AM")
    assert dt is not None
    assert dt.year == 2026
    assert dt.month == 3
    assert dt.day == 15
    assert dt.hour == 10


def test_parse_german_date():
    dt = _parse_clipping_date("15. März 2026 10:23:45")
    assert dt is not None
    assert dt.year == 2026
    assert dt.month == 3
    assert dt.day == 15


def test_parse_invalid_date():
    assert _parse_clipping_date("not a date") is None
    assert _parse_clipping_date("") is None


# ── Metadata line parsing ──────────────────────────────────────────


def test_parse_meta_line_english_highlight():
    result = _parse_meta_line(
        "- Your Highlight on Location 234-240 | Added on Monday, March 15, 2026 10:23:45 AM"
    )
    assert result is not None
    assert result["type"] == "highlight"
    assert result["location"] == "234-240"
    assert result["page"] is None


def test_parse_meta_line_english_note():
    result = _parse_meta_line(
        "- Your Note on Location 234 | Added on Monday, March 15, 2026 10:24:00 AM"
    )
    assert result is not None
    assert result["type"] == "note"
    assert result["location"] == "234"


def test_parse_meta_line_english_bookmark():
    result = _parse_meta_line(
        "- Your Bookmark on Location 500 | Added on Tuesday, March 16, 2026 02:15:00 PM"
    )
    assert result is not None
    assert result["type"] == "bookmark"


def test_parse_meta_line_german():
    result = _parse_meta_line(
        "- Ihre Markierung bei Position 1234-1256 | Hinzugefügt am Montag, 15. März 2026 10:23:45"
    )
    assert result is not None
    assert result["type"] == "highlight"
    assert result["location"] == "1234-1256"


def test_parse_meta_line_german_note():
    result = _parse_meta_line(
        "- Ihre Notiz bei Position 1234 | Hinzugefügt am Montag, 15. März 2026 10:24:00"
    )
    assert result is not None
    assert result["type"] == "note"


def test_parse_meta_line_invalid():
    assert _parse_meta_line("not a metadata line") is None


# ── Provider tests ──────────────────────────────────────────────────


def test_kindle_provider_name():
    p = KindleProvider()
    assert p.name == "kindle"


def test_kindle_provider_can_handle():
    p = KindleProvider()
    assert p.can_handle("My Clippings.txt")
    assert p.can_handle("my clippings.txt")
    assert p.can_handle("/mnt/kindle/My Clippings.txt")
    assert not p.can_handle("notes.txt")
    assert not p.can_handle("book.epub")


def test_kindle_provider_english_fixture():
    p = KindleProvider()
    results = p.extract(str(FIXTURES / "my_clippings_en.txt"))
    assert len(results) == 3

    # First: highlight
    assert results[0].type == "highlight"
    assert results[0].source == "kindle"
    assert results[0].book_title == "The Structure of Scientific Revolutions"
    assert results[0].book_author == "Thomas S. Kuhn"
    assert "Normal science" in results[0].text
    assert results[0].location == "loc:234-240"

    # Second: note
    assert results[1].type == "note"
    assert "key definition" in results[1].text

    # Third: bookmark (empty text)
    assert results[2].type == "bookmark"
    assert results[2].text == ""


def test_kindle_provider_german_fixture():
    p = KindleProvider()
    results = p.extract(str(FIXTURES / "my_clippings_de.txt"))
    assert len(results) == 2

    assert results[0].type == "highlight"
    assert results[0].book_title == "Die Blechtrommel"
    assert results[0].book_author == "Günter Grass"
    assert "Insasse" in results[0].text

    assert results[1].type == "note"
    assert "erster Satz" in results[1].text


def test_kindle_provider_nonexistent():
    p = KindleProvider()
    assert p.extract("/nonexistent/My Clippings.txt") == []
