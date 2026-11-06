"""The scan reports ranges and one emit walks the raw text (spec §3, parts 2 and 3).

BootUI has no ``ranges`` case in ``SqlStatementNormalizerTests``; its ``tokens`` cases there classify the same scan and
are ported to ``scan_ranges``. ``shown`` ports the classify-then-emit of ``SqlSinkText.mask``, which BootUI tests
through its agent, so the ``shown`` cases are sharpit's own.
"""

from __future__ import annotations

import itertools

import pytest
from tests.dialect_ids import dialect_id
from tests.masking import sql_corpus

from sharpit.engine.capture import sqlscan
from sharpit.engine.capture.sqlscan import Range, normalize, scan_ranges, shown
from sharpit.engine.masking import MASK
from sharpit.engine.sqltext import Dialect

CORPUS_ROWS = 2000
DIALECTS = (
    (sql_corpus.GENERIC, Dialect.UNSUPPORTED),
    (sql_corpus.MYSQL, Dialect.MYSQL_FAMILY),
    (sql_corpus.POSTGRESQL, Dialect.UNSUPPORTED),
)


def _span(sql: str, part: str) -> tuple[int, int]:
    start = sql.index(part)
    return start, start + len(part)


@pytest.mark.parametrize(("corpus", "dialect"), DIALECTS, ids=dialect_id)
def test_shown_with_nothing_hidden_equals_normalize(corpus: str, dialect: Dialect) -> None:
    rows = sql_corpus.rows(7, CORPUS_ROWS, corpus)
    differing = [row.text[:80] for row in rows if shown(row.text, [], dialect) != normalize(row.text, dialect).sql]
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
        "\ufeff",
    ],
)
def test_shown_with_nothing_hidden_equals_normalize_on_the_edges(sql: str) -> None:
    assert shown(sql, [], Dialect.UNSUPPORTED) == normalize(sql, Dialect.UNSUPPORTED).sql


@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        ('`in   (`, "x"', "`in   (`, ?"),  # the list check looks past the spaces a quoted name keeps
        ('`)   ,(`, "x"', "`)   ,(`, ?"),  # and so does the second row of a ``VALUES``
    ],
)
def test_a_value_position_is_read_past_a_run_of_spaces(sql: str, expected: str) -> None:
    assert normalize(sql, Dialect.UNSUPPORTED).sql == expected


def test_a_hidden_equals_sign_does_not_change_a_literal() -> None:
    sql = 'basic = "x"'
    assert shown(sql, [_span(sql, "=")], Dialect.UNSUPPORTED) == "basic = ?"


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
    assert shown(sql, [_span(sql, part)], Dialect.UNSUPPORTED) == expected


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
    assert shown(sql, [_span(sql, part) for part in parts], Dialect.UNSUPPORTED) == expected


def test_a_hidden_run_in_code_is_one_mask_and_keeps_its_structure() -> None:
    sql = "WHERE k = abcdef AND z"
    assert shown(sql, [_span(sql, "= abcdef")], Dialect.UNSUPPORTED) == f"WHERE k = {MASK} AND z"


def test_a_hidden_character_in_a_literal_is_already_a_placeholder() -> None:
    sql = "SELECT 'abc', 1"
    assert shown(sql, [_span(sql, "b")], Dialect.UNSUPPORTED) == "SELECT ?, ?"


def test_a_hidden_character_in_a_comment_is_dropped_with_it() -> None:
    sql = "SELECT /* abc */ 1"
    assert shown(sql, [_span(sql, "b")], Dialect.UNSUPPORTED) == "SELECT ?"


def test_a_hidden_span_across_a_literal_masks_only_the_code() -> None:
    sql = "ab = 'x' cd"
    assert shown(sql, [(0, len(sql))], Dialect.UNSUPPORTED) == f"{MASK} = ? {MASK}"


def test_a_hidden_quoted_name_keeps_its_quotes() -> None:
    sql = "SELECT `abc`"
    assert shown(sql, [_span(sql, "abc")], Dialect.UNSUPPORTED) == f"SELECT `{MASK}`"


def test_hidden_spans_may_overlap_and_run_off_the_text() -> None:
    assert shown("abcdef", [(-5, 2), (1, 3), (4, 4), (100, 200)], Dialect.UNSUPPORTED) == f"{MASK}def"


def test_shown_scans_the_raw_text_once(monkeypatch: pytest.MonkeyPatch) -> None:
    real, seen = sqlscan._scan, []  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

    def spy(sql: str, dialect: Dialect) -> object:
        seen.append(sql)
        return real(sql, dialect)

    monkeypatch.setattr(sqlscan, "_scan", spy)
    sql = 'basic = "x"'
    shown(sql, [_span(sql, "=")], Dialect.UNSUPPORTED)
    assert seen == [sql]


def test_ranges_report_literals_and_comments_with_their_kind() -> None:
    assert scan_ranges("SELECT 'a', /* c */ 1 -- d\n", Dialect.UNSUPPORTED) == [
        Range(7, 10, True),
        Range(12, 19, False),
        Range(20, 21, True),
        Range(22, 26, False),
    ]


def test_a_double_quoted_value_is_frozen_as_a_literal_in_the_raw_scan() -> None:
    assert scan_ranges('basic = "x"', Dialect.UNSUPPORTED) == [Range(8, 11, True)]


# ported: SqlStatementNormalizerTests.tokensClassifyTheTextTheWayNormalizeLexesIt
def test_a_quoted_name_is_not_a_range() -> None:
    assert scan_ranges('"n", `b`, [c], 1', Dialect.UNSUPPORTED) == [Range(15, 16, True)]


# ported: SqlRowLimitsTests.anEmptyHashCommentEndsAtItsLineAndAtTheEndOfTheText
def test_a_hash_comment_at_the_end_runs_to_the_end_of_the_text() -> None:
    assert scan_ranges("select 1 #", dialect=Dialect.MYSQL_FAMILY) == [Range(7, 8, True), Range(9, 10, False)]


def test_ranges_stop_at_the_scan_limit() -> None:
    sql = "'a' " + "x" * sql_corpus.SCAN_LIMIT + " 'y'"
    assert scan_ranges(sql, Dialect.UNSUPPORTED) == [Range(0, 3, True)]


@pytest.mark.parametrize(("corpus", "dialect"), DIALECTS, ids=dialect_id)
def test_ranges_count_what_normalize_counts(corpus: str, dialect: Dialect) -> None:
    rows = sql_corpus.rows(7, CORPUS_ROWS, corpus)
    differing = [
        row.text[:80]
        for row in rows
        if sum(found.literal for found in scan_ranges(row.text, dialect)) != normalize(row.text, dialect).literal_count
    ]
    assert differing == []


# --- statements that read two ways (spec §3, part 4) ------------------------------------------------------------------


AMBIGUOUS = [
    # ported: JournalTextExposureTests.sqlWhoseBackslashesReadDifferentlyByDialectShowsNothingAfterItsFirstQuote
    ("path='C:\\', note='x'", "path= ?"),
    ("select * from t where a = 'it\\'s x' and b = 1", "select * from t where a = ?"),
    ('select * from t where a = "x\\"y"', "select * from t where a = ?"),
    ('k="a\\" x "', "k= ?"),  # both readings give the same text; MySQL's is one literal, and only the ``"`` run says so
    # ported: JournalTextExposureTests.sqlThatCannotBeToldApartFromAValueIsNeverShownMasked
    ("SELECT q'[it's x]' FROM dual", "SELECT q ?"),
    ("SELECT Q'[it's x]'", "SELECT Q ?"),
    ("SELECT nq'[it's x]'", "SELECT nq ?"),
    ("SELECT /* outer /* inner */ ' */ 'x'", "SELECT ?"),
    ("/* /* n */ it's */ SELECT 'x'", "it ?"),
    ("-- c\r, 'a\nS', 'b'", "?"),
    ("SELECT ['a]', 'x']", "SELECT [ ?"),
    ("SELECT ['a b] c', 'x']", "SELECT [ ?"),
    # derived: review C1, each valid on PostgreSQL 18.2: a bracket read as one literal inverts the quotes after it
    ("SELECT ARRAY[['a]', 'SECRET'], ['[y', 'z']]", "SELECT ARRAY[[ ?"),
    ("SELECT ARRAY[['a]', 'SECRET']] -- don't", "SELECT ARRAY[[ ?"),
    ("SELECT ARRAY[['a]', 'SECRET'], ['b]', 'SECRET2']] -- don't", "SELECT ARRAY[[ ?"),
    ("SELECT ['a]', 'x'] -- don't", "SELECT [ ?"),
    ("SELECT ['a]', 'x'], \"it's\"", "SELECT [ ?"),
    ("SELECT ['a]', 'x', '[b', 'c'], 'y'", "SELECT [ ?"),
    ("SELECT [it's], 'x'", "SELECT [it ?"),  # (r5)
    ("SELECT ['a], 'x'", "SELECT [ ?"),
    ("SELECT [it's], 'x' -- don't", "SELECT [it ?"),
    ("SELECT /*! 'a */ secret' */", "SELECT ?"),  # MySQL runs what such a comment holds
    ('SELECT /*!50000 "a */ secret" */', "SELECT ?"),
    ("SELECT /*M! 'a */ secret' */", "SELECT ?"),
    # derived: re-review N4, each runs on SQLite; 0.4.0 hid the value: a bracket reads as a name after a name too
    ("SELECT a[it's], 'SECRET' FROM (SELECT 1 AS a)", "SELECT a[it ?"),
    ("SELECT (1)[it's], 'SECRET'", "SELECT (?)[it ?"),
    ("SELECT[it's], 'SECRET' FROM (SELECT 1 AS [it's])", "SELECT[it ?"),
    ("SELECT ARRAY[it's], 'SECRET'", "SELECT ARRAY[it ?"),  # ``ARRAY`` is a name there
    ("SELECT [a`b], 'SECRET' FROM (SELECT 1 AS [a`b])", "SELECT [a ?"),
    ("SELECT a[b`c], 'SECRET'", "SELECT a[b ?"),
    ("SELECT [a\"b], 'SECRET'", "SELECT [a ?"),
    # the price, each valid on PostgreSQL and each hiding more than it must: nothing tells them from the rows above
    ("SELECT d['a]']", "SELECT d[ ?"),
    ("SELECT ARRAY['a]', 'x']", "SELECT ARRAY[ ?"),
    ("SELECT ARRAY ['a]', 'x']", "SELECT ARRAY [ ?"),
]


