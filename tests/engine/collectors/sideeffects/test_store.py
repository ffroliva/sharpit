import collections
import copy

from sharpit.engine.capture.journal import RuntimeJournal
from sharpit.engine.collectors.sideeffects.store import (
    MAX_ROWS_PER_SENSOR,
    SideEffectsStore,
)
from sharpit.engine.collectors.sideeffects.wording import OTHER, SEEN_ONCE


class FakeSensorRows:
    def __init__(self) -> None:
        self.queues: dict[str, list[dict[str, object]]] = collections.defaultdict(list)
        self.drops: dict[str, int] = collections.defaultdict(int)
        self.clear_times: dict[str, int] = collections.defaultdict(int)

    def append(self, row: dict[str, object]) -> None:
        sensor = str(row.get("sensor") or row.get("source") or "processes")
        self.queues[sensor].append(row)

    def drain(self, sensor: str) -> list[dict[str, object]]:
        items = list(self.queues[sensor])
        self.queues[sensor].clear()
        return items

    def dropped(self, sensor: str) -> int:
        return self.drops[sensor]

    def cleared_at(self, sensor: str) -> int:
        return self.clear_times[sensor]

    def clear(self, sensor: str, now: int) -> None:
        self.queues[sensor].clear()
        self.clear_times[sensor] = now


def sink_row(
    request: int | str,
    target: str,
    *,
    kind: str = "command",
    raw_hash: int = 1,
    redacted_hash: int = 2,
    parameter: str = "param",
    numeric: bool = False,
    position_unknown: bool = False,
    at: int = 1_000_000,
    route: str = "GET /search",
) -> dict[str, object]:
    return {
        "source": "security-sinks",
        "kind": kind,
        "target": target,
        "parameter": parameter,
        "numeric": numeric,
        "positionUnknown": position_unknown,
        "callSite": "demo:run",
        "at": at,
        "requestId": f"{request:016x}" if isinstance(request, int) else str(request),
        "rawHash": raw_hash,
        "redactedHash": redacted_hash,
        "route": route,
    }


def process_row(
    target: str,
    *,
    at: int = 1_000_000,
    request: int | str | None = None,
    route: str | None = None,
) -> dict[str, object]:
    row: dict[str, object] = {
        "source": "processes",
        "kind": "start",
        "target": target,
        "at": at,
        "callSite": "demo:run",
    }
    if request is not None:
        row["requestId"] = f"{request:016x}" if isinstance(request, int) else str(request)
    if route is not None:
        row["route"] = route
    return row


def file_row(
    target: str,
    *,
    kind: str = "read",
    at: int = 1_000_000,
    request: int | str | None = None,
    route: str | None = None,
    location: str | None = None,
) -> dict[str, object]:
    row: dict[str, object] = {
        "source": "files",
        "kind": kind,
        "target": target,
        "at": at,
        "callSite": "demo:run",
    }
    if request is not None:
        row["requestId"] = f"{request:016x}" if isinstance(request, int) else str(request)
    if route is not None:
        row["route"] = route
    if location is not None:
        row["location"] = location
    return row


# ported: SecuritySinksStoreTests.repeatedTextsNeverFillTheConfirmationsAndADifferentValueConfirms
def test_repeated_texts_never_fill_the_confirmations_and_a_different_value_confirms() -> None:
    rings = FakeSensorRows()
    store = SideEffectsStore(rings)
    for req in range(1, 6):
        rings.append(
            sink_row(
                req,
                "convert, argument 1",
                kind="command",
                parameter="sort",
                raw_hash=11,
                redacted_hash=7,
                numeric=True,
            )
        )
    store.drain()
    assert store.rows_of("security-sinks") == []
    assert store.unconfirmed() == 1

    rings.append(
        sink_row(
            6,
            "convert, argument 1",
            kind="command",
            parameter="sort",
            raw_hash=12,
            redacted_hash=7,
            numeric=True,
        )
    )
    store.drain()
    rows = store.rows_of("security-sinks")
    assert len(rows) == 1
    row = rows[0]
    assert row.detail is not None
    assert "argument 1 of `convert`" in row.detail
    assert SEEN_ONCE not in row.detail
    assert row.count == 6
    assert store.unconfirmed() == 0


