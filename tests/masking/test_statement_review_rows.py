"""Statement-text leaks that two reviews of Task 7 found (r8a, r8b), each a row that is red until its task closes it.

A row names its owning task and the review's finding. A guard names the mutant it kills. A string here is a shape a
review named; tokens are built by concatenation.
"""

from __future__ import annotations

import string

import pytest

from sharpit.engine.capture.sqlscan import shown
from sharpit.engine.capture.statement import statement_text
from sharpit.engine.collectors.postgresql.querytext import query_text
from sharpit.engine.masking import Exposure, Masker
from sharpit.engine.sqltext import Dialect

MASKER = Masker(Exposure.MASKED, True)
TOKEN = "9f8e7d6c" + "5b4a3f2e1d0c"
KEY = "AKIA" + "IOSFODNN7EXAMPLE"
VALUE = "hunter2xyz"
SECOND = "hunter2xyz2"
NO_CAP = 10**6


def text(sql: str, dialect: Dialect = Dialect.UNSUPPORTED) -> str:
    out = statement_text(MASKER, sql, dialect)
    assert out is not None
    return out


def parts_of(token: str) -> list[str]:
    return [token[i : i + 8] for i in range(len(token) - 7)]


# T23, review r8a Critical: a token in a URL query, before ``=``, was hidden at 0.4.0 and now shows its tail
@pytest.mark.parametrize(
    "sql",
    [
        f"select https://h/?token={TOKEN}=2",
        f"select https://h/?api_key={TOKEN}='auth'",
        f"select {KEY}/X-Api-Key='v'@{TOKEN}",
    ],
    ids=["url_token", "corpus_api_key", "aws_key_tail"],
)
def test_a_token_in_a_url_query_shows_no_part_of_it(sql: str) -> None:
    out = text(sql)
    assert not any(part in out for part in parts_of(TOKEN))


def test_a_secret_token_leaves_no_part_visible_through_any_joiner() -> None:
    for joiner in string.punctuation + string.whitespace + "☃💥":
        for dialect in (Dialect.MYSQL_FAMILY, Dialect.UNSUPPORTED):
            tail = TOKEN[:10] + joiner + TOKEN[10:]
            out = text(f"select {KEY}/X-Api-Key='v'{joiner}{tail}", dialect)
            assert not any(part in out for part in parts_of(TOKEN)), (joiner, dialect, out)


# T23, review r8a Critical (owner of the MySQL-family row: T17): a double-quoted name and a value, on MySQL
def test_a_double_quoted_name_before_a_value_shows_no_value_on_mysql() -> None:
    assert VALUE not in text(f'select "password":{VALUE}="v"', Dialect.MYSQL_FAMILY)


# T23, review r8a: NOT a regression, 0.4.0 showed this too; it is red on head and on the base
def test_a_single_quoted_name_before_a_value_shows_no_value_on_mysql() -> None:
    assert VALUE not in text(f"select 'password':{VALUE}=1", Dialect.MYSQL_FAMILY)


# T28, review r8a Important: free text taken down the relaxed path by the verb branch keeps what follows the name
@pytest.mark.parametrize(
    "prefix",
    [
        "comment:",
        "change ",
        "signal:",
        "clone ",
        "cluster ",
        "binlog ",
        "update:",
        "set:",
        "start=",
        "do.",
        "use/",
        "kill!",
        "show?",
    ],
)
@pytest.mark.parametrize("payload", ["password=a {}", "Cookie: session=x; other={}"], ids=["password", "cookie"])
def test_free_text_after_a_verb_branch_shows_no_value(prefix: str, payload: str) -> None:
    assert SECOND not in text(prefix + payload.format(SECOND))


# T26, review r8b: the real leak of ``test_no_literal_is_visible[query_text-pg_valid]``, a non-ASCII space before ``$$``
def test_query_text_after_a_unicode_space_before_dollars_shows_no_literal() -> None:
    marker = "mk" + "0a1b2c3d4e"
    out = query_text(MASKER, f"SELECT \xa0$$, 'a $$ {marker} '", NO_CAP)
    assert out is not None
    assert marker not in out


# guard, review r8a Important (T17): kills the mutant that drops the non-ASCII class of ``_RUN_OPENER``. The review's
# ``SELECT @a\xa0$$, ' $$ M '`` survives that mutant (``$$`` needs no class); a tag holding U+00A0 does not
def test_a_dollar_tag_holding_a_non_ascii_space_opens_a_cut_on_mysql() -> None:
    assert text("SELECT \\$\xa0$ ' M '", Dialect.MYSQL_FAMILY) == "SELECT \\ ?"


def test_a_dollar_tag_after_a_non_ascii_name_is_no_quote_on_mysql() -> None:
    assert text("SELECT @a\xa0$$, ' $$ M '", Dialect.MYSQL_FAMILY) == "SELECT @a\xa0$$, ?"


# guard, review r8a Minor (T23): kills the mutant that drops ``cursor < start`` in ``_release_name``: a hit that begins
# at the first character releases the name, and ``flags[-1]`` is the last character's
def test_a_hit_from_the_first_character_keeps_its_name() -> None:
    sql = 'bio="vvvv"'
    assert shown(sql, [(0, len(sql))], Dialect.UNSUPPORTED) == "bio=?"
