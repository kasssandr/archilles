"""Tests for hierarchical-aware `_score_chunks` (review 2026-07-03, finding 3.1).

``_score_chunks`` only counted ``chunk_type == 'content'`` as a content chunk.
Hierarchically prepared chunks are typed ``parent``/``child``, so on a
hierarchical corpus ``content_chunks`` was always empty, ``total`` fell back
to 1, and every text metric was computed over nothing — the composite score
degenerated to a constant 90.0 regardless of actual quality, breaking
``--quality-select`` wherever hierarchical chunking is the default (which it
now is for the full modes).

Fix: count ``chunk_type in (CONTENT, CHILD)`` as content; exclude ``PARENT``
rows from the back-matter numerator and from the max(chunk_index) threshold
computation (parents duplicate their children's text/index range).
"""

from scripts.batch_index import _score_chunks
from src.archilles.constants import ChunkType, SectionType


# ── flat mode: byte-identical golden regression ─────────────────────


def test_flat_mode_score_unchanged():
    # A fixed flat (non-hierarchical) chunk list must keep scoring exactly
    # as before the fix — flat corpora have no parent/child chunks, so
    # widening the content-chunk filter must not move any number here.
    flat_chunks = [
        {'chunk_type': ChunkType.CONTENT, 'chunk_index': 0,
         'text': 'Introduction text that ends cleanly.',
         'page_number': 1, 'section_title': 'Intro'},
        {'chunk_type': ChunkType.CONTENT, 'chunk_index': 1,
         'text': ' '.join(['word'] * 25) + ' unfinished',
         'page_number': 2, 'section_title': 'Chapter 1'},
        {'chunk_type': ChunkType.CONTENT, 'chunk_index': 2,
         'text': 'Short bit.', 'page_number': 3, 'section_title': None},
        {'chunk_type': ChunkType.CONTENT, 'chunk_index': 3,
         'text': 'A concluding paragraph with a full stop.',
         'page_number': 4, 'section_title': 'Chapter 2'},
    ]

    result = _score_chunks(flat_chunks)

    assert result == {
        'score': 80.0,
        'chunk_count': 4,
        'content_chunks': 4,
        'truncation_rate': 0.25,
        'misplaced_back_rate': 0.0,
        'cv': 1.086,
        'short_rate': 1.0,
        'section_coverage': 0.75,
        'has_pages': True,
    }


# ── hierarchical mode: must discriminate, not degenerate to a constant ──


def _child(idx, text, *, section_title='Chapter', page_number=1,
           section_type=SectionType.MAIN_CONTENT):
    return {
        'chunk_type': ChunkType.CHILD,
        'chunk_index': idx,
        'text': text,
        'section_title': section_title,
        'page_number': page_number,
        'section_type': section_type,
    }


def _parent(idx, text, *, section_type=SectionType.MAIN_CONTENT):
    return {
        'chunk_type': ChunkType.PARENT,
        'chunk_index': idx,
        'text': text,
        'section_type': section_type,
    }


def test_hierarchical_content_chunks_count_children_not_parents():
    chunks = [
        _parent(0, 'Parent text covering children 0 and 1.'),
        _child(0, 'First child sentence, well formed.'),
        _child(1, 'Second child sentence, well formed.'),
        _parent(1, 'Parent text covering children 2 and 3.'),
        _child(2, 'Third child sentence, well formed.'),
        _child(3, 'Fourth child sentence, well formed.'),
    ]

    result = _score_chunks(chunks)

    # 4 CHILD chunks are content; the 2 PARENT chunks must not be counted
    # (they duplicate the children's text).
    assert result['content_chunks'] == 4


def test_hierarchical_scores_discriminate_between_good_and_bad_format():
    # "Good": children end on sentence boundaries, carry section titles and
    # page numbers, no back-matter pollution.
    good_chunks = [
        _parent(0, 'Parent summary of a well-formed section.'),
        _child(0, ' '.join(['word'] * 60) + ' that ends properly.'),
        _child(1, ' '.join(['word'] * 60) + ' that also ends properly.'),
        _child(2, ' '.join(['word'] * 60) + ' and this one too.'),
        _child(3, ' '.join(['word'] * 60) + ' concluding the section.'),
    ]

    # "Bad": children are truncated mid-sentence, no section titles, no
    # page numbers — same chunk_type/shape, worse content.
    bad_chunks = [
        _parent(0, 'Parent summary of a broken section'),
        _child(0, ' '.join(['word'] * 60) + ' cut off mid', section_title=None, page_number=None),
        _child(1, ' '.join(['word'] * 60) + ' cut off mid', section_title=None, page_number=None),
        _child(2, ' '.join(['word'] * 60) + ' cut off mid', section_title=None, page_number=None),
        _child(3, ' '.join(['word'] * 60) + ' cut off mid', section_title=None, page_number=None),
    ]

    good_score = _score_chunks(good_chunks)
    bad_score = _score_chunks(bad_chunks)

    # Under the bug both collapse to the same constant (90.0) because
    # content_chunks is always empty for hierarchical input.
    assert good_score['score'] > bad_score['score']
    assert good_score['truncation_rate'] == 0.0
    assert bad_score['truncation_rate'] == 1.0


def test_parent_rows_excluded_from_back_matter_numerator():
    # Only the PARENT is tagged back_matter (an odd but possible section
    # classification); its children are all main content. If the parent
    # were not excluded, it would be double-counted as "misplaced" text
    # that the children don't actually contain.
    chunks = [
        _parent(0, 'Parent text', section_type=SectionType.BACK_MATTER),
        _child(0, 'Child one, main content.'),
        _child(1, 'Child two, main content.'),
        _child(2, 'Child three, main content.'),
        _child(3, 'Child four, main content.'),
        _child(4, 'Child five, main content.'),
    ]

    result = _score_chunks(chunks)

    assert result['misplaced_back_rate'] == 0.0
