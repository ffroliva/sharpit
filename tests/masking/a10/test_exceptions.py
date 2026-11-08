from __future__ import annotations

import logging

import pytest
import sqlalchemy as sa

from sharpit.engine.capture.exceptions import ExceptionStore
from sharpit.engine.capture.logtail import SharpitLogHandler
from sharpit.engine.masking import Exposure, Masker
from sharpit.engine.sqltext import Dialect, error_text

MASKER = Masker(Exposure.MASKED, True)
SECRET = "A10" + "DRIVER" + "VALUE"
pytestmark = pytest.mark.needs_sqlalchemy


def test_error_text_reads_real_sqlalchemy_exception_without_tuple_message() -> None:
    import pymysql

    original = pymysql.err.OperationalError(1644, f"bad password {SECRET}")
    error = sa.exc.DBAPIError.instance("SELECT 1", (), original, pymysql.err.Error)

    shown = error_text(MASKER, error, Dialect.MYSQL_FAMILY)

    assert SECRET not in (shown or "")
    assert "1644" in (shown or "")


@pytest.mark.parametrize("surface", ["exception_store", "logtail"])
def test_exception_surfaces_mask_object_messages(surface: str) -> None:
    error = RuntimeError(f"failed password='{SECRET}'")
    if surface == "exception_store":
        store = ExceptionStore(10, 5, 20, MASKER, lambda: Dialect.SQLITE)
        store.record(error, "test", None, None)
        shown = next(iter(store._groups.values())).message
    else:
        handler = SharpitLogHandler.__new__(SharpitLogHandler)
        logging.Handler.__init__(handler)
        handler.masker = MASKER
        handler.application = lambda: Dialect.SQLITE
        row = handler.line(logging.LogRecord("app", logging.ERROR, "f", 1, "%s", (error,), None))
        shown = None if row is None else row["message"]

    assert SECRET not in (shown or "")


@pytest.mark.parametrize("kind", ["str_raises", "huge_message"])
def test_an_exception_that_cannot_be_read_fails_closed(kind: str) -> None:
    if kind == "str_raises":
        error = type("Broken", (Exception,), {"__str__": lambda _self: (_ for _ in ()).throw(RuntimeError())})()
    else:
        error = RuntimeError("x" * (1024 * 1024))

    shown = error_text(MASKER, error, Dialect.UNSUPPORTED)

    assert shown is None


def test_a_record_with_no_proof_counts_in_the_bucket() -> None:
    from tests.masking.a10.conftest import a10_surface

    rows = [("no_proof", Dialect.SQLITE, Dialect.UNSUPPORTED, "", "")]
    report = a10_surface("exceptions", lambda: rows)
    assert report.counts["no_proof"] == 1


def test_exception_store_keeps_ordinary_value_error_cause_and_hides_sqlite_driver_cause() -> None:
    store = ExceptionStore(10, 5, 20, MASKER, lambda: Dialect.SQLITE)
    try:
        try:
            raise ValueError("bad number")
        except ValueError as cause:
            raise RuntimeError("outer ordinary") from cause
    except RuntimeError as ordinary_outer:
        store.record(ordinary_outer, "test", None, None)

    with sa.create_engine("sqlite://").connect() as connection:
        try:
            connection.exec_driver_sql(f"ATTACH DATABASE '/no/dir/{SECRET}' AS x")
        except Exception as db_outer:  # noqa: BLE001
            store.record(db_outer, "test", None, None)

    groups = {group["message"]: group["id"] for group in store.report()["groups"]}
    ordinary_detail = store.detail(groups["outer ordinary"])
    assert ordinary_detail is not None
    ordinary_cause = ordinary_detail["causes"][0]
    assert ordinary_cause["exceptionClassName"] == "ValueError"
    assert ordinary_cause["message"] == "bad number"
    assert len(ordinary_cause["frames"]) >= 1
    assert isinstance(ordinary_cause["commonFrames"], int)

    db_gid = next(gid for msg, gid in groups.items() if msg != "outer ordinary")
    db_detail = store.detail(db_gid)
    assert db_detail is not None
    db_cause = db_detail["causes"][0]
    assert db_cause["exceptionClassName"] == "sqlite3.OperationalError"
    assert db_cause["message"] == "(sqlite3.OperationalError) SQLITE_CANTOPEN"  # owner 2026-11-07: structured codes
    assert SECRET not in str(db_cause)
    assert len(db_cause["frames"]) >= 1


def test_mysql_driver_cause_keeps_numeric_code_without_message() -> None:
    import pymysql

    store = ExceptionStore(10, 5, 20, MASKER, lambda: Dialect.MYSQL_FAMILY)
    try:
        try:
            raise pymysql.err.OperationalError(1644, f"Access denied for user {SECRET}")
        except pymysql.err.OperationalError as driver_cause:
            direct_shown = error_text(MASKER, driver_cause, Dialect.MYSQL_FAMILY)
            raise RuntimeError("mysql wrapper") from driver_cause
    except RuntimeError as outer:
        store.record(outer, "test", None, None)

    assert direct_shown == "(pymysql.err.OperationalError) 1644"
    assert SECRET not in (direct_shown or "")
    gid = store.report()["groups"][0]["id"]
    detail = store.detail(gid)
    assert detail is not None
    cause = detail["causes"][0]
    assert cause["exceptionClassName"] == "pymysql.err.OperationalError"
    assert cause["message"] == "(pymysql.err.OperationalError) 1644"
    assert SECRET not in str(detail)
    assert len(cause["frames"]) >= 1
