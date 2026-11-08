"""An ``UNSUPPORTED`` statement has no identity: not grouped, never an N+1 finding, a baseline or a dismissal.

Owner's default, 2026-11-05 (architecture spec section 5). Every consumer of the recorder's fingerprint is read with
two runs of one hidden statement: one group would be every hidden statement of the application folded together.
"""

# derived: architecture spec section 5, identity; no BootUI source (BootUI groups every statement it shows)

from __future__ import annotations

from typing import Any

import pytest

from sharpit.engine import sqltext
from sharpit.engine.capture.activity import _groups  # pyright: ignore[reportPrivateUsage]
from sharpit.engine.capture.sqlinsights import _add  # pyright: ignore[reportPrivateUsage]
from sharpit.engine.capture.sqltrace import SqlTraceRecorder
from sharpit.engine.collectors.database_advisor.rules_runtime import NORMALIZED_ONLY, facts
from sharpit.engine.collectors.sqlastats import _select_counts  # pyright: ignore[reportPrivateUsage]
from sharpit.engine.masking import Exposure, Masker
from sharpit.engine.sources.dispatch import SqlEvent
from sharpit.engine.sqltext import Dialect
from sharpit.engine.testsession.sink import TestSessionSink

STATEMENT = "SELECT TOP 1 * FROM t WHERE id = 7"
OTHER = "SELECT TOP 1 * FROM u WHERE id = 8"
MASKED = Masker(Exposure.MASKED, True)
CAPTURE = Masker(Exposure.MASKED, True, capture_parameters=True)


def _rows(masker: Masker = MASKED, request_id: str | None = "r1") -> list[dict[str, Any]]:
    recorder = SqlTraceRecorder(masker, max_sql_length=10_000)
    for statement in (STATEMENT, STATEMENT, OTHER):
        recorder.record(
            statement, duration_ns=1, thread="t", connection_id=None, dialect=Dialect.UNSUPPORTED, request_id=request_id
        )
    return recorder.rows()


def _recorder() -> SqlTraceRecorder:
    recorder = SqlTraceRecorder(MASKED, max_sql_length=10_000)
    recorder.record(STATEMENT, duration_ns=1, thread="t", connection_id=None, dialect=Dialect.UNSUPPORTED)
    return recorder


def test_the_aggregates_hold_no_hidden_statement() -> None:
    assert _recorder().aggregate_count == 0


def test_insights_group_no_hidden_statement() -> None:
    groups: dict[str, Any] = {}
    for row in _rows():
        _add(groups, row)
    assert groups == {}


def test_activity_groups_no_hidden_statement() -> None:
    assert _groups(_rows(), 2) == []


def test_sqlastats_counts_no_hidden_statement() -> None:
    assert _select_counts(_rows()) == ({}, {})


def _sink() -> TestSessionSink:
    sink = TestSessionSink("gw0", MASKED)
    for statement in (STATEMENT, STATEMENT, OTHER):
        sink.on_sql(
            SqlEvent("sqlalchemy", statement, None, False, None, 0, 1, -1, None, None, None, Dialect.UNSUPPORTED), None
        )
    return sink


def test_the_test_session_lists_no_hidden_statement() -> None:
    """The N+1, baseline and dismissal keys all come from the sink's fingerprint."""
    assert list(_sink().facts.top_unattributed) == []


def test_the_test_session_still_counts_the_statements() -> None:
    assert _sink().facts.unattributed == 3


def test_the_orm_groups_no_hidden_statement() -> None:
    pytest.importorskip("sqlalchemy")
    from sharpit.engine.sqla.orm import _masked_fingerprint  # pyright: ignore[reportPrivateUsage]

    assert _masked_fingerprint(STATEMENT, Dialect.UNSUPPORTED) is None


def test_a_literal_count_on_a_hidden_row_counts_it_hidden() -> None:
    """``rules_runtime.py:46`` reads ``sql == shape.text``: a hidden row is one whose literals are gone (predict F6)."""
    assert facts(_rows(CAPTURE)) == {"skipped": NORMALIZED_ONLY}


TAILS = {
    "bearer": ("Authorization: Bearer abc'x'def.ghi.jkl", "def.ghi.jkl"),
    "userinfo": ("postgres://user:pw'x'd@host/db", "pw"),
    "redis_token": ("HSET session:1 token abc123", "abc123"),
}


@pytest.mark.parametrize("dialect", [Dialect.POSTGRESQL, Dialect.MYSQL_FAMILY, Dialect.SQLITE], ids=lambda d: d.name)
@pytest.mark.parametrize(("text", "tail"), TAILS.values(), ids=TAILS)
def test_the_strict_last_pass_keeps_the_tail_hidden(dialect: Dialect, text: str, tail: str) -> None:
    """Council finding 5: with the verb route gone, text on a statement surface is a statement, and its tail stays
    hidden on a known dialect."""
    assert tail not in (sqltext.statement_text(MASKED, text, dialect) or "")


@pytest.mark.parametrize("dialect", [Dialect.POSTGRESQL, Dialect.MYSQL_FAMILY, Dialect.SQLITE], ids=lambda d: d.name)
@pytest.mark.parametrize(("text", "tail"), TAILS.values(), ids=TAILS)
def test_a_statement_on_a_known_dialect_is_not_blanked(dialect: Dialect, text: str, tail: str) -> None:
    """The surface says: a statement keeps its words, as a verb-led one did at CP6 (owner's condition on item 5)."""
    del tail
    assert sqltext.statement_text(MASKED, text, dialect) != sqltext.MASK
