"""A statement is read from raw text once, and free text in its place hides more (spec §3, the Task 6 amendment)."""

from __future__ import annotations

import pytest

from sharpit.engine import sqltext
from sharpit.engine.capture.statement import masked_shape, statement_text
from sharpit.engine.capture.traces import _sql_attribute  # pyright: ignore[reportPrivateUsage]
from sharpit.engine.masking import MASK, Exposure, Masker
from sharpit.engine.sqltext import Dialect

MASKER = Masker(Exposure.MASKED, True)
GITHUB_TOKEN = "ghp_" + "qMJX61wKzKlsVEOXgKQti54E"  # split: the host refuses a push holding a whole token
STRIPE_KEY = "sk_live_" + "caJxl2ed6lutLaJzdLustUfh"


def _statement(sql: str, dialect: Dialect = Dialect.UNSUPPORTED) -> str | None:
    return _sql_attribute(MASKER, "db.statement", sql, dialect)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT \"hunter2\" FROM t # 'x'",
        "SELECT `hunter2` FROM t # 'x'",
        'SELECT "hunter2" FROM t # \\',
    ],
)
def test_unsupported_hash_cut_hides_the_first_opener(sql: str) -> None:
    assert statement_text(MASKER, sql, Dialect.UNSUPPORTED) == "SELECT ?"


@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        ("UPDATE u SET password='x' WHERE id=1", f"UPDATE u SET password={MASK} WHERE id=?"),
        ("update u set token = 'x', name = 'y' where id = 1", f"update u set token = {MASK}, name = ? where id = ?"),
        ("/* app */ UPDATE u SET pwd='x' WHERE id=1", f"UPDATE u SET pwd={MASK} WHERE id=?"),
        ("(SELECT 1 FROM u WHERE secret='x' AND id=2)", f"(SELECT ? FROM u WHERE secret={MASK} AND id=?)"),
    ],
)
def test_a_sensitive_column_keeps_its_clauses(sql: str, expected: str) -> None:
    assert _statement(sql) == expected


# finding I2: punctuation tight against the verb is still a statement, ``-`` is not: ``set-cookie: password=...``
@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        ("SELECT*FROM u WHERE password=? AND id=?", f"SELECT*FROM u WHERE password={MASK} AND id=?"),
        ("SELECT`a`FROM t WHERE token='x'", f"SELECT`a`FROM t WHERE token={MASK}"),
        ("UPDATE`u`SET password='x' WHERE id=1", f"UPDATE`u`SET password={MASK} WHERE id=?"),
        ("SET@password='x'", f"SET@password={MASK}"),
    ],
)
def test_punctuation_tight_against_the_verb_keeps_the_statement(sql: str, expected: str) -> None:
    assert _statement(sql) == expected


# no statement starts this way, so a hit hides the whole text: a value's end is a guess here, and the scan has split
# what it read. The first has a token ahead of the first quote; ``mask_text`` of the render showed the tail of the last
@pytest.mark.parametrize(
    "text",
    [
        f"{GITHUB_TOKEN}', 'bzUC6kUuQ6tvvSTlLV3N",
        "password=hunter2 and the rest of the line",
        "failed for key=abc: 'still here'",
        "failed to update password=hunter2 and the rest",  # a verb counts only as the first word
        "set-cookie: password=hunter2 and the rest",
        "x=password=abc",  # only the strict read sees the key nested in a value
        "REPAIR u USING password='x'",  # a verb the list lacks: it costs the statement, toward hiding
    ],
)
def test_text_with_no_verb_and_a_hit_is_hidden_whole(text: str) -> None:
    assert _statement(text) == MASK


@pytest.mark.parametrize("verb", ["BINLOG", "CHANGE", "CLONE", "CLUSTER", "COMMENT", "RESIGNAL", "SIGNAL"])
def test_a_rarer_verb_keeps_the_statement(verb: str) -> None:
    assert _statement(f"{verb} t WHERE password='x' AND id=1") == f"{verb} t WHERE password={MASK} AND id=?"


# the token pass reads ``bio="sk_live_..."`` as one token and hides all of it, but the value is a literal: spec A3
@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        (
            f'UPDATE t SET bio="{STRIPE_KEY}", name=1 WHERE id=1',
            "UPDATE t SET bio=?, name=? WHERE id=?",
        ),
        (f"UPDATE t SET bio='{STRIPE_KEY}' WHERE id=1", "UPDATE t SET bio=? WHERE id=?"),
    ],
)
def test_a_name_beside_a_secret_literal_stays(sql: str, expected: str) -> None:
    assert _statement(sql) == expected