@pytest.mark.parametrize(("sql", "expected"), AMBIGUOUS)
def test_a_statement_that_reads_two_ways_stops_at_its_first_quote(sql: str, expected: str) -> None:
    assert normalize(sql, Dialect.UNSUPPORTED).sql == expected


@pytest.mark.parametrize(("sql", "expected"), AMBIGUOUS)
def test_shown_stops_where_normalize_stops(sql: str, expected: str) -> None:
    assert shown(sql, [], Dialect.UNSUPPORTED) == expected


@pytest.mark.parametrize(("sql", "_expected"), AMBIGUOUS)
def test_a_cut_counts_as_one_literal_in_the_ranges(sql: str, _expected: str) -> None:
    assert (
        sum(found.literal for found in scan_ranges(sql, Dialect.UNSUPPORTED))
        == normalize(sql, Dialect.UNSUPPORTED).literal_count
    )


def test_what_a_cut_drops_is_one_literal_range_to_the_end() -> None:
    sql = "path='C:\\', note='x'"
    assert scan_ranges(sql, Dialect.UNSUPPORTED)[-1] == Range(sql.index("'"), len(sql), True)


def test_a_cut_is_a_predicate_literal_where_the_text_stops_at_one() -> None:
    assert normalize("path='C:\\', note='x'", Dialect.UNSUPPORTED).predicate_literal_count == 1


# derived: conflicts hide (spec section 6): with no family known a ``#`` is a comment, an operator or a variable, and
# a statement on a conflict showed ``# password hunter2``. It stops at the ``#``, on any line.
GENERIC_HASH = [
    ("SELECT # it's\n 'x'", "SELECT"),
    ("data #>> '{a}'", "data"),
    ("SELECT a # b", "SELECT a"),
    ("SELECT 'a' # b", "SELECT ?"),
    ("SELECT 1 # $1", "SELECT ?"),
    ("SELECT 1 # `\n, 1234567 # `\n", "SELECT ?"),
    ("SELECT 1 # x $$\n$$SECRET$$", "SELECT ?"),
    (
        "CREATE PROCEDURE p() LANGUAGE JAVASCRIPT AS # $$\n $$ SECRET $$",
        "CREATE PROCEDURE p() LANGUAGE JAVASCRIPT AS",
    ),
]


@pytest.mark.parametrize(("sql", "expected"), GENERIC_HASH)
def test_a_statement_with_no_family_stops_at_a_hash(sql: str, expected: str) -> None:
    assert normalize(sql, Dialect.UNSUPPORTED).sql == expected


@pytest.mark.parametrize(("sql", "expected"), GENERIC_HASH)
def test_shown_stops_at_a_hash_where_normalize_stops(sql: str, expected: str) -> None:
    assert shown(sql, [], Dialect.UNSUPPORTED).strip() == expected


@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        ("SELECT 'C:\\dir', 'y'", "SELECT ?, ?"),  # the backslash reads the same both ways
        ("color='#fff', note='x'", "color=?, note=?"),  # a trigger inside a literal is text
        ("SELECT '/* /* */', 'x'", "SELECT ?, ?"),
        ("SELECT 'q''x', 'y'", "SELECT ?, ?"),
        ("SELECT seq'x', 'y'", "SELECT seq?, ?"),  # the end of a name is no alternative quote
        ("/* a */ SELECT 'x' /* b */", "SELECT ?"),
        ("-- c\r\nSELECT 'x'", "SELECT ?"),  # a Windows line end, not a lone CR
        ("SELECT [ 'x' ]", "SELECT [ ? ]"),
    ],
)
def test_a_statement_that_reads_one_way_is_not_cut(sql: str, expected: str) -> None:
    assert normalize(sql, Dialect.UNSUPPORTED).sql == expected


@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        ("path='C:\\', note='x'", "path= ?"),  # D7: under NO_BACKSLASH_ESCAPES the first string ends at the backslash
        ("SELECT 'it\\'s', 'x'", "SELECT ?"),
        ('UPDATE u SET pw="a\\"x" WHERE id=1', "UPDATE u SET pw= ?"),
        ("/* /* n */ it's */ SELECT 'x'", "it ?"),
        ("SELECT /*! 'a */ secret' */", "SELECT ?"),
    ],
)
def test_a_nested_comment_and_a_differing_backslash_cut_on_mysql(sql: str, expected: str) -> None:
    assert normalize(sql, Dialect.MYSQL_FAMILY).sql == expected


@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        ("SELECT q'a', 'b'", "SELECT q?, ?"),  # no alternative quoting on MySQL
        ("SELECT # it's\n 'x'", "SELECT ?"),  # a comment there, and one reading
        ("SELECT 'C:\\\\', 'x'", "SELECT ?, ?"),  # an escaped backslash reads the same both ways
    ],
)
def test_what_mysql_reads_one_way_is_not_cut(sql: str, expected: str) -> None:
    assert normalize(sql, Dialect.MYSQL_FAMILY).sql == expected


# derived: review I2, each read as written on the server named there; spec A3: 0 on statements that read one way
@pytest.mark.parametrize(
    ("sql", "dialect", "expected"),
    [
        ("-- ticket #12\nSELECT 'x', 'y'", Dialect.UNSUPPORTED, "SELECT ?, ?"),
        ("SELECT 1 /* # 'a */, 'b'", Dialect.UNSUPPORTED, "SELECT ? , ?"),
        ("SELECT `a#b`, 'x', 'y'", Dialect.UNSUPPORTED, "SELECT `a#b`, ?, ?"),
        ("SELECT 1 AS `q'a`, 'x', 'y'", Dialect.UNSUPPORTED, "SELECT ? AS `q'a`, ?, ?"),
        ("SELECT `a\\b`, 'x', 'y'", Dialect.UNSUPPORTED, "SELECT `a\\b`, ?, ?"),
        ("SELECT `a\\b`, 'x', 'y'", Dialect.MYSQL_FAMILY, "SELECT `a\\b`, ?, ?"),
        ("SELECT 1 AS \"a\\b\", 'y'", Dialect.UNSUPPORTED, "SELECT ? AS ?, ?"),
        ("SELECT \"C:\\dir\", 'y'", Dialect.UNSUPPORTED, "SELECT ?, ?"),
    ],
    ids=dialect_id,
)
def test_a_trigger_in_a_comment_or_a_closed_name_is_text(sql: str, dialect: Dialect, expected: str) -> None:
    assert normalize(sql, dialect).sql == expected


TWO_WAY = [
    "SELECT 1 # /* \n, 'a */ SECRET -- '",  # review Q1: a literal on MySQL; the only quote after ``#`` is in a comment
    "SELECT 5--q'a\nSECRET', 'b'",  # review Q1: tight, so a literal on MySQL
    "SELECT 5--#'a\nSECRET', 'b'",
    "SELECT `a#b 'x', SECRET' ",  # an open backtick is no name on PostgreSQL: ``'x'`` and ``SECRET`` are code there
    "SELECT /* # 'a, SECRET'",  # an open comment proves nothing
    "SELECT /*!# */ 'SECRET', 'b'",  # MySQL runs an executable comment, so its ``#`` is code
    "SELECT 'C:\\', SECRET, 'b'",
    'SELECT "a\\" SECRET ", \'b\'',  # ``"`` ends at the backslash here and past it on MySQL
]


@pytest.mark.parametrize("sql", TWO_WAY)
def test_a_statement_that_reads_two_ways_still_cuts(sql: str) -> None:
    assert "SECRET" not in normalize(sql, Dialect.UNSUPPORTED).sql


# derived: re-review N1, MySQL 8.4.10 returns (1, 'SECRET') for each: it skips a comment or a name inside ``/*!``, so
# the run ends later than the scan's first ``*/``
@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        ("SELECT 1 /*! -- */ don't\n, 'SECRET' */", "SELECT ? don ?"),
        ("SELECT 1 /*! # */ don't\n, 'SECRET' */", "SELECT ? don ?"),
        ("SELECT 1 /*M! # */ don't\n, 'SECRET' */", "SELECT ? don ?"),
        ("SELECT /*M! '*/', 'MARK' */", "SELECT ?"),
        ("SELECT /*!50000 1 AS `*/`, 'SECRET' */", "SELECT ?"),
    ],
)
@pytest.mark.parametrize("dialect", [Dialect.UNSUPPORTED, Dialect.MYSQL_FAMILY], ids=dialect_id)
def test_an_executable_comment_ends_later_than_the_scan_reads(sql: str, expected: str, dialect: Dialect) -> None:
    assert normalize(sql, dialect).sql == expected


