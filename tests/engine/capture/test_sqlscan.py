"""The scan reports ranges and one emit walks the raw text (spec §3, parts 2 and 3).

BootUI has no ``ranges`` case in ``SqlStatementNormalizerTests``; its ``tokens`` cases there classify the same scan and
are ported to ``scan_ranges``. ``shown`` ports the classify-then-emit of ``SqlSinkText.mask``, which BootUI tests
through its agent, so the ``shown`` cases are sharpit's own.
"""

from __future__ import annotations

import pytest
from tests.masking import sql_corpus

from sharpit.engine.capture import sqlscan
from sharpit.engine.capture.sqlscan import Range, normalize, scan_ranges, shown
from sharpit.engine.masking import MASK

CORPUS_ROWS = 2000
DIALECTS = ((sql_corpus.GENERIC, False), (sql_corpus.MYSQL, True), (sql_corpus.POSTGRESQL, False))


def _span(sql: str, part: str) -> tuple[int, int]:
    start = sql.index(part)
    return start, start + len(part)


@pytest.mark.parametrize(("dialect", "mysql"), DIALECTS)
def test_shown_with_nothing_hidden_equals_normalize(dialect: str, mysql: bool) -> None:
    rows = sql_corpus.rows(7, CORPUS_ROWS, dialect)
    differing = [row.text[:80] for row in rows if shown(row.text, [], mysql) != normalize(row.text, mysql).sql]
    assert differing == []


@pytest.mark.parametrize(
    "sql",
    [
        "",
        " \n\t ",
        "SELECT `a  b`, [c  d] FROM t",  # the scan copies a quoted name as it is: whitespace in it does not collapse
        "SELECT `a\n\tb`",
        "SELECT `a  ",
        "/* c */ SELECT 1 -- d",
        "SELECT 'x'\r\n\tFROM  t",
        "a IN (1, 2, 3) AND b IN ('x')",
        '"a"."b" = "c"',
        "ARRAY['x'], a[1], (ARRAY[1])[1]",
        "col1 tfoo",
    ],
)
def test_shown_with_nothing_hidden_equals_normalize_on_the_edges(sql: str) -> None:
    assert shown(sql, []) == normalize(sql).sql


@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        ('`in   (`, "x"', "`in   (`, ?"),  # the list check looks past the spaces a quoted name keeps
        ('`)   ,(`, "x"', "`)   ,(`, ?"),  # and so does the second row of a ``VALUES``
    ],
)
def test_a_value_position_is_read_past_a_run_of_spaces(sql: str, expected: str) -> None:
    assert normalize(sql).sql == expected


def test_a_hidden_equals_sign_does_not_change_a_literal() -> None:
    sql = 'basic = "x"'
    assert shown(sql, [_span(sql, "=")]) == "basic = ?"


@pytest.mark.parametrize(
    ("sql", "part", "expected"),
    [
        ('name like "x"', "like", f"name {MASK} ?"),
        ('insert into t values ("x", "y")', "values", f"insert into t {MASK} (?, ?)"),
        ('a in ("x")', "in", f"a {MASK} (?)"),
    ],
)
def test_a_hidden_keyword_does_not_change_a_literal(sql: str, part: str, expected: str) -> None:
    """``=`` is structural, so a scan of the masked text still reads it: a second scan loses these words instead."""
    assert shown(sql, [_span(sql, part)]) == expected


@pytest.mark.parametrize(
    ("sql", "parts", "expected"),
    [
        ("pin (1,2,3)", ["p"], f"{MASK}in (?,?,?)"),  # the mask must not make ``in`` a keyword
        ("a in (1,2,3)", ["in"], f"a {MASK} (?)"),  # and hiding the keyword must not undo the collapse
        ("ab IN (1, 2) AND cd", ["ab", "cd"], f"{MASK} IN (?) AND {MASK}"),
        ("abc def IN (1, 2) AND gh", ["abc def"], f"{MASK} {MASK} IN (?) AND gh"),
    ],
)
def test_a_list_collapses_as_the_raw_scan_read_it(sql: str, parts: list[str], expected: str) -> None:
    assert shown(sql, [_span(sql, part) for part in parts]) == expected


def test_a_hidden_run_in_code_is_one_mask_and_keeps_its_structure() -> None:
    sql = "WHERE k = abcdef AND z"
    assert shown(sql, [_span(sql, "= abcdef")]) == f"WHERE k = {MASK} AND z"


def test_a_hidden_character_in_a_literal_is_already_a_placeholder() -> None:
    sql = "SELECT 'abc', 1"
    assert shown(sql, [_span(sql, "b")]) == "SELECT ?, ?"


def test_a_hidden_character_in_a_comment_is_dropped_with_it() -> None:
    sql = "SELECT /* abc */ 1"
    assert shown(sql, [_span(sql, "b")]) == "SELECT ?"


def test_a_hidden_span_across_a_literal_masks_only_the_code() -> None:
    sql = "ab = 'x' cd"
    assert shown(sql, [(0, len(sql))]) == f"{MASK} = ? {MASK}"


def test_a_hidden_quoted_name_keeps_its_quotes() -> None:
    sql = "SELECT `abc`"
    assert shown(sql, [_span(sql, "abc")]) == f"SELECT `{MASK}`"


def test_hidden_spans_may_overlap_and_run_off_the_text() -> None:
    assert shown("abcdef", [(-5, 2), (1, 3), (4, 4), (100, 200)]) == f"{MASK}def"


def test_shown_scans_the_raw_text_once(monkeypatch: pytest.MonkeyPatch) -> None:
    real, seen = sqlscan._scan, []  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

    def spy(sql: str, mysql: bool) -> object:
        seen.append(sql)
        return real(sql, mysql)

    monkeypatch.setattr(sqlscan, "_scan", spy)
    sql = 'basic = "x"'
    shown(sql, [_span(sql, "=")])
    assert seen == [sql]


def test_ranges_report_literals_and_comments_with_their_kind() -> None:
    assert scan_ranges("SELECT 'a', /* c */ 1 -- d\n") == [
        Range(7, 10, True),
        Range(12, 19, False),
        Range(20, 21, True),
        Range(22, 26, False),
    ]


def test_a_double_quoted_value_is_frozen_as_a_literal_in_the_raw_scan() -> None:
    assert scan_ranges('basic = "x"') == [Range(8, 11, True)]


# ported: SqlStatementNormalizerTests.tokensClassifyTheTextTheWayNormalizeLexesIt
def test_a_quoted_name_is_not_a_range() -> None:
    assert scan_ranges('"n", `b`, [c], 1') == [Range(15, 16, True)]


# ported: SqlRowLimitsTests.anEmptyHashCommentEndsAtItsLineAndAtTheEndOfTheText
def test_a_hash_comment_at_the_end_runs_to_the_end_of_the_text() -> None:
    assert scan_ranges("select 1 #", mysql=True) == [Range(7, 8, True), Range(9, 10, False)]


def test_ranges_stop_at_the_scan_limit() -> None:
    sql = "'a' " + "x" * sql_corpus.SCAN_LIMIT + " 'y'"
    assert scan_ranges(sql) == [Range(0, 3, True)]


@pytest.mark.parametrize(("dialect", "mysql"), DIALECTS)
def test_ranges_count_what_normalize_counts(dialect: str, mysql: bool) -> None:
    rows = sql_corpus.rows(7, CORPUS_ROWS, dialect)
    differing = [
        row.text[:80]
        for row in rows
        if sum(found.literal for found in scan_ranges(row.text, mysql)) != normalize(row.text, mysql).literal_count
    ]
    assert differing == []
