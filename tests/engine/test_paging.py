import pytest

from sharpit.engine.paging import BadRequest, paged, parse_int_param

ITEMS = [f"item{i}" for i in range(10)]


def _page(q=None, offset=None, limit=None, items=ITEMS):
    return paged(items, q, offset, limit, lambda s: [s])


# ported: PagedList clamp (MAX_LIMIT=1000)
def test_limit_clamped_to_1000():
    _, page = _page(limit=5000)
    assert page["limit"] == 1000


def test_limit_zero_clamped_to_1():
    rows, page = _page(limit=0)
    assert page["limit"] == 1
    assert len(rows) == 1


def test_negative_offset_zero():
    _, page = _page(offset=-3)
    assert page["offset"] == 0


def test_unbounded_limit_equals_matched():
    rows, page = _page(q="item1")
    assert page == {"total": 10, "matched": 1, "offset": 0, "limit": 1, "returned": 1, "hasMore": False}
    assert rows == ["item1"]
    _, page = _page()
    assert page["limit"] == page["matched"] == 10


def test_has_more():
    rows, page = _page(offset=2, limit=3)
    assert rows == ["item2", "item3", "item4"]
    assert page["hasMore"] is True
    _, page = _page(offset=7, limit=3)
    assert page["hasMore"] is False and page["returned"] == 3


def test_q_case_insensitive_trimmed():
    rows, _ = _page(q="  ITEM3 ")
    assert rows == ["item3"]
    rows, _ = paged(["a", "b"], "  ", None, None, lambda s: [s])
    assert len(rows) == 2


def test_text_may_yield_none():
    rows, _ = paged(["a", "b"], "a", None, None, lambda s: [None, s])
    assert rows == ["a"]


def test_parse_int_rejects_abc():
    with pytest.raises(BadRequest, match="Invalid 'offset' parameter"):
        parse_int_param("abc", "offset")
    assert parse_int_param(None, "offset") is None
    assert parse_int_param("-4", "offset") == -4
