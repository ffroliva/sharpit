"""The server corpus keeps every row (2026-11-05 design section 8, Task 6).

# derived: data tests, new in the architecture plan. The rows come from spike 2's inputs, arch/r2's stored MySQL-family
readings and SQLite run in process. PostgreSQL readings were never kept per statement, so only its 128 real-leak
statements are here. Set ``SHARPIT_SERVER_CORPUS`` to read the file from outside the tree.
"""

from __future__ import annotations

import gzip
from collections import Counter

import pytest
from tests.masking import server_corpus

REAL_LEAK = {"mysql": 540, "postgresql": 128, "sqlite": 2308}
READING = {"maria": 7281, "my80": 5260, "my84": 5874, "sqlite": 2828}
SERVERS = {"mysql", "postgresql", "sqlite", "maria", "my80", "my84"}


def test_the_corpus_counts_each_server() -> None:
    real = Counter(r.server for r in server_corpus.rows("real_leak"))
    assert dict(real) == REAL_LEAK
    reading = Counter(r.server for r in server_corpus.rows("reading"))
    assert dict(reading) == READING


def test_the_real_leaks_hold_1501_statements_and_1475_d6_rows() -> None:
    real = server_corpus.rows("real_leak")
    assert sum(not r.d6 for r in real) == 1501
    assert sum(r.d6 for r in real) == 1475


def test_postgresql_has_statements_but_no_readings() -> None:
    """Spike 2 kept PostgreSQL counts only: this corpus cannot prove what PostgreSQL returned, the live job must."""
    assert "postgresql" in {r.server for r in server_corpus.rows("real_leak")}
    assert "postgresql" not in {r.server for r in server_corpus.rows("reading")}


def test_every_row_names_its_server_and_session() -> None:
    every = server_corpus.rows("real_leak") + server_corpus.rows("reading")
    assert {r.server for r in every} == SERVERS
    assert all(isinstance(r.session, str) for r in every)
    assert all(r.text and r.marker for r in every)


def test_a_session_setting_comes_with_a_server_that_has_one() -> None:
    sessions = {(r.server, r.session) for r in server_corpus.rows("reading")}
    assert ("sqlite", "") in sessions
    assert ("maria", "ORACLE") in sessions
    assert ("my84", "NO_BACKSLASH_ESCAPES") in sessions


def test_every_row_decompresses_once(monkeypatch: pytest.MonkeyPatch) -> None:
    server_corpus._load.cache_clear()
    opened: list[object] = []
    real_open = gzip.open

    def counting(*a: object, **k: object):
        opened.append(a[0])
        return real_open(*a, **k)  # type: ignore[arg-type]

    monkeypatch.setattr(gzip, "open", counting)
    server_corpus.rows("reading")
    server_corpus.rows("real_leak")
    server_corpus.rows("reading")
    assert len(opened) == 1


def test_an_unknown_kind_is_refused() -> None:
    with pytest.raises(ValueError, match="kind must be one of"):
        server_corpus.rows("everything")
