"""The journal's read output, byte for byte (lane perf sql-journal-compact).

``tests/fixtures/journal/read_golden.json`` was recorded on ``origin/release/0.6.0`` cc72bf4a, before the journal
stored compact records: ``records()``, ``status()``, the insights snapshot, ``/activity/journal`` and the window and
coverage of ``/runtime-insights`` for a fixed set of events of every produced source, in each producer's key order.
A change to how the journal stores an event must reproduce it exactly: every key, in order, nulls included.
"""

from __future__ import annotations

import itertools
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from fastapi import FastAPI
from sharpit import install
from sharpit.engine.capture import journal as journal_module
from sharpit.engine.capture.journal import RuntimeJournal
from sharpit.engine.collectors.insights import snapshot
from sharpit.engine.masking import Exposure, Masker
from sharpit.settings_registry import JOURNAL_SOURCES

GOLDEN = Path(__file__).parents[2] / "fixtures" / "journal" / "read_golden.json"
SECRET = "sk_" + "live_" + "EXAMPLE0123456789"  # built at load: no secret-shaped literal in the source or the fixture
TRACE = "0af7651916cd43dd8448eb211c80319c"

HTTP = [
    {
        "source": "http",
        "epochMillis": 1_700_000_000_000 + i,
        "durationNanos": 1_500_000 * (i + 1),
        "startNanos": 9_000_000 + i,
        "traceId": TRACE if i % 2 else None,
        "thread": "AnyIO worker thread",
        "requestId": f"req-{i}",
        "method": "GET",
        "path": f"/pets/{i};jsessionid={SECRET}",
        "routeTemplate": "/pets/{pet_id}",
        "operation": None,
        "status": 500 if i == 2 else 200,
        "route": "GET /pets/{pet_id}",
    }
    for i in range(4)
]
SQL = [
    {
        "source": "sql",
        "sql": text,
        "traceId": None,
        "requestId": f"req-{i}",
        "thread": "MainThread",
        "durationNanos": 42_000 + i,
        "startedAt": 1_700_000_000_100 + i,
        "dataSource": None,
        "failed": i == 3,
        "phase": None,
        "completedNanos": 9_100_000 + i,
        "codePathStamp": 0,
        "provenance": "EXECUTION",
        "batchSize": 1,
        "callSite": "app/pets.py:12" if i % 2 else None,
    }
    for i, text in enumerate(
        [
            "select * from pets where id = ?",
            f"select * from api_keys where credential = '{SECRET}'",
            f'select "name" from pets where token = "{SECRET}" # tail',
            "select * from pets where id = ?",
        ]
    )
]
LOG = [
    {
        "source": "log",
        "epochMillis": 1_700_000_000_200,
        "durationNanos": -1,
        "traceId": None,
        "thread": "MainThread",
        "requestId": "req-2",
        "failedOrSlow": True,
        "logger": "app.pets",
        "level": "ERROR",
        "template": f"lookup failed password={SECRET} for %s",
        "exceptionClass": "builtins.KeyError",
    },
    {
        "source": "log",
        "epochMillis": 1_700_000_000_201,
        "durationNanos": -1,
        "traceId": TRACE,
        "thread": "worker-1",
        "requestId": None,
        "failedOrSlow": False,
        "logger": "app.pets",
        "level": "WARN",
        "template": None,
        "exceptionClass": None,
    },
]
MAIL = [
    {
        "source": "mail",
        "recipients": 3,
        "attachments": 1,
        "sent": True,
        "failed": False,
        "traceId": None,
        "requestId": "req-1",
        "thread": "MainThread",
        "durationNanos": -1,
        "completedNanos": 9_200_000,
        "codePathStamp": 0,
    }
]
AI = [
    {
        "source": "ai",
        "operation": "chat",
        "traceId": TRACE,
        "requestId": "req-1",
        "durationNanos": 2_000_000,
        "provider": "openai",
        "model": "gpt-example",
        "inputTokens": 9000,
        "outputTokens": 7,
        "finishReason": "stop",
        "failed": False,
        "spanId": "00f067aa0ba902b7",
        "completedNanos": 9_300_000,
        "codePathStamp": 0,
    }
]
EXCEPTION = [  # nested (``types`` is a list): offered through ``offer``, which copies it
    {
        "source": "exception",
        "epochMillis": 1_700_000_000_300,
        "durationNanos": -1,
        "traceId": None,
        "thread": "MainThread",
        "requestId": "req-2",
        "failedOrSlow": True,
        "groupId": "0123456789abcdef",
        "exceptionClass": "builtins.KeyError",
        "signature": "fedcba9876543210",
        "types": ["builtins.KeyError", "builtins.LookupError"],
        "logged": False,
    }
]
RAW = {  # what a capture source could hand over unmasked: masked when read, whatever its shape
    "source": "http",
    "message": f"login password={SECRET}",
    "headers": {"Authorization": f"Bearer {SECRET}", "Accept": ["a", ("b", 1.5)]},
    "password": SECRET,
    "raw": f"token={SECRET}".encode(),
    "tags": {"b", "a"},
    "count": 3,
    "ratio": 0.25,
    "ok": True,
}
UNCONFIGURED = "not a source"  # a space no registry name has: no sensor will ever configure it (asserted below)
SOURCES = ("ai", "exception", "http", "log", "mail", "sql")  # the six offered here: another producer changes nothing


