"""Every surface that renders SQL or an error, under every exposure, capture setting, mask setting and dialect.

The rules are the owner's (item 7, 2026-11-07) and the masking contract's: ``METADATA_ONLY`` shows no value; sharpit's
own token is never shown, ``FULL`` included; capture on keeps ``mask_text`` on a known dialect; an ``UNSUPPORTED``
statement is the marker at every exposure, ``FULL`` included, and capture on does not lift it; an ``UNSUPPORTED``
driver error renders as a classified one and never shows the driver's text. A cell fails by naming the rule it broke.
"""

# derived: architecture spec section 7 and the owner's item 7 ruling, no BootUI source

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

import pytest
from tests.masking.test_statement_surfaces import (
    ERROR_DRIVERS,
    STATEMENT_DRIVERS,
    Driver,
    _mysql_query_text,  # pyright: ignore[reportPrivateUsage]
    _query_text,  # pyright: ignore[reportPrivateUsage]
)

from sharpit.engine import sqltext
from sharpit.engine.capture.logtail import SharpitLogHandler
from sharpit.engine.capture.sqltrace import SqlTraceRecorder
from sharpit.engine.masking import Exposure, Masker
from sharpit.engine.sqltext import Dialect

MARKER = "[statement hidden: unsupported database]"
OWN = "sharpitOwnToken7f3a9c"  # the console's token: never shown, whatever the exposure
VALUE = "hunter2plain"  # an inline literal no pattern knows
PATTERN = "ghp_" + "a1B2" * 9  # an inline literal ``mask_text`` knows
BOUND = "s3cretParam"
FREE = "FREEDRIVERTEXT"
STATEMENT = f"SELECT * FROM t WHERE a = '{VALUE}' AND b = '{PATTERN}' AND c = '{OWN}'"
DRIVERS = {
    Dialect.POSTGRESQL: ("psycopg", "ProgrammingError"),
    Dialect.MYSQL_FAMILY: ("pymysql.err", "ProgrammingError"),
    Dialect.SQLITE: ("sqlite3", "OperationalError"),
    Dialect.UNSUPPORTED: ("pyodbc", "ProgrammingError"),
}
EXPOSURES = {"masked": Exposure.MASKED, "full": Exposure.FULL, "metadata_only": Exposure.METADATA_ONLY}
CAPTURES = {"capture_off": False, "capture_on": True}
MASKS = {"mask_on": True, "mask_off": False}
DIALECTS = {
    "postgresql": Dialect.POSTGRESQL,
    "mysql_family": Dialect.MYSQL_FAMILY,
    "sqlite": Dialect.SQLITE,
    "unsupported": Dialect.UNSUPPORTED,
}


def error_string(dialect: Dialect) -> str:
    """The text SQLAlchemy's ``DBAPIError`` gives: driver line, block, parameters and docs link."""
    module, name = DRIVERS[dialect]
    return (
        f"({module}.{name}) {FREE} near WHERE\n[SQL: {STATEMENT}]\n[parameters: ('{BOUND}',)]\n"
        "(Background on this error at: https://sqlalche.me/e/21/f405)"
    )


def error_exception(dialect: Dialect) -> BaseException:
    sa_exc = pytest.importorskip("sqlalchemy.exc")
    module, name = DRIVERS[dialect]
    driver = type(name, (Exception,), {"__module__": module})(f"{FREE} near WHERE")
    return sa_exc.ProgrammingError(STATEMENT, (BOUND,), driver)


def _statement_text(masker: Masker, dialect: Dialect) -> str | None:
    return sqltext.statement_text(masker, STATEMENT, dialect)


def _statement_shape(masker: Masker, dialect: Dialect) -> str | None:
    shape = sqltext.statement_shape(masker, STATEMENT, dialect)
    return f"{shape.text}\n{shape.fingerprint}"


def _error_text_of_str(masker: Masker, dialect: Dialect) -> str | None:
    return sqltext.error_text(masker, error_string(dialect), dialect)


def _error_text_of_exception(masker: Masker, dialect: Dialect) -> str | None:
    return sqltext.error_text(masker, error_exception(dialect), dialect)


def _recorder_entry(masker: Masker, dialect: Dialect) -> str | None:
    """The whole stored row: statement, parameters and error, as the SQL panel, MCP and CLI read it."""
    recorder = SqlTraceRecorder(masker, max_sql_length=10**6)
    recorder.record(
        STATEMENT,
        duration_ns=1,
        thread="t",
        connection_id=None,
        dialect=dialect,
        parameters=(BOUND,),
        error=error_exception(dialect),
    )
    return json.dumps(recorder.rows()[-1], default=str)


def _log_line_of(logger: str, masker: Masker, message: str, dialect: Dialect) -> str | None:
    """The log tail, with the application's family the cell names: ``logtail.py`` reads its dialect from there."""
    family = None if dialect is Dialect.UNSUPPORTED else dialect
    record = logging.LogRecord(logger, logging.INFO, __file__, 1, message, None, None)
    line = SharpitLogHandler(masker, None, application=lambda: family).line(record)
    return None if line is None else line["message"]


def _log_statement(masker: Masker, dialect: Dialect) -> str | None:
    return _log_line_of("sqlalchemy.engine.Engine", masker, STATEMENT, dialect)


