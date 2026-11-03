"""A section that could not be read says so with a masked reason; the lock-wait SQL is valid on MySQL and MariaDB."""

from __future__ import annotations

import pytest
from tests.engine.collectors.mysql.fakes import FakeMySqlConnection

from sharpit.engine.collectors.mysql.limits import ReadBudget, RowLimits
from sharpit.engine.collectors.mysql.sections import DataSourceData, collect_all
from sharpit.engine.masking import Exposure, Masker

MASKED = Masker(Exposure.MASKED, True)
PASSWORD = "hunter2-secret-pw"
SECRET_ERROR = f"could not read: mysql://app:{PASSWORD}@db:3306/app"
LOCK_WAIT = {
    "waiting_trx_id": "421",
    "waiting_pid": 12,
    "waiting_query": "UPDATE t SET v = 1 WHERE id = 1",
    "blocking_trx_id": "420",
    "blocking_pid": 11,
    "blocking_query": None,
}


def _collect(conn: FakeMySqlConnection) -> DataSourceData:
    return collect_all(conn, MASKED, RowLimits(), ReadBudget.start(15.0), DataSourceData("primary"))


def _section(data: DataSourceData, section_id: str) -> dict[str, object]:
    return next((s for s in data.sections if s["id"] == section_id), {})


@pytest.mark.parametrize(
    ("kind", "section_id"), [("LOCK_WAITS", "lock-waits"), ("REPLICATION", "replication-channels")]
)
def test_failed_section_is_failed(kind: str, section_id: str) -> None:
    data = _collect(FakeMySqlConnection().fail(kind, SECRET_ERROR))
    assert _section(data, section_id).get("status") == "FAILED"


@pytest.mark.parametrize("kind", ["LOCK_WAITS", "REPLICATION"])
def test_failed_section_reason_says_why(kind: str) -> None:
    data = _collect(FakeMySqlConnection().fail(kind, SECRET_ERROR))
    assert any("could not read" in str(s["reason"]) for s in data.sections)


def test_failed_metrics_is_an_error_diagnostic() -> None:
    data = _collect(FakeMySqlConnection().fail("STATUS", SECRET_ERROR))
    assert any(d["source"] == "primary/metrics" and d["level"] == "ERROR" for d in data.diagnostics)


@pytest.mark.parametrize("kind", ["INDEXES", "TABLES", "VARIABLES"])
def test_section_driver_error_dsn_password_masked(kind: str) -> None:
    data = _collect(FakeMySqlConnection().fail(kind, SECRET_ERROR))
    assert PASSWORD not in repr(data)


@pytest.mark.parametrize("dialect", ["mysql", "mariadb"])
def test_lock_wait_rows_are_read(dialect: str) -> None:
    # The fake rejects an undeclared alias and a lock table the server does not have, as the server does.
    data = _collect(FakeMySqlConnection(dialect).with_rows("LOCK_WAITS", LOCK_WAIT))
    assert len(data.lock_waits) == 1
