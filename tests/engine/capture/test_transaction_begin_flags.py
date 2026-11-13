"""r7 of #166: the begin path reads one flag on the journal, never ``accepts``; it follows every state change."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

sa = pytest.importorskip("sqlalchemy")

from fastapi import FastAPI  # noqa: E402
from sharpit import install  # noqa: E402
from sharpit.engine import sqla  # noqa: E402
from sharpit.engine.capture.journal import RuntimeJournal  # noqa: E402

pytestmark = pytest.mark.needs_sqlalchemy


@pytest.fixture(autouse=True)
def clean_listeners() -> Iterator[None]:
    sqla.detach_all()
    yield
    sqla.detach_all()


def _install(**options: Any) -> tuple[Any, Any]:
    engine = sa.create_engine("sqlite://")
    handle = install(
        FastAPI(), enabled="ON", show_banner=False, config_scan=False, engines=[engine],
        runtime_journal_sources=("transaction",), **options,
    )  # fmt: skip
    return handle, engine


def _commit(engine: Any) -> None:
    with engine.begin() as conn:
        conn.execute(sa.text("select 1"))


def _count(handle: Any) -> int:
    return len(handle.context.capture.journal.records("transaction"))


def test_begin_path_reads_the_flag_and_never_calls_accepts(monkeypatch: pytest.MonkeyPatch):
    handle, engine = _install()

    def refused(self: RuntimeJournal, source: str) -> bool:
        raise AssertionError("the begin path called accepts")

    monkeypatch.setattr(RuntimeJournal, "accepts", refused)
    _commit(engine)
    assert _count(handle) == 1


def test_flag_follows_suspend_and_resume():
    handle, engine = _install()
    journal = handle.context.capture.journal
    journal.suspend()
    _commit(engine)
    assert _count(handle) == 0
    journal.resume()
    _commit(engine)
    assert _count(handle) == 1


def test_flag_follows_a_source_set_change():
    handle, engine = _install()
    journal = handle.context.capture.journal
    journal.sources = frozenset({"http"})
    _commit(engine)
    assert _count(handle) == 0
    assert journal.status()["dropped"].get("transaction") == 1
    journal.sources = frozenset({"transaction"})
    _commit(engine)
    assert _count(handle) == 1


def test_flag_follows_a_source_set_cleared_to_no_filter():
    handle, engine = _install()
    journal = handle.context.capture.journal
    journal.sources = frozenset({"http"})
    journal.sources = None
    _commit(engine)
    assert _count(handle) == 1


def test_a_suspended_journal_stays_suspended_when_the_source_set_changes():
    handle, engine = _install()
    journal = handle.context.capture.journal
    journal.suspend()
    journal.sources = frozenset({"transaction"})
    _commit(engine)
    assert _count(handle) == 0


def test_no_journal_offers_nothing_and_the_panel_still_records():
    handle, engine = _install(runtime_journal_enabled=False)
    assert handle.context.capture.journal is None
    _commit(engine)
    assert len(handle.context.capture.transactions.report(None)["entries"]) == 1


def test_a_source_the_journal_refuses_is_counted_only_for_a_recording_panel():
    handle, engine = _install()
    journal = handle.context.capture.journal
    journal.sources = frozenset({"http"})
    handle.context.capture.transactions.set_recording(False)
    _commit(engine)
    assert journal.status()["dropped"].get("transaction") is None
