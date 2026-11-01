from __future__ import annotations

from types import SimpleNamespace

import pytest

from sharpit import pytest_plugin
from sharpit.engine.testsession.sink import TestSessionSink


def test_worker_and_controller_collect_the_same_facts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(pytest_plugin.sys.modules, "asyncpg", object())
    worker = SimpleNamespace(sink=TestSessionSink("gw0"), sqlite_attached=False)
    controller = SimpleNamespace(sink=TestSessionSink("master"), sqlite_attached=False)

    pytest_plugin._final_facts(worker)  # type: ignore[arg-type]
    pytest_plugin._final_facts(controller)  # type: ignore[arg-type]

    assert worker.sink.facts.untraced_drivers == controller.sink.facts.untraced_drivers
    assert worker.sink.facts.engine_drivers == controller.sink.facts.engine_drivers
    assert worker.sink.facts.sources == controller.sink.facts.sources
