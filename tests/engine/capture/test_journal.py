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
    from fastapi.testclient import TestClient

    from fastapi import FastAPI
    from sharpit import install

    assert getattr(CaptureState(), "journal", None) is None
    assert _journal_module().NULL_SINK.offer({"source": "test"}) is False
    app = FastAPI()
    handle = install(app, enabled="ON", show_banner=False, runtime_journal_enabled=False)
    try:
        before = {thread.ident for thread in threading.enumerate()}
        with TestClient(app) as client:
            client.get("/sharpit/api/activity/journal")
            names = {hook.name for hook in handle.context.capture.hooks.hooks()}
            assert handle.context.capture.journal is None
            assert "runtime-journal" not in names
        assert {thread.ident for thread in threading.enumerate()} == before
    finally:
        handle.uninstall_capture()


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
    assert status["retainedEvents"] <= 100
    assert status["retainedBytes"] <= 4096
    assert status["evictedEvents"] + status["retainedEvents"] == 10_000, "every event is retained or counted evicted"
    assert status["droppedEvents"] == 0, "queue-capacity refuses nothing: there is no queue"
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
    assert journal.status()["dropped"] == {"test": 1}, "dropped is keyed by source, as BootUI's is"
    journal.resume()
    assert journal.offer({"source": "test"}) is True