def _log_error(masker: Masker, dialect: Dialect) -> str | None:
    return _log_line_of("host.app", masker, error_string(dialect), dialect)


Surface = Callable[[Masker, Dialect], str | None]


def _statement_driver(driver: Driver) -> Surface:
    return lambda masker, dialect: driver(masker, STATEMENT, dialect)


def _error_driver(driver: Driver) -> Surface:
    return lambda masker, dialect: driver(masker, error_string(dialect), dialect)


SURFACES: dict[str, Surface] = {
    "statement_text": _statement_text,
    "statement_shape": _statement_shape,
    "error_text_str": _error_text_of_str,
    "error_text_exception": _error_text_of_exception,
    "recorder_entry": _recorder_entry,
    "logtail_statement": _log_statement,
    "logtail_error": _log_error,
    **{name: _statement_driver(driver) for name, driver in STATEMENT_DRIVERS.items()},
    **{name: _error_driver(driver) for name, driver in ERROR_DRIVERS.items() if name != "log_handler_error"},
}
# these resolve their family from an application that names none, so they read as UNSUPPORTED whatever the cell says:
# only the UNSUPPORTED column is a real cell for them
UNSUPPORTED_ONLY = {
    "exception_message",
    "causes",
    "transactions",
    "data",
    "health",
    "probe",
    "test_session_exception",
}
# ``sqla/orm.py`` masks with ``report_masker()``, the default policy, whatever the console's: only that policy's cells
DEFAULT_POLICY_ONLY = {"orm_statement"}
# a server's own statement text: read only on its own database
ONE_DIALECT: dict[str, tuple[Callable[[Masker, str], str | None], Dialect]] = {
    "postgresql_query_text": (_query_text, Dialect.POSTGRESQL),
    "mysql_query_text": (_mysql_query_text, Dialect.MYSQL_FAMILY),
}
STATEMENT_ONLY = {"statement_text", "statement_shape", "logtail_statement", *STATEMENT_DRIVERS, *ONE_DIALECT}
# a hidden statement has no identity, so the test session lists none: nothing shown, which hides more than the marker
NOTHING_FOR_UNSUPPORTED = {"test_session_sql"}


def _applies(name: str, exposure: str, capture: str, mask: str, member: Dialect) -> bool:
    if name in ONE_DIALECT:
        return ONE_DIALECT[name][1] is member
    if name in UNSUPPORTED_ONLY:
        return member is Dialect.UNSUPPORTED
    if name in DEFAULT_POLICY_ONLY:
        return (exposure, capture, mask) == ("masked", "capture_off", "mask_on")
    return True


def _cells() -> list[Any]:
    return [
        pytest.param(name, exposure, capture, mask, dialect, id=f"{name}-{exposure}-{capture}-{mask}-{dialect}")
        for exposure in EXPOSURES
        for capture in CAPTURES
        for mask in MASKS
        for dialect, member in DIALECTS.items()
        for name in [*SURFACES, *ONE_DIALECT]
        if _applies(name, exposure, capture, mask, member)
    ]


def _shown(name: str, masker: Masker, dialect: Dialect) -> str | None:
    if name in ONE_DIALECT:
        return ONE_DIALECT[name][0](masker, STATEMENT)
    return SURFACES[name](masker, dialect)


def violations(
    shown: str | None, surface: str, exposure: Exposure, capture: bool, mask: bool, dialect: Dialect
) -> list[str]:
    """The rules ``shown`` breaks; ``[]`` when it holds every one that applies to its cell."""
    text = (shown or "").lower()
    broken: list[str] = []

    def never(rule: str, *values: str) -> None:
        broken.extend(f"{rule}: {value} shown" for value in values if value.lower() in text)

    never("sharpit's own token is never shown", OWN)
    if exposure is Exposure.METADATA_ONLY:
        never("METADATA_ONLY shows no value", VALUE, PATTERN, BOUND, FREE)
        return broken
    if dialect is Dialect.UNSUPPORTED:
        never("an UNSUPPORTED statement is hidden, capture on included", VALUE, PATTERN)
        if surface not in STATEMENT_ONLY:
            never("an UNSUPPORTED driver error never shows driver text", FREE)
        if MARKER.lower() not in text and not (shown is None and surface in NOTHING_FOR_UNSUPPORTED):
            broken.append("an UNSUPPORTED statement shows the marker")
    if exposure is Exposure.MASKED and mask and capture and dialect is not Dialect.UNSUPPORTED:
        never("capture on keeps mask_text on a known dialect", PATTERN)
    if exposure is Exposure.MASKED and mask and not capture:
        never("MASKED with capture off shows no inline literal or bound value", VALUE, PATTERN, BOUND)
    return broken


@pytest.mark.parametrize(("surface", "exposure", "capture", "mask", "dialect"), _cells())
def test_surface_under_exposure(surface: str, exposure: str, capture: str, mask: str, dialect: str) -> None:
    member = DIALECTS[dialect]
    policy = EXPOSURES[exposure]
    masker = Masker(policy, MASKS[mask], token=OWN, capture_parameters=CAPTURES[capture])
    shown = _shown(surface, masker, member)
    assert violations(shown, surface, policy, CAPTURES[capture], MASKS[mask], member) == [], shown