# derived: re-review N2, MySQL 8.4.10 reads a name after ``@`` or ``.``, under both sql modes; ``t.$$`` is a syntax
# error on PostgreSQL, so ``.`` holds in both modes
@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        ("SELECT @$$ := 'a $$ SECRET '", "SELECT @$$ := ?"),
        ("SET @$$ = 'a $$ SECRET '", "SET @$$ = ?"),
        ("SELECT @$a$ := 'q $a$ SECRET '", "SELECT @$a$ := ?"),
    ],
)
def test_a_dollar_after_at_is_a_name_on_mysql(sql: str, expected: str) -> None:
    assert normalize(sql, Dialect.MYSQL_FAMILY).sql == expected


@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        (
            "SELECT 1 FROM (SELECT 1 AS `$a$`) t WHERE t.$a$ = 'a $a$ SECRET '",
            "SELECT ? FROM (SELECT ? AS `$a$`) t WHERE t.$a$ = ?",
        ),
        (
            "SELECT t.$$ FROM (SELECT 1 AS `$$`) t WHERE t.$$ = 'a $$ SECRET '",
            "SELECT t.$$ FROM (SELECT ? AS `$$`) t WHERE t.$$ = ?",
        ),
    ],
)
def test_a_dollar_after_a_dot_is_a_name_on_mysql(sql: str, expected: str) -> None:
    assert normalize(sql, Dialect.MYSQL_FAMILY).sql == expected


# (r6) re-review 2 D1: ``t.$$`` is a name on MySQL and a syntax error elsewhere, and 0.4.0 hid what follows it, so with
# the dialect unknown a ``.`` keeps its reading and the statement stops at its first opener, as after ``@``
@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        ("SELECT t.$$ = 'a $$ SECRET '", "SELECT t. ?"),
        ("SELECT 1 FROM (SELECT 1 AS `$a$`) t WHERE t.$a$ = 'a $a$ SECRET '", "SELECT ? FROM (SELECT ? AS ?"),
        ("SELECT t.$$ FROM (SELECT 1 AS `$$`) t WHERE t.$$ = 'a $$ SECRET '", "SELECT t. ?"),
    ],
)
def test_a_dollar_after_a_dot_stops_the_statement_with_the_dialect_unknown(sql: str, expected: str) -> None:
    assert normalize(sql, Dialect.UNSUPPORTED).sql == expected


# (r8) re-review 4: a syntax error on all three engines, or a name on MySQL when a column has it: one reading, so it
# took a cut it did not need. With nothing else to open, there is nothing for a second reading to flip
@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        ("SELECT x.$$SECRET$$ FROM (SELECT 1 AS x) x", "SELECT x.? FROM (SELECT ? AS x) x"),
        ("SELECT x.$a$SECRET$a$ FROM t WHERE id = 1", "SELECT x.? FROM t WHERE id = ?"),
        ("SELECT x.$$SECRET", "SELECT x.?"),
        ("SELECT 'a', t.$$ x$$ FROM t", "SELECT ?, t.? FROM t"),  # (r9) an opener before the dot does not count
    ],
)
def test_a_dollar_quote_after_a_dot_with_no_other_opener_reads_one_way(sql: str, expected: str) -> None:
    assert normalize(sql, Dialect.UNSUPPORTED).sql == expected


# (r8) an opener anywhere else keeps the cut: past the closer (the second dollar quote holds a string on MySQL, whose
# ``x$$$$`` is one name) or in the body (a comment on MySQL)
@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        ("SELECT x.$$a$$, 'SECRET'", "SELECT x. ?"),
        ("SELECT t.$$ + x$$$$, ' $$ SECRET ' FROM t", "SELECT t. ?"),
        ("SELECT t.$$ /* $$ SECRET */ FROM t", "SELECT t. ?"),
        ("SELECT t.$$ -- $$ SECRET\n FROM t", "SELECT t. ?"),
        ("SELECT t.$$ # $$ SECRET\n FROM t", "SELECT t. ?"),
    ],
)
def test_a_dollar_quote_after_a_dot_beside_another_opener_still_stops(sql: str, expected: str) -> None:
    assert normalize(sql, Dialect.UNSUPPORTED).sql == expected


# (r7) re-review 3 NB1: ``SELECT`` refuses a dollar quote, but MySQL 8.4.10's lexer has one and its grammar takes it as
# a routine body: each of these is stored under both sql modes and ``routine_definition`` returns the body
ROUTINE = "CREATE PROCEDURE p1() LANGUAGE JAVASCRIPT AS "


@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        (f"{ROUTINE}$$ const k = SECRET; $$", f"{ROUTINE}?"),
        (f"{ROUTINE}$a$ SECRET $a$", f"{ROUTINE}?"),
        (
            "CREATE FUNCTION f1() RETURNS INT DETERMINISTIC LANGUAGE JAVASCRIPT AS $$ return SECRET; $$",
            "CREATE FUNCTION f1() RETURNS INT DETERMINISTIC LANGUAGE JAVASCRIPT AS ?",
        ),
        (
            "CREATE FUNCTION f2() RETURNS INT NO SQL LANGUAGE JAVASCRIPT AS $js$ return SECRET; $js$",
            "CREATE FUNCTION f2() RETURNS INT NO SQL LANGUAGE JAVASCRIPT AS ?",
        ),
        (f"{ROUTINE}$$ it's SECRET $$", f"{ROUTINE}?"),
        (f"{ROUTINE}$1$ SECRET $1$", f"{ROUTINE}?"),
        (f"{ROUTINE}$1a$ SECRET $1a$", f"{ROUTINE}?"),
        (f"{ROUTINE}$1_b$ SECRET $1_b$", f"{ROUTINE}?"),
        (f"{ROUTINE}$_$ SECRET $_$", f"{ROUTINE}?"),
        (f"{ROUTINE}$é$ SECRET $é$", f"{ROUTINE}?"),
        (f"{ROUTINE}$€$ SECRET $€$", f"{ROUTINE}?"),
        (f"{ROUTINE}$a$b$ SECRET $a$", f"{ROUTINE}?"),
        (f"{ROUTINE}/* c */ $$ SECRET $$", f"{ROUTINE}?"),
        (f"{ROUTINE}# $$\n $$ SECRET $$", f"{ROUTINE}?"),
        ("SELECT $$x$$", "SELECT ?"),
        ("SELECT $a$x$a$", "SELECT ?"),
        ("SELECT 'a', $$, 'b'", "SELECT ?, ?"),
    ],
)
def test_a_dollar_quote_opens_where_a_token_starts_on_mysql(sql: str, expected: str) -> None:
    assert normalize(sql, Dialect.MYSQL_FAMILY).sql == expected


@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        ("SELECT @$$ := 'a $$ SECRET '", "SELECT @$$ := ?"),
        ("SET @$a$ = 'a $a$ SECRET '", "SET @$a$ = ?"),
        ("SELECT t.$a$ = 'a $a$ SECRET '", "SELECT t.$a$ = ?"),
        (
            "SELECT 1$a$, 'a $a$ SECRET ' FROM (SELECT 1 AS `1$a$`) t",
            "SELECT ?$a$, ? FROM (SELECT ? AS `1$a$`) t",
        ),
        ("SELECT a$b$, 'a $b$ SECRET '", "SELECT a$b$, ?"),
        ("SELECT $a, 'a $a SECRET '", "SELECT $a, ?"),
        (
            "CREATE PROCEDURE p12() LANGUAGE JAVASCRIPT AS$$ x $$",
            "CREATE PROCEDURE p12() LANGUAGE JAVASCRIPT AS$$ x ?",
        ),
    ],
)
def test_a_dollar_stays_a_name_after_a_name_on_mysql(sql: str, expected: str) -> None:
    assert normalize(sql, Dialect.MYSQL_FAMILY).sql == expected


# (r7) found by the fuzz: MySQL 8.4.10's closing match does not step back. A failed match skips what it read, the
# failing character too, so a closer straight after a ``$`` or a part of the tag closes nothing. Each body was read back
@pytest.mark.parametrize(
    "body",
    [
        "$js$$1$$js$ SECRET $js$",
        "$a$x$$a$ SECRET $a$",
        "$a$$$a$ SECRET $a$",
        "$a$$b$$a$ SECRET $a$",
        "$a$b$$a$ SECRET $a$",
        "$ab$x$a$ab$ SECRET $ab$",
        "$ab$x$$ab$ SECRET $ab$",
        "$$$ SECRET $$",
    ],
)
def test_a_dollar_quote_closes_where_mysql_closes_it(body: str) -> None:
    assert normalize(f"{ROUTINE}{body}", Dialect.MYSQL_FAMILY).sql == f"{ROUTINE}?"


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("$a$x$a$", "?"),
        ("$$x$$", "?"),
        ("$ab$x$aab$y$ab$", "?"),
        # derived: Task 2, the family stops at the quote, so what follows the closer goes with it. It was ``?, ?``
        ("$a$ $ $a$, 1", "?"),  # a lone ``$`` then the closer: closed there, 1064 on what follows
        ("$a$x$$$a$, 1", "?"),
    ],
)
def test_a_dollar_quote_still_closes_on_mysql(body: str, expected: str) -> None:
    assert normalize(f"{ROUTINE}{body}", Dialect.MYSQL_FAMILY).sql == f"{ROUTINE}{expected}"


# (r7) the ROUTINE rows above cut everything past the opener, so they cannot tell a quote that closes from one that
# never does. These two keep text past the closer: a bracket that stays, and a ``/*!`` comment it lets through
@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        ("SELECT 'x', [$a$x$a$]", "SELECT ?, [ ?"),
        ("SELECT 'a', $a$x$$a$ /*! 1 */", "SELECT ?, ?"),
    ],
)
def test_a_closed_dollar_quote_on_mysql_keeps_what_the_cut_would_hide(sql: str, expected: str) -> None:
    assert normalize(sql, Dialect.MYSQL_FAMILY).sql == expected


