"""Medium 7: a known database error also shares the dollar-boundary rule."""

import pytest

from sharpit.engine.masking import Exposure, Masker
from sharpit.engine.sqltext import Dialect, error_text


@pytest.mark.parametrize("dialect", list(Dialect))
@pytest.mark.parametrize("before", ["\xa0", "\u2003", "\u3000", "\ufeff", "\u200b", "a"])
def test_known_sql_error_stops_at_an_unsafe_dollar_boundary(dialect: Dialect, before: str) -> None:
    marker = "Zq7hunterVALUE9"
    out = error_text(Masker(Exposure.MASKED, True), f"SELECT {before}$tag${marker}$tag$", dialect, known=True)
    assert out is not None
    assert marker not in out


@pytest.mark.parametrize("known", [False, True])
@pytest.mark.parametrize("line_break", ["\n", "\r", "\u2028"])
@pytest.mark.parametrize("tail", ["DETAIL:", "context omitted"])
def test_sql_looking_error_head_keeps_its_error_regions(known: bool, line_break: str, tail: str) -> None:
    marker = "Zq7hunterVALUE9"
    source = f"SELECT failed{line_break}{tail} {marker}"
    out = error_text(Masker(Exposure.MASKED, True), source, Dialect.POSTGRESQL, known=known)
    assert out == "SELECT failed"


@pytest.mark.parametrize("dialect", [Dialect.POSTGRESQL, Dialect.UNSUPPORTED])
@pytest.mark.parametrize(
    "template",
    ['SELECT failed: "{}"', 'TABLE "{}" already exists', 'COPY failed: "{}"', 'SELECT "{}", a$tag$body$tag$'],
)
def test_sql_looking_driver_line_keeps_its_quote_mask(dialect: Dialect, template: str) -> None:
    marker = "Zq7hunterVALUE9"
    out = error_text(Masker(Exposure.MASKED, True), template.format(marker), dialect, known=True)
    assert out is not None
    assert marker not in out


def test_sql_looking_driver_line_hides_its_unread_tail() -> None:
    marker = "Zq7hunterVALUE9"
    source = f"SELECT {' ' * 20_000}\u2003$tag${marker}$tag$"
    out = error_text(Masker(Exposure.MASKED, True), source, Dialect.POSTGRESQL, known=True)
    assert out is not None
    assert marker not in out
