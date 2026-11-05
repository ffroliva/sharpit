"""The acceptance gates of the output masking redesign (spec §1: A1, A3, A4), one row per surface that shows SQL.

Every surface drives the production function that fills it. A1 and A3 are functions over a surface and rows
(``failures_visible``, ``failures_shape``, ``failures_regions``), with thin tests on top, so a planted or mutated build
can be driven through them and compared by failing-row count. ``expected`` comes from ``sql_corpus``, never a lexer.
"""

from __future__ import annotations

import ast
import asyncio
import atexit
import collections
import functools
import logging
import os
import re
from collections.abc import Callable, Iterable, Sequence
from functools import partial
from pathlib import Path
from types import SimpleNamespace
from typing import Any, NamedTuple

import pytest
from tests.engine.collectors.mysql.fakes import FakeMySqlConnection, FakeMySqlEngine
from tests.engine.collectors.mysql.fakes import FakeRegistry as MySqlRegistry
from tests.engine.postgresql.fakes import FakePgEngine
from tests.engine.postgresql.fakes import FakeRegistry as PgRegistry
from tests.masking import sql_corpus
from tests.masking.sql_corpus import Row

from sharpit.engine.activation import ActivationStatus
from sharpit.engine.capture.exceptions import ExceptionStore
from sharpit.engine.capture.logtail import SharpitLogHandler
from sharpit.engine.capture.sqltrace import SqlTraceRecorder
from sharpit.engine.capture.traces import SpanBuffer, _attributes  # pyright: ignore[reportPrivateUsage]
from sharpit.engine.capture.transactions import TransactionRecorder
from sharpit.engine.collectors import data
from sharpit.engine.collectors.health import HealthService
from sharpit.engine.collectors.mysql import sections as mysql_sections
from sharpit.engine.collectors.mysql.querytext import mysql_query_text
from sharpit.engine.collectors.mysql.sections import DataSourceData, RowLimits, collect_replication
from sharpit.engine.collectors.mysql.service import refresh_mysql
from sharpit.engine.collectors.postgresql import sections as postgresql_sections
from sharpit.engine.collectors.postgresql.querytext import query_text
from sharpit.engine.collectors.postgresql.service import refresh_postgresql
from sharpit.engine.context import SharpitContext
from sharpit.engine.masking import MASK, Exposure, Masker
from sharpit.engine.probe import ProbeRequest, run_probe
from sharpit.engine.sources.dispatch import SqlEvent
from sharpit.engine.sqla.orm import _unbounded_read_statement_shape  # pyright: ignore[reportPrivateUsage]
from sharpit.engine.testsession.sink import TestSessionSink
from sharpit.settings import load_settings

