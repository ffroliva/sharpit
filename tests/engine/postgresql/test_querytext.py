from __future__ import annotations

from sharpit.engine.collectors.postgresql.querytext import MAX_QUERY_TEXT_LENGTH, query_text, truncate
from sharpit.engine.masking import MASK, Exposure, Masker

MASKED = Masker(Exposure.MASKED, True)


def test_query_text_masks_single_quoted_escape_and_dollar_quoted_literals() -> None:
    # ported: PostgresHelpersTests.queryTextMasksSingleQuotedEscapeAndDollarQuotedLiterals
    sql = (
        "SELECT * FROM users "
        "WHERE email = 'alice@example.com' "
        "AND note = E'it\\'s secret' "
        "AND body = $$raw token$$ "
        'AND payload = $json${"secret":1}$json$'
    )
    assert query_text(MASKED, sql) == (
        "SELECT * FROM users WHERE email = '******' AND note = '******' AND body = $$******$$ AND payload = $$******$$"
    )


def test_query_text_after_a_unicode_space_before_dollars_shows_no_literal() -> None:
    # derived: the facade replaces the ambiguous dollar-quoted value with a placeholder.
    secret = "A10" + "QUERY" + "SECRET"
    shown = query_text(MASKED, f"SELECT\u2003$tag${secret}$tag$")
    assert secret not in (shown or "")
    assert shown == "SELECT\u2003 ?"  # Unicode spaces are text, not whitespace (Task 1), so truncate keeps them


def test_query_text_masks_unterminated_string_literals() -> None:
    # ported: PostgresHelpersTests.queryTextMasksUnterminatedStringLiterals
    assert query_text(MASKED, "SELECT * FROM users WHERE token = 'sk-live-truncated") == (
        "SELECT * FROM users WHERE token = ******"
    )
    assert query_text(MASKED, "DO $$BEGIN PERFORM 'secret") == "DO $$******$$"


def test_query_text_preserves_parameter_placeholders_and_identifiers() -> None:
    # ported: PostgresHelpersTests.queryTextPreservesParameterPlaceholdersAndIdentifiers
    sql = 'SELECT "user_email", c.relname FROM orders WHERE user_id = $1 AND status = $2'
    assert query_text(MASKED, sql) == sql


def test_query_text_collapses_whitespace_and_truncates_to_400_chars() -> None:
    # ported: PostgresHelpersTests.queryTextCollapsesWhitespaceAndTruncatesTo400Chars
    assert query_text(MASKED, "  SELECT   1 \n FROM \t pg_stat_activity  ") == "SELECT 1 FROM pg_stat_activity"
    long_sql = "SELECT " + "a, " * 200 + "FROM pg_stat_activity"
    shortened = query_text(MASKED, long_sql)
    assert shortened is not None
    assert len(shortened) == MAX_QUERY_TEXT_LENGTH + 3
    assert shortened.endswith("...")
    assert truncate("abcdef", 4) == "abcd..."


def test_query_text_respects_exposure_level() -> None:
    # ported: PostgresHelpersTests.queryTextRespectsExposureLevel
    sql = "SELECT * FROM users WHERE email = 'alice@example.com' AND id = $1"
    assert query_text(Masker(Exposure.METADATA_ONLY, True), "SELECT * FROM users WHERE id = $1") == MASK
    assert query_text(Masker(Exposure.FULL, False), sql) == sql
    assert query_text(MASKED, sql) == "SELECT * FROM users WHERE email = '******' AND id = $1"
    assert query_text(MASKED, None) is None
    assert query_text(MASKED, "   ") is None


def test_query_text_fails_closed_for_unicode_dollar_tags_and_non_ascii_spacing() -> None:
    token = "A10" + "QUERY" + "SECRET"
    assert token not in (query_text(MASKED, f"SELECT $é$ {token} $é$") or "")
    assert query_text(MASKED, "SELECT\u00a0$1") == "SELECT\u00a0$1"  # Task 1: a no-break space stays text
    assert query_text(Masker(Exposure.FULL, False), "SELECT $1") == "SELECT $1"


def test_query_text_a_dollar_inside_a_string_is_not_a_dollar_quote() -> None:
    # derived: the WIP masked dollar quotes before strings, so `$a$` inside a literal swallowed the rest of the text
    assert query_text(MASKED, "SELECT 'cost $a$' , x FROM t") == "SELECT '******' , x FROM t"


def test_query_text_masks_strings_and_dollar_quotes_in_one_pass() -> None:
    # derived: review finding 10, the WIP (f247d7e) masked dollar quotes before strings in two passes
    sql = "SELECT 'price $usd$', name FROM t WHERE body = $usd$x$usd$"
    assert query_text(MASKED, sql) == "SELECT '******', name FROM t WHERE body = $$******$$"


def test_query_text_masks_numeric_literals() -> None:
    # derived: review finding 1 (stricter than BootUI): psycopg2 inlines real parameter values into the query text
    assert (
        query_text(MASKED, "select * from cards where pan = 4111111111111111")
        == "select * from cards where pan = ******"
    )
    assert (
        query_text(MASKED, "update t2 set amount = 12.50 where id = $1")
        == "update t2 set amount = ****** where id = $1"
    )


def test_query_text_drops_comment_bodies() -> None:
    # derived: review finding 1: a comment can carry a value (an ORM tag, a pasted customer id)
    assert query_text(MASKED, "select 1 /* customer 5555 secret */ from t -- secret note\nwhere x") == (
        "select 1 from t where x"
    )


def test_query_text_masks_an_ambiguous_backslash_quote_to_the_end_of_the_text() -> None:
    # derived: final round (1): after an ambiguous \' the literal may close on any later line, so the rest of the
    # text is masked; supersedes test_query_text_masks_a_backslash_escaped_quote_conservatively (end of line)
    shown = query_text(MASKED, r"select 'x\' from t" + "\nwhere a = 'b' and pin = secret")
    assert shown == "select '******'"


def test_query_text_masks_postgresql_16_numeric_forms_whole() -> None:
    # derived: final round (2): hex, octal, binary and underscore-grouped literals (PostgreSQL 16)
    shown = query_text(MASKED, "select a from t where h = 0xDEAD and o = 0o17 and b = 0b101 and p = 4111_1111")
    assert shown == "select a from t where h = ****** and o = ****** and b = ****** and p = ******"


def test_query_text_masks_nested_comments_whole() -> None:
    # derived: final round (3): PostgreSQL block comments nest
    assert query_text(MASKED, "select a /* outer /* inner */ secret */ from t") == "select a from t"


def test_a_double_quoted_value_hides_on_postgresql() -> None:
    # spec A1: the lexer hides this on every other surface, and the corpus's row reaches this one
    shown = query_text(MASKED, 'SELECT id FROM t WHERE email = "alice@example.com"')
    assert shown == "SELECT id FROM t WHERE email = '******'"


def test_a_double_quoted_name_stays_on_postgresql() -> None:
    assert query_text(MASKED, 'SELECT "t"."id" FROM "t"') == 'SELECT "t"."id" FROM "t"'