def test_journal_accepted_offer_overhead_budget() -> None:
    """Measured alone (-n 0, Windows 11, CPython 3.13): 3.6-4.1 µs per accepted offer over three runs.

    The budget leaves room for slower CI runners.

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
    assert status["dropped"] == {"processes": 1}
    assert status["recorded"] == {}


def test_a_new_journal_source_is_refused_by_settings_until_it_is_catalogued() -> None:
    # "network" is the next sensor source (W6 S5): "processes" and "files" were catalogued by S3
    settings = load_settings({}, {"SHARPIT_RUNTIME_JOURNAL_SOURCES": "sql,network"})
    assert "Ignoring invalid SHARPIT_RUNTIME_JOURNAL_SOURCES value 'sql,network'" in settings.warnings
    assert "network" not in settings.runtime_journal_sources
    assert "sql" in settings.runtime_journal_sources


def test_offer_never_raises_into_the_host() -> None:
    journal = _journal_module().RuntimeJournal(max_events=10, max_bytes=4096, queue_capacity=10)

    class Broken(dict):
        def items(self):
            raise RuntimeError("a source built a bad event")

    assert journal.offer(Broken(source="test", payload={"x": 1})) is False
    assert journal.status()["dropped"] == {"failed": 1}


def test_the_journal_is_a_ring_that_keeps_the_newest_events() -> None:
    journal = _journal_module().RuntimeJournal(max_events=50, max_bytes=1_000_000, queue_capacity=10)
    accepted = [journal.offer({"source": "http", "i": i}) for i in range(57)]
    status = journal.status()
    assert all(accepted), "a full journal evicts; it never refuses"
    assert [event["i"] for event in journal.records("http")] == list(range(7, 57))
    assert status["evictedEvents"] == 7
    assert status["bindingBound"] == "COUNT"
    assert status["droppedEvents"] == 0


def test_the_byte_bound_evicts_the_oldest_events() -> None:
    event = {"source": "http", "message": "x" * 100}  # 6 + 4 + 7 + 100 = 117 estimated bytes
    journal = _journal_module().RuntimeJournal(max_events=1000, max_bytes=117 * 3, queue_capacity=1)
    accepted = [journal.offer(event) for _ in range(5)]
    status = journal.status()
    assert all(accepted)
    assert status["retainedEvents"] == 3
    assert status["retainedBytes"] <= 117 * 3
    assert status["evictedEvents"] == 2
    assert status["bindingBound"] == "BYTES"


def _masked_record(**fields: object) -> dict[str, object]:
    journal = _journal_module().RuntimeJournal(masker=Masker(Exposure.MASKED, True))
    assert journal.offer({"source": "sql", **fields}) is True
    return journal.records("sql")[0]


class _Opaque:
    def __init__(self, secret: str) -> None:
        self.secret = secret

    def __repr__(self) -> str:
        return f"Opaque(password={self.secret})"

    __str__ = __repr__


def test_records_mask_bytes_sets_objects_and_nested_values() -> None:
    canary = "c4n4ry0123456789abcdef"
    record = _masked_record(
        raw=f"password={canary}".encode(),
        tags={f"token={canary}"},
        frozen=frozenset({f"secret={canary}"}),
        obj=_Opaque(canary),
        nested={"deep": [{"inner": (f"password={canary}".encode(), _Opaque(canary))}]},
    )
    shown = json.dumps(record, default=repr)  # what any serialiser of a leftover object would show
    assert canary not in shown


def test_records_show_sql_without_literals() -> None:
    # ported: JournalTextExposureTests.sqlWhoseBackslashesReadDifferentlyByDialectShowsNothingAfterItsFirstQuote
    def sql(text: str) -> object:
        return _masked_record(sql=text)["sql"]

    assert sql("select * from t where a = 'x' and b = 'y'") == "select * from t where a = ? and b = ?"
    assert "sk_live_EXAMPLE" not in str(sql(r"SELECT 'C:\', 'sk_live_EXAMPLE'"))
    assert "sk_live_EXAMPLE" not in str(sql(r"select * from t where a = 'it\'s sk_live_EXAMPLE' and b = 1"))
    assert "trailing" not in str(sql(r"select * from t where a = E'password=x\' trailing sk_live_EXAMPLE' and b = 1"))
    assert sql('select * from t where a = "x\\"sk_live_EXAMPLE"') == "select * from t where a = ?"
    assert "hunter2pass" not in str(sql('insert into users(pw) values("x\\"hunter2pass")'))
    assert sql("INSERT INTO api_keys(value) # '\nVALUES ('sk_live_EXAMPLE')") == "INSERT INTO api_keys(value) ?"


def test_records_never_show_sql_that_reads_like_a_value() -> None:
    # ported: JournalTextExposureTests.sqlThatCannotBeToldApartFromAValueIsNeverShownMasked
    def sql(text: str) -> str:
        return str(_masked_record(sql=text)["sql"])

    for text, secret in [
        ("select * from t where body = $$top secret$$", "top secret"),
        ("select * from t where body = $tag$top secret (truncated", "top secret"),
        ("select * from t where body = $$top secret", "top secret"),
        ('select * from t where name = "alice"', "alice"),
        ("select * from api_keys where credential = $$prefix sk_live_EXAMPLE$$", "sk_live_EXAMPLE"),
        ("select * from api_keys where credential = $k$prefix sk_live_EXAMPLE$k$", "sk_live_EXAMPLE"),
        ("select * from t where password = :password and api_key = sk_live_EXAMPLE", "sk_live_EXAMPLE"),
        ("SELECT 1 # password=?sk_live_EXAMPLE", "sk_live_EXAMPLE"),
        ("UPDATE t SET `password`=sk_live_EXAMPLE", "sk_live_EXAMPLE"),
        ("SELECT [password]=sk_live_EXAMPLE FROM t", "sk_live_EXAMPLE"),
        ("SELECT /* outer /* inner */ ' */ 'sk_live_EXAMPLE'", "sk_live_EXAMPLE"),
        ("SELECT $é$sk_live_EXAMPLE", "sk_live_EXAMPLE"),
        ("SELECT q'[it's sk_live_EXAMPLE]' FROM dual", "sk_live_EXAMPLE"),
    ]:
        assert secret not in sql(text), text
    assert sql("select * from t where id = $1") == "select * from t where id = $1"
    assert sql("SELECT 123_456, 1.5e-3 FROM t") == "SELECT ?, ? FROM t"
    assert sql("SELECT .123456 FROM t") == "SELECT ? FROM t"
    assert sql("SELECT 0x736b5f6c6976655f4558414d504c45, 0b1011 FROM t") == "SELECT ?, ? FROM t"


def test_records_mask_path_matrix_parameters() -> None:
    # adapted: JournalTextExposureTests.metadataOnlyMasksEveryMatrixParameterValueWhateverItsName;
    # BootUI does this under METADATA_ONLY only, sharpit under MASKED too (stricter: masked whole, as the
    # traces panel does: session ids live in matrix parameters)
    assert _masked_record(path="/callback;code=opaqueCredential/x;flag")["path"] == "/callback;code=******/x;******"


def test_records_are_verbatim_with_masking_off() -> None:
    journal = _journal_module().RuntimeJournal(masker=Masker(Exposure.FULL, False))
    journal.offer({"source": "sql", "sql": "select 'x'", "path": "/a;code=1"})
    assert journal.records("sql") == ({"source": "sql", "sql": "select 'x'", "path": "/a;code=1"},)


def test_a_later_host_mutation_changes_neither_the_stored_event_nor_its_bytes() -> None:
    journal = _journal_module().RuntimeJournal(max_events=10, max_bytes=4096)
    payload = {"k": "v", "rows": ["a"]}
    assert journal.offer({"source": "http", "payload": payload}) is True
    charged = journal.status()["retainedBytes"]
    payload["k"] = "x" * 10_000
    payload["rows"].append("y" * 10_000)  # pyright: ignore[reportAttributeAccessIssue]
    assert journal.records("http")[0]["payload"] == {"k": "v", "rows": ["a"]}
    assert journal.status()["retainedBytes"] == charged


def test_recorded_lists_only_sources_with_events() -> None:
    # ported: RuntimeJournalServiceTests.reportsTheJournalsBoundsCountsAndDropsByPropertyName
    # (recorded: only sources with a count)
    journal = _journal_module().RuntimeJournal(max_events=10, max_bytes=4096, sources=("sql", "http", "log"))
    journal.offer({"source": "http"})
    assert journal.status()["recorded"] == {"http": 1}


def test_dropped_is_keyed_by_source_and_unattributed_drops_by_reason() -> None:
    # ported: RuntimeJournalServiceTests.reportsTheJournalsBoundsCountsAndDropsByPropertyName (dropped, per source);
    # reentrant and failed offers have no source to read
    journal = _journal_module().RuntimeJournal(max_events=10, max_bytes=64)
    assert journal.offer({"source": "sql", "sql": "x" * 100}) is False  # larger than the whole byte bound
    assert journal.offer({"source": 7}) is False
    status = journal.status()
    assert status["dropped"] == {"sql": 1, "failed": 1}
    assert status["droppedEvents"] == 2


def test_a_read_masks_each_sql_event_exactly_as_masking_it_alone_at_every_exposure() -> None:
    """W5a P-sql r3: a read reuses one masked text across events; the output is the per-value masking, unchanged."""
    module = _journal_module()
    shapes = ["select a from t where b = 'secret-literal' and c = ?", 'select "password" from u where id = ?', "x # y"]
    events = [
        {"source": "sql", "sql": shapes[i % 3], "thread": "worker-1", "traceId": None, "batchSize": i, "failed": False}
        for i in range(9)
    ]
    for exposure in Exposure:
        journal = module.RuntimeJournal(max_events=100, max_bytes=1_000_000, masker=Masker(exposure, True))
        for event in events:
            journal.offer(event)
        expected = tuple({key: module._mask(value, key, journal.masker) for key, value in e.items()} for e in events)
        assert journal.records("sql") == expected


def test_offer_flat_with_a_size_below_one_still_charges_the_event_and_respects_the_byte_bound() -> None:
    """W5a P-sql r3: a caller's size of 0 or less never bypasses ``max_bytes`` nor drives the byte count negative."""
    journal = _journal_module().RuntimeJournal(max_events=10, max_bytes=100)
    assert journal.offer_flat({"source": "sql", "sql": "x" * 200}, size=-5) is False
    assert journal.offer_flat({"source": "sql", "sql": "select 1"}, size=0) is True
    assert journal.status()["retainedBytes"] > 0


