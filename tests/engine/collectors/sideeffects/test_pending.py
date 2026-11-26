from __future__ import annotations

from sharpit.engine.collectors.sideeffects.pending import Pending


def test_a_request_the_journal_never_names_counts_under_an_unknown_route_once_it_waited_long_enough() -> None:
    # ported: SideEffectsServiceTests.aRequestTheJournalNeverNamesCountsUnderAnUnknownRouteOnceItWaitedLongEnough
    pending = Pending(lambda ids: {}, lambda: 0)
    pending.add({"at": 1000, "sensor": "files", "target": "x"}, "r1")
    rows = pending.resolve(31_001)
    assert len(rows) == 1
    assert rows[0]["attribution"] == "(unknown route)"


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
    rows = pending.resolve(30_250)
    assert rows[0]["attribution"] == "GET /items"


def test_a_request_whose_http_event_was_evicted_counts_under_unknown_route() -> None:
    pending = Pending(lambda ids: {}, lambda: 0)
    pending.add({"at": 1000, "sensor": "files", "target": "x"}, "r1")
    rows = pending.resolve(100_000)
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
    rows = pending.resolve(100_000)
    assert len(rows) == 10_000


def test_a_row_before_readiness_counts_under_startup() -> None:
    pending = Pending(lambda ids: {}, lambda: 2000)
    pending.add({"at": 1000, "sensor": "files", "target": "x"}, None)
    rows = pending.resolve(2001)
    assert rows[0]["attribution"] == "startup"


def test_an_unowned_row_after_readiness_counts_under_its_thread_family() -> None:
    pending = Pending(lambda ids: {}, lambda: 1000)
    pending.add({"at": 2000, "sensor": "files", "target": "x", "threadName": "pool-3-thread-12"}, None)
    rows = pending.resolve(2001)
    assert rows[0]["attribution"] == "pool-{n}-thread-{n}"


def test_an_unowned_row_with_no_thread_name_is_unattributed() -> None:
    pending = Pending(lambda ids: {}, lambda: 1000)
    pending.add({"at": 2000, "sensor": "files", "target": "x"}, None)
    rows = pending.resolve(2001)
    assert rows[0]["attribution"] == "(unattributed)"


def test_a_thread_family_collapses_digit_runs_and_keeps_only_safe_characters() -> None:
    from sharpit.engine.collectors.sideeffects.pending import thread_family

    assert thread_family("pool-3-thread-12") == "pool-{n}-thread-{n}"
    assert thread_family("a=b&c") == "a?b?c"


def test_a_thread_name_holding_a_secret_never_reaches_its_family() -> None:
    from sharpit.engine.collectors.sideeffects.pending import thread_family

    assert "AKIAIOSFODNN7EXAMPLE" not in str(thread_family("worker-AKIAIOSFODNN7EXAMPLE"))


def test_resolved_requests_leave_no_route_behind() -> None:
    pending = Pending(lambda ids: dict.fromkeys(ids, "GET /items"), lambda: 0)
    request_ids = {f"r{index}" for index in range(20)}
    for request_id in request_ids:
        pending.add({"at": 1000}, request_id)

    pending.resolve(1001)

    assert pending._routes.keys().isdisjoint(request_ids)


def test_a_secret_straddling_the_thread_family_cut_never_shows() -> None:
    from sharpit.engine.collectors.sideeffects.pending import thread_family

    family = thread_family("x" * 110 + "AKIAIOSFODNN7EXAMPLE")

    assert "AKIA" not in str(family)
