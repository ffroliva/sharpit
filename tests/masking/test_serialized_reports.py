"""A secret reaches no serialized report, in any field (2026-11-05 design section 5, Task 4).

The other gates read one text per surface. This one ``json.dumps`` the whole report, because ``id`` and the test-session
group keys were built from text the masker never saw. The search ignores case: a fingerprint is lower-cased, and a
vendor token lower-cased no longer looks like one to the masker. Three paths reach it: a statement that runs, a
statement that fails, and the two that write outside the request (the ORM's unbounded read, a span's ``db.statement``).
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

sa = pytest.importorskip("sqlalchemy")

from fastapi.testclient import TestClient  # noqa: E402

from fastapi import FastAPI  # noqa: E402
from sharpit import install  # noqa: E402
from sharpit.engine.capture.statement import masked_shape  # noqa: E402
from sharpit.engine.capture.traces import _attributes  # noqa: E402  # pyright: ignore[reportPrivateUsage]
from sharpit.engine.masking import Exposure, Masker  # noqa: E402
from sharpit.engine.sources.dispatch import SqlEvent  # noqa: E402
from sharpit.engine.sqla.orm import (  # noqa: E402
    _masked_fingerprint,  # pyright: ignore[reportPrivateUsage]
    _unbounded_read_statement_shape,  # pyright: ignore[reportPrivateUsage]
)
from sharpit.engine.sqltext import Dialect  # noqa: E402
from sharpit.engine.testsession.sink import TestSessionSink  # noqa: E402

pytestmark = pytest.mark.needs_sqlalchemy

STRIPE = "sk_live_" + "4eC39HqLyjWDarjtT1zdp7dc"
AWS = "AKIA" + "IOSFODNN7EXAMPLE"
API = "/sharpit/api"
NODE = "tests/test_x.py::test_x"
EXECUTIONS = 6  # past the N+1 threshold, so the statement reaches sqlalchemy-statistics
GOLDEN = Path(__file__).parents[1] / "fixtures" / "bootui" / "2.2.0" / "sql-trace" / "insights.captured.json"

STATEMENTS = {  # as Codex ran them in council 6: valid SQLite, so each one runs and reaches every report
    "unquoted_alias": (f"SELECT 1 AS {STRIPE}", STRIPE),
    "quoted_name": (f'SELECT 1 AS "{STRIPE}"', STRIPE),
    "upper_case_alias": (f"SELECT 1 AS {AWS}", AWS),
    "upper_case_quoted_name": (f'SELECT 1 AS "{AWS}"', AWS),
}
PLAIN = "PLAINVALUE7Q"
FAILING = {  # capture off only: with capture on a literal in ``[SQL: ...]`` is shown by design
    # the masker edits the statement, so the replace of ``[SQL: ...]`` has to run first
    "no_such_table": f"select * from nosuch where h = 'Bearer abcdefghijk' and b = '{PLAIN}'",
    "driver_echo": f"select 'a' 'b' '{PLAIN}'",  # SQLite quotes it in its own ``near`` message, outside ``[SQL: ...]``
}


def _mcp(client: TestClient, tool: str) -> Any:
    call = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": tool, "arguments": {}}}
    return client.post(f"{API}/mcp", json=call).json()


HTTP_REPORTS: dict[str, Callable[[TestClient], Any]] = {
    "sql_trace": lambda client: client.get(f"{API}/sql-trace").json(),
    "insights": lambda client: client.get(f"{API}/sql-trace/insights").json(),
    "attribution": lambda client: client.get(f"{API}/sql-trace/insights").json()["attribution"],
    "sqlastats": lambda client: client.get(f"{API}/sqlalchemy-statistics").json(),
    "activity": lambda client: client.get(f"{API}/activity").json(),
    "activity_journal": lambda client: client.get(f"{API}/activity/journal").json(),
    "mcp_sql_traces": lambda client: _mcp(client, "get_sql_traces"),
    "mcp_live_activity": lambda client: _mcp(client, "get_live_activity"),
}


@pytest.fixture(params=[False, True], ids=["capture_off", "capture_on"])
def capture(request: pytest.FixtureRequest) -> bool:
    return request.param


@contextmanager
def _served(statement: str, capture: bool, failures: int) -> Iterator[TestClient]:
    """A request that runs the statement ``EXECUTIONS`` times, on an app with the MCP endpoint on."""
    engine = sa.create_engine("sqlite://")
    app = FastAPI()

    @app.get("/run")
    def run() -> dict[str, int]:  # pyright: ignore[reportUnusedFunction]
        failed = 0
        with engine.connect() as conn:
            for _ in range(EXECUTIONS):
                try:
                    conn.execute(sa.text(statement))
                except sa.exc.DBAPIError:
                    failed += 1
        return {"failed": failed}

    handle = install(
        app,
        enabled="ON",
        show_banner=False,
        mcp_enabled="ON",
        sql_trace_sqlite3_enabled=False,
        sql_trace_capture_parameters=capture,
    )
    client = TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000))
    assert client.get("/run").json() == {"failed": failures}
    yield client
    handle.uninstall_capture()


@pytest.fixture(params=STATEMENTS, ids=str)
def traced(request: pytest.FixtureRequest, capture: bool) -> Iterator[tuple[TestClient, str]]:
    statement, secret = STATEMENTS[request.param]
    with _served(statement, capture, 0) as client:
        yield client, secret


@pytest.fixture(params=FAILING, ids=str)
def failed(request: pytest.FixtureRequest) -> Iterator[TestClient]:
    with _served(FAILING[request.param], False, EXECUTIONS) as client:
        entries = client.get(f"{API}/sql-trace").json()["entries"]
        assert entries[0]["errorMessage"], "no error reached the report: it proved nothing"
        yield client


def _assert_hidden(report: Any, secret: str) -> None:
    dumped = json.dumps(report)
    assert secret.lower() not in dumped.lower(), dumped[:600]


@pytest.mark.parametrize("surface", HTTP_REPORTS)
def test_no_secret_in_a_serialized_report(surface: str, traced: tuple[TestClient, str]) -> None:
    client, secret = traced
    report = HTTP_REPORTS[surface](client)
    assert report, "the report is empty: it proved nothing"
    _assert_hidden(report, secret)


@pytest.mark.parametrize("surface", HTTP_REPORTS)
def test_no_literal_of_a_failing_statement_in_a_serialized_report(surface: str, failed: TestClient) -> None:
    report = HTTP_REPORTS[surface](failed)
    assert report, "the report is empty: it proved nothing"
    _assert_hidden(report, PLAIN)


def _test_session_facts(statement: str, attempt_test: bool) -> dict[str, Any]:
    sink = TestSessionSink("gw0")
    tag = (NODE, sink.begin_test(NODE), "call") if attempt_test else None
    for _ in range(EXECUTIONS):
        event = SqlEvent("sqlalchemy", statement, None, False, None, 0, 1, -1, None, None, None, Dialect.UNSUPPORTED)
        sink.on_sql(event, tag)
    return sink.facts.to_json()


@pytest.mark.parametrize("attributed", [True, False], ids=["attributed", "unattributed"])
@pytest.mark.parametrize(("statement", "secret"), STATEMENTS.values(), ids=STATEMENTS)
def test_no_secret_in_test_session_facts(statement: str, secret: str, attributed: bool) -> None:
    facts = _test_session_facts(statement, attributed)
    assert facts["unattributed"] == (0 if attributed else EXECUTIONS)
    _assert_hidden(facts, secret)


@pytest.mark.parametrize(("statement", "secret"), STATEMENTS.values(), ids=STATEMENTS)
def test_no_secret_in_a_relationship_group(statement: str, secret: str) -> None:
    # the key of ``relationshipOf`` and ``statementSites``, joined with the sink's on the same text
    assert secret.lower() not in (_masked_fingerprint(statement, Dialect.POSTGRESQL) or "").lower()


@pytest.mark.parametrize(("statement", "secret"), STATEMENTS.values(), ids=STATEMENTS)
def test_no_secret_in_an_unbounded_read_fact(statement: str, secret: str) -> None:
    # the statement of ``UnboundedReadFact``, which the test-session report serializes
    shown = _unbounded_read_statement_shape(None, statement)[0]
    assert secret.lower() not in shown.lower()


@pytest.mark.parametrize("key", ["db.statement", "db.query.text"])
@pytest.mark.parametrize(("statement", "secret"), STATEMENTS.values(), ids=STATEMENTS)
def test_no_secret_in_a_span_statement(statement: str, secret: str, key: str) -> None:
    attributes = _attributes(Masker(Exposure.MASKED, True), {key: statement}, Dialect.UNSUPPORTED)
    assert secret.lower() not in json.dumps(attributes).lower()


def test_id_stays_the_lower_cased_shape_without_a_secret() -> None:
    # ported: sql-trace/insights.captured.json, BootUI's ``id`` is the lower-cased statement
    golden = json.loads(GOLDEN.read_text(encoding="utf-8"))["statements"]
    masker = Masker(Exposure.MASKED, True)
    assert golden, "the golden holds no statement"
    for row in golden:
        assert masked_shape(masker, row["sql"], Dialect.POSTGRESQL).fingerprint == row["id"]
