"""The journal-driven fixture the insights tests share: requests through the http producer (``http_event``) and
statements through the production listener path (``dispatch.deliver``), never hand-made rows."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

from fastapi import FastAPI
from sharpit import install
from sharpit.engine import sqla
from sharpit.engine.capture.correlation import REQUEST, RequestInfo
from sharpit.engine.capture.exchanges import http_event
from sharpit.engine.collectors.insights.registry import KINDS
from sharpit.engine.collectors.insights.service import InsightsService
from sharpit.engine.collectors.insights.snapshot import project
from sharpit.engine.sources import dispatch
from sharpit.engine.sources.dispatch import SqlEvent
from sharpit.engine.sqltext import Dialect

MS = 1_000_000
KIND = "route-time-breakdown"
BASE_MS = 1_700_000_000_000
ORDERS = "GET /api/orders/{id}"
Row = dict[str, Any]
Sql = tuple[float, float]  # (offset in ms from the request's start, duration in ms)
PERF0 = 5_000_000_000  # where the monotonic clock stands at the first request
SEC = 1_000_000_000
SUB_MS = 600_000  # a request starts 0.6 ms into a wall-clock millisecond, as a real one almost never starts on one


def _ns(ms: float) -> int:
    return round(ms * MS)


class Run:
    def __init__(self, sources: tuple[str, ...] = ("http", "sql", "ai"), **options: Any) -> None:
        sqla.detach_all()
        self.handle = install(
            FastAPI(), enabled="ON", show_banner=False, config_scan=False, runtime_journal_sources=sources, **options
        )
        self.ctx = self.handle.context
        self.journal: Any = self.ctx.capture.journal
        self.requests = 0

    def close(self) -> None:
        self.handle.uninstall_capture()

    def request(
        self,
        route: str,
        duration_ms: float,
        *statements: Sql,
        status: int = 200,
        text: str = "select 1",
        path: str | None = None,
        matched: bool = True,
        monotonic_start: bool = True,
    ) -> str:
        method, label = route.split(" ", 1)
        template = label if matched else None  # unmatched: the route label comes from the masked path
        self.requests += 1
        request_id = f"r{self.requests}"
        start_ns, epoch_ns = PERF0 + self.requests * SEC, (BASE_MS + self.requests * 1000) * MS + SUB_MS
        shown = path if path is not None else label.replace("{id}", "42")
        info = RequestInfo(
            request_id, self.ctx.context_id, method, shown, template, start_ns, start_ns + _ns(duration_ms)
        )
        token = REQUEST.set(info)
        try:
            for offset, ms in statements:
                self.statement(start_ns + _ns(offset), _ns(ms), epoch_ns + _ns(offset + ms), text)
        finally:
            REQUEST.reset(token)
        event = http_event(info, [], epoch_ns, status, template)
        if not monotonic_start:
            event.pop("startNanos", None)  # a producer that does not write BootUI's ``timing.startNanos``
        self.journal.offer(event)
        return request_id

    def statement(self, started_ns: int, duration_ns: int, ended_epoch_ns: int, text: str) -> None:
        event = SqlEvent("sqlalchemy", text, None, False, None, started_ns, duration_ns, -1, None, None, None,
                         Dialect.POSTGRESQL)  # fmt: skip
        clock = SimpleNamespace(time_ns=lambda: ended_epoch_ns)
        with patch.object(dispatch, "time", clock), patch.object(dispatch, "call_site", return_value=None):
            dispatch.deliver(event, [self.ctx])

    def report(self) -> Row:
        return InsightsService(self.journal).report()

    def check(self) -> Row:
        return next(c for c in self.report()["checks"] if c["kind"] == KIND)

    def rows(self) -> dict[str, Row]:
        return {str(o["subject"]): o for o in self.report()["observations"] if o["kind"] == KIND}

    def cells(self, row: Row) -> list[list[str]]:
        rows: list[Row] = InsightsService(self.journal).insight(str(row["id"]))["rows"]
        return [r["cells"] for r in rows]

    def findings(self) -> dict[str, Any]:
        evaluate = next(k for k in KINDS if k.kind == KIND).evaluate
        assert evaluate is not None, "route-time-breakdown is still a stub"
        return {f.subject: f for f in evaluate(project(self.journal)).findings}
