"""Profile the SQLAlchemy per-statement listener path (lane S0).

Runs the workload of ``tests/fastapi/test_sql_trace_overhead.py::test_statement_overhead_budget`` with the production
listener functions attached and detached for at least 20,000 statements per side across 3 repetitions.

Usage: ``uv run python -m scripts.dev.profile_sql_listener [--statements 20000] [--runs 3]``
"""

from __future__ import annotations

import argparse
import cProfile
import pstats
import statistics
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from tests.fastapi.test_sql_trace_overhead import FULL_RING, PER_ROUND, _round
from tests.overhead import Paired, paired

from fastapi import FastAPI
from sharpit import install
from sharpit.engine import otel, sqla
from sharpit.engine.capture.correlation import INTERNAL, REQUEST, RequestInfo
from sharpit.engine.capture.journal import RuntimeJournal
from sharpit.engine.capture.sqltrace import SqlTraceRecorder, _truncate, call_site, category_of
from sharpit.engine.sources import dispatch
from sharpit.engine.sqla import dialect_source, listeners, orm
from sharpit.engine.sqltext import Dialect

STATEMENT_SQL = "select * from (select 1 as n) where n = :n"


@dataclass(frozen=True)
class FunctionRow:
    label: str
    calls: int
    tottime_us: float
    cumtime_us: float
    per_call_tot_us: float
    per_call_cum_us: float
    tot_share_pct: float
    cum_share_pct: float


def _short_file(filename: str) -> str:
    norm = filename.replace("\\", "/")
    if "src/sharpit/" in norm:
        return norm.split("src/sharpit/", 1)[1]
    if "site-packages/" in norm:
        return norm.split("site-packages/", 1)[1]
    if norm.startswith("<"):
        return norm
    return Path(norm).name


def _is_sharpit_sql_file(filename: str) -> bool:
    norm = filename.replace("\\", "/")
    return "src/sharpit/engine/" in norm


def _execute_n(conn: Any, statement: Any, count: int) -> int:
    started = time.perf_counter_ns()
    for i in range(count):
        conn.execute(statement, {"n": i})
    return time.perf_counter_ns() - started


def _run_one_paired(rounds: int, *, full_ring: bool) -> Paired:
    sqla.detach_all()
    engine = sa.create_engine("sqlite://")
    handle = install(FastAPI(), enabled="ON", show_banner=False, engines=[engine])
    statement = sa.text(STATEMENT_SQL)
    token = None
    try:
        if full_ring:
            journal = handle.context.capture.journal
            assert journal is not None
            journal.max_events = FULL_RING
            token = REQUEST.set(RequestInfo("r-full", handle.context.context_id, "GET", "/x", None, 0, None))
        with engine.connect() as conn:
            _round(conn, statement)
            sqla.remove(handle.context)

            def on() -> int:
                sqla.add(handle.context, statements=True, discovery=True)
                elapsed = _round(conn, statement)
                sqla.remove(handle.context)
                return elapsed

            def off() -> int:
                return _round(conn, statement)

            if full_ring:
                on()
            result = paired(off, on, rounds)
        recorder = handle.context.capture.sql_trace
        assert recorder is not None
        expected = (rounds + (2 if full_ring else 1)) * PER_ROUND
        assert recorder.report([])["totalCaptured"] == expected
        return result
    finally:
        if token is not None:
            REQUEST.reset(token)
        handle.uninstall_capture()
        engine.dispose()