# adapted from: SecuritySinksStoreTests.pastTheCapsAnUnconfirmedMatchIsNotShownAndTheOtherRowClaimsNoLiteral
def test_past_the_caps_an_unconfirmed_match_is_not_shown_and_the_other_row_counts_it() -> None:
    rings = FakeSensorRows()
    store = SideEffectsStore(rings, max_rows_per_sensor=1)
    rings.append(
        sink_row(
            1,
            "convert, argument 1",
            parameter="name",
            raw_hash=1,
            redacted_hash=2,
            numeric=False,
        )
    )
    rings.append(
        sink_row(
            1,
            "resize, argument 1",
            parameter="sort",
            raw_hash=3,
            redacted_hash=4,
            numeric=True,
        )
    )
    rings.append(
        sink_row(
            1,
            "optimize, argument 1",
            parameter="name",
            raw_hash=5,
            redacted_hash=6,
            numeric=False,
        )
    )
    store.drain()
    rows = store.rows_of("security-sinks")
    assert len(rows) == 2
    other = rows[1]
    assert other.scope == "other"
    assert other.count == 1
    assert other.detail == OTHER
    assert store.unconfirmed() == 1


# ported: SecuritySinksStoreTests.aMatchWhoseRedactedTextWasNotKeptIsNeverConfirmed
def test_a_match_whose_redacted_text_was_not_kept_is_never_confirmed() -> None:
    rings = FakeSensorRows()
    store = SideEffectsStore(rings)
    rings.append(
        sink_row(
            1,
            "(text not kept)",
            parameter="param",
            raw_hash=1,
            redacted_hash=0,
            position_unknown=True,
        )
    )
    rings.append(
        sink_row(
            2,
            "(text not kept)",
            parameter="param",
            raw_hash=2,
            redacted_hash=0,
            position_unknown=True,
        )
    )
    store.drain()
    assert store.rows_of("security-sinks") == []
    assert store.unconfirmed() == 1


# adapted from: SecuritySinksStoreTests.aValueInsideTrueFalseOrANumberWaitsAndOneCrossingALiteralStandsAlone
def test_a_number_and_an_unknown_position_wait_and_a_plain_value_stands_alone() -> None:
    rings = FakeSensorRows()
    store = SideEffectsStore(rings)
    rings.append(
        sink_row(
            1,
            "calc, argument 1",
            parameter="val",
            numeric=True,
            raw_hash=1,
            redacted_hash=2,
        )
    )
    store.drain()
    assert store.rows_of("security-sinks") == []

    rings.append(
        sink_row(
            3,
            "calc, argument 2",
            parameter="lat",
            position_unknown=True,
            raw_hash=5,
            redacted_hash=6,
        )
    )
    store.drain()
    assert store.rows_of("security-sinks") == []

    rings.append(
        sink_row(
            2,
            "run, argument 1",
            parameter="name",
            numeric=False,
            position_unknown=False,
            raw_hash=3,
            redacted_hash=4,
        )
    )
    store.drain()
    rows = store.rows_of("security-sinks")
    assert len(rows) == 1
    row = rows[0]
    assert row.target == "run, argument 1"
    assert row.detail is not None
    assert row.detail.endswith(SEEN_ONCE)


# ported: SideEffectsStoreTests.aSensorPastItsCapCountsTheRestInItsOtherRowWhichSortsLast
def test_a_sensor_past_its_cap_counts_the_rest_in_its_other_row_which_sorts_last() -> None:
    rings = FakeSensorRows()
    store = SideEffectsStore(rings)
    for i in range(MAX_ROWS_PER_SENSOR + 10):
        rings.append(file_row(f"./reports/report-{i}.csv"))
    store.drain()

    rows = store.rows_of("files")
    assert len(rows) == MAX_ROWS_PER_SENSOR + 1
    assert rows[-1].scope == "other"
    assert rows[-1].count == 10
    assert store.folded() == 10
    assert store.counts("files") == (MAX_ROWS_PER_SENSOR + 1, MAX_ROWS_PER_SENSOR + 10)