# derived: spike 2 Q2 and Q3. MariaDB 12.3.3 and MySQL 8.0.44 have no dollar quote and return each marker: ``$$`` is a
# name there, so the first ``'`` opens a string; MySQL 8.4.10 refuses these. One bit cannot tell them apart
@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        ("SELECT $$, 'a $$ SECRET ' FROM (SELECT 1 AS $$) t", "SELECT ?"),
        ("SELECT 1 AS $$, 'x $$ SECRET '", "SELECT ? AS ?"),
        ("SELECT 1 $$, 'x $$ SECRET '", "SELECT ? ?"),
        ("SELECT $a$, 'x $a$ SECRET ' FROM (SELECT 1 AS $a$) t", "SELECT ?"),
        ("SELECT $a$, 'a $a$ ZQXJKV ' FROM (SELECT 1 AS `$a$`) t", "SELECT ?"),
        ("SELECT ($a$), 'a $a$ ZQXJKV ' FROM (SELECT 1 AS `$a$`) t", "SELECT ( ?"),
        ("SELECT 1,$a$, 'a $a$ ZQXJKV ' FROM (SELECT 1 AS `$a$`) t", "SELECT ?, ?"),
        ("SELECT $a$=1, 'a $a$ ZQXJKV ' FROM (SELECT 1 AS `$a$`) t", "SELECT ?"),
        ("SELECT 'a' AS $b$, 'c $b$ SECRET '", "SELECT ? AS ?"),
        ("SELECT 'a' AS $$, 'b $$ SECRET ' FROM DUAL", "SELECT ? AS ?"),
        ("SELECT $a$x$a$$b$, 'a $b$ ZQXJKV '", "SELECT ?"),
        ("SELECT `$$`, $$, 'a $$ SECRET ' FROM t", "SELECT `$$`, ?"),
        ("SELECT $$ x $$ + b", "SELECT ?"),  # the other read has no run left: it goes on to the end of the text
        ("CREATE PROCEDURE zp() BEGIN SELECT $$, 'a $$ SECRET ' FROM (SELECT 1 AS $$) t; END",
         "CREATE PROCEDURE zp() BEGIN SELECT ?"),
    ],
)  # fmt: skip
def test_a_dollar_tag_cuts_where_the_family_disagrees(sql: str, expected: str) -> None:
    assert normalize(sql, Dialect.MYSQL_FAMILY).sql == expected


def test_shown_and_the_ranges_cut_where_the_family_disagrees() -> None:
    sql = "SELECT $$, 'a $$ SECRET ' FROM (SELECT 1 AS $$) t"
    assert shown(sql, [], Dialect.MYSQL_FAMILY) == "SELECT ?"
    assert scan_ranges(sql, Dialect.MYSQL_FAMILY)[-1] == Range(7, len(sql), True)


# derived: spike 2 q3c, the rows with a ``$`` the two readings place alike: a cut at the first opener fails each
@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        ("SELECT @$a$ := 'q $a$ ZQXJKV '", "SELECT @$a$ := ?"),
        ("SET @$$ = 'a $$ ZQXJKV '", "SET @$$ = ?"),
        ("SELECT @$$, 'a $$ ZQXJKV '", "SELECT @$$, ?"),
        ("SELECT 1$a$, 'a $a$ ZQXJKV ' FROM (SELECT 1 AS `1$a$`) t", "SELECT ?$a$, ? FROM (SELECT ? AS `1$a$`) t"),
        ("SELECT 0xAB$a$, 'a $a$ ZQXJKV ' FROM (SELECT 1 AS `0xAB$a$`) t",
         "SELECT ?$a$, ? FROM (SELECT ? AS `0xAB$a$`) t"),
        ("SELECT rv.1.$$, ' $$ ZQXJKV ' FROM rv.1", "SELECT rv.?.$$, ? FROM rv.?"),
        ("SELECT 1 FROM (SELECT 1 AS `$a$`) t WHERE t.$a$ = 'a $a$ ZQXJKV '",
         "SELECT ? FROM (SELECT ? AS `$a$`) t WHERE t.$a$ = ?"),
        ("SELECT a$b, 'ZQXJKV' FROM t", "SELECT a$b, ? FROM t"),
        ("SELECT $, 'ZQXJKV' FROM t", "SELECT $, ? FROM t"),
        ("SELECT `$$`, 'ZQXJKV' FROM t", "SELECT `$$`, ? FROM t"),
        ("SELECT 'a $$ b', 'ZQXJKV' FROM t", "SELECT ?, ? FROM t"),
        ("SELECT 'a', $$, 'b'", "SELECT ?, ?"),
        ("CREATE PROCEDURE p() LANGUAGE JAVASCRIPT AS $$ ZQXJKV $$", "CREATE PROCEDURE p() LANGUAGE JAVASCRIPT AS ?"),
    ],
)  # fmt: skip
def test_a_mysql_dollar_quote_with_no_disagreement_is_unchanged(sql: str, expected: str) -> None:
    assert normalize(sql, Dialect.MYSQL_FAMILY).sql == expected


# derived: spec section 6: a gate on ``$`` once dropped the backslash cut. ``sql_mode`` is session state no text shows
@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        ("SELECT 'a\\', 'SECRET $$'", "SELECT ?"),
        ("SELECT 'a\\', $$, 'SECRET'", "SELECT ?"),
        ("SELECT 1 /*! -- */ don't\n, '$$ SECRET' */", "SELECT ? don ?"),
        ("SELECT 1 AS [it's], '$$ SECRET'", "SELECT ? AS [it ?"),
        ("SELECT 1 AS [a$$], 'b $$ SECRET '", "SELECT ? AS [a$$], ?"),
        ("SELECT 'x', [$a$x$$a$ SECRET]", "SELECT ?"),  # MySQL's closer leaves the body open: a cut at the first opener
    ],
)
def test_the_other_cuts_stand_on_a_text_holding_a_dollar(sql: str, expected: str) -> None:
    assert normalize(sql, Dialect.MYSQL_FAMILY).sql == expected


def test_a_digit_led_tag_opens_nothing_with_the_dialect_unknown() -> None:
    """PostgreSQL's tag rule. SQLite reads ``$1$`` as a variable, so opening there would show what follows it."""
    assert normalize("SELECT $1$, 'a $1$ SECRET '", Dialect.UNSUPPORTED).sql == "SELECT $1$, ?"


# derived: re-review 2 B1, MySQL 8.4.10 reads a digit-led name for each, under both sql modes; PostgreSQL and SQLite
# answer a syntax error to ``1$$x$$``, so a ``$`` tight after a number opens nothing anywhere
@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        ("SELECT 1$a$, 'a $a$ SECRET ' FROM (SELECT 1 AS `1$a$`) t", "SELECT ?$a$, ? FROM (SELECT ? AS `1$a$`) t"),
        ("SELECT 1$$, 'a $$ SECRET ' FROM (SELECT 1 AS `1$$`) t", "SELECT ?$$, ? FROM (SELECT ? AS `1$$`) t"),
        (
            "SELECT 0xAB$a$, 'a $a$ SECRET ' FROM (SELECT 1 AS `0xAB$a$`) t",
            "SELECT ?$a$, ? FROM (SELECT ? AS `0xAB$a$`) t",
        ),
        (
            "SELECT 1_2$a$, 'a $a$ SECRET ' FROM (SELECT 1 AS `1_2$a$`) t",
            "SELECT ?$a$, ? FROM (SELECT ? AS `1_2$a$`) t",
        ),
        ("SELECT 1 AS 1$a$, 'a $a$ SECRET '", "SELECT ? AS ?$a$, ?"),
        (
            "SELECT 'SECRET' FROM (SELECT 1 AS `1$a$`) t WHERE 1$a$ = 1 OR 'a $a$ SECRET' = ''",
            "SELECT ? FROM (SELECT ? AS `1$a$`) t WHERE ?$a$ = ? OR ? = ?",
        ),
    ],
)
@pytest.mark.parametrize("dialect", [Dialect.UNSUPPORTED, Dialect.MYSQL_FAMILY], ids=dialect_id)
def test_a_dollar_after_a_number_opens_nothing(sql: str, expected: str, dialect: Dialect) -> None:
    assert normalize(sql, dialect).sql == expected


@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        ("SELECT a ?$$SECRET$$", "SELECT a ??"),  # a raw ``?`` is PostgreSQL's operator, not a just-read literal
        ("SELECT 'a'$$SECRET$$", "SELECT ??"),  # a syntax error everywhere: only a number goes on as a name
        ("SELECT $$a$$$$SECRET$$", "SELECT ??"),
    ],
)
def test_a_dollar_after_anything_else_that_is_no_name_still_opens(sql: str, expected: str) -> None:
    assert normalize(sql, Dialect.UNSUPPORTED).sql == expected


def test_a_dollar_quote_after_at_reads_two_ways_with_the_dialect_unknown() -> None:
    """``SELECT @$$5$$::int`` is ``5`` on PostgreSQL, a variable on MySQL."""
    assert normalize("SELECT @$$ := 'a $$ SECRET '", Dialect.UNSUPPORTED).sql == "SELECT @ ?"


def test_a_dollar_quote_after_at_stops_the_statement_with_no_quote_to_stop_at() -> None:
    assert normalize("SELECT @$$5$$::int", Dialect.UNSUPPORTED).sql == "SELECT @ ?"


