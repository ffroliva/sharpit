"""The ``transaction`` journal events of one seeded scenario, byte for byte (r7 of #166: the begin path's cheaper facts and
flags change cost, never an event). ``golden/transaction_events.json`` was generated from 7ed7c6b4, before the cuts.

Volatile fields (clocks) are replaced by their type; the call-site line is replaced by ``L``. Everything else is
compared as the journal serialises it: key order included.
"""

from __future__ import annotations

import json
import os
import re
import sys
import types
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

sa = pytest.importorskip("sqlalchemy")

from sharpit import install  # noqa: E402
from sharpit.engine import sqla  # noqa: E402
from sharpit.engine.capture.correlation import REQUEST, RequestInfo  # noqa: E402
from fastapi import FastAPI  # noqa: E402

pytestmark = pytest.mark.needs_sqlalchemy

GOLDEN = Path(__file__).parent / "golden" / "transaction_events.json"
TRACE_ID = 0x0123456789ABCDEF0123456789ABCDEF
VOLATILE = ("epochMillis", "durationNanos", "startNanos")


@pytest.fixture(autouse=True)
def clean_listeners() -> Iterator[None]:
    sqla.detach_all()
    yield
    sqla.detach_all()


class _Span:
    def get_span_context(self) -> Any:
        return types.SimpleNamespace(trace_id=TRACE_ID, is_valid=True)


def _write(conn: Any) -> None:
    conn.execute(sa.text("create table if not exists w (a integer)"))
    conn.execute(sa.text("insert into w values (1)"))


def _scenario(tmp_path: Path) -> list[dict[str, Any]]:
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'g.db'}")
    handle = install(
        FastAPI(), enabled="ON", show_banner=False, config_scan=False, engines=[engine],
        runtime_journal_sources=("transaction",),
    )  # fmt: skip
    token = REQUEST.set(RequestInfo("req-1", handle.context.context_id, "GET", "/x", None, 0, None))
    try:
        with engine.begin() as conn:  # begin / commit
            conn.execute(sa.text("select 1"))
        with engine.connect() as conn:  # rollback after a write
            _write(conn)
            conn.rollback()
        with engine.connect() as conn:  # a write-free rollback
            conn.execute(sa.text("select 1"))
            conn.rollback()
        with engine.begin() as outer:  # nested: a second connection begun inside the first
            outer.execute(sa.text("select 1"))
            with engine.begin() as inner:
                inner.execute(sa.text("select 1"))
        with engine.begin() as conn:  # savepoints, one released and one rolled back
            with conn.begin_nested():
                conn.execute(sa.text("select 1"))
            savepoint = conn.begin_nested()
            _write(conn)
            savepoint.rollback()
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:  # no transaction at all
            conn.execute(sa.text("select 1"))
        with engine.execution_options(isolation_level="SERIALIZABLE").begin() as conn:  # a carried isolation level
            conn.execute(sa.text("select 1"))
        with pytest.raises(RuntimeError, match="boom"):  # an exception inside begin() is a rollback
            with engine.begin() as conn:
                _write(conn)
                raise RuntimeError("boom")

        def failing(_conn: Any) -> None:
            raise RuntimeError("begin failed")

        sa.event.listen(sa.engine.Engine, "begin", failing)
        try:
            with pytest.raises(RuntimeError, match="begin failed"), engine.begin():  # a failed begin
                pass
        finally:
            sa.event.remove(sa.engine.Engine, "begin", failing)
        with engine.begin() as conn:  # the next begin closes the failed one as UNKNOWN
            conn.execute(sa.text("select 1"))
    finally:
        REQUEST.reset(token)
        engine.dispose()
    journal = handle.context.capture.journal
    assert journal is not None
    return [dict(r) for r in journal.records("transaction")]


def _normal(record: dict[str, Any]) -> dict[str, Any]:
    shown = {k: (type(v).__name__ if k in VOLATILE else v) for k, v in record.items()}
    shown["method"] = re.sub(r":\d+$", ":L", str(shown["method"]))
    return shown


def test_transaction_events_of_the_seeded_scenario_are_byte_identical_to_the_golden(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    trace = types.ModuleType("opentelemetry.trace")
    trace.get_current_span = lambda: _Span()  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "opentelemetry.trace", trace)
    events = json.dumps([_normal(r) for r in _scenario(tmp_path)], indent=1)
    if os.environ.get("SHARPIT_REGEN_GOLDEN"):
        GOLDEN.parent.mkdir(exist_ok=True)
        GOLDEN.write_text(events + "\n", encoding="utf-8")
    assert events + "\n" == GOLDEN.read_text(encoding="utf-8")