def test_offer_flat_with_a_size_builds_no_store_per_call(monkeypatch: Any) -> None:
    """W5a P-transaction r4: a sized flat offer hands its event and size straight on; no closure per offer."""
    journal = _journal_module().RuntimeJournal(max_events=10, max_bytes=4096)
    stores: list[object] = []
    append = journal._append

    def spy(event: Any, store: object) -> bool:
        stores.append(store)
        return append(event, store)

    monkeypatch.setattr(journal, "_append", spy)
    assert journal.offer_flat({"source": "sql", "sql": "select 1"}, size=30) is True
    assert stores == [30]  # the size itself, not a closure
    assert journal.status()["retainedBytes"] == 30


def test_a_suspended_journal_accepts_no_source() -> None:
    # a paused SQL Trace panel asks accepts() before building an event: a suspended journal must not cost it one
    journal = _journal_module().RuntimeJournal(max_events=10, max_bytes=4096, queue_capacity=10)
    assert journal.accepts("sql") is True
    journal.suspend()
    assert journal.accepts("sql") is False


def test_count_dropped_takes_the_lock_the_other_writers_hold() -> None:
    from sharpit.engine.capture.journal import RuntimeJournal

    journal = RuntimeJournal(max_events=10, max_bytes=10_000, queue_capacity=10)
    done = threading.Event()
    worker = threading.Thread(target=lambda: (journal.count_dropped("log"), done.set()))
    with journal._lock:
        worker.start()
        blocked = not done.wait(0.3)
    worker.join(5)
    assert blocked
    assert done.is_set()