# derived: re-review N3, MySQL 8.4.10 returns (6, 'SECRET'): the tight ``--`` hides the backtick that opens the name
def test_a_tight_double_dash_holding_a_backtick_cuts() -> None:
    sql = "SELECT 5--`a\nb`, 'SECRET' FROM (SELECT 1 AS `a\nb`) t"
    assert normalize(sql, Dialect.UNSUPPORTED).sql == "SELECT ? ?"


def test_mysql_reads_two_minus_signs_and_a_name_there() -> None:
    sql = "SELECT 5--`a\nb`, 'SECRET' FROM (SELECT 1 AS `a\nb`) t"
    assert normalize(sql, Dialect.MYSQL_FAMILY).sql == "SELECT ?--`a\nb`, ? FROM (SELECT ? AS `a\nb`) t"


# derived: re-review 2 A1, MySQL 8.4.10 returns 1234567 for each, under both sql modes: the statement holds no quote or
# the number is before it, so only a backtick is there to stop at
@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        ("SELECT 1 /*!50000 AS `*/`, 1234567 */", "SELECT ? ?"),
        ("SELECT /*! 1 AS `*/`, 1234567 */", "SELECT ?"),
        ("SELECT /*! 1 AS `*/`, 1234567, 'x' */", "SELECT ?"),
        ("SELECT 1 /*! # */ `\n, 1234567 # `\n */", "SELECT ? ?"),
    ],
)
@pytest.mark.parametrize("dialect", [Dialect.UNSUPPORTED, Dialect.MYSQL_FAMILY], ids=dialect_id)
def test_a_backtick_stops_the_cut(sql: str, expected: str, dialect: Dialect) -> None:
    assert normalize(sql, dialect).sql == expected


@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        ("SELECT 5--`a\nb`, 1234567 FROM (SELECT 1 AS `a\nb`) t", "SELECT ? ?"),
        ("SELECT 5--`a\nb`, 1234567, 'x' FROM (SELECT 1 AS `a\nb`) t", "SELECT ? ?"),
    ],
)
def test_a_backtick_stops_the_cut_with_the_dialect_unknown(sql: str, expected: str) -> None:
    assert normalize(sql, Dialect.UNSUPPORTED).sql == expected


# derived: re-review 2 B2, MySQL 8.4.10 returns the value for each, under both sql modes: two minus signs and a block
# comment over the newline, so a quote or a backtick inside it opens a run for the scan alone
@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        ("SELECT 5--/*\n don't */1, 'SECRET'", "SELECT ? don ?"),
        ("SELECT 5--1 /*\n don't */, 'SECRET'", "SELECT ? don ?"),
        ("SELECT 5--/*\n ` */1, 'SECRET'", "SELECT ? ?"),
    ],
)
def test_a_tight_double_dash_holding_a_block_comment_cuts(sql: str, expected: str) -> None:
    assert normalize(sql, Dialect.UNSUPPORTED).sql == expected


def test_mysql_reads_two_minus_signs_and_a_block_comment_there() -> None:
    assert normalize("SELECT 5--/*\n don't */1, 'SECRET'", Dialect.MYSQL_FAMILY).sql == "SELECT ?-- ?, ?"


def test_a_tight_double_dash_with_no_opener_after_it_has_nothing_to_stop_at() -> None:
    assert normalize("SELECT 5--/* c\n, 2", Dialect.UNSUPPORTED).sql == "SELECT ? , ?"


# derived: re-review 1 N5, ruled: with CREATE OPERATOR a backtick is an operator on PostgreSQL 18.2, and
# ``SELECT 1 ` 'SECRET'`` returns the value, while the scan reads a name and copies it
@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        ("SELECT 1 ` 'SECRET'", "SELECT ? ?"),
        ("SELECT `a 'x', SECRET' ", "SELECT ?"),
        ('SELECT 1 ` "SECRET"', "SELECT ? ?"),
        ("SELECT `a'b`, 'SECRET' FROM (SELECT 1 AS `a'b`) t", "SELECT ?"),
        ('SELECT `a"b`, 1234567', "SELECT ?"),
    ],
)
def test_a_backtick_run_holding_a_quote_reads_two_ways_with_the_dialect_unknown(sql: str, expected: str) -> None:
    assert normalize(sql, Dialect.UNSUPPORTED).sql == expected


def test_a_backtick_run_is_a_name_on_mysql() -> None:
    sql = "SELECT `a'b`, 'SECRET' FROM (SELECT 1 AS `a'b`) t"
    assert normalize(sql, Dialect.MYSQL_FAMILY).sql == "SELECT `a'b`, ? FROM (SELECT ? AS `a'b`) t"


def test_a_backtick_run_with_no_quote_keeps_the_statement() -> None:
    assert normalize("SELECT `a b`, 'x'", Dialect.UNSUPPORTED).sql == "SELECT `a b`, ?"


# (r7) re-review 3 NB3: with CREATE OPERATOR what follows a backtick is code on PostgreSQL 18.2, and an unclosed run is
# invalid on MySQL and SQLite, so nothing readable is lost
@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        ("SELECT 1 ` 1234567", "SELECT ? ?"),
        ("SELECT 1`1234567", "SELECT ? ?"),
        ("SELECT 1 ` /* c */ 1234567", "SELECT ? ?"),
        ("SELECT 1 ` 1234567 FROM (SELECT 1) t", "SELECT ? ?"),
        ("SELECT 1 ` $$SECRET$$::text", "SELECT ? ?"),
        ("SELECT 1 ` $a$SECRET$a$::text", "SELECT ? ?"),
        ("SELECT 1 ``` 1234567", "SELECT ? ?"),  # a doubled backtick does not close it
        ("SELECT `a`` 1234567", "SELECT ?"),
        ("SELECT `a``", "SELECT ?"),  # ends on a backtick, still open
        ("SELECT `a` ` 1234567", "SELECT ?"),  # a closed name before it: the first opener is the stop
    ],
)
def test_an_unclosed_backtick_stops_the_statement_with_the_dialect_unknown(sql: str, expected: str) -> None:
    assert normalize(sql, Dialect.UNSUPPORTED).sql == expected


@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        ("SELECT `a`", "SELECT `a`"),
        ("SELECT `a```", "SELECT `a```"),  # a doubled backtick, then the closing one
        ("SELECT ````, 1", "SELECT ````, ?"),
        ("SELECT `a b` FROM t", "SELECT `a b` FROM t"),
        ("SELECT 1 ` 1234567 ` 2", "SELECT ? ` 1234567 ` ?"),  # a closed pair is every backticked name: for the owner
    ],
)
def test_a_closed_backtick_run_keeps_the_statement_with_the_dialect_unknown(sql: str, expected: str) -> None:
    assert normalize(sql, Dialect.UNSUPPORTED).sql == expected


def test_an_unclosed_backtick_is_a_name_on_mysql() -> None:
    assert normalize("SELECT 1 ` 1234567", Dialect.MYSQL_FAMILY).sql == "SELECT ? ` 1234567"


def test_a_lone_cr_in_a_line_comment_cuts() -> None:
    """PostgreSQL ends the comment at the CR, MySQL and SQLite at the newline: ``S`` is in a literal for one of them."""
    assert "S" not in normalize("-- c\r, 'a\nS', 'b'", Dialect.UNSUPPORTED).sql


# --- literals the scan read as something else -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        ("SELECT .5", "SELECT ?"),
        ("SELECT .123456 FROM t", "SELECT ? FROM t"),
        ("SELECT .5e3, (.5)", "SELECT ?, (?)"),
        ("SELECT 0xFF", "SELECT ?"),
        ("SELECT 0b101", "SELECT ?"),
        ("SELECT 1_000", "SELECT ?"),
        ("SELECT 1_000_000.5", "SELECT ?"),
        # derived: review I1, each valid on PostgreSQL 18.2
        ("SELECT 0xFF_FF", "SELECT ?"),
        ("SELECT 0x_ff", "SELECT ?"),
        ("SELECT 0b10_10", "SELECT ?"),
        ("SELECT 0o777", "SELECT ?"),
        ("SELECT 0o7_7", "SELECT ?"),
        ("SELECT 1e1_0", "SELECT ?"),
        ("SELECT t.c1, t0x1, a_1 FROM s.t", "SELECT t.c1, t0x1, a_1 FROM s.t"),
    ],
)
@pytest.mark.parametrize("dialect", [Dialect.UNSUPPORTED, Dialect.MYSQL_FAMILY], ids=dialect_id)
# ported: JournalTextExposureTests.sqlThatCannotBeToldApartFromAValueIsNeverShownMasked
def test_a_number_is_a_literal_however_it_is_spelled(sql: str, expected: str, dialect: Dialect) -> None:
    assert normalize(sql, dialect).sql == expected


@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        ("SELECT $$x", "SELECT ?"),
        ("SELECT $tag$x", "SELECT ?"),
        ("SELECT $$it's", "SELECT ?"),
        ("select a$b$c from t", "select a$b$c from t"),
        ("select a$b$c$b$ from t", "select a$b$c$b$ from t"),  # a ``$`` inside a name opens nothing, closed or not
        ("SELECT 1$$x$$", "SELECT ?$$x$$"),  # (r6) a syntax error on PostgreSQL and SQLite, a name on MySQL
        ("select * from t where id = $1", "select * from t where id = $1"),
    ],
)
# ported: JournalTextExposureTests.sqlThatCannotBeToldApartFromAValueIsNeverShownMasked
def test_an_open_dollar_quote_runs_to_the_end(sql: str, expected: str) -> None:
    assert normalize(sql, Dialect.UNSUPPORTED).sql == expected


