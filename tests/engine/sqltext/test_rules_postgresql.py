"""PostgreSQL rules from study.md section 5 and section 1.1: scan.l citations and behavior."""

from __future__ import annotations

from sharpit.engine import sqltext
from sharpit.engine.capture import sqlscan
from sharpit.engine.sqltext import Dialect

PG = Dialect.POSTGRESQL


# scan.l:261-267, 555-561: E'...' opens xe, backslash escapes inside
def test_escape_string_constant() -> None:
    assert sqlscan.normalize(r"SELECT E'hello\nworld'", PG).sql == "SELECT E?"
    assert sqlscan.normalize(r"SELECT E'hello\'world'", PG).sql == "SELECT E?"


def test_non_ascii_identifier_before_e_does_not_make_an_escape_string() -> None:
    sql = "SELECT \xa0E'\\', 'MARK'"
    assert "MARK" not in sqlscan.normalize(sql, PG).sql


# scan.l:301-307, 562-572: U&'...' Unicode escape string, '' doubling, no backslash escape
def test_unicode_escape_string() -> None:
    assert sqlscan.normalize("SELECT U&'hello''world'", PG).sql == "SELECT U&?"


# scan.l:285-287, 757-776: dollar quote $tag$...$tag$ closed at first identical tag
def test_dollar_quote() -> None:
    assert sqlscan.normalize("SELECT $tag$hello it's$tag$", PG).sql == "SELECT ?"
    assert sqlscan.normalize("SELECT $$secret$$", PG).sql == "SELECT ?"


# scan.l:332-335: ident_cont holds $, so $ after an identifier character is a name, not a dollar quote
def test_dollar_after_name_character_is_identifier() -> None:
    assert "FROM t" not in sqlscan.normalize("SELECT col$$ FROM t", PG).sql
    assert "FROM t" not in sqlscan.normalize("SELECT col$tag$ FROM t", PG).sql


# scan.l:421: integer_junk is {decinteger}{identifier}; identifier cannot start with $, so 1$$ opens
def test_dollar_after_number_opens_quote() -> None:
    assert sqlscan.normalize("SELECT 1$$hello$$", PG).sql == "SELECT ? ?"


def test_dollar_quotes_after_ascii_boundaries_and_ambiguous_dollars() -> None:
    assert sqlscan.normalize("SELECT $1, $$body$$", PG).sql == "SELECT $1, ?"
    assert sqlscan.normalize("SELECT $tag$body$tag$", PG).sql == "SELECT ?"
    for sql in ("SELECT €$1$$MK0Z", "SELECT \xa0$1$$MK0Z", "SELECT ٣$1$$MK0Z", "SELECT $1$1$$MK0Z"):
        assert sqltext.LEXER.scan(sql, PG).cut == sql.rfind("$$")
        assert "MK0Z" not in sqlscan.normalize(sql, PG).sql


def test_earlier_backslash_cut_wins_over_later_ambiguous_dollar() -> None:
    sql = "$1'\\', MK0Z$$\xa0E'"
    assert "MK0Z" not in sqlscan.normalize(sql, PG).sql


# scan.l:447-485: block comments nest: xcdepth
def test_nested_block_comments() -> None:
    assert sqlscan.normalize("SELECT /* outer /* inner */ still comment */ 1", PG).sql == "SELECT ?"


def test_nested_gate_row() -> None:
    assert sqlscan.normalize("SELECT /* /* x */ */ 'a', 'b'", PG).sql == "SELECT ?, ?"


def test_executable_comment_prefix_is_not_postgresql_syntax() -> None:
    sql = "SELECT /*! 'inside' */ 'outside'"
    assert not sqltext.LEXER.reads_two_ways(sql, PG)


# scan.l:210-213: line comment ends at newline or CR
def test_line_comment_ends_at_cr_or_lf() -> None:
    assert sqlscan.normalize("SELECT 1 -- comment\rSELECT 2", PG).sql == "SELECT ? SELECT ?"
    sql = "SELECT 1 -- comment\rSELECT 2\n, 'MARK'"
    assert sqlscan.normalize(sql, PG).sql == "SELECT ? SELECT ? , ?"


