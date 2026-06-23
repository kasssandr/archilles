"""Tests for HTMLExtractor.

Regression guard: ``find_all(['p', ..., 'li'])`` used to match *every* nesting
level, so text inside deeply nested block elements was emitted once per
ancestor level. On real-world SingleFile snapshots this inflated the extracted
text 16x+ and filled the index with duplicate chunks (Zotero web snapshots).
"""

from pathlib import Path

from src.extractors.html_extractor import HTMLExtractor


def _extract(tmp_path: Path, html: str) -> str:
    p = tmp_path / "doc.html"
    p.write_text(html, encoding="utf-8")
    return HTMLExtractor().extract(p).full_text


def test_nested_block_tags_do_not_duplicate_text(tmp_path):
    """Text in a nested <li> must appear exactly once, not once per level."""
    html = (
        "<html><body>"
        "<ul><li>OUTER_ITEM"
        "<ul><li>INNER_UNIQUE_SENTENCE</li></ul>"
        "</li></ul>"
        "</body></html>"
    )
    full_text = _extract(tmp_path, html)
    assert full_text.count("INNER_UNIQUE_SENTENCE") == 1


def test_nested_blocks_preserve_all_text(tmp_path):
    """De-duplication must not drop text from outer or inner blocks."""
    html = (
        "<html><body>"
        "<ul><li>OUTER_ITEM"
        "<ul><li>INNER_UNIQUE_SENTENCE</li></ul>"
        "</li></ul>"
        "</body></html>"
    )
    full_text = _extract(tmp_path, html)
    assert "OUTER_ITEM" in full_text
    assert "INNER_UNIQUE_SENTENCE" in full_text


def test_deeply_nested_blocks_do_not_inflate(tmp_path):
    """Sharp guard: at arbitrary nesting depth the core text stays singular.

    Real SingleFile snapshots nest blocks dozens deep; the old extractor
    emitted the innermost text once per level (16x+ on real data).
    """
    depth = 20
    html = (
        "<html><body>"
        + "<ul><li>X" * depth
        + "CORE_SENTENCE"
        + "</li></ul>" * depth
        + "</body></html>"
    )
    full_text = _extract(tmp_path, html)
    assert full_text.count("CORE_SENTENCE") == 1


def test_flat_paragraphs_still_extracted(tmp_path):
    """Non-nested paragraphs and headings are extracted normally."""
    html = (
        "<html><body>"
        "<h1>Title Heading</h1>"
        "<p>First paragraph.</p>"
        "<p>Second paragraph.</p>"
        "</body></html>"
    )
    full_text = _extract(tmp_path, html)
    assert "Title Heading" in full_text
    assert "First paragraph." in full_text
    assert "Second paragraph." in full_text
    assert full_text.count("First paragraph.") == 1
