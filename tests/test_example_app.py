"""The sample app's opt-in extras for the UI end-to-end run (ui/tests/e2e)."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from examples.fastapi_sample.app import create_app
from fastapi.testclient import TestClient

BULK = "fastapi_sample.bulk."


def _bulk_loggers() -> set[str]:
    return {name for name in logging.root.manager.loggerDict if name.startswith(BULK)}


def test_many_loggers_flag_adds_that_many_loggers(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SAMPLE_MANY_LOGGERS", "3")
    app = create_app(show_banner=False, state_dir=str(tmp_path))
    client = TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000))
    body = client.get("/sharpit/api/loggers", params={"q": BULK}).json()
    assert [logger["name"] for logger in body["loggers"]] == [f"{BULK}0000", f"{BULK}0001", f"{BULK}0002"]


def test_sample_adds_no_bulk_loggers_by_default(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("SAMPLE_MANY_LOGGERS", raising=False)
    before = _bulk_loggers()
    create_app(show_banner=False, state_dir=str(tmp_path))
    assert _bulk_loggers() == before


@pytest.mark.parametrize("raw", ["", "lots", "-5"])
def test_many_loggers_flag_treats_a_bad_value_as_zero(
    raw: str, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("SAMPLE_MANY_LOGGERS", raw)
    before = _bulk_loggers()
    create_app(show_banner=False, state_dir=str(tmp_path))
    assert _bulk_loggers() == before
