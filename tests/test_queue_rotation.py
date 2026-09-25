"""Once the priority books are done, three lanes take turns, then comments rule.

The tail of the Calibre queue used to be ordered by recency alone, so a 3★
book or one with a long comment (a translation, a review) waited behind every
newer addition. Now each run opens with newest, 3★ and longest-comment dealt
one at a time, ``LANE_QUOTA`` each, and continues by comment length alone.
"""

from src.archilles.watchdog import LANE_QUOTA, _order_calibre_queue


def _library(n: int = 60) -> dict:
    """Books 1..n; every 5th is 3★, comment length grows as the id falls."""
    return {
        cid: {
            'author': '', 'title': '', 'tags': [],
            'rating': 6 if cid % 5 == 0 else 0,
            'comments': 'x' * (n - cid),
        }
        for cid in range(1, n + 1)
    }


def _ids(books: dict, **first) -> list[int]:
    entries = [{'calibre_id': cid} for cid in books]
    order = _order_calibre_queue(
        entries, books,
        first.get('authors', []), first.get('tags', []), first.get('titles', []),
    )
    return [e['calibre_id'] for e in order]


def test_lanes_alternate_one_book_at_a_time():
    ids = _ids(_library())
    # newest, 3★, longest comment -- then again from lane 1
    assert ids[:9] == [60, 55, 1, 59, 50, 2, 58, 45, 3]


def test_each_lane_gives_its_quota_then_comment_length_takes_over():
    ids = _ids(_library())
    mixed = ids[:3 * LANE_QUOTA]
    assert mixed[0::3] == [60, 59, 58, 57, 56, 54, 53, 52, 51, 49]    # newest (55, 50 dealt as 3★)
    assert mixed[1::3] == [55, 50, 45, 40, 35, 30, 25, 20, 15, 10]    # 3★
    assert mixed[2::3] == [1, 2, 3, 4, 5, 6, 7, 8, 9, 11]             # comment (10 dealt as 3★)
    # the rest: longest comment first, i.e. lowest id first here
    assert ids[3 * LANE_QUOTA:3 * LANE_QUOTA + 3] == [12, 13, 14]


def test_a_dry_lane_is_skipped():
    books = _library()
    for b in books.values():
        b['rating'] = 0
    assert _ids(books)[:4] == [60, 1, 59, 2]


def test_every_book_appears_exactly_once():
    books = _library()
    ids = _ids(books)
    assert sorted(ids) == sorted(books)


def test_priority_and_top_ratings_stay_in_front():
    books = _library()
    books[3]['tags'] = ['BBB']
    books[7]['rating'] = 10
    books[8]['rating'] = 8
    ids = _ids(books, tags=['BBB'])
    assert ids[:3] == [3, 7, 8]
    assert ids[3:6] == [60, 55, 1]


def test_an_empty_queue_stays_empty():
    assert _order_calibre_queue([], {}, [], [], []) == []