def test_a_non_ascii_dollar_tag_is_one_literal() -> None:
    assert normalize("$€$it's$€$, 'S'", Dialect.UNSUPPORTED).sql == "?, ?"


@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        ("SELECT 5--'a\nb', 'x'", "SELECT ?--?, ?"),  # without a space MySQL reads two minus signs
        ("SELECT 1 -- 'c\n, 2", "SELECT ? , ?"),
        ("SELECT 1 --", "SELECT ?"),
        # derived: review I3, 8.4.10 returns (1, 'S', 'b') for both, under both sql modes
        ("SELECT 1 --\x01'c\n, 'S', 'b'", "SELECT ? , ?, ?"),
        ("SELECT 1 --\x7f'c\n, 'S', 'b'", "SELECT ? , ?, ?"),
    ],
)
def test_two_dashes_open_a_mysql_comment_only_before_a_space_a_control_or_the_end(sql: str, expected: str) -> None:
    assert normalize(sql, Dialect.MYSQL_FAMILY).sql == expected


def test_two_dashes_open_a_comment_elsewhere_without_a_space() -> None:
    assert normalize("SELECT 5--c\n, 2", Dialect.UNSUPPORTED).sql == "SELECT ? , ?"


def test_an_unknown_dialect_tight_double_dash_cuts() -> None:
    """On MySQL it is two minus signs and a string, elsewhere a comment; only the column name of a real server shows."""
    assert "S" not in normalize("SELECT 5--'a\nS', 'b'", Dialect.UNSUPPORTED).sql.replace("SELECT", "")


@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        ("/*!40101 SET x=1 */ SELECT 'y', 'z'", "SELECT ?"),  # the price: a dump header takes the tail
        ("SELECT /*! 1 */ 'y', 'z'", "SELECT ?"),
        ("SELECT /*! 1 */ 2", "SELECT ?"),  # nothing to stop at, and no literal to lose
    ],
)
def test_an_executable_comment_stops_a_statement_with_a_quote_anywhere(sql: str, expected: str) -> None:
    assert normalize(sql, Dialect.MYSQL_FAMILY).sql == expected


# derived: review M1: ``ARRAY [`` decides this, the planted removal passed both named files
def test_an_array_with_a_space_before_its_bracket_is_a_subscript() -> None:
    assert normalize("SELECT ARRAY [TRUE], [TRUE]", Dialect.UNSUPPORTED).sql == "SELECT ARRAY [?], [TRUE]"


# derived: re-review N4 and A1: a backtick stops the cut, so a number after it never reaches a head with an open run
@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        ("SELECT [a`b], 123456", "SELECT [a ?"),
        ("SELECT a[b`c], 123456", "SELECT a[b ?"),
    ],
)
def test_a_bracket_holding_a_backtick_is_one_literal(sql: str, expected: str) -> None:
    assert normalize(sql, Dialect.UNSUPPORTED).sql == expected


@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        ("SELECT a['it''s']", "SELECT a[?]"),  # even: the quotes stay balanced, so it reads one way
        ("SELECT doc['x']['y'], 'z'", "SELECT doc[?][?], ?"),
        ("SELECT a[`b`], 'z'", "SELECT a[`b`], ?"),
    ],
)
def test_a_subscript_with_balanced_quotes_keeps_its_reading(sql: str, expected: str) -> None:
    assert normalize(sql, Dialect.UNSUPPORTED).sql == expected


@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        ("SELECT ARRAY['x']", "SELECT ARRAY[?]"),
        ("SELECT arr[1]", "SELECT arr[?]"),
        ("SELECT a [b] FROM t", "SELECT a [b] FROM t"),
        ("SELECT [a 1], 'x'", "SELECT [a ?], ?"),
    ],
)
def test_a_bracket_without_a_quote_keeps_its_reading(sql: str, expected: str) -> None:
    assert normalize(sql, Dialect.UNSUPPORTED).sql == expected


# derived: re-review 2 A2, each runs on SQLite, where a bracket closes at its first ``]`` whatever is in it; 0.4.0 hid
# the value but on the last row (D6): a run opened in the body and open at its end flips the reading of what follows
@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        ("SELECT [$$], 'a $$ SECRET ' FROM (SELECT 1 AS [$$])", "SELECT [ ?"),
        ("SELECT a[$$], 'a $$ SECRET ' FROM (SELECT 1 AS a)", "SELECT a[ ?"),
        ("SELECT [$a$], 'a $a$ SECRET ' FROM (SELECT 1 AS [$a$])", "SELECT [ ?"),
        ("SELECT [-- ], 'a\n', 'SECRET' FROM (SELECT 1 AS [-- ])", "SELECT [ ?"),
        ("SELECT a[-- ], 'a\n', 'SECRET' FROM (SELECT 1 AS a)", "SELECT a[ ?"),
        ("SELECT [x-- y], 'a\n', 'SECRET' FROM (SELECT 1 AS [x-- y])", "SELECT [x ?"),
        ("SELECT [/*], 'a*/', 'SECRET' FROM (SELECT 1 AS [/*])", "SELECT [ ?"),
        ("SELECT a[/*], 'a*/', 'SECRET' FROM (SELECT 1 AS a)", "SELECT a[ ?"),
        ("SELECT [/*], 2 AS `*/`, 'SECRET' FROM (SELECT 1 AS [/*])", "SELECT [ ?"),
        ("SELECT [it's[b], 'SECRET' FROM (SELECT 1 AS [it's[b])", "SELECT [it ?"),
        ("SELECT a[it's[b], 'SECRET' FROM (SELECT 1 AS a)", "SELECT a[it ?"),
        ("SELECT 1['[x], 'SECRET'", "SELECT ?[ ?"),
        ("SELECT ['[x], 'SECRET' FROM (SELECT 1 AS ['[x])", "SELECT [ ?"),
        ("SELECT [a`[b], 'SECRET' FROM (SELECT 1 AS [a`[b])", "SELECT [a ?"),
        ("SELECT @a[`[x], 1234567", "SELECT @a[ ?"),
        ("SELECT [`'`'], 'SECRET', [`'`'] FROM (SELECT 1 AS [`'`'])", "SELECT [ ?"),
        ("SELECT ['`'`], 2 AS `x`, 'SECRET' FROM (SELECT 1 AS ['`'`])", "SELECT [ ?"),
        ("SELECT a[`'`'], 'SECRET'", "SELECT a[ ?"),
        ('SELECT [\'"\'"], "SECRET" FROM (SELECT 1 AS [\'"\'"])', "SELECT [ ?"),
        ('SELECT a[\'"\'"], "SECRET" FROM (SELECT 1 AS a)', "SELECT a[ ?"),
    ],
)
def test_a_run_left_open_in_a_bracket_stops_the_statement(sql: str, expected: str) -> None:
    assert normalize(sql, Dialect.UNSUPPORTED).sql == expected


# each returns the value on PostgreSQL 18.2 and e8210e8 hid it: read as one literal, the bracket inverts what follows,
# so a dollar quote or a comment left open in a bracket is itself a place to stop
@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        ("SELECT ARRAY[$$a]$$, $$SECRET$$]", "SELECT ARRAY[ ?"),
        ("SELECT ARRAY[$$a]$$, $$SECRET$$], 'x'", "SELECT ARRAY[ ?"),
        ("SELECT ARRAY[/*]$$*/$$SECRET$$]", "SELECT ARRAY[ ?"),
    ],
)
def test_a_bracket_stops_at_the_opener_it_leaves_open(sql: str, expected: str) -> None:
    assert normalize(sql, Dialect.UNSUPPORTED).sql == expected


# a further ``[`` with no run open is read by the scan when it gets there: each is valid on PostgreSQL or SQLite
@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        ("SELECT ARRAY['a', 'b']", "SELECT ARRAY[?, ?]"),
        ("SELECT a['it''s']", "SELECT a[?]"),
        ("SELECT arr[1], 'x'", "SELECT arr[?], ?"),
        ("SELECT [a 1], 'x'", "SELECT [a ?], ?"),
        ("SELECT ARRAY[1,2], 'x'", "SELECT ARRAY[?,?], ?"),
        ("SELECT (ARRAY[1])[1], 'x'", "SELECT (ARRAY[?])[?], ?"),
        ("SELECT ARRAY[['a','b']], 'x'", "SELECT ARRAY[[?,?]], ?"),
        ("SELECT ARRAY[ARRAY['a']], 'x'", "SELECT ARRAY[ARRAY[?]], ?"),
        ("SELECT ARRAY[$$x$$], 'y'", "SELECT ARRAY[?], ?"),
        ("SELECT ARRAY[/* c */ 1], 'y'", "SELECT ARRAY[ ?], ?"),
        ("SELECT [a[b], 'SECRET' FROM (SELECT 1 AS [a[b])", "SELECT [a[b], ? FROM (SELECT ? AS [a[b])"),
        ("SELECT [a[b], 1234567 FROM (SELECT 1 AS [a[b])", "SELECT [a[b], ? FROM (SELECT ? AS [a[b])"),
        ("SELECT [-- \n], 'x'", "SELECT [ ], ?"),  # the run closes inside: the first ``]`` reads the same both ways
    ],
)
def test_a_run_closed_in_a_bracket_keeps_the_statement(sql: str, expected: str) -> None:
    assert normalize(sql, Dialect.UNSUPPORTED).sql == expected


def test_a_bracket_is_read_by_the_rules_of_its_mode() -> None:
    assert "SECRET" not in normalize("SELECT [#], 'a\n', 'SECRET'", Dialect.MYSQL_FAMILY).sql


