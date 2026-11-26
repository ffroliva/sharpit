from __future__ import annotations

from sharpit.engine.collectors.sideeffects.pending import Pending


def test_a_request_the_journal_never_names_counts_under_an_unknown_route_once_it_waited_long_enough() -> None:
    # ported: SideEffectsServiceTests.aRequestTheJournalNeverNamesCountsUnderAnUnknownRouteOnceItWaitedLongEnough
    completed: list[dict[str, object]] = []
    pending = Pending(lambda ids: {}, lambda: 0)
    pending.add({"at": 1000, "sensor": "files", "target": "x"}, "r1")
    assert pending.resolve(31_001) == completed + [{"scope": "route", "attribution": "(unknown route)", "sensor": "files", "target": "x"}]


def test_waiting_observations_are_bounded_and_dropped_past_the_bound() -> None:
    # ported: SideEffectsStoreTests.waitingObservationsAreBoundedAndDroppedPastTheBound
    pending = Pending(lambda ids: {}, lambda: 0)
    for index in range(10_001):
        pending.add({"at": index, "sensor": "files", "target": "x"}, f"r{index}")
    assert pending.waiting_count == 10_000
    assert pending.dropped == 1


def test_clear_recording_drops_waiting_observations() -> None:
    # adapted from: SideEffectsStoreTests.clearRecordingDropsRowsAndWaitingObservations
    pending = Pending(lambda ids: {}, lambda: 0)
    pending.add({"at": 99, "sensor": "files", "target": "x"}, "r1")
    pending.clear(100)
    assert pending.waiting_count == 0


def test_a_running_requests_rows_wait_for_its_route() -> None:
    pending = Pending(lambda ids: {}, lambda: 0)
    pending.add({"at": 1000, "sensor": "files", "target": "x"}, "r1")
    assert pending.resolve(30_000) == []
    pending.reader = lambda ids: {"r1": "GET /items"}
    rows = pending.resolve(30_001)
    assert rows[0]["attribution"] == "GET /items"


def test_a_request_whose_http_event_was_evicted_counts_under_unknown_route() -> None:
    pending = Pending(lambda ids: {}, lambda: 0)
    pending.add({"at": 1000, "sensor": "files", "target": "x"}, "r1")
    rows = pending.resolve(31_000)
    assert rows[0]["attribution"] == "(unknown route)"


def test_metadata_only_keeps_confirmation_and_routes() -> None:
    pending = Pending(lambda ids: {"r1": "GET /items"}, lambda: 0)
    pending.add({"at": 1000, "sensor": "files", "target": "x"}, "r1")
    rows = pending.resolve(1001)
    assert rows[0]["attribution"] == "GET /items"


def test_a_row_older_than_the_wait_is_named_while_its_http_event_is_held() -> None:
    pending = Pending(lambda ids: {"r1": "GET /items"}, lambda: 0)
    pending.add({"at": 1000, "sensor": "files", "target": "x"}, "r1")
    rows = pending.resolve(41_000)
    assert rows[0]["attribution"] == "GET /items"


def test_one_read_at_the_caps_sorts_and_resolves_in_bounded_time() -> None:
    pending = Pending(lambda ids: {}, lambda: 0)
    for index in range(10_000):
        pending.add({"at": index, "sensor": "files", "target": str(index)}, f"r{index}")
    rows = pending.resolve(31_000)
    assert len(rows) == 10_000