def _pin_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    ticks = itertools.count(1_700_000_001_000_000_000, 1_000_000)  # one millisecond per stamp
    monkeypatch.setattr(journal_module, "time", SimpleNamespace(time_ns=lambda: next(ticks)))


def _fill(journal: RuntimeJournal) -> None:
    journal.run_id = "golden00"
    for event in (*HTTP, *LOG, *MAIL, *AI):
        assert journal.offer_flat(dict(event)) is True  # type: ignore[arg-type]
    for event in SQL:
        assert journal.offer_flat(dict(event)) is True  # type: ignore[arg-type]
    for event in (*EXCEPTION, RAW):
        assert journal.offer(event) is True
    assert journal.offer({"source": UNCONFIGURED, "port": 5}) is False  # a source not configured: counted
    assert journal.offer({"source": 7}) is False


def _read(journal: RuntimeJournal) -> dict[str, Any]:
    view = snapshot.project(journal)
    return {
        "records": {source: journal.records(source) for source in SOURCES},
        "status": journal.status(),
        "snapshot": {
            "status": view.status,
            "records": {source: view.records[source] for source in SOURCES},
            "newestAt": view.newest_at,
        },
    }


def _api() -> dict[str, Any]:
    app = FastAPI()
    handle = install(app, enabled="ON", show_banner=False, config_scan=False)
    try:
        journal = handle.context.capture.journal
        assert journal is not None
        _fill(journal)
        with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as client:
            insights = client.get("/sharpit/api/runtime-insights").json()
            return {
                "/activity/journal": client.get("/sharpit/api/activity/journal").json(),
                # the journal's part of the report only: the checks change with every insight kind
                "/runtime-insights": {
                    "available": insights["available"],
                    "window": insights["window"],
                    "coverage": [row for row in insights["coverage"] if row["source"] in SOURCES],
                },
            }
    finally:
        handle.uninstall_capture()


def observed(monkeypatch: pytest.MonkeyPatch) -> str:
    _pin_clock(monkeypatch)
    out: dict[str, Any] = {}
    for name, masker in (
        ("MASKED", Masker(Exposure.MASKED, True)),
        ("METADATA_ONLY", Masker(Exposure.METADATA_ONLY, True)),
        ("FULL", Masker(Exposure.FULL, False)),
    ):
        journal = RuntimeJournal(sources=SOURCES, masker=masker)
        _fill(journal)
        out[name] = _read(journal)
    ring = RuntimeJournal(max_events=5, max_bytes=2000, sources=SOURCES)  # both bounds evict
    _fill(ring)
    out["ring"] = _read(ring)
    out["api"] = _api()
    text = json.dumps(out, indent=1, ensure_ascii=False) + "\n"
    return text.replace(SECRET, "<canary>")  # FULL exposure shows the canary: the fixture never holds it


def test_the_unconfigured_source_can_never_be_configured() -> None:
    assert UNCONFIGURED not in JOURNAL_SOURCES
    assert " " not in "".join(JOURNAL_SOURCES)


def test_the_journal_reads_exactly_what_the_base_read(monkeypatch: pytest.MonkeyPatch) -> None:
    assert observed(monkeypatch) == GOLDEN.read_text(encoding="utf-8")