# adapted from: SideEffectsStoreTests.clearRecordingDropsRowsAndWaitingObservations
def test_clear_recording_drops_rows() -> None:
    rings = FakeSensorRows()
    store = SideEffectsStore(rings)
    rings.append(process_row("git"))
    rings.append(file_row("./data.csv"))
    store.drain()
    assert len(store.rows_of("processes")) == 1
    assert len(store.rows_of("files")) == 1

    store.clear(now=1_000_000)
    assert store.rows_of("processes") == []
    assert store.rows_of("files") == []
    assert store.counts("processes") == (0, 0)
    assert store.counts("files") == (0, 0)
    assert store.folded() == 0
    assert store.unconfirmed() == 0
    assert store.clears() == 1


# ported: SecuritySinksStoreTests.theSameRequestTwiceNeverConfirms
def test_the_same_request_twice_never_confirms() -> None:
    rings = FakeSensorRows()
    store = SideEffectsStore(rings)
    rings.append(
        sink_row(
            1,
            "convert, argument 1",
            parameter="sort",
            raw_hash=11,
            redacted_hash=7,
            numeric=True,
        )
    )
    rings.append(
        sink_row(
            1,
            "convert, argument 1",
            parameter="sort",
            raw_hash=12,
            redacted_hash=7,
            numeric=True,
        )
    )
    store.drain()
    assert store.rows_of("security-sinks") == []
    assert store.unconfirmed() == 1


# ported: SecuritySinksStoreTests.theSameRawTextFromTwoRequestsNeverConfirms
def test_the_same_raw_text_from_two_requests_never_confirms() -> None:
    rings = FakeSensorRows()
    store = SideEffectsStore(rings)
    rings.append(
        sink_row(
            1,
            "convert, argument 1",
            parameter="sort",
            raw_hash=11,
            redacted_hash=7,
            numeric=True,
        )
    )
    rings.append(
        sink_row(
            2,
            "convert, argument 1",
            parameter="sort",
            raw_hash=11,
            redacted_hash=7,
            numeric=True,
        )
    )
    store.drain()
    assert store.rows_of("security-sinks") == []
    assert store.unconfirmed() == 1


# adapted from: SideEffectsService.java:2248
def test_a_row_queued_before_a_clear_is_never_shown_after_it() -> None:
    rings = FakeSensorRows()
    store = SideEffectsStore(rings)
    store.clear(now=2000)
    rings.append(process_row("git", at=1999))
    store.drain()
    assert store.rows_of("processes") == []
    assert store.cleared() == 1


# adapted from: SideEffectsService.java:2248
def test_a_row_after_a_clear_is_shown() -> None:
    rings = FakeSensorRows()
    store = SideEffectsStore(rings)
    store.clear(now=2000)
    rings.append(process_row("git", at=2001))
    store.drain()
    rows = store.rows_of("processes")
    assert len(rows) == 1
    assert store.cleared() == 0


def test_the_store_never_changes_a_ring_row() -> None:
    rings = FakeSensorRows()
    store = SideEffectsStore(rings)
    row = process_row("git", at=1000)
    rings.append(row)
    expected = copy.deepcopy(row)
    store.drain()
    assert row == expected
    assert len(store.rows_of("processes")) == 1


def test_rows_survive_journal_eviction() -> None:
    journal = RuntimeJournal(max_events=1)
    rings = FakeSensorRows()
    store = SideEffectsStore(rings)
    rings.append(process_row("git", at=1000))
    store.drain()
    assert len(store.rows_of("processes")) == 1
    journal.discard()
    assert len(store.rows_of("processes")) == 1


def test_a_process_or_file_row_is_shown_from_one_occurrence() -> None:
    rings = FakeSensorRows()
    store = SideEffectsStore(rings)
    rings.append(process_row("python", at=1000))
    rings.append(file_row("./output.log", at=1000))
    store.drain()
    assert len(store.rows_of("processes")) == 1
    assert len(store.rows_of("files")) == 1
    assert store.counts("processes") == (1, 1)
    assert store.counts("files") == (1, 1)