# scan.l:367: # is an operator, never a comment
def test_hash_is_operator() -> None:
    assert sqlscan.normalize("SELECT data #>> '{a}' FROM t", PG).sql == "SELECT data #>> ? FROM t"
    assert not sqltext.LEXER.reads_two_ways("SELECT 1 # 'x'", PG)


# scan.l:366: [ is self, a single token, not an identifier or bracket quote
def test_bracket_is_character() -> None:
    assert sqlscan.normalize("SELECT [col] FROM t", PG).sql == "SELECT [col] FROM t"
    assert sqltext.LEXER.scan("SELECT [col] FROM t", PG).runs == ()


# scan.l:367: backtick is an operator: no run
def test_backtick_is_operator() -> None:
    assert sqlscan.normalize("SELECT 1 ` 2", PG).sql == "SELECT ? ` ?"
    assert not sqltext.LEXER.reads_two_ways("SELECT `col'x` FROM t", PG)


# scan.l:366, 545: ARRAY[...] bracket is character, string inside is literal
def test_array_bracket() -> None:
    assert sqlscan.normalize("SELECT ARRAY['x', 'y']", PG).sql == "SELECT ARRAY[?, ?]"
    assert sqlscan.normalize("SELECT ARRAY['a]', 'x']", PG).sql == "SELECT ARRAY[?, ?]"


# scan.l:386-393: 0x, 0o, 0b, _ are integer and numeric literals
def test_radix_literals() -> None:
    assert sqlscan.normalize("SELECT 0x1f, 0o77, 0b101, 1_000_000", PG).sql == "SELECT ?, ?, ?, ?"


# asyncpg placeholders $1, $2 stay placeholders
def test_asyncpg_placeholders_stay_placeholders() -> None:
    assert sqlscan.normalize("SELECT $1", PG).sql == "SELECT $1"
    assert sqlscan.normalize("SELECT x=$1", PG).sql == "SELECT x=$1"
    assert sqlscan.normalize("SELECT $1$", PG).sql == "SELECT $1$"
    assert sqlscan.normalize("SELECT $1 $2", PG).sql == "SELECT $1 $2"
    assert sqlscan.normalize("SELECT $1$$ MARK $$", PG).sql == "SELECT $1 ?"


def test_non_ascii_dollar_tag_characters_open_a_quote() -> None:
    for tag in ("٣", "²", "٣٣", "٣a"):
        sql = f"SELECT ${tag}$ MARK ${tag}$"
        assert "MARK" not in sqlscan.normalize(sql, PG).sql


def test_placeholder_after_closed_dollar_quote_stays_visible() -> None:
    sql = "SELECT $$é$$$1$$MK0Z...$$"
    assert sqlscan.normalize(sql, PG).sql == "SELECT ?$1 ?"


# A1: double-quoted value in value position hides, "t"."id" stays
def test_a_double_quoted_value_hides_on_postgresql() -> None:
    assert "alice@example.com" not in sqlscan.normalize('SELECT id FROM t WHERE email = "alice@example.com"', PG).sql
    assert "Alice Smith" not in sqlscan.normalize('UPDATE t SET name = "Alice Smith"', PG).sql
    assert "SECRET" not in sqlscan.normalize('INSERT INTO t VALUES ("it\'s SECRET", 1)', PG).sql
    assert '"t"."id"' in sqlscan.normalize('SELECT "t"."id" FROM t', PG).sql


# A1: a backslash in '...' whose readings differ keeps its cut
def test_a_postgresql_backslash_keeps_its_cut() -> None:
    sql = r"UPDATE t SET path='C:\', note='secret' WHERE id=1"
    scan = sqltext.LEXER.scan(sql, PG)
    assert scan.cut >= 0
    assert "secret" not in sqlscan.normalize(sql, PG).sql
    assert sqltext.LEXER.reads_two_ways(sql, PG)


def test_a_backslash_in_a_postgresql_quoted_name_does_not_cut() -> None:
    sql = 'SELECT "a\\b" FROM t'
    assert sqltext.LEXER.scan(sql, PG).cut == -1
