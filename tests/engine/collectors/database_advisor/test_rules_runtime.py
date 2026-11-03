"""DB-RUNTIME-001 over a seeded SQL Trace window (plan A-dbadv-2 Task 2)."""

from __future__ import annotations

from typing import Any

from sharpit.engine.capture.sqltrace import normalize
from sharpit.engine.collectors.database_advisor import rules_runtime
from sharpit.engine.collectors.database_advisor.catalog import Outcome, Source


def _raw(*statements: str) -> list[dict[str, Any]]:
    """Ring rows as SqlTraceRecorder keeps them when parameters are captured: the raw text and its shape."""
    return [{"sql": sql, "shape": normalize(sql)} for sql in statements]


def _normalized(*statements: str) -> list[dict[str, Any]]:
    """Ring rows as SqlTraceRecorder keeps them by default: the literals already replaced."""
    return [{"sql": normalize(sql).sql, "shape": normalize(sql)} for sql in statements]


def _check(rows: list[dict[str, Any]] | None) -> Outcome:
    catalog: dict[str, Any] = {"tables": []}
    if rows is not None:
        catalog["runtime"] = rules_runtime.facts(rows)
    source = Source("db", "sqlite", "pysqlite", "AVAILABLE", None, catalog)
    return rules_runtime.RULES[0].check(source)


def test_runtime_001_reports_a_shape_with_text_variations() -> None:
    # ported: DatabaseAdvisorRuntimeRulesTests (distinct texts of one shape with predicate literals are one finding)
    outcome = _check(
        _raw("SELECT * FROM t WHERE id = 1", "SELECT * FROM t WHERE id = 2", "SELECT * FROM t WHERE id = 2")
    )

    assert isinstance(outcome, list)
    assert len(outcome) == 1
    assert "3 executions, 2 distinct texts" in outcome[0][1]


def test_runtime_001_never_emits_sql_text_or_literals() -> None:
    outcome = _check(_raw("SELECT * FROM u WHERE token = 's3cr3t-a'", "SELECT * FROM u WHERE token = 's3cr3t-b'"))

    assert isinstance(outcome, list)
    assert len(outcome) == 1
    assert all("s3cr3t" not in part and "token" not in part for part in outcome[0])


def test_runtime_001_placeholder_list_lengths_count_once() -> None:
    outcome = _check(
        _raw(
            "SELECT * FROM t WHERE kind = 'a' AND id IN (?, ?)", "SELECT * FROM t WHERE kind = 'a' AND id IN (?, ?, ?)"
        )
    )

    assert outcome == []


def test_runtime_001_one_text_is_not_a_variation() -> None:
    outcome = _check(_raw("SELECT * FROM t WHERE id = 1", "SELECT * FROM t WHERE id = 1"))

    assert outcome == []


def test_runtime_001_skips_an_empty_window() -> None:
    assert isinstance(_check([]), str)


def test_runtime_001_skips_when_only_normalized_text_is_kept() -> None:
    outcome = _check(_normalized("SELECT * FROM t WHERE id = 1", "SELECT * FROM t WHERE id = 2"))

    assert isinstance(outcome, str)
    assert "parameter capture" in outcome


def test_runtime_001_skips_when_the_window_was_not_read() -> None:
    assert isinstance(_check(None), str)
