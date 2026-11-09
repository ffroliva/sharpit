"""A statement sharpit cannot read is hidden (architecture spec section 7; owner's rulings, items 7 and 8, 2026-11-07).

``UNSUPPORTED`` text is not presented at any exposure, ``FULL`` included, and capture on does not lift it. The event
keeps its safe fields. A driver error of an ``UNSUPPORTED`` provider renders as a classified one: its class, a strict
structured code, the marker for its block and the constant parameters region; never the driver's free text.
"""

# derived: architecture spec section 7, no BootUI source (BootUI renders unknown text with a cut)

from __future__ import annotations

import json
from collections.abc import Iterator

import pytest

from sharpit.engine import sqltext
from sharpit.engine.capture.sqltrace import SqlTraceRecorder
from sharpit.engine.masking import MASK, Exposure, Masker
from sharpit.engine.sqltext import Dialect
from sharpit.settings import load_settings

UNSUPPORTED_STATEMENT = "[statement hidden: unsupported database]"  # spec section 7

SECRET = "hunter2"
BOUND = "s3cretParam"
FREE = "SECRETFREETEXT"
STATEMENTS = {
    "mssql": f"SELECT TOP 1 * FROM t WHERE pw = N'{SECRET}'",
    "oracle": f"SELECT q'[{SECRET}]' FROM dual",
    "plain": f"SELECT * FROM t WHERE pw = '{SECRET}'",
}
MASKERS = {
    "masked": Masker(Exposure.MASKED, True),
    "full": Masker(Exposure.FULL, True),
    "masked_capture": Masker(Exposure.MASKED, True, capture_parameters=True),
    "full_capture": Masker(Exposure.FULL, True, capture_parameters=True),
}
CLASSIFIED = f"(pyodbc.IntegrityError)\n[SQL: {UNSUPPORTED_STATEMENT}]\n[parameters: {MASK}]"


def _driver_error(module: str, name: str, message: str) -> BaseException:
    sa_exc = pytest.importorskip("sqlalchemy.exc")
    driver = type(name, (Exception,), {"__module__": module})(message)
    return sa_exc.IntegrityError(STATEMENTS["mssql"], (BOUND,), driver)


@pytest.mark.parametrize("masker", MASKERS.values(), ids=MASKERS)
@pytest.mark.parametrize("statement", STATEMENTS.values(), ids=STATEMENTS)
def test_a_statement_shows_the_marker(masker: Masker, statement: str) -> None:
    assert sqltext.statement_text(masker, statement, Dialect.UNSUPPORTED) == UNSUPPORTED_STATEMENT


def test_metadata_only_gives_nothing() -> None:
    masker = Masker(Exposure.METADATA_ONLY, True)
    assert sqltext.statement_text(masker, STATEMENTS["mssql"], Dialect.UNSUPPORTED) is None


@pytest.mark.parametrize("masker", MASKERS.values(), ids=MASKERS)
def test_the_shape_shows_the_marker(masker: Masker) -> None:
    assert sqltext.statement_shape(masker, STATEMENTS["mssql"], Dialect.UNSUPPORTED).text == UNSUPPORTED_STATEMENT


@pytest.mark.parametrize("masker", MASKERS.values(), ids=MASKERS)
def test_the_shape_has_no_identity(masker: Masker) -> None:
    assert sqltext.statement_shape(masker, STATEMENTS["mssql"], Dialect.UNSUPPORTED).fingerprint is None


def _recorded(masker: Masker, error: BaseException | None = None) -> dict[str, object]:
    recorder = SqlTraceRecorder(masker, max_sql_length=10_000)
    recorder.record(
        STATEMENTS["mssql"],
        duration_ns=3_000_000,
        thread="t",
        connection_id=None,
        dialect=Dialect.UNSUPPORTED,
        parameters=(BOUND,),
        error=error,
    )
    return recorder.rows()[-1]


@pytest.mark.parametrize("masker", MASKERS.values(), ids=MASKERS)
def test_a_recorder_stores_the_marker(masker: Masker) -> None:
    """Item 7: capture on does not lift the hide on the recorder's stored ``sql`` (``capture/sqltrace.py:274``)."""
    assert _recorded(masker)["sql"] == UNSUPPORTED_STATEMENT


def test_a_recorder_fed_an_unsupported_statement_never_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """Safety rule 5: a lexer that refuses the dialect degrades; it never raises into the host."""

    def refuses(*_: object) -> object:
        raise ValueError("no reading")

    monkeypatch.setattr(sqltext.LEXER, "scan", refuses)
    raised: Exception | None = None
    try:
        _recorded(MASKERS["masked"])
    except ValueError as exc:
        raised = exc
    assert raised is None


def test_the_event_keeps_its_safe_fields() -> None:
    row = _recorded(MASKERS["masked"], _driver_error("pyodbc", "IntegrityError", "duplicate"))
    assert row["durationMillis"] == 3
    assert row["category"] == "SELECT"
    assert row["success"] is False


@pytest.mark.parametrize("masker", MASKERS.values(), ids=MASKERS)
def test_an_exception_renders_classified(masker: Masker) -> None:
    error = _driver_error("pyodbc", "IntegrityError", f"The duplicate key value is ({FREE}).")
    assert sqltext.error_text(masker, error, Dialect.UNSUPPORTED) == CLASSIFIED


@pytest.mark.parametrize("masker", MASKERS.values(), ids=MASKERS)
def test_a_recorded_error_renders_classified(masker: Masker) -> None:
    error = _driver_error("pyodbc", "IntegrityError", f"The duplicate key value is ({FREE}).")
    assert _recorded(masker, error)["errorMessage"] == CLASSIFIED


