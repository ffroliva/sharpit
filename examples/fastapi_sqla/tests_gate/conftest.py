"""Fixtures for the sharpit CI gate demo: the sample app on a fresh, migrated-by-hand SQLite file."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest
from examples.fastapi_sqla.app import create_app
from fastapi.testclient import TestClient

SCHEMA = """
CREATE TABLE owners (id INTEGER PRIMARY KEY, name VARCHAR(100) NOT NULL, email VARCHAR(200));
CREATE TABLE pets (id INTEGER PRIMARY KEY, owner_id INTEGER NOT NULL REFERENCES owners(id),
                   name VARCHAR(100) NOT NULL, species VARCHAR(50) NOT NULL);
"""


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    with sqlite3.connect(tmp_path / "sample.db") as db:
        db.executescript(SCHEMA)
    app = create_app(db_dir=tmp_path, show_banner=False)
    try:
        with TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000)) as test_client:
            yield test_client
    finally:
        app.state.sharpit.uninstall_capture()
