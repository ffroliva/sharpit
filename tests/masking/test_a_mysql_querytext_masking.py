"""PROCESSLIST text is raw (0.5.0 release council): MySQL lexing decides what a literal is, not the generic scan."""

from __future__ import annotations

import pytest

from sharpit.engine.capture import sqlscan
from sharpit.engine.capture.sqltrace import normalize_sql
from sharpit.engine.collectors.mysql.querytext import mysql_query_text
from sharpit.engine.masking import MASK, Exposure, Masker
from sharpit.engine.sqltext import Dialect

SECRET = "Hunter2Value"
HEX = "DEADBEEFCAFE"
MASKER = Masker(Exposure.MASKED, True)


@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        (f'SELECT * FROM u WHERE "{SECRET}"=pw', "SELECT * FROM u WHERE ?=pw"),
        (f'CALL login("bob","{SECRET}")', "CALL login(?,?)"),
        (f'SELECT MD5("{SECRET}")', "SELECT MD5(?)"),
        (f'UPDATE u SET pw="a\\"{SECRET}" WHERE id=1', "UPDATE u SET pw= ?"),  # D7: the readings differ, so it stops
        (f"SELECT 1 # {SECRET}\n, 2", "SELECT ? , ?"),
        (f"UPDATE u SET k=0x{HEX}", "UPDATE u SET k=?"),
        ("UPDATE u SET k=0b1011", "UPDATE u SET k=?"),
    ],
    ids=["dq-left", "dq-call", "dq-function", "dq-escaped-quote", "hash-comment", "hex", "binary"],
)
def test_a_mysql_literal_never_survives(sql: str, expected: str) -> None:
    assert mysql_query_text(MASKER, sql) == expected


@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        (f"SELECT 'C:\\\\', '{SECRET}'", "SELECT ?, ?"),
        (f"UPDATE u SET a='x\\\\', b='{SECRET}' WHERE id=1", "UPDATE u SET a=?, b=? WHERE id=?"),
        (f'INSERT INTO u(n,pw) VALUES ("a b","{SECRET}")', "INSERT INTO u(n,pw) VALUES (?,?)"),
        (f'UPDATE u SET pw="{SECRET}"', "UPDATE u SET pw=?"),
    ],
)
def test_a_literal_the_generic_scan_already_caught_stays_caught(sql: str, expected: str) -> None:
    assert mysql_query_text(MASKER, sql) == expected


def test_a_mysql_identifier_stays_readable() -> None:
    sql = "SELECT `first name` FROM `user` WHERE id = 1"
    assert mysql_query_text(MASKER, sql) == "SELECT `first name` FROM `user` WHERE id = ?"


def test_a_hash_inside_a_string_is_not_a_comment() -> None:
    assert mysql_query_text(MASKER, "SELECT '#', 1") == "SELECT ?, ?"


def test_a_digit_inside_an_identifier_is_not_a_hex_literal() -> None:
    assert mysql_query_text(MASKER, "SELECT t0x1 FROM t") == "SELECT t0x1 FROM t"


def test_mysql_query_text_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(_sql: str, _dialect: Dialect) -> None:
        raise RuntimeError

    monkeypatch.setattr(sqlscan, "_scan", broken)
    assert mysql_query_text(MASKER, f"UPDATE fails_closed SET note='{SECRET}'") == MASK


@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        ('SELECT "firstName" FROM "user"', 'SELECT "firstName" FROM "user"'),
        ("SELECT a # b", "SELECT a # b"),
        ("SELECT 0xFF", "SELECT ?"),
        ('SELECT "a\\"b', "SELECT ?"),
    ],
    ids=["identifiers", "xor-operator", "hex", "backslash"],
)
def test_the_generic_scan_keeps_its_output(sql: str, expected: str) -> None:
    assert normalize_sql(sql, Dialect.UNSUPPORTED) == expected