DRIVER_REGIONS = {
    "duplicate_key": (
        f"(pyodbc.IntegrityError) The duplicate key value is ({FREE}).\n"
        f"[SQL: {STATEMENTS['mssql']}]\n[parameters: ('{BOUND}',)]\n"
        "(Background on this error at: https://sqlalche.me/e/20/gkpj)",
        CLASSIFIED,
    ),
    "no_parameters": (
        f"(oracledb.DatabaseError) ORA-00001: unique constraint violated ({FREE})\n[SQL: {STATEMENTS['oracle']}]",
        f"(oracledb.DatabaseError)\n[SQL: {UNSUPPORTED_STATEMENT}]",
    ),
    "bare_text": (f"The duplicate key value is ({FREE}).", MASK),
    "planted_class": (f"(x.{FREE}) failed\n[SQL: SELECT 1]", f"(x.{FREE})\n[SQL: {UNSUPPORTED_STATEMENT}]"),
    "jwt_class": ("(eyJhbGciOiJI.eyJzdWIiOiIx.SflKxwRJSMeKKF2Q) x\n[SQL: SELECT 1]", f"[SQL: {UNSUPPORTED_STATEMENT}]"),
}


@pytest.mark.parametrize("masker", MASKERS.values(), ids=MASKERS)
@pytest.mark.parametrize(("text", "expected"), DRIVER_REGIONS.values(), ids=DRIVER_REGIONS)
def test_an_unsupported_driver_region(masker: Masker, text: str, expected: str) -> None:
    """Item 8: never the driver's free text. A dotted name in parentheses that passes the masker is the class."""
    assert sqltext.error_text(masker, text, Dialect.UNSUPPORTED, known=True) == expected


@pytest.mark.parametrize("masker", MASKERS.values(), ids=MASKERS)
def test_an_unsupported_driver_region_hides_the_free_text(masker: Masker) -> None:
    shown = sqltext.error_text(masker, DRIVER_REGIONS["duplicate_key"][0], Dialect.UNSUPPORTED) or ""
    assert FREE not in shown


def test_free_text_with_no_sql_takes_mask_text() -> None:
    masker = MASKERS["masked"]
    text = "the cache refused the key token=abcdef123456 for user bob"
    assert sqltext.error_text(masker, text, Dialect.UNSUPPORTED) == masker.mask_text(text)


def test_metadata_only_gives_no_error() -> None:
    masker = Masker(Exposure.METADATA_ONLY, True)
    assert sqltext.error_text(masker, DRIVER_REGIONS["duplicate_key"][0], Dialect.UNSUPPORTED, known=True) is None


def test_a_log_statement_shows_the_marker() -> None:
    assert sqltext.log_statement(MASKERS["masked"], STATEMENTS["mssql"], Dialect.UNSUPPORTED) == UNSUPPORTED_STATEMENT


def _capture_warnings(**kwargs: object) -> list[str]:
    return [w for w in load_settings(kwargs, {}).warnings if "inline literals" in w]


def test_capture_on_warns_at_install() -> None:
    assert len(_capture_warnings(sql_trace_capture_parameters=True)) == 1


def test_the_capture_warning_names_error_text() -> None:
    assert all("error text" in w for w in _capture_warnings(sql_trace_capture_parameters=True))


def test_capture_off_does_not_warn() -> None:
    assert _capture_warnings() == []


def test_metadata_only_with_capture_does_not_warn() -> None:
    assert _capture_warnings(sql_trace_capture_parameters=True, expose_values="METADATA_ONLY") == []


# --- the served reports: MCP and HTTP read the recorder the listener filled -------------------------------------------


@pytest.fixture(params=[False, True], ids=["capture_off", "capture_on"])
def served(request: pytest.FixtureRequest) -> Iterator[object]:
    sa = pytest.importorskip("sqlalchemy")
    from fastapi.testclient import TestClient

    from fastapi import FastAPI
    from sharpit import install

    engine = sa.create_engine("sqlite://")
    engine.dialect.name = "mssql"  # a server sharpit has no rules for, on a connection that runs here
    app = FastAPI()

    @app.get("/run")
    def run() -> dict[str, bool]:  # pyright: ignore[reportUnusedFunction]
        with engine.connect() as conn:
            conn.execute(sa.text(f"SELECT '{SECRET}' AS pw"))
        return {"ran": True}

    handle = install(
        app,
        enabled="ON",
        show_banner=False,
        mcp_enabled="ON",
        sql_trace_sqlite3_enabled=False,
        sql_trace_capture_parameters=request.param,
        engines=[engine],
    )
    client = TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000))
    assert client.get("/run").json() == {"ran": True}
    yield client
    handle.uninstall_capture()


def test_mcp_shows_the_marker(served: object) -> None:
    from fastapi.testclient import TestClient

    assert isinstance(served, TestClient)
    call = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "get_sql_traces", "arguments": {}}}
    dumped = json.dumps(served.post("/sharpit/api/mcp", json=call).json())
    assert SECRET not in dumped
    assert UNSUPPORTED_STATEMENT in dumped


def test_http_shows_the_marker(served: object) -> None:
    from fastapi.testclient import TestClient

    assert isinstance(served, TestClient)
    dumped = json.dumps(served.get("/sharpit/api/sql-trace").json())
    assert SECRET not in dumped
    assert UNSUPPORTED_STATEMENT in dumped


def test_cli_shows_the_marker(served: object) -> None:
    from fastapi.testclient import TestClient

    assert isinstance(served, TestClient)
    dumped = served.post("/sharpit/api/cli/tools/get_sql_traces", json={}).text
    assert SECRET not in dumped
    assert UNSUPPORTED_STATEMENT in dumped