def test_a_hit_that_starts_before_the_name_stays_hidden() -> None:
    # finding I1: the name is the tail of a url the masker hid whole, so releasing it shows ``abc123def``
    assert _statement('update x https://h/?token=abc123def="v"') == f"update x {MASK}={MASK}=?"


def test_a_secret_beside_a_secret_literal_stays_hidden() -> None:
    assert _statement(f"SELECT {GITHUB_TOKEN}='{STRIPE_KEY}'") == f"SELECT {MASK}?"


def test_text_with_no_verb_and_no_hit_keeps_the_render() -> None:
    assert _statement("connection refused 'x' at .5") == "connection refused ? at ?"


def test_mysql_mode_reaches_the_scan() -> None:
    assert _statement('SELECT "x y"', Dialect.MYSQL_FAMILY) == "SELECT ?"
    assert _statement('SELECT "firstName"') == 'SELECT "firstName"'


def test_metadata_only_returns_nothing_in_the_function() -> None:
    assert statement_text(Masker(Exposure.METADATA_ONLY, True), "SELECT 1", Dialect.UNSUPPORTED) is None


def test_a_broken_render_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(_sql: str, _dialect: Dialect) -> None:
        raise RuntimeError

    monkeypatch.setattr(sqltext.LEXER, "scan", broken)
    assert statement_text(MASKER, "UPDATE broken SET note='SECRET'", Dialect.UNSUPPORTED) == MASK


@pytest.mark.parametrize("method", ["mask_spans", "mask_statement"])
def test_a_broken_render_keeps_a_hidden_shape(method: str) -> None:
    class Broken(Masker):
        def __getattribute__(self, name: str) -> object:
            if name == method:
                raise RuntimeError(method)
            return super().__getattribute__(name)

    try:
        result = sqltext.statement_shape(Broken(Exposure.MASKED, True), "SELECT 1", Dialect.SQLITE)
    except RuntimeError:
        result = sqltext.Shape("raised", None, Dialect.SQLITE, 0, 0)
    assert result.text == MASK
    assert result.fingerprint is None


def test_metadata_only_does_not_scan(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(_sql: str, _dialect: Dialect) -> None:
        raise AssertionError("scan must not run")

    monkeypatch.setattr(sqltext.LEXER, "scan", broken)
    assert statement_text(Masker(Exposure.METADATA_ONLY, True), "SELECT 'secret'", Dialect.SQLITE) is None


def test_a_token_is_hidden_with_secrets_off() -> None:
    masker = Masker(Exposure.MASKED, False, token="sharpit-token-value")
    assert statement_text(masker, "SELECT sharpit-token-value FROM t", Dialect.UNSUPPORTED) == f"SELECT {MASK} FROM t"


def test_capture_on_shows_the_masked_statement() -> None:
    masker = Masker(Exposure.MASKED, True, capture_parameters=True)
    assert _sql_attribute(masker, "db.statement", "SELECT 'x'", Dialect.UNSUPPORTED) == "SELECT 'x'"


@pytest.mark.parametrize(
    "sql",
    ["SELECT x=password=abc FROM t", "UPDATE t SET x=password=abc WHERE id=1", "SELECT a:password=abc FROM t"],
)
def test_a_key_nested_in_a_bare_value_reads_as_code(sql: str) -> None:
    # ``x = password = abc`` is valid SQL over three columns, and 0.4.0 shows the same: no value is in it
    assert "abc" in (statement_text(MASKER, sql, Dialect.UNSUPPORTED) or "")


def test_a_shape_and_its_text_come_from_one_scan(monkeypatch: pytest.MonkeyPatch) -> None:
    # derived: 2026-11-05 design, "classified once and emitted once": the miss budget pays for one read of raw text
    calls: list[str] = []
    real = sqltext.LEXER.scan

    def counted(sql: str, dialect: Dialect) -> object:
        calls.append(sql)
        return real(sql, dialect)

    monkeypatch.setattr(sqltext.LEXER, "scan", counted)
    sql = "SELECT * FROM one_scan WHERE id = 7"
    assert masked_shape(MASKER, sql, Dialect.UNSUPPORTED).sql == "SELECT * FROM one_scan WHERE id = ?"
    assert calls == [sql]
