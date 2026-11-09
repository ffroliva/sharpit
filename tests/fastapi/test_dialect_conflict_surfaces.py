"""A dialect conflict on the error path hides the statement on every surface, with a real sqlite3 error.

# derived: BootUI has no dialect resolver. Spec section 6: conflicts hide. The engine says MySQL and the driver chain
says SQLite, so no reading of the text can be trusted: nothing past a ``#`` may show, whichever reading is true.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator

import pytest

sa = pytest.importorskip("sqlalchemy")

from fastapi.testclient import TestClient  # noqa: E402

from fastapi import FastAPI  # noqa: E402
from sharpit import install  # noqa: E402
from sharpit.engine import sqla  # noqa: E402
from sharpit.engine.capture.errortext import mask_error  # noqa: E402
from sharpit.engine.context import application_family  # noqa: E402
from sharpit.engine.sqla.dialect_source import exception_dialect  # noqa: E402
from sharpit.engine.sqltext import Dialect  # noqa: E402

pytestmark = pytest.mark.needs_sqlalchemy

API = "/sharpit/api"
SECRET = "hunter2"
STATEMENT = f"SELECT 1 # password {SECRET}"
SECOND_STATEMENT = f"SELECT \"{SECRET}\" FROM t # 'x'"
LOCAL = ("127.0.0.1", 50000)


class Conflict:
    """One real failed statement, on an engine that says MySQL over a driver that is SQLite."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, **options: object) -> None:
        self.engine = sa.create_engine("sqlite://")
        monkeypatch.setattr(self.engine.dialect, "name", "mysql")
        app = FastAPI()
        self.failure: sa.exc.OperationalError | None = None

        @app.get("/fails")
        def fails() -> dict[str, bool]:  # pyright: ignore[reportUnusedFunction]
            with self.engine.connect() as conn:
                conn.exec_driver_sql(STATEMENT)  # the exception store records what escapes
            return {"ok": True}

        @app.get("/fails2")
        def fails2() -> dict[str, bool]:  # pyright: ignore[reportUnusedFunction]
            with self.engine.connect() as conn:
                conn.exec_driver_sql(SECOND_STATEMENT)
            return {"ok": True}

        @app.get("/logged")
        def logged() -> dict[str, bool]:  # pyright: ignore[reportUnusedFunction]
            with self.engine.connect() as conn:
                for statement in (STATEMENT, SECOND_STATEMENT):
                    try:
                        conn.exec_driver_sql(statement)
                    except sa.exc.OperationalError as error:
                        self.failure = error
                        conn.rollback()
                        logging.getLogger("host.db").error("query failed: %s", error)  # noqa: TRY400 - a host's own line
            return {"ok": True}

        self.handle = install(
            app,
            enabled="ON",
            show_banner=False,
            stream_max_seconds=0.05,
            engines=[self.engine],
            sql_trace_sqlite3_enabled=False,
            **options,  # pyright: ignore[reportArgumentType]
        )
        self.client = TestClient(app, base_url="http://localhost", client=LOCAL, raise_server_exceptions=False)
        self.client.get("/logged")
        self.client.get("/fails")
        self.client.get("/fails2")

    def body(self, path: str) -> str:
        response = self.client.get(f"{API}/{path}")
        assert response.status_code == 200
        return response.text


@pytest.fixture
def conflict(monkeypatch: pytest.MonkeyPatch) -> Iterator[Conflict]:
    sqla.detach_all()
    built = Conflict(monkeypatch)
    yield built
    built.handle.uninstall_capture()


def _error(conflict: Conflict) -> sa.exc.OperationalError:
    assert conflict.failure is not None
    return conflict.failure


def test_the_fixture_is_a_conflict_with_a_real_sqlite3_error(conflict: Conflict):
    error = _error(conflict)

    assert type(error.orig).__module__ == "sqlite3"
    assert exception_dialect(error, lambda: application_family(conflict.handle.context)) is Dialect.UNSUPPORTED


@pytest.mark.parametrize("surface", ["sql-trace", "sql-trace/insights", "activity", "exceptions", "log-tail/recent"])
def test_a_conflict_hides_the_statement_on_the_surface(conflict: Conflict, surface: str):
    assert SECRET not in conflict.body(surface)


def test_a_conflict_hides_the_statement_in_the_recorded_row(conflict: Conflict):
    recorder = conflict.handle.context.capture.sql_trace
    assert recorder is not None

    rows = recorder.rows()

    # Task 29: a conflict is UNSUPPORTED, so its statement is the marker (owner, item 7)
    assert [row["sql"] for row in rows] == ["[statement hidden: unsupported database]"] * 4


def test_a_conflict_hides_the_statement_in_the_recorded_error(conflict: Conflict):
    recorder = conflict.handle.context.capture.sql_trace
    assert recorder is not None

    assert all(SECRET not in row["errorMessage"] for row in recorder.rows())


def test_a_conflict_hides_the_statement_in_an_exception_detail(conflict: Conflict):
    groups = conflict.client.get(f"{API}/exceptions").json()["groups"]

    assert groups
    assert all(SECRET not in conflict.body(f"exceptions/{group['id']}") for group in groups)


def test_mask_error_hides_the_statement_of_a_conflict(conflict: Conflict):
    error = _error(conflict)
    dialect = exception_dialect(error, lambda: application_family(conflict.handle.context))

    assert SECRET not in (mask_error(conflict.handle.context.masker, str(error), dialect) or "")
