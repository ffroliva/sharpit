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
    assert journal.status()["dropped"].get("suspended", 0) == 1
    journal.resume()
    assert journal.offer({"source": "test"}) is True


def test_journal_append_overhead_budget() -> None:
    module = _journal_module()
    event = {"source": "test", "message": "small event"}

    def noop_round() -> float:
        start = time.perf_counter_ns()
        for _ in range(500):
            pass
        return (time.perf_counter_ns() - start) / 500

    def offer_round() -> float:
        journal = module.RuntimeJournal(max_events=1000, max_bytes=1_000_000, queue_capacity=1000)
        start = time.perf_counter_ns()
        for _ in range(500):
            journal.offer(event)
        return (time.perf_counter_ns() - start) / 500

    result = paired(noop_round, offer_round, 15)
    check_budget("runtime journal offer", result, 100_000, "µs", 1000)


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
    # ported: JournalTextExposureTests.metadataOnlyMasksEveryMatrixParameterValueWhateverItsName (masked whole, as the
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
