from __future__ import annotations

import importlib
import importlib.util
import json
import threading
import time
from dataclasses import fields
from typing import Any

from tests.overhead import check_budget, paired

from sharpit.engine.capture import CaptureState
from sharpit.engine.masking import Exposure, Masker
from sharpit.settings import load_settings


def _journal_module():
    spec = importlib.util.find_spec("sharpit.engine.capture.journal")
    assert spec is not None, "runtime journal module is missing"
    return importlib.import_module("sharpit.engine.capture.journal")


def test_journal_off_allocates_nothing() -> None:
    before = threading.enumerate()
    assert getattr(CaptureState(), "journal", None) is None
    assert threading.enumerate() == before
    assert _journal_module().NULL_SINK.offer({"source": "test"}) is False


def test_journal_bounds_and_counts_drops() -> None:
    journal = _journal_module().RuntimeJournal(max_events=100, max_bytes=4096, queue_capacity=25)
    event = {"source": "test", "message": "x" * 100}

    def publish() -> None:
        for _ in range(5000):
            journal.offer(event)

    workers = [threading.Thread(target=publish) for _ in range(2)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()
    status = journal.status()
    assert status["retainedEvents"] <= 25
    assert status["droppedEvents"] > 0
    assert sum(status["dropped"].values()) == status["droppedEvents"]


def test_reentrant_append_is_dropped_and_counted() -> None:
    journal = _journal_module().RuntimeJournal(max_events=10, max_bytes=4096, queue_capacity=10)
    event = {"source": "test", "message": "outer"}

    class Reentrant(dict):
        def items(self):
            journal.offer(event)
            return super().items()

    assert journal.offer(Reentrant(source="test", message="outer")) is True
    assert journal.status()["dropped"].get("reentrant", 0) == 1


def test_journal_masks_raw_events_when_records_are_read() -> None:
    module = _journal_module()
    journal = module.RuntimeJournal(
        max_events=10,
        max_bytes=4096,
        queue_capacity=10,
        masker=Masker(Exposure.MASKED, True),
    )
    raw = {"source": "test", "message": "password=canary-secret", "headers": {"Authorization": "Bearer canary-token"}}
    assert journal.offer(raw) is True
    assert raw["message"] == "password=canary-secret"
    serialized = json.dumps(journal.records("test"))
    assert "canary-secret" not in serialized
    assert "canary-token" not in serialized


def test_runtime_journal_settings_have_bootui_defaults_and_parse_values() -> None:
    setting_names = {item.name for item in fields(load_settings({}, {}))}
    assert "runtime_journal_enabled" in setting_names
    settings = load_settings(
        {},
        {
            "SHARPIT_RUNTIME_JOURNAL_ENABLED": "false",
            "SHARPIT_RUNTIME_JOURNAL_MAX_EVENTS": "123",
            "SHARPIT_RUNTIME_JOURNAL_MAX_BYTES": "2MB",
            "SHARPIT_RUNTIME_JOURNAL_QUEUE_CAPACITY": "44",
            "SHARPIT_RUNTIME_JOURNAL_SOURCES": "sql,http",
        },
    )
    assert settings.runtime_journal_enabled is False
    assert settings.runtime_journal_max_events == 123
    assert settings.runtime_journal_max_bytes == 2 * 1024 * 1024
    assert settings.runtime_journal_queue_capacity == 44
    assert settings.runtime_journal_sources == ("sql", "http")


def test_journal_status_dto_reads_live_values() -> None:
    journal = _journal_module().RuntimeJournal(max_events=10, max_bytes=4096, queue_capacity=8)
    journal.offer({"source": "test", "message": "hello"})
    dto = importlib.import_module("sharpit.engine.capture.activity").journal_status_dto(journal)
    assert dto["enabled"] is True
    assert dto["retainedEvents"] == 1
    assert dto["maxEvents"] == 10
    assert dto["maxBytes"] == 4096
    assert dto["queueCapacity"] == 8
    assert dto["recorded"] == {"test": 1}


def test_suspended_journal_counts_suspended_drops() -> None:
    journal = _journal_module().RuntimeJournal(max_events=10, max_bytes=4096, queue_capacity=10)
    journal.suspend()
    assert journal.offer({"source": "test"}) is False
    assert journal.status()["dropped"].get("suspended", 0) == 1
    journal.resume()
    assert journal.offer({"source": "test"}) is True


def test_journal_append_overhead_budget() -> None:
    """Measured alone (-n 0, Windows 11, CPython 3.13) at 3.6-4.1 µs per accepted offer (three runs); the budget leaves CI room.

    "off" is the disabled journal (``NULL_SINK``) called the same way, so the overhead is the append itself.
    """
    module = _journal_module()
    event = {"source": "http", "message": "GET /pets 200", "durationMs": 3}
    per_round = 500

    def round_of(sink: Any) -> float:
        start = time.perf_counter_ns()
        for _ in range(per_round):
            sink.offer(event)
        return (time.perf_counter_ns() - start) / per_round

    journals: list[Any] = []

    def offer_round() -> float:
        journal = module.RuntimeJournal(max_events=1000, max_bytes=1_000_000, queue_capacity=1000, sources=("http",))
        journals.append(journal)
        return round_of(journal)

    result = paired(lambda: round_of(module.NULL_SINK), offer_round, 60)
    assert all(journal.status()["recorded"] == {"http": per_round} for journal in journals), "timed the reject path"
    check_budget("runtime journal offer", result, 20_000, "µs", 1000)


def test_an_unconfigured_source_is_dropped_and_counted() -> None:
    journal = _journal_module().RuntimeJournal(max_events=10, max_bytes=4096, queue_capacity=10, sources=("sql",))
    assert journal.offer({"source": "processes", "pid": 1}) is False
    status = journal.status()
    assert status["dropped"] == {"source-disabled": 1}
    assert status["recorded"] == {"sql": 0}


def test_a_new_journal_source_is_refused_by_settings_until_it_is_catalogued() -> None:
    settings = load_settings({}, {"SHARPIT_RUNTIME_JOURNAL_SOURCES": "sql,processes"})
    assert "Ignoring invalid SHARPIT_RUNTIME_JOURNAL_SOURCES value 'sql,processes'" in settings.warnings
    assert "processes" not in settings.runtime_journal_sources
    assert "sql" in settings.runtime_journal_sources


def test_offer_never_raises_into_the_host() -> None:
    journal = _journal_module().RuntimeJournal(max_events=10, max_bytes=4096, queue_capacity=10)

    class Broken(dict):
        def items(self):
            raise RuntimeError("a source built a bad event")

    assert journal.offer(Broken(source="test", payload={"x": 1})) is False
    assert journal.status()["dropped"] == {"failed": 1}
