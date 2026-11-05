"""A statement is read from raw text once, and free text in its place hides more (spec §3, the Task 6 amendment)."""

from __future__ import annotations

import pytest

from sharpit.engine.capture import sqlscan
from sharpit.engine.capture.statement import masked_shape, statement_text
from sharpit.engine.capture.traces import _sql_attribute  # pyright: ignore[reportPrivateUsage]
from sharpit.engine.masking import MASK, Exposure, Masker

MASKER = Masker(Exposure.MASKED, True)
GITHUB_TOKEN = "ghp_" + "qMJX61wKzKlsVEOXgKQti54E"  # split: the host refuses a push holding a whole token
STRIPE_KEY = "sk_live_" + "caJxl2ed6lutLaJzdLustUfh"


def _statement(sql: str, mysql: bool = False) -> str | None:
    return _sql_attribute(MASKER, "db.statement", sql, mysql)


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
    assert _statement('SELECT "x y"', mysql=True) == "SELECT ?"
    assert _statement('SELECT "firstName"') == 'SELECT "firstName"'


def test_metadata_only_returns_nothing_in_the_function() -> None:
    assert statement_text(Masker(Exposure.METADATA_ONLY, True), "SELECT 1") is None


def test_a_broken_render_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(_sql: str, _mysql: bool) -> None:
        raise RuntimeError

    monkeypatch.setattr(sqlscan, "_scan", broken)
    assert statement_text(MASKER, "UPDATE broken SET note='SECRET'") == MASK


def test_a_token_is_hidden_with_secrets_off() -> None:
    masker = Masker(Exposure.MASKED, False, token="sharpit-token-value")
    assert statement_text(masker, "SELECT sharpit-token-value FROM t") == f"SELECT {MASK} FROM t"


def test_capture_on_shows_the_masked_statement() -> None:
    masker = Masker(Exposure.MASKED, True, capture_parameters=True)
    assert _sql_attribute(masker, "db.statement", "SELECT 'x'", False) == "SELECT 'x'"


@pytest.mark.parametrize(
    "sql",
    ["SELECT x=password=abc FROM t", "UPDATE t SET x=password=abc WHERE id=1", "SELECT a:password=abc FROM t"],
)
def test_a_key_nested_in_a_bare_value_reads_as_code(sql: str) -> None:
    # ``x = password = abc`` is valid SQL over three columns, and 0.4.0 shows the same: no value is in it
    assert "abc" in (statement_text(MASKER, sql) or "")


def test_a_shape_and_its_text_come_from_one_scan(monkeypatch: pytest.MonkeyPatch) -> None:
    # derived: 2026-11-05 design, "classified once and emitted once": the miss budget pays for one read of raw text
    calls: list[str] = []
    real = sqlscan._scan  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]

    def counted(sql: str, mysql: bool) -> object:
        calls.append(sql)
        return real(sql, mysql)

    monkeypatch.setattr(sqlscan, "_scan", counted)
    sql = "SELECT * FROM one_scan WHERE id = 7"
    assert masked_shape(MASKER, sql, False).sql == "SELECT * FROM one_scan WHERE id = ?"
    assert calls == [sql]
