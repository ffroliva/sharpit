"""Runtime SQL rule DB-RUNTIME-001 (port of BootUI ``SqlLiteralConcatenationRule``, 2.2.0) over the SQL Trace ring.

``facts(rows)`` reads ``SqlTraceRecorder.rows()`` once and keeps only counts and digests: per normalized shape with
predicate literals, how many executions and how many distinct raw texts (``IN (?, ?)`` lists folded). No SQL text and no
literal value leaves it. The raw text is in a row only when SQL Trace captures parameters; otherwise the row holds the
normalized text, variations cannot be observed and the rule is ``SKIPPED``.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from typing import Any

from sharpit.engine.advisors.rules import RuleDefinition
from sharpit.engine.collectors.database_advisor.catalog import Outcome, Rule, Source
from sharpit.engine.sqltext import UNSUPPORTED_STATEMENT

MIN_VARIANTS = 2
MAX_TRACKED_VARIANTS = 64
MAX_TRACKED_SHAPES = 500
NOT_READ = "The SQL Trace window was not read for this datasource."
NOTHING_CAPTURED = (
    "No statements have been captured by SQL Trace, so runtime SQL could not be inspected. Enable SQL Trace and "
    "exercise the application, then run the checks again."
)
NORMALIZED_ONLY = (
    "SQL Trace keeps only normalized SQL text (parameter capture is off), so text variations with predicate "
    "literals cannot be observed."
)
_PLACEHOLDER = r"(?:\?|%s|\$\d+|:\w+|%\(\w+\)s)"
_PLACEHOLDER_LIST = re.compile(rf"\(\s*{_PLACEHOLDER}(?:\s*,\s*{_PLACEHOLDER})+\s*\)")


def _digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _count(shapes: dict[str, tuple[list[int], set[str]]], fingerprint: str, sql: str) -> None:
    """One execution of ``fingerprint``, and its text as a variant, while the bounds leave room."""
    if fingerprint not in shapes and len(shapes) >= MAX_TRACKED_SHAPES:
        return
    executions, texts = shapes.setdefault(fingerprint, ([0], set()))
    executions[0] += 1
    if len(texts) < MAX_TRACKED_VARIANTS:
        texts.add(_digest(_PLACEHOLDER_LIST.sub("(?)", sql)))


def facts(rows: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Counts per shape over the retained window, or ``{"skipped": reason}``."""
    if not rows:
        return {"skipped": NOTHING_CAPTURED}
    shapes: dict[str, tuple[list[int], set[str]]] = {}
    hidden = 0
    for row in rows:
        shape, sql = row.get("shape"), row.get("sql")
        if shape is not None and sql == UNSUPPORTED_STATEMENT:  # hidden whole: its literals were never read
            hidden += 1
            continue
        if shape is None or not sql or shape.predicate_literal_count == 0:
            continue
        if shape.fingerprint is None:
            continue
        if sql == shape.text:  # the literals were dropped at capture time
            hidden += 1
            continue
        _count(shapes, shape.fingerprint, sql)
    if hidden and not shapes:
        return {"skipped": NORMALIZED_ONLY}
    found = [
        {"key": _digest(fingerprint)[:32], "executions": executions[0], "variants": len(texts)}
        for fingerprint, (executions, texts) in shapes.items()
        if len(texts) >= MIN_VARIANTS
    ]
    found.sort(key=lambda s: (-int(s["variants"]), str(s["key"])))
    return {"statements": len(rows), "shapes": found}


def _variations(source: Source) -> Outcome:
    window = source.catalog.get("runtime")
    if window is None:
        return NOT_READ
    if "skipped" in window:
        return window["skipped"]
    retained = window["statements"]
    return [
        (
            f"sql-trace/shape {s['key']}",
            f"Shape {s['key']}: {s['executions']} {'execution' if s['executions'] == 1 else 'executions'}, "
            f"{s['variants']}{'+' if s['variants'] >= MAX_TRACKED_VARIANTS else ''} distinct texts containing "
            f"predicate literals. Retained window: {retained} statements.",
            f"shape={s['key']}",
        )
        for s in window["shapes"]
    ]


RULES = (
    Rule(
        RuleDefinition(
            "DB-RUNTIME-001",
            "SQL text variations with predicate literals",
            "Runtime SQL",
            "LOW",
            "Observes distinct retained SQL texts sharing a normalized shape and containing predicate literals. Text "
            "differences may be in projections, comments or whitespace; this does not identify which part changed or "
            "why. Examines at most 500 eligible shapes in the retained SQL Trace window and counts at most 64 distinct "
            "texts per shape. No SQL text is displayed; the shape id is opaque.",
            "Review the existing SQL Trace evidence and its capture window to understand these text variations. "
            "Framework-generated constants and formatting differences can explain this observation; it does not "
            "establish a defect or prescribe a query change.",
            "https://docs.sqlalchemy.org/en/20/core/tutorial.html#using-textual-sql",
        ),
        _variations,
    ),
)
