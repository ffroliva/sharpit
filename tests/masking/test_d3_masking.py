"""Pool reports do not expose credentials from a SQLAlchemy URL (D3)."""

from __future__ import annotations

from pathlib import Path

import pytest

from fastapi import FastAPI
from sharpit import install
from sharpit.engine.collectors.pools import pools_report

pytestmark = pytest.mark.needs_sqlalchemy
sa = pytest.importorskip("sqlalchemy")


def test_database_password_is_masked_from_pool_report(tmp_path: Path):
    secret = "d3-pool-password"
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'masked.db'}")
    engine.url = engine.url.set(username="app", password=secret)
    handle = install(FastAPI(), enabled="ON", show_banner=False, engines=[engine])
    try:
        report = pools_report(handle.context)
        assert secret not in str(report)
    finally:
        handle.uninstall_capture()