ROWS = int(os.environ.get("MASKING_GATE_ROWS", "2000"))  # Task 11 runs the same gates at 60,000
pytestmark = pytest.mark.timeout(max(300, ROWS // 5))  # the time of a surface grows with the rows, not with a bug
SEEDS = (7, 8)
DIALECTS = {"generic": sql_corpus.GENERIC, "mysql": sql_corpus.MYSQL, "pg_valid": sql_corpus.POSTGRESQL}
NO_CAP = 10**6
# decision D6, issue #59: the share of the generic corpus that holds a quoted identifier; a rise must be noticed
QUOTED_IDENTIFIER_SHARE = 0.013
# spec A3: how often the fallback that loses statement text fires, per mode; a rise must be noticed
FALLBACK_SHARE = {"generic": 0.35, "mysql": 0.11, "pg_valid": 0.11}
NODE = "tests/test_x.py::test_x"
BOUND = "bound-value-7"
DETAIL = "detail-value-7"
VALUE = "hunter2plain"
ALWAYS_HIDDEN = (BOUND, DETAIL)  # what an error carries beside its statement: on no row, whatever its class

type Surface = Callable[[Masker, str], str | None]
type Driver = Callable[[Masker, str, bool], str | None]


class Carrier(NamedTuple):
    """A driver's first lines as they arrive and as they must read, and SQLAlchemy's docs link."""

    driver: str
    shown: str
    link: str


SQLITE = Carrier(
    "(sqlite3.IntegrityError) UNIQUE constraint failed: u.name",
    "(sqlite3.IntegrityError) UNIQUE constraint failed: u.name",
    "https://sqlalche.me/e/21/gkpj",
)
PYMYSQL = Carrier(  # spec A3 (r3): the tuple is opened first
    "(pymysql.err.IntegrityError) (1062, \"Duplicate entry 'x' for key 'u.name'\")",
    '(pymysql.err.IntegrityError) (1062, "Duplicate entry ?")',
    "https://sqlalche.me/e/21/gkpj",
)
PSYCOPG = Carrier(  # spec "A ``DETAIL:`` line never survives", and the first-to-last quote rule
    '(psycopg2.errors.UniqueViolation) duplicate key value violates unique constraint "u_name"\n'
    f"DETAIL:  Key (name)=({DETAIL}) already exists.\n",
    "(psycopg2.errors.UniqueViolation) duplicate key value violates unique constraint ?",
    "https://sqlalche.me/e/21/gkpj",
)


def error_text(statement: str, carrier: Carrier) -> str:
    """The text SQLAlchemy's ``DBAPIError`` gives for ``statement``."""
    return (
        f"{carrier.driver}\n[SQL: {statement}]\n[parameters: ('{BOUND}', 1)]\n"
        f"(Background on this error at: {carrier.link})"
    )


def stacktrace_text(text: str, statement: str) -> str:
    """``exception.stacktrace`` as OTel records it; the frame's code line holds the statement, as source code does."""
    code = repr(statement.splitlines()[0][:200])
    return (
        'Traceback (most recent call last):\n  File "/srv/app/db.py", line 12, in run\n'
        f"    conn.exec_driver_sql({code})\nsqlalchemy.exc.IntegrityError: {text}\n"
    )


_PROBE_RUNNER = asyncio.Runner()  # one loop for the whole gate: a new loop per row ran a test out of its timeout
atexit.register(_PROBE_RUNNER.close)


def _attribute(key: str, masker: Masker, value: str, mysql: bool) -> str | None:
    return _attributes(masker, {key: value}, mysql)[0]["value"]  # noqa: SLF001


def _recorded(masker: Masker, sql: str, mysql: bool, error: BaseException | None = None) -> dict[str, Any]:
    recorder = SqlTraceRecorder(masker, max_sql_length=NO_CAP)
    recorder.record(sql, duration_ns=1, thread="t", connection_id=None, error=error, mysql=mysql)
    return recorder.rows()[-1]


def _recorder_sql(masker: Masker, statement: str, mysql: bool) -> str | None:
    return _recorded(masker, statement, mysql)["sql"]


def _recorder_error_of_another_statement(masker: Masker, text: str, mysql: bool) -> str | None:
    return _recorded(masker, "SELECT 2", mysql, RuntimeError(text))["errorMessage"]


def _recorder_error(carrier: Carrier, mysql: bool, masker: Masker, statement: str) -> str | None:
    """The error names the statement the recorder holds, so the recorder's own replace runs."""
    return _recorded(masker, statement, mysql, RuntimeError(error_text(statement, carrier)))["errorMessage"]


def _orm_statement(_masker: Masker, statement: str, mysql: bool) -> str | None:
    """``sqla/orm.py`` masks with ``report_masker()``, whatever the caller's masker, so the argument goes unused."""
    bind = SimpleNamespace(dialect=SimpleNamespace(name="mysql" if mysql else "sqlite"))
    return _unbounded_read_statement_shape(SimpleNamespace(session=SimpleNamespace(bind=bind)), statement)[0]  # noqa: SLF001


def _test_session_sql(masker: Masker, statement: str, mysql: bool) -> str | None:
    """Unattributed, because only a test's SELECTs reach ``sql_of``; a fresh sink, as its top list keeps 500."""
    sink = TestSessionSink("gw0", masker)
    sink.on_sql(SqlEvent("sqlalchemy", statement, None, False, None, 0, 1, -1, None, None, None, mysql), None)
    return next(iter(sink.facts.top_unattributed), None)


def _test_session_exception(masker: Masker, text: str, _mysql: bool) -> str | None:
    sink = TestSessionSink("gw0", masker)
    attempt = sink.begin_test(NODE)
    sink.on_exception(RuntimeError(text), "logging", (NODE, attempt, "call"))
    assert sink.current_test is not None
    groups = sink.current_test.phases["call"].exception_groups
    return next(iter(groups.values()))[1] if groups else None


def _log_line(logger: str, masker: Masker, message: str, _mysql: bool = False) -> str | None:
    record = logging.LogRecord(logger, logging.INFO, __file__, 1, message, None, None)
    line = SharpitLogHandler(masker, None).line(record)
    return None if line is None else line["message"]


def _stored_exception(masker: Masker, exc: Exception) -> tuple[ExceptionStore, str]:
    store = ExceptionStore(5, 5, 5, masker)
    store.record(exc, "logging", None, None)
    return store, store.report()["groups"][0]["id"]


def _exception_message(masker: Masker, text: str, _mysql: bool) -> str | None:
    store, gid = _stored_exception(masker, RuntimeError(text))
    detail = store.detail(gid)
    assert detail is not None
    return detail["group"]["message"]


def _cause_message(masker: Masker, text: str, _mysql: bool) -> str | None:
    outer = RuntimeError("the read failed")
    outer.__cause__ = RuntimeError(text)
    store, gid = _stored_exception(masker, outer)
    detail = store.detail(gid)
    assert detail is not None
    return detail["causes"][0]["message"]


def _trace_status(masker: Masker, text: str, mysql: bool) -> str | None:
    span = SimpleNamespace(
        context=SimpleNamespace(trace_id=1, span_id=1),
        parent=None,
        name="query",
        kind=SimpleNamespace(name="CLIENT"),
        resource=SimpleNamespace(attributes={}),
        instrumentation_scope=SimpleNamespace(name="tests"),
        start_time=1,
        end_time=2,
        status=SimpleNamespace(status_code=SimpleNamespace(name="ERROR"), description=text),
        attributes={"db.system": "mysql" if mysql else "sqlite"},
        events=[],
    )
    return SpanBuffer(masker)._span(span)["statusMessage"]  # noqa: SLF001


def _transaction_error(masker: Masker, text: str, _mysql: bool) -> str | None:
    recorder = TransactionRecorder(masker)
    entry = recorder.begin(1, parent=None, method="a:b", thread="MainThread", trace_id=None, connection_id="db-1")
    recorder.end(entry, "UNKNOWN", RuntimeError(text))
    return recorder.report([])["entries"][0]["errorMessage"]


def _data_warning(masker: Masker, text: str, _mysql: bool) -> str | None:
    ctx: Any = SimpleNamespace(masker=masker)
    return data._masked(ctx, f"Could not read a mapper (RuntimeError: {text})").removesuffix(")")  # noqa: SLF001


def _health_failure(masker: Masker, text: str, _mysql: bool) -> str | None:
    service: Any = SimpleNamespace(_ctx=SimpleNamespace(masker=masker))
    return HealthService._failure(service, RuntimeError(text))  # noqa: SLF001


def _probe_error(masker: Masker, text: str, _mysql: bool) -> str | None:
    async def app(_scope: Any, _receive: Any, _send: Any) -> None:
        raise RuntimeError(text)

    return _PROBE_RUNNER.run(run_probe(app, ProbeRequest("GET", "/fail", "", {}), {}, "", masker))["error"]


def _postgresql_failure(masker: Masker, statement: str) -> str | None:
    ctx: Any = SimpleNamespace(masker=masker)
    return postgresql_sections._describe(ctx, "Indexes", RuntimeError(error_text(statement, PSYCOPG)))  # noqa: SLF001


def _mysql_failure(masker: Masker, statement: str) -> str | None:
    return mysql_sections._reason(masker, RuntimeError(error_text(statement, PYMYSQL)))  # noqa: SLF001


LAST_ERROR_HEAD = "Worker 1 failed executing transaction"


def _mysql_last_error(masker: Masker, statement: str) -> str | None:
    """MySQL's replication applier names the failed statement in ``last_error_message``."""
    where = "Error 'Duplicate entry' on query. Default database: 'app'."
    message = f"{LAST_ERROR_HEAD} 'ANONYMOUS'; {where} Query: '{statement}'"
    conn = FakeMySqlConnection().with_rows("REPLICATION", {"channel_name": "", "last_error_message": message})
    found = DataSourceData("primary")
    collect_replication(conn, RowLimits(), found, masker)
    return found.replication_channels[0]["lastErrorMessage"]


def _context(registry: Any) -> SharpitContext:
    activation = ActivationStatus(True, True, "Enabled by SHARPIT_ENABLED=ON", ())
    introspector: Any = SimpleNamespace(app_info=lambda: None, routes=list, providers=list)
    ctx = SharpitContext(load_settings({"config_scan": False}, {}), activation, introspector)
    ctx.capture.engine_registry = registry
    return ctx


_PG_ENGINE = FakePgEngine()
_MYSQL_ENGINE = FakeMySqlEngine()


@functools.cache
def _pg_context() -> SharpitContext:
    pytest.importorskip("sqlalchemy")  # a refresh reports DISABLED until the host has imported it
    return _context(PgRegistry(("primary", _PG_ENGINE)))


@functools.cache
def _mysql_context() -> SharpitContext:
    pytest.importorskip("sqlalchemy")
    return _context(MySqlRegistry(("primary", _MYSQL_ENGINE)))


def _postgresql_refused(_masker: Masker, statement: str) -> str | None:
    """``postgresql/service.py``, its own ``mask_error`` call; the context holds its own masker, the same policy."""
    _PG_ENGINE.refuse = error_text(statement, PSYCOPG)
    return _PROBE_RUNNER.run(refresh_postgresql(_pg_context()))["databases"][0]["message"]


def _mysql_refused(_masker: Masker, statement: str) -> str | None:
    """``mysql/service.py``, its own ``mask_error`` call; the context holds its own masker, the same policy."""
    _MYSQL_ENGINE.refuse = error_text(statement, PYMYSQL)
    return _PROBE_RUNNER.run(refresh_mysql(_mysql_context()))["dataSources"][0]["message"]


def _query_text(masker: Masker, statement: str) -> str | None:
    return query_text(masker, statement, NO_CAP)


def _mysql_query_text(masker: Masker, statement: str) -> str | None:
    return mysql_query_text(masker, statement, NO_CAP)


STATEMENT_DRIVERS: dict[str, Driver] = {
    "db_statement": partial(_attribute, "db.statement"),
    "db_query_text": partial(_attribute, "db.query.text"),
    "recorder_sql": _recorder_sql,
    "orm_statement": _orm_statement,
    "test_session_sql": _test_session_sql,
}
ERROR_DRIVERS: dict[str, Driver] = {
    "recorder_error_of_another_statement": _recorder_error_of_another_statement,
    "exception_message_attribute": partial(_attribute, "exception.message"),
    "trace_status": _trace_status,
    "log_handler_error": partial(_log_line, "host.app"),
    "exception_message": _exception_message,
    "causes": _cause_message,
    "transactions": _transaction_error,
    "data": _data_warning,
    "health": _health_failure,
    "probe": _probe_error,
    "test_session_exception": _test_session_exception,
}
MODES = (("generic", False, SQLITE), ("mysql", True, PYMYSQL))


def _driven(driver: Driver, mysql: bool, masker: Masker, statement: str) -> str | None:
    return driver(masker, statement, mysql)


def _driven_error(driver: Driver, mysql: bool, carrier: Carrier, masker: Masker, statement: str) -> str | None:
    return driver(masker, error_text(statement, carrier), mysql)


def _stacktrace(mysql: bool, carrier: Carrier, masker: Masker, statement: str) -> str | None:
    text = stacktrace_text(error_text(statement, carrier), statement)
    return _attribute("exception.stacktrace", masker, text, mysql)


def _statement_surfaces() -> dict[str, Surface]:
    surfaces: dict[str, Surface] = {
        f"{name}-{mode}": partial(_driven, driver, mysql)
        for name, driver in STATEMENT_DRIVERS.items()
        for mode, mysql, _ in MODES
    }
    # generic only: a log record names no driver, so nothing tells the handler the text is MySQL's
    surfaces["log_handler_statement-generic"] = partial(_log_line, "sqlalchemy.engine.Engine")
    surfaces["mysql_query_text-mysql"] = _mysql_query_text
    surfaces["query_text-pg_valid"] = _query_text
    return surfaces


def _error_surfaces() -> dict[str, tuple[Surface, Carrier]]:
    surfaces: dict[str, tuple[Surface, Carrier]] = {}
    for mode, mysql, carrier in MODES:
        for name, driver in ERROR_DRIVERS.items():
            surfaces[f"{name}-{mode}"] = (partial(_driven_error, driver, mysql, carrier), carrier)
        surfaces[f"recorder_error-{mode}"] = (partial(_recorder_error, carrier, mysql), carrier)
        surfaces[f"exception_stacktrace-{mode}"] = (partial(_stacktrace, mysql, carrier), carrier)
    surfaces["postgresql_error-generic"] = (_postgresql_failure, PSYCOPG)
    surfaces["mysql_error-mysql"] = (_mysql_failure, PYMYSQL)
    surfaces["postgresql_refused-generic"] = (_postgresql_refused, PSYCOPG)
    surfaces["mysql_refused-mysql"] = (_mysql_refused, PYMYSQL)
    return surfaces


STATEMENT_SURFACES = _statement_surfaces()
ERROR_SURFACES = _error_surfaces()
SURFACES: dict[str, Surface] = {
    **STATEMENT_SURFACES,
    **{name: surface for name, (surface, _) in ERROR_SURFACES.items()},
    "mysql_last_error-mysql": _mysql_last_error,  # the applier's text, with no ``[SQL: `` block to parse back
}
# these cut what they show: a statement over the limit cannot equal ``expected`` there, and A1 still reads it
CAPPED = {"log_handler_statement-generic", *ERROR_SURFACES}
NEEDS_SQLALCHEMY = {"postgresql_refused-generic", "mysql_refused-mysql"}
_MASKER = Masker(Exposure.MASKED, True)
_BLOCK = re.compile(r"\[SQL: (.*?)\]?\s*(?:\[parameters: |\(Background on |\Z)", re.DOTALL)
_REGIONS = re.compile(
    r"(?P<driver>.*?)\n+\[SQL: (?P<sql>.*)\]\n\[parameters: (?P<parameters>.*)\]\n"
    r"\(Background on this error at: (?P<link>\S+)\)\s*",
    re.DOTALL,
)


def failures_visible(surface: Surface, rows: Sequence[Row]) -> list[Row]:
    """A1: the rows showing a marker or a value an error carries. No output is a failure: it proved nothing."""
    failing: list[Row] = []
    for row in rows:
        shown = surface(_MASKER, row.text)
        if shown is None or any(hidden in shown for hidden in (*row.markers, *ALWAYS_HIDDEN)):
            failing.append(row)
    return failing


def quoted_identifiers_shown(surface: Surface, rows: Sequence[Row]) -> list[Row]:
    """D6: the rows showing a quoted identifier, the one exception to A1's target of 0. Counted, not failed."""
    return [
        row
        for row in rows
        if row.quoted_identifier and any(name in (surface(_MASKER, row.text) or "") for name in row.quoted_identifier)
    ]


def _statement_of(shown: str | None) -> str | None:
    """The statement in ``shown``: an error's block, wherever it ends. Regions are ``failures_regions``'s job."""
    if shown is None:
        return None
    block = _BLOCK.search(shown)
    return block.group(1) if block else shown


def _shape_fails(row: Row, statement: str | None) -> bool:
    if row.plain:
        return statement != row.expected
    return statement is None or row.tail not in statement


def failures_shape(surface: Surface, rows: Sequence[Row]) -> list[Row]:
    """A3, the anti-blanking oracle: a ``plain`` row must equal the template, any other row must keep its tail.

    An ambiguous row is plain and equals its cut, so a statement that reads one way cannot take the fallback: that is
    spec A3's "0 on statements that read one way".
    """
    return [row for row in rows if _shape_fails(row, _statement_of(surface(_MASKER, row.text)))]


def broken_regions(shown: str | None, carrier: Carrier, tail: str = "", statement: str | None = None) -> list[str]:
    """The regions of an error that do not read back; none means driver line, block, parameters and link all do."""
    found = _REGIONS.fullmatch(shown or "")
    if found is None:
        return ["structure"]
    holds = {
        "driver": found["driver"].endswith(carrier.shown),
        "block": tail in found["sql"] and statement in (None, found["sql"]),
        "parameters": found["parameters"] == MASK,
        "link": found["link"] == carrier.link,
    }
    return [region for region, held in holds.items() if not held]


def _closes(row: Row) -> bool:
    """Whether the block can end: an ambiguous statement or one past the scan limit has no closer to find (spec §3)."""
    return not row.ambiguous and len(row.text) <= sql_corpus.SCAN_LIMIT


def failures_regions(surface: Surface, rows: Sequence[Row], carrier: Carrier) -> list[Row]:
    """A3: the rows whose error does not parse back. ``failures_visible`` reads the rest, for the carried values."""
    return [row for row in rows if _closes(row) and broken_regions(surface(_MASKER, row.text), carrier, row.tail)]


@functools.cache
def gate_rows(mode: str) -> tuple[Row, ...]:
    return tuple(row for seed in SEEDS for row in sql_corpus.rows(seed, ROWS, DIALECTS[mode]))


def _params(names: Iterable[str]) -> list[Any]:
    """Surface names as parameters: a refresh needs SQLAlchemy imported, and the no-sqlalchemy job has none."""
    return [pytest.param(n, marks=pytest.mark.needs_sqlalchemy) if n in NEEDS_SQLALCHEMY else n for n in names]


def _mode(name: str) -> str:
    return name.rsplit("-", 1)[1]


def _summary(failing: Sequence[Row], total: int) -> str:
    return f"{len(failing)} of {total} rows; first, {failing[0].shape}: {failing[0].text[:200]!r}" if failing else ""


# --- the corpus ------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("dialect", DIALECTS.values())
def test_the_corpus_is_seeded(dialect: str) -> None:
    assert sql_corpus.rows(7, 300, dialect) == sql_corpus.rows(7, 300, dialect)


def test_the_corpus_refuses_an_unknown_dialect() -> None:
    with pytest.raises(ValueError, match="oracle"):
        sql_corpus.rows(7, 1, "oracle")


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("dialect", DIALECTS.values())
def test_every_row_holds_its_markers_and_expected_shows_none(dialect: str, seed: int) -> None:
    for row in sql_corpus.rows(seed, 30_000, dialect):
        assert row.markers, row.text
        assert all(marker in row.text for marker in row.markers), row.text
        assert not any(marker in row.expected for marker in row.markers), row.text


@pytest.mark.parametrize(
    ("dialect", "shapes"),
    [
        (sql_corpus.GENERIC, {"shapes", "sensitive_name", "sensitive_table", "comments", "names", "trailing_backslash",
                              "nested_comment", "oracle_quote", "hash", "unclosed_dollar", "long_literal",
                              "long_identifier", "odd_bracket", "quiet_trigger", "executable_comment", "tight_dash",
                              "at_dollar", "backtick_quote", "dollar_names", "digit_bracket", "dot_digit",
                              "doubled_quote", "tight_verb", "unlisted_verb", "unicode_space"}),
        (sql_corpus.MYSQL, {"shapes", "sensitive_name", "sensitive_table", "comments", "names", "hash", "long_literal",
                            "long_identifier", "mysql_escaped", "quiet_trigger", "mysql_name", "executable_comment",
                            "mysql_routine", "family_dollar", "dot_digit", "tight_verb", "unlisted_verb",
                            "unicode_space"}),
        (sql_corpus.POSTGRESQL, {"shapes", "sensitive_name", "sensitive_table", "comments", "names",
                                 "trailing_backslash", "nested_comment", "unclosed_dollar", "long_literal",
                                 "tight_verb", "unicode_space"}),
    ],
    ids=DIALECTS,
)  # fmt: skip
def test_a_dialect_holds_exactly_its_valid_classes(dialect: str, shapes: set[str]) -> None:
    assert {row.shape for row in sql_corpus.rows(7, 2000, dialect)} == shapes


@pytest.mark.parametrize("dialect", DIALECTS.values())
def test_the_corpus_crosses_the_scan_limit(dialect: str) -> None:
    long = [row for row in sql_corpus.rows(7, 2000, dialect) if row.shape == "long_literal"]
    assert long
    assert all(row.text.index(row.markers[1]) < sql_corpus.SCAN_LIMIT for row in long)
    assert all(row.text.index(row.markers[2]) > sql_corpus.SCAN_LIMIT for row in long)


def test_a_cut_identifier_opens_before_the_limit_and_closes_after_it() -> None:
    long = [row for row in sql_corpus.rows(7, 2000) if row.shape == "long_identifier"]
    assert long
    assert all(row.text.index('"') < sql_corpus.SCAN_LIMIT for row in long)
    assert all(row.text.rindex('"') > sql_corpus.SCAN_LIMIT for row in long)


@pytest.mark.parametrize(
    ("mode", "shapes"),
    [
        (
            "generic",
            {
                "trailing_backslash",
                "nested_comment",
                "oracle_quote",
                "hash",
                "odd_bracket",
                "executable_comment",
                "tight_dash",
                "at_dollar",
                "backtick_quote",
            },
        ),
        ("mysql", {"mysql_escaped", "executable_comment", "family_dollar"}),
        ("pg_valid", {"trailing_backslash"}),
    ],
)
def test_the_corpus_marks_only_the_valid_shapes_ambiguous(mode: str, shapes: set[str]) -> None:
    assert {row.shape for row in sql_corpus.rows(7, 2000, DIALECTS[mode]) if row.ambiguous} == shapes


@pytest.mark.parametrize("mode", DIALECTS)
def test_an_ambiguous_row_is_plain(mode: str) -> None:
    assert all(row.plain for row in gate_rows(mode) if row.ambiguous)


@pytest.mark.parametrize("mode", DIALECTS)
def test_the_fallback_is_counted(mode: str) -> None:
    rows = gate_rows(mode)
    counted = collections.Counter(row.shape for row in rows if row.ambiguous)
    print(f"fallback {mode}: {sum(counted.values())} of {len(rows)} rows, {dict(counted)}")
    assert sum(counted.values()) <= FALLBACK_SHARE[mode] * len(rows), counted


@pytest.mark.parametrize("mode", DIALECTS)
def test_a_row_that_is_not_plain_names_its_tail(mode: str) -> None:
    assert all(row.tail for row in gate_rows(mode) if not row.plain)


def test_the_corpus_imports_no_lexer() -> None:
    tree = ast.parse(Path(sql_corpus.__file__).read_text(encoding="utf-8"))
    imported = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    imported |= {node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    assert imported
    assert not [name for name in imported if name.split(".")[0] == "sharpit"]


# --- A1 --------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("name", _params(SURFACES))
def test_no_literal_is_visible(name: str) -> None:
    rows = gate_rows(_mode(name))
    failing = failures_visible(SURFACES[name], rows)
    assert not failing, _summary(failing, len(rows))


def test_the_corpus_holds_its_share_of_quoted_identifiers() -> None:
    """Reads the corpus, not a build. The population share is 0.010, so at 2,000 rows a seed pair can land over the cap
    on noise alone; at 20,000 it would take six standard deviations."""
    rows = [row for seed in SEEDS for row in sql_corpus.rows(seed, max(ROWS, 20_000))]
    in_corpus = sum(bool(row.quoted_identifier) for row in rows)
    assert in_corpus > 0
    assert in_corpus <= QUOTED_IDENTIFIER_SHARE * len(rows)


@pytest.mark.parametrize("name", _params(name for name in SURFACES if name.endswith("-generic")))
def test_a_quoted_identifier_is_counted_not_failed(name: str) -> None:
    """D6 keeps a name readable, and the count is what the template says: fewer means a name was lost to a cut."""
    rows = gate_rows("generic")
    in_corpus = sum(bool(row.quoted_identifier) for row in rows)
    shown = quoted_identifiers_shown(SURFACES[name], rows)
    print(f"D6 {name}: {len(shown)} of {in_corpus} rows")
    assert len(shown) == in_corpus, f"{len(shown)} of {in_corpus} rows show their quoted identifier"


# --- A3 --------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("name", _params(name for name in SURFACES if name != "mysql_last_error-mysql"))
def test_output_equals_the_expected_shape(name: str) -> None:
    rows = [row for row in gate_rows(_mode(name)) if not (name in CAPPED and len(row.text) > sql_corpus.SCAN_LIMIT)]
    failing = failures_shape(SURFACES[name], rows)
    assert not failing, _summary(failing, len(rows))


@pytest.mark.parametrize("name", _params(ERROR_SURFACES))
def test_an_error_keeps_its_regions(name: str) -> None:
    surface, carrier = ERROR_SURFACES[name]
    rows = gate_rows(_mode(name))
    failing = failures_regions(surface, rows, carrier)
    assert not failing, f"{_summary(failing, sum(_closes(row) for row in rows))}"


def test_a_correct_stacktrace_parses_back() -> None:
    """The oracle itself: a traceback ends in a newline, which is no reason to fail a correct render."""
    shown = f"{SQLITE.shown}\n[SQL: SELECT ?]\n[parameters: {MASK}]\n(Background on this error at: {SQLITE.link})"
    assert broken_regions(stacktrace_text(shown, "SELECT 1"), SQLITE) == []


def test_the_applier_error_stays_readable() -> None:
    assert (_mysql_last_error(_MASKER, "SELECT 1") or "").startswith(LAST_ERROR_HEAD)


@pytest.fixture(scope="module")
def live_error() -> str:
    """A real SQLAlchemy error on a live SQLite: spec A3's example, bound parameters and all."""
    sa = pytest.importorskip("sqlalchemy")
    engine = sa.create_engine("sqlite://")
    with engine.connect() as conn:
        conn.exec_driver_sql("CREATE TABLE u (id INTEGER, name TEXT UNIQUE, note TEXT)")
        conn.exec_driver_sql("INSERT INTO u VALUES (?, ?, ?)", (1, BOUND, "x"))
        with pytest.raises(sa.exc.IntegrityError) as caught:
            conn.exec_driver_sql("INSERT INTO u VALUES (?, ?, ?)", (2, BOUND, "x"))
    return str(caught.value)


@pytest.mark.needs_sqlalchemy
@pytest.mark.parametrize("name", ERROR_DRIVERS)
def test_a_live_error_stays_readable(name: str, live_error: str) -> None:
    driver_line = live_error.split("\n", 1)[0]
    link = re.search(r"https://sqlalche\.me/\S+?(?=\))", live_error)
    assert link is not None
    shown = ERROR_DRIVERS[name](_MASKER, live_error, False)
    carrier = Carrier(driver_line, driver_line, link.group())
    assert broken_regions(shown, carrier, statement="INSERT INTO u VALUES (?, ?, ?)") == []


# --- the masker reads the recorder's statement, 2026-11-05 design section 10 step 1 ---------------------------------

CODE_TOKEN = "ghp_" + "a1B2" * 9
CODE_POSITIONS = {
    "url_query": f"SELECT * FROM t WHERE u = 'x' AND note = https://h/?token={CODE_TOKEN}",
    "alias": f"SELECT 1 AS {CODE_TOKEN}",
    "pair": f"SELECT * FROM t WHERE api_key={CODE_TOKEN}",
}


@pytest.mark.parametrize("name", ["recorder_sql-generic", "recorder_sql-mysql"])
@pytest.mark.parametrize("statement", CODE_POSITIONS.values(), ids=CODE_POSITIONS)
def test_the_masker_reads_the_recorders_statement(name: str, statement: str) -> None:
    assert CODE_TOKEN not in _shown_by(name, statement)


# --- A4: each trigger survives every other job ---------------------------------------------------------------------

# PostgreSQL reads ``"..."`` as a name, so there these two statements hold no value
DOUBLE_QUOTED_VALUE = [name for name in SURFACES if name != "query_text-pg_valid"]


def _shown_by(name: str, statement: str) -> str:
    shown = SURFACES[name](_MASKER, statement)
    assert shown is not None
    return shown


@pytest.mark.parametrize("name", _params(SURFACES))
def test_key_survives_the_scan(name: str) -> None:
    assert VALUE not in _shown_by(name, f"SELECT 'pwd': {VALUE} FROM t")


@pytest.mark.parametrize("name", _params(SURFACES))
def test_quote_survives_the_scheme(name: str) -> None:
    assert VALUE not in _shown_by(name, f"SELECT 'Basic plan', '{VALUE}' FROM t")


@pytest.mark.parametrize("name", _params(DOUBLE_QUOTED_VALUE))
def test_value_position_survives_the_scheme(name: str) -> None:
    assert VALUE not in _shown_by(name, f'SELECT id FROM t WHERE basic = "{VALUE}"')


@pytest.mark.parametrize("name", _params(DOUBLE_QUOTED_VALUE))
def test_newline_pair_keeps_the_value_hidden(name: str) -> None:
    assert VALUE not in _shown_by(name, f'UPDATE t SET pwd=\n"{VALUE}", note=? WHERE id=?')


@pytest.mark.parametrize("name", _params(name for name in SURFACES if name != "mysql_last_error-mysql"))
def test_a_sensitive_column_keeps_where(name: str) -> None:
    assert "WHERE id=?" in _shown_by(name, "UPDATE users SET password=? WHERE id=?")