# derived: re-review 2's probes, a server returned the value for each and head hides it: pins, each already green
PROBED_ON_MYSQL = [
    "SELECT 'SECRET', t.$$ FROM (SELECT 1 AS `$$`) t WHERE t.$$ <> 'a $$ SECRET '",
    "SELECT /*! `*/`, 'SECRET' */ FROM (SELECT 1 AS `*/`) t",
    "SELECT 5--/*!\n1 AS `*/`, 'SECRET' */",
    "SELECT 'a $a$ SECRET ' FROM (SELECT 1) 1$a$",
    "SELECT /*+ QB_NAME(`a`) */ 1, 'SECRET'",
    "SELECT /*+ QB_NAME(`a*b`) */ 1, 'SECRET'",
]
PROBED_ELSEWHERE = [
    "SELECT 5--$$\n, 'a $$ SECRET '",
    "SELECT 5--[\n, 'SECRET'",
    "SELECT 5--x\r, 'SECRET'\n",
    "SELECT ['\"'\"], 1 AS \"x\", 'SECRET' FROM (SELECT 1 AS ['\"'\"])",
    "SELECT ['\"'\"], \"x\", 'SECRET' FROM (SELECT 1 AS ['\"'\"], 2 AS x)",
    "SELECT [[it's], 'SECRET' FROM (SELECT 1 AS [[it's])",
    "SELECT [a\nb's], 'SECRET' FROM (SELECT 1 AS [a\nb's])",
    "SELECT [a\\], 'SECRET' FROM (SELECT 1 AS [a\\])",
    "SELECT [a#b], 'SECRET' FROM (SELECT 1 AS [a#b])",
    "SELECT [q'x'], 'SECRET' FROM (SELECT 1 AS [q'x'])",
    "SELECT [e], 'SECRET' FROM (SELECT 1 AS [e])",
    "SELECT [`], 1234567, [`] FROM (SELECT 1 AS [`])",
    "SELECT [a b], 1234567 FROM (SELECT 1 AS [a b])",
    "SELECT 1::int || $$SECRET$$",
    "SELECT $$SECRET$$",
    "SELECT $a$SECRET$a$",
    'SELECT [\'"\'"], 1234567, "x" FROM (SELECT 1 AS [\'"\'"])',
    "SELECT @$$-5$$::int, 'SECRET'",
    "SELECT @ $$-5$$::int, 1234567",
    "SELECT ARRAY[1] @> $$ {1} $$::int[], 'SECRET'",
]


@pytest.mark.parametrize("sql", PROBED_ON_MYSQL + PROBED_ELSEWHERE)
def test_a_probed_value_stays_hidden(sql: str) -> None:
    shown_text = normalize(sql, Dialect.UNSUPPORTED).sql
    assert "SECRET" not in shown_text
    assert "1234567" not in shown_text


@pytest.mark.parametrize("sql", PROBED_ON_MYSQL)
def test_a_probed_value_stays_hidden_on_mysql(sql: str) -> None:
    assert "SECRET" not in normalize(sql, Dialect.MYSQL_FAMILY).sql


# (r7) re-review 3 NB2: a nested comment or a lone CR flips the state and no quote stops it. PostgreSQL 18.2 returned
# the value of each of these, MySQL 8.4.10 stored the body of each ``CREATE`` row
@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        ("SELECT /* /* */ $$ */ $$SECRET$$", "SELECT ?"),
        ("SELECT /*/**/$$*/$$SECRET$$", "SELECT ?"),
        ("SELECT /* /* */ $$ */ $$ SECRET $$, 2", "SELECT ?"),
        ("SELECT /* /* */ $a$ */ $a$ SECRET $a$", "SELECT ?"),
        ("SELECT /* /* */ $$ */ $$SECRET$$, 'x'", "SELECT ?"),
        ("SELECT /* /* */ $$ */ $$SECRET$$ AS a, 2 AS b FROM (SELECT 1) t", "SELECT ?"),
        ("SELECT 1, -- x\r $$\n SECRET $$", "SELECT ?, ?"),
        ("SELECT -- x\r $a$\n SECRET $a$", "SELECT ?"),
        ("SELECT 1 --\r, $$\n SECRET $$", "SELECT ? ?"),
        ("SELECT 1, -- x\r $$\n SECRET $$, 'x'", "SELECT ?, ?"),
        ("SELECT 5--$$\n SECRET $$", "SELECT ? ?"),
        (
            "CREATE PROCEDURE p() LANGUAGE JAVASCRIPT /*! AS $$ */ SECRET $$ */",
            "CREATE PROCEDURE p() LANGUAGE JAVASCRIPT ?",
        ),
        (
            "CREATE PROCEDURE p() LANGUAGE JAVASCRIPT /*!50000 AS $€$ */ SECRET $€$ */",
            "CREATE PROCEDURE p() LANGUAGE JAVASCRIPT ?",
        ),
    ],
)
def test_a_cut_stops_at_a_dollar_quote(sql: str, expected: str) -> None:
    assert normalize(sql, Dialect.UNSUPPORTED).sql == expected


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT /* /* */ $$ */ $$SECRET$$",
        "SELECT /* /* */ $a$ */ $a$ SECRET $a$",
        "CREATE PROCEDURE p() LANGUAGE JAVASCRIPT /*! AS $$ */ SECRET $$ */",
        "CREATE PROCEDURE p() LANGUAGE JAVASCRIPT /*!50000 AS $$ */ x SECRET $$ */",
    ],
)
def test_a_cut_stops_at_a_dollar_quote_on_mysql(sql: str) -> None:
    assert normalize(sql, Dialect.MYSQL_FAMILY).sql.endswith(" ?")


@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        ("SELECT /* /* */ a FROM t WHERE id = $1, 'x'", "SELECT a FROM t WHERE id = $1, ?"),
        ("SELECT /* /* */ 1234567", "SELECT ?"),
        ("SELECT /* /* */ */ 1234567", "SELECT */ ?"),
        ("SELECT /*!50000 a */ FROM t", "SELECT FROM t"),
        ("SELECT $$x$$, 'y'", "SELECT ?, ?"),
    ],
)
def test_a_parameter_or_a_comment_is_not_where_a_cut_stops(sql: str, expected: str) -> None:
    assert normalize(sql, Dialect.UNSUPPORTED).sql == expected


# (r7) re-review 3 NB4: after a space a ``[`` is no subscript, and PostgreSQL 18.2 ran the first two and read the number
@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        (
            "SELECT (ARRAY[1,2]) [CASE WHEN FALSE THEN 1234567 ELSE 1 END]",
            "SELECT (ARRAY[?,?]) [CASE WHEN ? THEN ? ELSE ? END]",
        ),
        (
            "SELECT a [CASE WHEN TRUE THEN 1234567 END] FROM (SELECT ARRAY[1] AS a) t",
            "SELECT a [CASE WHEN ? THEN ? END] FROM (SELECT ARRAY[?] AS a) t",
        ),
        ("SELECT [a 1b]", "SELECT [a ?b]"),
        ("SELECT [a 0x10 b]", "SELECT [a ? b]"),
    ],
)
@pytest.mark.parametrize("dialect", [Dialect.UNSUPPORTED, Dialect.MYSQL_FAMILY], ids=dialect_id)
def test_a_bracket_holding_a_word_led_by_a_digit_is_read_inside(sql: str, expected: str, dialect: Dialect) -> None:
    assert normalize(sql, dialect).sql == expected


@pytest.mark.parametrize("sql", ["SELECT [a b]", "SELECT [col_1]", "SELECT [a b2]", "SELECT [_1 x]", "SELECT [a  b ]"])
def test_a_bracket_of_words_stays_a_name(sql: str) -> None:
    assert normalize(sql, Dialect.UNSUPPORTED).sql == sql


def test_a_double_quote_cut_open_at_the_scan_limit_is_a_literal() -> None:
    sql = f'SELECT {"name, " * 3330}"{"y" * 300}" FROM t'
    assert '"' in sql[: sql_corpus.SCAN_LIMIT]
    assert normalize(sql, Dialect.UNSUPPORTED).sql.endswith(", ?")


# (r8) re-review 4: a keyword is a word, and PostgreSQL and SQLite read ``THEN.1234567`` as ``THEN 0.1234567``. No list
# of keywords can be complete, so after a word the ``.`` is copied and the digits are a literal; it reads inside, no cut
@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        ("SELECT.1234567", "SELECT.?"),
        ("SELECT CASE WHEN 1=1 THEN.1234567 END", "SELECT CASE WHEN ?=? THEN.? END"),
        ("SELECT 1 WHERE 1=1 AND.1234567>0", "SELECT ? WHERE ?=? AND.?>?"),
        ("SELECT /* /* */ */ CASE WHEN TRUE THEN.1234567 END", "SELECT */ CASE WHEN ? THEN.? END"),
        ("SELECT.1234567e3", "SELECT.?"),
        ("SELECT.1_234_567", "SELECT.?"),
        ("SELECT t.123 FROM t", "SELECT t.? FROM t"),
        ("SELECT a1.5, _b.5, c$.5", "SELECT a1.?, _b.?, c$.?"),
        ("SELECT t..123", "SELECT t..?"),
        ("SELECT ..123", "SELECT ..?"),
    ],
)
@pytest.mark.parametrize("dialect", [Dialect.UNSUPPORTED, Dialect.MYSQL_FAMILY], ids=dialect_id)
def test_digits_after_a_word_and_a_dot_are_a_literal(sql: str, expected: str, dialect: Dialect) -> None:
    assert normalize(sql, dialect).sql == expected


