"""Rings and the tee (security-sinks visible rows, Task 5)."""

from __future__ import annotations

import threading

from sharpit.engine.capture.journal import RuntimeJournal
from sharpit.engine.sensors.rows import RING_CAPACITY, SensorRows, TeeSink


def _row(source: str, n: int = 0, at: int = 1) -> dict[str, str | int | bool | None]:
    return {"source": source, "n": n, "at": at}


def test_an_accepted_row_reaches_its_sensors_ring() -> None:
    rows = SensorRows()
    tee = TeeSink(RuntimeJournal(sources=["processes"]), rows)
    tee.offer_flat(_row("processes"))
    assert [row["source"] for row in rows.drain("processes")] == ["processes"]
    assert rows.drain("processes") == []


def test_a_journal_without_the_source_still_feeds_the_side_effects_rows() -> None:
    # O7: the rings are fed before the journal's source filter
    rows, journal = SensorRows(), RuntimeJournal(sources=["processes"])
    tee = TeeSink(journal, rows)
    assert tee.offer_flat(_row("files")) is False
    assert journal.records("files") == ()
    assert len(rows.drain("files")) == 1


def test_a_full_ring_keeps_the_newest_rows_and_counts_dropped() -> None:
    rows = SensorRows()
    for n in range(RING_CAPACITY + 5):
        rows.append(_row("files", n))
    drained = rows.drain("files")
    assert len(drained) == RING_CAPACITY
    assert drained[0]["n"] == 5
    assert drained[-1]["n"] == RING_CAPACITY + 4
    assert rows.dropped("files") == 5


def test_a_full_ring_fed_through_the_tee_counts_dropped() -> None:
    rows = SensorRows()
    tee = TeeSink(RuntimeJournal(sources=["files"]), rows)
    for n in range(RING_CAPACITY + 3):
        tee.offer_flat(_row("files", n))
    assert len(rows.drain("files")) == RING_CAPACITY
    assert rows.dropped("files") == 3


def test_a_file_flood_never_drops_a_security_sinks_row() -> None:
    rows = SensorRows()
    for n in range(RING_CAPACITY + 1):
        rows.append(_row("files", n))
    rows.append(_row("security-sinks"))
    assert len(rows.drain("security-sinks")) == 1
    assert rows.dropped("files") > 0
    assert rows.dropped("security-sinks") == 0


def test_a_read_racing_appends_loses_and_duplicates_nothing() -> None:
    rows, seen, done = SensorRows(), [], threading.Event()

    def produce(base: int) -> None:
        for n in range(2_000):
            rows.append(_row("processes", base + n))

    def read() -> None:
        while not done.is_set():
            seen.extend(row["n"] for row in rows.drain("processes"))

    threads = [threading.Thread(target=produce, args=(i * 2_000,)) for i in range(4)]
    reader = threading.Thread(target=read)
    reader.start()
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    done.set()
    reader.join()
    seen.extend(row["n"] for row in rows.drain("processes"))
    assert sorted(seen, key=int) == list(range(8_000))


def test_the_tee_answers_every_journal_sink_call() -> None:
    journal = RuntimeJournal(sources=["processes"])
    tee = TeeSink(journal, SensorRows())
    assert tee.offer({"source": "processes", "n": 1}) is True
    assert tee.records("processes") == journal.records("processes")
    assert len(tee.records("processes")) == 1
    assert tee.accepts("processes") is True
    assert tee.accepts("files") is False
    tee.count_dropped("probe")
    assert journal.status()["dropped"]["probe"] == 1


def test_the_recording_clear_empties_the_ring_and_records_its_time() -> None:
    rows = SensorRows()
    rows.append(_row("files"))
    assert rows.cleared_at("files") == 0
    rows.clear("files", 5_000)
    assert rows.drain("files") == []
    assert rows.cleared_at("files") == 5_000


def test_a_row_queued_before_a_clear_is_never_shown_after_it() -> None:
    # rings half of the timestamp rule (SideEffectsService.java:2248); the store drops the row by its time
    rows = SensorRows()
    rows.clear("files", 5_000)
    rows.append(_row("files", at=4_000))
    drained = rows.drain("files")
    assert [row["at"] for row in drained] == [4_000]
    assert rows.cleared_at("files") > 4_000


def test_the_lane_feeds_its_rows_before_the_journals_source_filter() -> None:
    from sharpit.engine.sensors.audit import AuditHub
    from sharpit.engine.sensors.lane import build_lane

    hooks: list[object] = []
    journal = RuntimeJournal(sources=["http"])
    lane = build_lane(("processes",), journal, lambda p: p, audit=AuditHub(add_hook=hooks.append))
    assert lane is not None
    lane.attach()
    hooks[0]("os.system", ("echo hi",))  # type: ignore[operator]
    assert journal.records("processes") == ()
    assert len(lane.rows.drain("processes")) == 1