def run_paired_overhead(statements: int, runs: int, *, full_ring: bool = False) -> list[Paired]:
    """Run uninstrumented paired alternating rounds using the production budget-test round function."""
    rounds = max(1, statements // PER_ROUND)
    return [_run_one_paired(rounds, full_ring=full_ring) for _ in range(runs)]


def _collect_cprofile_run(statements: int, swap: bool) -> tuple[pstats.Stats, pstats.Stats, int, int]:
    sqla.detach_all()
    engine = sa.create_engine("sqlite://")
    handle = install(FastAPI(), enabled="ON", show_banner=False, engines=[engine])
    statement = sa.text(STATEMENT_SQL)
    prof_on = cProfile.Profile()
    prof_off = cProfile.Profile()
    try:
        with engine.connect() as conn:
            _execute_n(conn, statement, PER_ROUND)
            sqla.remove(handle.context)

            def run_on() -> int:
                sqla.add(handle.context, statements=True, discovery=True)
                prof_on.enable()
                ns = _execute_n(conn, statement, statements)
                prof_on.disable()
                sqla.remove(handle.context)
                return ns

            def run_off() -> int:
                prof_off.enable()
                ns = _execute_n(conn, statement, statements)
                prof_off.disable()
                return ns

            if swap:
                on_ns = run_on()
                off_ns = run_off()
            else:
                off_ns = run_off()
                on_ns = run_on()

        recorder = handle.context.capture.sql_trace
        assert recorder is not None
        assert recorder.report([])["totalCaptured"] == PER_ROUND + statements
        return pstats.Stats(prof_on), pstats.Stats(prof_off), on_ns, off_ns
    finally:
        handle.uninstall_capture()
        engine.dispose()


def _extract_sharpit_rows(
    stats_on: pstats.Stats,
    statements: int,
) -> tuple[list[FunctionRow], list[FunctionRow], float]:
    raw_stats: dict[tuple[str, int, str], Any] = stats_on.stats  # type: ignore[attr-defined]
    root_cum_s = 0.0
    for (file, _line, name), (_cc, _nc, _tt, ct, _callers) in raw_stats.items():
        if _is_sharpit_sql_file(file) and name in ("before_cursor_execute", "after_cursor_execute"):
            root_cum_s += ct
    denom_us = max(root_cum_s * 1_000_000.0, 1.0)

    sharpit_rows: list[FunctionRow] = []
    callee_totals: dict[str, list[float]] = {}

    for (file, line, name), (_cc, nc, tt, ct, callers) in raw_stats.items():
        if _is_sharpit_sql_file(file):
            if nc < statements:
                continue
            label = f"{_short_file(file)}:{line}:{name}"
            tot_us = tt * 1_000_000.0
            cum_us = ct * 1_000_000.0
            sharpit_rows.append(
                FunctionRow(
                    label=label,
                    calls=nc,
                    tottime_us=tot_us,
                    cumtime_us=cum_us,
                    per_call_tot_us=tot_us / statements,
                    per_call_cum_us=cum_us / statements,
                    tot_share_pct=(tot_us / denom_us) * 100.0,
                    cum_share_pct=(cum_us / denom_us) * 100.0,
                )
            )
            continue
        for (c_file, c_line, c_name), caller_stat in callers.items():
            if not _is_sharpit_sql_file(c_file):
                continue
            c_nc, _c_cc, c_tt, c_ct = caller_stat
            if c_nc < statements:
                continue
            callee_label = f"{_short_file(file)}:{line}:{name} (from {_short_file(c_file)}:{c_line}:{c_name})"
            entry = callee_totals.setdefault(callee_label, [0.0, 0.0, 0.0])
            entry[0] += c_nc
            entry[1] += c_tt * 1_000_000.0
            entry[2] += c_ct * 1_000_000.0

    callee_rows = [
        FunctionRow(
            label=label,
            calls=int(vals[0]),
            tottime_us=vals[1],
            cumtime_us=vals[2],
            per_call_tot_us=vals[1] / statements,
            per_call_cum_us=vals[2] / statements,
            tot_share_pct=(vals[1] / denom_us) * 100.0,
            cum_share_pct=(vals[2] / denom_us) * 100.0,
        )
        for label, vals in callee_totals.items()
    ]
    sharpit_rows.sort(key=lambda r: r.tottime_us, reverse=True)
    callee_rows.sort(key=lambda r: r.cumtime_us, reverse=True)
    return sharpit_rows, callee_rows, denom_us


def _capture_sample_args(conn: Any, statement: Any) -> dict[str, Any]:
    captured: dict[str, Any] = {}

    def spy(c: Any, cursor: Any, stmt: str, params: Any, context: Any, executemany: bool) -> None:
        captured["conn"] = c
        captured["cursor"] = cursor
        captured["statement"] = stmt
        captured["parameters"] = params
        captured["context"] = context
        captured["executemany"] = executemany

    sa.event.listen(conn.engine, "after_cursor_execute", spy)
    try:
        conn.execute(statement, {"n": 1})
    finally:
        sa.event.remove(conn.engine, "after_cursor_execute", spy)
    return captured


def _time_call(iters: int, fn: Any) -> float:
    started = time.perf_counter_ns()
    for _ in range(iters):
        fn()
    return (time.perf_counter_ns() - started) / iters / 1000.0


def _time_in_execute_hook(conn: Any, statement: Any, iters: int, fn: Any) -> float:
    total_ns = 0

    def hook(_c: Any, _cur: Any, _s: str, _p: Any, _ctx: Any, _em: bool) -> None:
        nonlocal total_ns
        t0 = time.perf_counter_ns()
        fn()
        total_ns += time.perf_counter_ns() - t0

    sa.event.listen(conn.engine, "after_cursor_execute", hook)
    try:
        for i in range(iters):
            conn.execute(statement, {"n": i})
    finally:
        sa.event.remove(conn.engine, "after_cursor_execute", hook)
    return total_ns / iters / 1000.0


def _time_noop_sqla_dispatch(conn: Any, statement: Any, iters: int) -> float:
    rounds = max(1, iters // PER_ROUND)

    def noop_before(_c: Any, _cur: Any, _s: str, _p: Any, _ctx: Any, _em: bool) -> None:
        return None

    def noop_after(_c: Any, _cur: Any, _s: str, _p: Any, _ctx: Any, _em: bool) -> None:
        return None

    def on() -> int:
        sa.event.listen(sa.engine.Engine, "before_cursor_execute", noop_before)
        sa.event.listen(sa.engine.Engine, "after_cursor_execute", noop_after)
        elapsed = _round(conn, statement)
        sa.event.remove(sa.engine.Engine, "before_cursor_execute", noop_before)
        sa.event.remove(sa.engine.Engine, "after_cursor_execute", noop_after)
        return elapsed

    def off() -> int:
        return _round(conn, statement)

    return paired(off, on, rounds).overhead / 1000.0


def run_component_timings(statements: int) -> list[tuple[str, float]]:
    """Measure production functions directly with perf_counter_ns over ``statements`` iterations."""
    sqla.detach_all()
    engine = sa.create_engine("sqlite://")
    handle = install(FastAPI(), enabled="ON", show_banner=False, engines=[engine])
    stmt_obj = sa.text(STATEMENT_SQL)
    try:
        with engine.connect() as conn:
            _execute_n(conn, stmt_obj, PER_ROUND)
            sqla.remove(handle.context)
            noop_dispatch_us = _time_noop_sqla_dispatch(conn, stmt_obj, statements)
            real_depth_call_site_us = _time_in_execute_hook(conn, stmt_obj, statements, lambda: call_site(None))

            sqla.add(handle.context, statements=True, discovery=True)
            sample = _capture_sample_args(conn, stmt_obj)
            c_conn = sample["conn"]
            cursor = sample["cursor"]
            sql_str: str = sample["statement"]
            params = sample["parameters"]
            exec_ctx = sample["context"]
            ctx = handle.context
            recorder = ctx.capture.sql_trace
            journal = ctx.capture.journal
            assert isinstance(recorder, SqlTraceRecorder)
            assert isinstance(journal, RuntimeJournal)

            targets = dispatch.recording(c_conn.engine)
            named_params, rows = listeners._named(params, exec_ctx, False)  # noqa: SLF001
            conn_id = hex(id(c_conn.connection.dbapi_connection))
            dialect = dialect_source.engine_dialect(c_conn) or Dialect.UNSUPPORTED
            sql_event = dispatch.SqlEvent(
                "sqlalchemy", sql_str, named_params, False, rows, 1000, 5000, -1, None, conn_id, c_conn.engine, dialect
            )
            site = call_site(None)
            thread_name = threading.current_thread().name
            shape = recorder._shape(sql_str, dialect)  # noqa: SLF001
            text = _truncate(shape.text, recorder._max_sql_length)  # noqa: SLF001
            j_record, j_size, j_started = dispatch._journal_event(  # noqa: SLF001
                ctx, recorder, sql_event, text, None, thread_name, site
            )

            return [
                ("SQLAlchemy Engine event-dispatch floor (no-op listeners)", noop_dispatch_us),
                (
                    "listeners.before_cursor_execute (total)",
                    _time_call(
                        statements,
                        lambda: listeners.before_cursor_execute(c_conn, cursor, sql_str, params, exec_ctx, False),
                    ),
                ),
                ("  INTERNAL.get()", _time_call(statements, INTERNAL.get)),
                (
                    "  orm._record_relationship(context)",
                    _time_call(statements, lambda: orm._record_relationship(exec_ctx)),  # noqa: SLF001
                ),
                (
                    "  dispatch.recording(conn.engine)",
                    _time_call(statements, lambda: dispatch.recording(c_conn.engine)),
                ),
                (
                    "    dispatch._targets(conn.engine)",
                    _time_call(statements, lambda: dispatch._targets(c_conn.engine)),  # noqa: SLF001
                ),
                (
                    "    EngineRegistry.holds(conn.engine)",
                    _time_call(
                        statements,
                        lambda: ctx.capture.engine_registry.holds(c_conn.engine),  # type: ignore[union-attr]
                    ),
                ),
                (
                    "listeners.after_cursor_execute (direct call depth=1)",
                    _time_call(
                        statements,
                        lambda: (
                            setattr(exec_ctx, "_sharpit_start", (1000, targets)),
                            listeners.after_cursor_execute(c_conn, cursor, sql_str, params, exec_ctx, False),
                        ),
                    ),
                ),
                (
                    "  listeners._pop_start(conn, context)",
                    _time_call(
                        statements,
                        lambda: (
                            setattr(exec_ctx, "_sharpit_start", (1000, targets)),
                            listeners._pop_start(c_conn, exec_ctx),  # noqa: SLF001
                        ),
                    ),
                ),
                (
                    "  listeners._named(parameters, context, False)",
                    _time_call(statements, lambda: listeners._named(params, exec_ctx, False)),  # noqa: SLF001
                ),
                (
                    "  hex(id(conn.connection.dbapi_connection))",
                    _time_call(statements, lambda: hex(id(c_conn.connection.dbapi_connection))),
                ),
                (
                    "  dialect_source.engine_dialect(conn)",
                    _time_call(statements, lambda: dialect_source.engine_dialect(c_conn)),
                ),
                (
                    "  dispatch.SqlEvent(...)",
                    _time_call(
                        statements,
                        lambda: dispatch.SqlEvent(
                            "sqlalchemy",
                            sql_str,
                            named_params,
                            False,
                            rows,
                            1000,
                            5000,
                            -1,
                            None,
                            conn_id,
                            c_conn.engine,
                            dialect,
                        ),
                    ),
                ),
                ("  sqltrace.call_site(None) [at real execute depth=10]", real_depth_call_site_us),
                (
                    "  sqltrace.call_site(None) [at direct loop depth=1]",
                    _time_call(statements, lambda: call_site(None)),
                ),
                ("  threading.current_thread().name", _time_call(statements, lambda: threading.current_thread().name)),
                (
                    "  dialect_source.event_dialect(event, ...)",
                    _time_call(
                        statements,
                        lambda: dialect_source.event_dialect(sql_event, lambda: Dialect.SQLITE),
                    ),
                ),
                (
                    "  SqlTraceRecorder.record(...)",
                    _time_call(
                        statements,
                        lambda: recorder.record(
                            sql_str,
                            duration_ns=5000,
                            thread=thread_name,
                            connection_id=conn_id,
                            dialect=dialect,
                            parameters=named_params,
                            executemany=False,
                            success=True,
                            error=None,
                            rowcount=-1,
                            request_id=None,
                            call_site=site,
                            batch_size=rows,
                        ),
                    ),
                ),
                (
                    "    recorder._shape(sql, dialect) [lru_cache hit]",
                    _time_call(statements, lambda: recorder._shape(sql_str, dialect)),  # noqa: SLF001
                ),
                (
                    "    _truncate(shape.text, max_sql_length)",
                    _time_call(statements, lambda: _truncate(shape.text, recorder._max_sql_length)),  # noqa: SLF001
                ),
                ("    category_of(sql) [lru_cache hit]", _time_call(statements, lambda: category_of(sql_str))),
                ("    time.time_ns()", _time_call(statements, time.time_ns)),
                (
                    "  dispatch._journal_event(...)",
                    _time_call(
                        statements,
                        lambda: dispatch._journal_event(  # noqa: SLF001
                            ctx, recorder, sql_event, text, None, thread_name, site
                        ),
                    ),
                ),
                ("    otel.current_trace_id()", _time_call(statements, otel.current_trace_id)),
                (
                    "  RuntimeJournal.offer_flat(record, size, started)",
                    _time_call(statements, lambda: journal.offer_flat(j_record, j_size, j_started)),
                ),
            ]
    finally:
        handle.uninstall_capture()
        engine.dispose()


def _print_paired(title: str, results: list[Paired]) -> None:
    print(f"=== {title} ===")
    overheads = [r.overhead / 1000.0 for r in results]
    noises = [r.noise / 1000.0 for r in results]
    for idx, res in enumerate(results, 1):
        print(f"  Run {idx}: {res.report('µs', 1000.0)}")
    print(
        f"  Median overhead: {statistics.median(overheads):.3f} µs "
        f"(min {min(overheads):.3f}, max {max(overheads):.3f}); "
        f"median split-half noise: {statistics.median(noises):.3f} µs\n"
    )


def _print_cprofile_run(
    run_idx: int,
    statements: int,
    on_ns: int,
    off_ns: int,
    sharpit_rows: list[FunctionRow],
    callee_rows: list[FunctionRow],
    listener_cum_us: float,
) -> None:
    diff_per_stmt_us = (on_ns - off_ns) / statements / 1000.0
    print(
        f"=== cProfile Run {run_idx} ({statements} statements/side): "
        f"on={on_ns / statements / 1000.0:.2f} µs/stmt, off={off_ns / statements / 1000.0:.2f} µs/stmt, "
        f"on-off={diff_per_stmt_us:.2f} µs/stmt, listener cumtime={listener_cum_us / statements:.2f} µs/stmt ==="
    )
    header = (
        f"{'Function (sharpit)':<64} {'Calls':>8} {'Tot µs':>10} "
        f"{'Tot/stmt':>10} {'Cum/stmt':>10} {'Tot %':>7} {'Cum %':>7}"
    )
    print(header)
    for row in sharpit_rows:
        print(
            f"{row.label:<64} {row.calls:>8} {row.tottime_us:>10.1f} "
            f"{row.per_call_tot_us:>9.3f}µs {row.per_call_cum_us:>9.3f}µs "
            f"{row.tot_share_pct:>6.1f}% {row.cum_share_pct:>6.1f}%"
        )
    print("\nTop 10 sharpit functions by self-time share (tottime % of listener cumtime):")
    for rank, row in enumerate(sharpit_rows[:10], 1):
        print(
            f"  {rank:>2}. {row.label:<60} {row.per_call_tot_us:>7.3f} µs/stmt "
            f"({row.tot_share_pct:>5.1f}% self, {row.cum_share_pct:>5.1f}% cum)"
        )
    print("\nTop 15 direct non-sharpit callees invoked by sharpit listener functions:")
    for rank, row in enumerate(callee_rows[:15], 1):
        print(
            f"  {rank:>2}. {row.label:<78} {row.calls:>7} calls "
            f"{row.per_call_cum_us:>7.3f} µs/stmt ({row.cum_share_pct:>5.1f}%)"
        )
    print()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--statements", type=int, default=20_000, help="statements per side (default: 20000)")
    parser.add_argument("--runs", type=int, default=3, help="number of repetitions (default: 3)")
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure") and (sys.stdout.encoding or "").lower() not in ("utf-8", "utf8"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]

    _print_paired(
        f"Paired uninstrumented overhead ({args.statements} statements/side, {args.runs} runs)",
        run_paired_overhead(args.statements, args.runs, full_ring=False),
    )
    _print_paired(
        f"Paired uninstrumented overhead, full journal ring ({args.statements} statements/side, {args.runs} runs)",
        run_paired_overhead(args.statements, args.runs, full_ring=True),
    )

    for run_idx in range(1, args.runs + 1):
        stats_on, _stats_off, on_ns, off_ns = _collect_cprofile_run(args.statements, swap=(run_idx % 2 == 0))
        sharpit_rows, callee_rows, listener_cum_us = _extract_sharpit_rows(stats_on, args.statements)
        _print_cprofile_run(run_idx, args.statements, on_ns, off_ns, sharpit_rows, callee_rows, listener_cum_us)

    print(f"=== Direct perf_counter_ns component timings ({args.statements} iterations, {args.runs} runs) ===")
    all_runs = [dict(run_component_timings(args.statements)) for _ in range(args.runs)]
    labels = [label for label, _ in run_component_timings(200)]
    print(f"{'Stage / Function':<58} {'Run 1':>9} {'Run 2':>9} {'Run 3':>9} {'Median':>9}")
    for label in labels:
        vals = [r[label] for r in all_runs]
        r1 = vals[0]
        r2 = vals[1] if len(vals) > 1 else r1
        r3 = vals[2] if len(vals) > 2 else r1
        med = statistics.median(vals)
        print(f"{label:<58} {r1:>7.3f}µs {r2:>7.3f}µs {r3:>7.3f}µs {med:>7.3f}µs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