# (r8) the rule's cost, toward hiding: MySQL reads both as names, and they lose their digits
@pytest.mark.parametrize(
    ("sql", "expected"),
    [("SELECT t.1col FROM t", "SELECT t.?col FROM t"), ("SELECT * FROM db.2020_sales", "SELECT * FROM db.?_sales")],
)
@pytest.mark.parametrize("dialect", [Dialect.UNSUPPORTED, Dialect.MYSQL_FAMILY], ids=dialect_id)
def test_a_name_led_by_a_digit_after_a_dot_loses_its_digits(sql: str, expected: str, dialect: Dialect) -> None:
    assert normalize(sql, dialect).sql == expected


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT.1234567",
        "SELECT DISTINCT.1234567",
        "SELECT ALL.1234567",
        "SELECT CASE WHEN.1234567>0 THEN 1 END",
        "SELECT CASE WHEN 1=0 THEN 1 ELSE.1234567 END",
        "SELECT 1 WHERE.1234567>0",
        "SELECT 1 WHERE 1=1 OR.1234567>0",
        "SELECT 1 WHERE NOT.1234567>0",
        "SELECT 1 GROUP BY 1 HAVING.1234567>0",
        "SELECT 1 ORDER BY.1234567",
        "SELECT 1 LIMIT.1234567",
        "SELECT 1 LIMIT 1 OFFSET.1234567",
        "SELECT 1 WHERE 1 IN(SELECT.1234567)",
        "SELECT 2 BETWEEN.1234567 AND 3",
        "SELECT 1 BETWEEN 0 AND.1234567",
        "SELECT 1 LIKE.1234567",
        "SELECT 1 IS.1234567",
        "VALUES(1) UNION SELECT.1234567",
        "SELECT 1 UNION ALL SELECT.1234567",
        "SELECT 1 FROM (SELECT 1 AS a) t JOIN (SELECT 1 AS b) u ON.1234567>0",
    ],
)
@pytest.mark.parametrize("dialect", [Dialect.UNSUPPORTED, Dialect.MYSQL_FAMILY], ids=dialect_id)
def test_no_keyword_keeps_the_digits_after_a_dot(sql: str, dialect: Dialect) -> None:
    assert "1234567" not in normalize(sql, dialect).sql
    assert shown(sql, [], dialect) == normalize(sql, dialect).sql


# (r9) a digit run reached through a word and a ``.`` is a name part on MySQL 8.4.10, so the ``.`` after it stays apart
# and the ``$`` after that opens nothing. Each row but the last was read on 8.4.10; its fraction reads on as a literal
@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        ("SELECT rv.1.$$, ' $$ SECRET ' FROM rv.1", "SELECT rv.?.$$, ? FROM rv.?"),
        ("SELECT rv.1.$1$, ' $1$ SECRET ' FROM rv.1", "SELECT rv.?.$1$, ? FROM rv.?"),
        ("SELECT rv.1.$a$, ' $a$ SECRET ' FROM rv.1", "SELECT rv.?.$a$, ? FROM rv.?"),
        ("SELECT 1 FROM rv.1 WHERE rv.1.$$ = ' $$ SECRET '", "SELECT ? FROM rv.? WHERE rv.?.$$ = ?"),
        ("SELECT rv.1.$$ # $$ SECRET\n FROM rv.1", "SELECT rv.?.$$ FROM rv.?"),
        ("SELECT rv.1.$$ /* $$ SECRET */ FROM rv.1", "SELECT rv.?.$$ FROM rv.?"),
        ("SELECT.1.2345678", "SELECT.??"),
    ],
)
def test_a_digit_run_through_a_word_and_a_dot_is_a_name_part_on_mysql(sql: str, expected: str) -> None:
    assert normalize(sql, Dialect.MYSQL_FAMILY).sql == expected


# derived: MySQL 8.4.10 accepts each of these, its lexer reads ``[\w.$]*`` after ``@`` as one token, a user variable or
# an account's host. A number in that token hides all of it, as a digit run hides anywhere else
@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        ("SELECT @1.$$, ' $$ SECRET '", "SELECT ?, ?"),
        ("SELECT @a.1.$$, ' $$ SECRET '", "SELECT ?, ?"),
        ("SELECT @1.5.$$, ' $$ SECRET '", "SELECT ?, ?"),
        ("SELECT @a.1.2.$$, ' $$ SECRET '", "SELECT ?, ?"),
        ("SELECT @.5.$$, ' $$ SECRET '", "SELECT ?, ?"),
        ("SELECT @.1.$$, ' $$ SECRET '", "SELECT ?, ?"),
        ("SELECT @1.5.$1$, ' $1$ SECRET '", "SELECT ?, ?"),
        ("SELECT @1.5.$a$, ' $a$ SECRET '", "SELECT ?, ?"),
        ("SET @1.5.$$ = ' $$ SECRET '", "SET ? = ?"),
        ("SELECT 1 WHERE @1.5.$$ = ' $$ SECRET '", "SELECT ? WHERE ? = ?"),
        ("CREATE USER u@1.5.$$ IDENTIFIED BY ' $$ SECRET '", "CREATE USER u? IDENTIFIED BY ?"),
    ],
)
def test_what_follows_at_is_one_token_on_mysql(sql: str, expected: str) -> None:
    assert normalize(sql, Dialect.MYSQL_FAMILY).sql == expected


@pytest.mark.parametrize("length", range(1, 6))
def test_no_spelling_after_at_opens_a_dollar_quote_on_mysql(length: int) -> None:
    names = map("".join, itertools.product("15.$_a", repeat=length))
    shown = [
        name for name in names if "SECRET" in normalize(f"SELECT @{name}$$, ' $$ SECRET '", Dialect.MYSQL_FAMILY).sql
    ]
    assert shown == []


@pytest.mark.parametrize(
    ("sql", "expected"), [("SELECT @a.b.$$", "SELECT @a.b.$$"), ("SELECT @a1, @_2", "SELECT @a1, @_2")]
)
def test_a_name_after_at_stays_on_mysql(sql: str, expected: str) -> None:
    assert normalize(sql, Dialect.MYSQL_FAMILY).sql == expected


@pytest.mark.parametrize(
    ("sql", "expected"),
    [("SELECT (1).5", "SELECT (?)?"), ("SELECT ?.5", "SELECT ??"), ('SELECT "a".5', 'SELECT "a"?')],
)
def test_a_dot_after_no_word_keeps_its_read(sql: str, expected: str) -> None:
    assert normalize(sql, Dialect.UNSUPPORTED).sql == expected


# the 19 non-ASCII spaces ``str.isspace`` accepts and no server reads as whitespace
_UNICODE_SPACES = [
    "\u0085",
    "\u00a0",
    "\u1680",
    *(chr(c) for c in range(0x2000, 0x200B)),
    "\u2028",
    "\u2029",
    "\u202f",
    "\u205f",
    "\u3000",
]


@pytest.mark.parametrize("space", _UNICODE_SPACES, ids=[f"U+{ord(c):04X}" for c in _UNICODE_SPACES])
def test_a_unicode_space_opens_nothing(space: str) -> None:
    for sql in ("SELECT x{c}$$, 'a $$ SECRET '", "SELECT {c}$$, 'a $$ SECRET '"):
        for dialect in (Dialect.UNSUPPORTED, Dialect.MYSQL_FAMILY):
            assert "SECRET" not in normalize(sql.format(c=space), dialect).sql, (sql, dialect)


def test_a_zero_width_space_is_a_name_character() -> None:
    """A guard, not a defect: U+200B is not ``isspace`` and no server reads it as whitespace, so it joins the name."""
    assert "SECRET" not in normalize("SELECT x\u200b$$, 'a $$ SECRET '", Dialect.UNSUPPORTED).sql


@pytest.mark.parametrize(
    "sql",
    [
        "  x IN (1, 2, 3",
        "x IN (1, 2, 3)  ",
        "SELECT a  b FROM t WHERE c IN (1, 2, 3) AND pw = 'x'",
        "SELECT a  b FROM t WHERE c IN (1, 2, 3",
    ],
)
def test_shown_equals_normalize_around_adjacent_unicode_spaces(sql: str) -> None:
    """A Unicode space is a name character: the list cuts of the scan text must fit ``pieces`` position for position."""
    assert shown(sql, [], Dialect.UNSUPPORTED) == normalize(sql, Dialect.UNSUPPORTED).sql


def test_a_hidden_unicode_space_is_masked_with_its_run() -> None:
    """A Unicode space is not whitespace: a hidden run holding one is a single mask, not two around a copied space."""
    sql = "SELECT id FROM t WHERE k=aa bb"
    start = sql.index("aa")
    assert shown(sql, [(start, len(sql))], Dialect.UNSUPPORTED) == f"SELECT id FROM t WHERE k={MASK}"


@pytest.mark.parametrize("space", _UNICODE_SPACES, ids=[f"U+{ord(c):04X}" for c in _UNICODE_SPACES])
@pytest.mark.parametrize("pad", ["", " ", "\t"])
@pytest.mark.parametrize("dialect", [Dialect.UNSUPPORTED, Dialect.MYSQL_FAMILY], ids=dialect_id)
def test_a_statement_of_only_unicode_spaces_is_a_name_in_both_outputs(space: str, pad: str, dialect: Dialect) -> None:
    """A Unicode space is no whitespace to a server: the statement is a name, so both outputs keep it."""
    sql = space + pad
    assert shown(sql, [], dialect) == normalize(sql, dialect).sql
