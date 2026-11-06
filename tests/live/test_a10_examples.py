"""A10 reaches each example app through a real SQLAlchemy engine."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from examples.fastapi_sqla.app import create_app
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from tests.live.conftest import LiveServer

from sharpit.engine.sqltext import Dialect

pytestmark = [pytest.mark.live, pytest.mark.needs_sqlalchemy]


@pytest.mark.parametrize(
    ("key", "expected"),
    [("postgresql", Dialect.POSTGRESQL), ("mysql84", Dialect.MYSQL_FAMILY)],
    ids=["postgresql", "mysql"],
)
def test_example_app_records_its_server_family(
    key: str,
    expected: Dialect,
    live_servers: Callable[[str], LiveServer],
    tmp_path: Path,
) -> None:
    server = live_servers(key)
    app = create_app(db_dir=tmp_path, database_url=server.url, show_banner=False)
    handle = app.state.sharpit
    with TestClient(app):
        with pytest.raises(DBAPIError), app.state.sync_engine.connect() as connection:
            connection.execute(text("SELECT 'A10VALUE' FROM missing_a10_table"))
        recorder = handle.context.capture.sql_trace
        assert recorder is not None
        row = recorder.rows()[-1]
        assert row["shape"].dialect is expected
        assert "A10VALUE" not in str(row["errorMessage"])
