"""SQL Trace rows are byte-identical on every reader before and after deferring the row dict (perf lane B, 2026-11-12).

The golden file was written by this module's ``main`` run against the untouched base (``origin/release/0.6.0`` at
``cc72bf4a``) in a temp worktree; the recorder change must not move one byte. Readers: ``rows()``, the panel report,
``get_sql_traces`` over MCP and CLI, Live Activity and the request profile, SQL insights, the SQLAlchemy statistics,
the database advisor's runtime facts, the transactions report and the change stream. Three exposures, parameter
capture on and off, an error row and eviction. Secret-shaped values are built at load; a FULL output's fragment
is written as ``<CANARY:length>``.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

import pytest

from sharpit.engine import sqla
from sharpit.engine.activation import ActivationStatus
from sharpit.engine.capture import activity, sqlinsights, transactions
from sharpit.engine.capture.exchanges import HttpExchangeBuffer, exchange_row
from sharpit.engine.capture.sqltrace import SqlTraceRecorder
from sharpit.engine.collectors import sqlastats
from sharpit.engine.collectors.database_advisor import rules_runtime
from sharpit.engine.context import SharpitContext
from sharpit.engine.spi import AppInfo, ProviderInfo, RouteInfo
from sharpit.engine.sqltext import Dialect
from sharpit.engine.tool_dispatch import call_tool
from sharpit.engine.tools import CallContext
from sharpit.settings import load_settings

GOLDEN = Path(__file__).resolve().parents[2] / "fixtures" / "sqltrace_rows_golden.json"
CANARY = "eyJ" + "hbGciOiJIUzI1NiJ9" + "." + "eyJzdWIiOiJnb2xkZW4ifQ" + "." + "c2lnbmF0dXJl" + "LWdvbGRlbg"
PASSWORD = "hunter" + "2-" + "golden"
ACTIVATION = ActivationStatus(True, True, "Enabled by SHARPIT_ENABLED=ON", ())
EPOCH_NS = 1_800_000_000_000_000_000
# FULL shows values, cut at the parameter length: every fragment of a planted value is written as its marker
_PLANTED = re.compile("(" + CANARY[:3] + r"[\w.-]*)|(" + PASSWORD[:6] + r"[\w-]*)")
CASES = (
    ("MASKED", False),
    ("MASKED", True),
    ("FULL", False),
    ("FULL", True),
    ("METADATA_ONLY", False),
    ("METADATA_ONLY", True),
)


class _Introspector:
    def app_info(self) -> AppInfo:
        return AppInfo("demo", "FastAPI", "0.115.0", None)

    def routes(self) -> list[RouteInfo]:
        return []

    def providers(self) -> list[ProviderInfo]:
        return []


class _Clock:
    """``time.time_ns`` one millisecond apart, so every timestamp is fixed."""

    def __init__(self) -> None:
        self.now = EPOCH_NS

    def __call__(self) -> int:
        self.now += 1_000_000
        return self.now


def _ctx(exposure: str, capture: bool) -> SharpitContext:
    options = {
        "config_scan": False,
        "expose_values": exposure,
        "sql_trace_capture_parameters": capture,
        "sql_trace_max_entries": 9,
        "sql_trace_max_sql_length": 90,
        "sql_trace_max_parameter_length": 24,
    }
    settings = load_settings(options, {})
    ctx = SharpitContext(settings, ACTIVATION, _Introspector())
    ctx.capture.exchanges = HttpExchangeBuffer(50)
    ctx.capture.sql_trace = SqlTraceRecorder(
        ctx.masker,
        max_entries=settings.sql_trace_max_entries,
        slow_query_threshold_millis=100,
        max_sql_length=settings.sql_trace_max_sql_length,
        max_parameter_length=settings.sql_trace_max_parameter_length,
        n_plus_one_threshold=3,
    )
    ctx.capture.transactions = transactions.TransactionRecorder(ctx.masker, application=lambda: Dialect.POSTGRESQL)
    return ctx


def _exchange(ctx: SharpitContext, rid: str, started: int) -> None:
    assert ctx.capture.exchanges is not None
    ctx.capture.exchanges.add(
        exchange_row(
            ctx.masker,
            request_id=rid,
            started_epoch_ns=started,
            method="GET",
            path=f"/pets/{rid}",
            query_string=b"",
            status=200,
            duration_ms=40,
            size=0,
            client=None,
            user=None,
            request_headers=[],
            response_headers=[],
            finished_epoch_ns=started + 40_000_000,
        )
    )


def _feed(recorder: SqlTraceRecorder) -> list[str | None]:
    """Every row shape the recorder stores; returns what ``record`` returned (the journal's text)."""
    base: dict[str, Any] = {"duration_ns": 2_345_678, "thread": "worker-1", "connection_id": "c1"}
    pg = Dialect.POSTGRESQL
    returned: list[str | None] = []

    def rec(sql: str, **kw: Any) -> None:
        fields: dict[str, Any] = {**base, "dialect": pg, **kw}
        returned.append(recorder.record(sql, **fields))

    rec("select * from pets where id = 1", request_id="r1", call_site="app.pets:get:12", rowcount=1)
    for n in range(3):  # an N+1 under r1
        rec(f"select * from owners where id = {n}", request_id="r1", parameters={"id": n}, rowcount=1)
    rec(
        "update users set password = %(password)s, token = %(token)s where id = %(id)s",
        parameters={"password": PASSWORD, "token": CANARY, "id": 7},
        request_id="r2",
        rowcount=1,
        duration_ns=150_000_000,
    )
    rec(
        f"select * from sessions where token = '{CANARY}' and note = 'a very long note that runs past the limit'",
        request_id="r2",
        duration_ns=210_000_000,
    )
    rec(
        "insert into pets (name, tag) values (%s, %s)",
        parameters=[("rex", CANARY), ("fido", "x" * 40), ("a", "b"), ("c", "d"), ("e", "f"), ("g", "h")],
        executemany=True,
    )
    rec("insert into pets (name) values (%s)", parameters=[("a",), ("b",)], executemany=True, batch_size=2)
    error = RuntimeError(f"duplicate key value violates unique constraint; token={CANARY} [SQL: select '{PASSWORD}']")
    rec("insert into users (token) values ('" + CANARY + "')", success=False, error=error, rowcount=3)
    recorder.lifespan_phase = "STARTUP"
    rec("create table if not exists audit (id int)", thread="MainThread", connection_id=None)
    recorder.lifespan_phase = None
    rec("vacuum", dialect=Dialect.UNSUPPORTED, parameters=("p",))
    rec("select * from pets where name = ?", dialect=Dialect.SQLITE, parameters=("rex",), call_site="app.db:q:3")
    rec("delete from pets where id = 9", request_id="r3", rowcount=0, success=False)
    return returned


def _no_reason(_ctx: SharpitContext) -> None:
    return None


def _json(value: object) -> str:
    return json.dumps(value, default=repr, ensure_ascii=False)  # key order too: a JSON body keeps the dict order


def _case(exposure: str, capture: bool, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    clock = _Clock()
    monkeypatch.setattr("time.time_ns", clock)
    monkeypatch.setattr(sqla, "unavailable_reason", lambda: None)
    monkeypatch.setattr(sqla, "sql_trace_unavailable_reason", _no_reason)
    ctx = _ctx(exposure, capture)
    recorder = ctx.capture.sql_trace
    assert recorder is not None
    signals: list[int] = []
    recorder.changes.forward_to(_Counter(signals))  # type: ignore[arg-type]  # duck-typed: only ``signal`` is called
    for n, rid in enumerate(("r1", "r2", "r3")):
        _exchange(ctx, rid, EPOCH_NS + n * 1_000_000)
    returned = _feed(recorder)
    call = CallContext(ctx, {})
    out = {
        "returned": returned,
        "rows": recorder.rows(),
        "report": recorder.report(["db"]),
        "mcp": call_tool(call, "get_sql_traces", {}, via="mcp"),
        "cli": call_tool(call, "get_sql_traces", {"query": "pets", "limit": 3}, via="cli"),
        "activity": activity.activity_report(ctx, None, None, None, None, None),
        "profile": activity.request_profile(ctx, "r2"),
        "insights": sqlinsights.insights_report(recorder, ctx.capture.exchanges, None),
        "statistics": sqlastats.statistics_report(ctx),
        "advisor": rules_runtime.facts(recorder.rows()),
        "transactions": transactions.context_report(ctx),
        "totals": recorder.totals(),
        "signals": len(signals),
    }
    text = _json(out)
    if exposure != "FULL":
        assert _PLANTED.search(text) is None, f"{exposure}: a planted value reached an output"
    return json.loads(_PLANTED.sub(_marker, text))


def _marker(match: re.Match[str]) -> str:
    """The fragment's kind and length, never its text: a longer or shorter cut still differs from base."""
    planted = CANARY if match.group(1) else PASSWORD
    assert planted.startswith(match.group(0)), "a FULL output shows a prefix of the planted value, nothing else"
    return f"<{'CANARY' if match.group(1) else 'PASSWORD'}:{len(match.group(0))}>"


class _Counter:
    def __init__(self, sink: list[int]) -> None:
        self._sink = sink

    def signal(self) -> None:
        self._sink.append(1)


def _all(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    return {
        f"{exposure}/{'capture' if capture else 'plain'}": _case(exposure, capture, monkeypatch)
        for exposure, capture in CASES
    }


def test_every_reader_is_byte_identical_to_base(monkeypatch: pytest.MonkeyPatch):
    expected = json.loads(GOLDEN.read_text(encoding="utf-8"))
    actual = _all(monkeypatch)
    assert sorted(actual) == sorted(expected)
    for case, surfaces in expected.items():
        for surface, value in surfaces.items():
            assert _json(actual[case][surface]) == _json(value), f"{case} {surface} differs from base"


def main(path: str) -> None:
    """Write the golden: run with the base's ``sharpit`` first on ``sys.path``."""
    with pytest.MonkeyPatch.context() as monkeypatch:
        Path(path).write_text(json.dumps(_all(monkeypatch), indent=1, ensure_ascii=False) + "\n", "utf-8")


if __name__ == "__main__":
    main(sys.argv[1])
