"""The request value holder of the security-sinks sensor: lifetime, reading, bounded matching and redaction."""

from __future__ import annotations

import contextlib
import threading
import uuid
from collections.abc import Iterator, Mapping
from typing import Any, NoReturn

import pytest

from sharpit.engine.capture.correlation import RequestInfo
from sharpit.engine.sensors.sinks import values as values_module
from sharpit.engine.sensors.sinks.values import (
    DEADLINE_SECONDS,
    ENTRIES,
    F_BUSY,
    F_OVERFLOW,
    F_PARTIAL,
    F_REPEATED,
    F_SEEN,
    F_STOPPED,
    MAX_CHECKS,
    MAX_QUERY,
    MAX_SCAN,
    MAX_VALUES,
    RequestValues,
    fallback_name,
    keyed_hash,
    number,
    unchecked,
)


def info(query: str = "", path: dict[str, Any] | None = None, request_id: str = "a" * 16) -> RequestInfo:
    scope = {"query_string": query.encode(), **({"path_params": path} if path is not None else {})}
    return RequestInfo(request_id, "ctx", "GET", "/", None, 0, None, scope=scope)


def raw(query: bytes) -> RequestInfo:
    return RequestInfo("a" * 16, "ctx", "GET", "/", None, 0, None, scope={"query_string": query})


def test_a_query_value_matches_until_the_request_ends() -> None:
    # ported: RequestValuesTests.aValueMatchesOnTheRequestsOwnWorkUntilTheRequestEnds
    held, request = RequestValues(), info("file=report-q3")
    assert held.match(request, "/srv/in/report-q3.pdf", "file").names == ("file",)
    request.finished_ns = 1
    held.end(request.id)
    assert held.match(request, "/srv/other/report-q3.pdf", "file").names == ()
    assert held.held() == 0


def test_a_percent_encoded_value_matches_in_its_decoded_form() -> None:
    assert RequestValues().match(info("f=docs%2Fq3+x"), "/srv/docs/q3 x", "file").redacted == "/srv/{f}"


def test_path_values_set_by_routing_after_the_first_check_are_read() -> None:
    # ported: RequestValuesTests.lateValuesAreReadAtTheFirstCheckOnceAHandlerMappingSetThem
    held, request = RequestValues(), info("a=zzzz")
    assert held.match(request, "in/quarterly", "file").names == ()
    assert request.scope is not None
    request.scope["path_params"] = {"name": "quarterly"}
    assert held.match(request, "in/quarterly", "file").names == ("name",)


@pytest.mark.parametrize(
    ("value", "names"),
    [("abc", ("w",)), ("abcd", ("v", "w")), ("a" * 256, ("v", "w")), ("a" * 257, ("w",))],
)
def test_only_values_of_four_to_256_characters_are_held(value: str, names: tuple[str, ...]) -> None:
    # ported: RequestValuesTests.valuesOutsideTheLengthsAndPastTheCountAreSkippedAndCounted
    match = RequestValues().match(info(path={"v": value, "w": "okay"}), value + "/okay", "file")
    assert match.names == names


def test_values_past_the_count_and_duplicates_are_skipped() -> None:
    # ported: RequestValuesTests.valuesOutsideTheLengthsAndPastTheCountAreSkippedAndCounted
    pairs = ["p0=value-00", "dup=value-00", *(f"p{i}=value-{i:02d}" for i in range(1, 40))]
    text = " ".join(f"value-{i:02d}" for i in range(40))
    match = RequestValues().match(info("&".join(pairs)), text, "file")
    assert match.names == tuple(f"p{i}" for i in range(MAX_VALUES))


def test_overlapping_and_repeated_spans_are_all_redacted() -> None:
    # ported: RequestValuesTests.redactionMergesOverlappingSpansAndReplacesEveryOccurrence
    match = RequestValues().match(info(path={"a": "abcd", "b": "cdef"}), "abcdef/abcd", "file")
    assert match.redacted == "{a}/{a}"


def test_a_partly_scanned_text_keeps_no_redacted_text_and_is_never_reported_repeated() -> None:
    # ported: RequestValuesTests.aPartlyScannedTextIsCheckedAgainEachTimeNeverReportedAsRepeated
    held, request = RequestValues(), info("v=needle")
    text = "x" * MAX_SCAN + "needle"
    assert [held.match(request, text, "file").flags for _ in range(2)] == [F_PARTIAL, F_PARTIAL]


def test_a_long_text_is_scanned_partly_and_then_keeps_no_redacted_text() -> None:
    # ported: RequestValuesTests.aLongTextIsScannedPartlyAndThenKeepsNoRedactedText
    text = "'alice' " + "z" * MAX_SCAN + " 'alice-after-the-limit'"
    match = RequestValues().match(info("name=alice"), text, "file")
    assert match.names == ("name",)
    assert match.flags == F_PARTIAL
    assert len(match.spans) == 1
    assert match.redacted is None


def test_nine_spans_overflow_and_keep_no_redacted_text() -> None:
    # ported: RequestValuesTests.moreThanEightSpansOverflowAndKeepNoRedactedText
    match = RequestValues().match(info("v=needle"), "needle " * 9, "file")
    assert match.flags & F_OVERFLOW
    assert match.redacted is None


def test_a_busy_entry_reports_busy_and_never_waits() -> None:
    held, request = RequestValues(), info("v=needle")
    held.match(request, "warm", "file")
    with held._entries[request.id].lock:
        match = held.match(request, "needle", "file")
    assert match.flags == F_BUSY
    assert unchecked(match)


def test_a_match_that_races_the_end_of_its_request_leaves_nothing() -> None:
    held, request = RequestValues(), info("v=needle")
    request.finished_ns = 1
    assert held.match(request, "needle", "file").names == ()
    assert held.held() == 0


def test_no_repr_shows_a_value_or_a_span_text() -> None:
    held, request = RequestValues(), info("v=needle")
    match = held.match(request, "needle", "file")
    assert "needle" not in repr(match) + repr(held) + repr(held._entries)


def test_a_missed_end_is_swept_after_the_deadline_and_clear_wipes_the_table() -> None:
    # ported: RequestValuesTests.aMissedEndIsSweptAfterTheDeadlineAndANewClaimWipesTheTable
    now = [0.0]
    held = RequestValues(clock=lambda: now[0])
    held.match(info("name=alice", request_id="a" * 16), "x/alice", "file")
    now[0] = DEADLINE_SECONDS + 1
    held.match(info("name=bobby", request_id="b" * 16), "x/bobby", "file")
    assert held.held() == 1
    held.clear()
    assert held.held() == 0


def test_a_request_past_the_deadline_never_holds_values_again() -> None:
    now = [0.0]
    held, old = RequestValues(clock=lambda: now[0]), info("name=alice", request_id="a" * 16)
    held.match(old, "x/alice", "file")
    now[0] = DEADLINE_SECONDS + 1
    held.match(info("name=bobby", request_id="b" * 16), "x/bobby", "file")
    assert held.match(old, "x/alice", "file").names == ()
    assert held.held() == 1


def test_names_that_are_not_safe_to_show_are_replaced_by_their_position() -> None:
    # ported: RequestValuesTests.namesThatAreNotSafeToShowAreReplacedByTheirPosition
    long = "x" * 65
    query = f"user%5Bname%5D=alpha&%3Cscript%3E=bravo&%ZZ=charlie&{long}=delta"
    match = RequestValues().match(info(query), "alpha bravo charlie delta", "command")
    assert match.names == ("user[name]", fallback_name("<script>"), "param#0000", fallback_name(long))
    assert fallback_name("hello") == "param#18d2"  # Java: "hello".hashCode() == 99162322
    assert "script" not in fallback_name("<script>")


def test_the_table_holds_at_most_its_entries_and_counts_the_rest() -> None:
    # ported: RequestValuesTests.theTableHoldsAtMostItsEntriesAndCountsTheRest
    held = RequestValues()
    last = None
    for i in range(ENTRIES + 1):
        last = held.match(info(f"name=value{i}", request_id=f"{i + 1:016x}"), f"x/value{i}", "file")
    assert held.held() == ENTRIES
    assert last is not None
    assert last.flags == 0


def test_checks_stop_at_their_budget_and_repeated_texts_are_not_checked_again() -> None:
    # ported: RequestValuesTests.checksStopAtTheirBudgetAndRepeatedTextsAreNotCheckedAgain
    held, request = RequestValues(), info("name=alice")
    assert held.match(request, "select 1", "file").names == ()
    repeated = held.match(request, "select 1", "file")
    assert repeated.flags == F_REPEATED
    assert repeated.redacted is None
    for _ in range(2 * MAX_CHECKS):
        held.match(request, "select 1", "file")
    assert held.match(request, "q 'alice'", "file").names == ("name",)
    again = held.match(request, "q 'alice'", "file")
    assert again.redacted == "q '{name}'"
    for i in range(MAX_CHECKS):
        held.match(request, f"text {i}", "file")
    stopped = held.match(request, "again 'alice'", "file")
    assert stopped.names == ()
    assert stopped.flags == F_STOPPED


def test_the_comparison_budget_stops_matching_for_the_request() -> None:
    # ported: RequestValuesTests.theComparisonBudgetStopsMatchingForTheRequest
    held, request = RequestValues(), info(path={f"p{i}": f"w{i:03d}" for i in range(MAX_VALUES)})
    big = "z" * MAX_SCAN
    for i in range(3):
        held.match(request, f"{i}{big}", "file")
    stopped = held.match(request, "w000", "file")
    assert stopped.flags == F_STOPPED
    assert stopped.names == ()


@pytest.mark.parametrize(("count", "checks"), [(8, 8), (MAX_VALUES, 2)])
def test_the_budget_charges_scanned_times_held_characters(count: int, checks: int) -> None:
    # ported: RequestValuesTests.theComparisonBudgetStopsMatchingForTheRequest
    held, request = RequestValues(), info(path={f"p{i}": f"w{i:03d}" for i in range(count)})
    big = "z" * MAX_SCAN
    done = 0
    while done < 20 and not held.match(request, f"{done}{big}", "file").flags & F_STOPPED:
        done += 1
    assert done == checks


def test_a_repeated_miss_costs_no_comparison_budget() -> None:
    held, request = RequestValues(), info(path={f"p{i}": f"w{i:03d}" for i in range(MAX_VALUES)})
    big = "z" * MAX_SCAN
    for _ in range(10):
        held.match(request, big, "file")
    assert held.match(request, "w000" + "z" * (MAX_SCAN - 4), "file").names == ("p0",)


def test_signed_and_decimal_numbers_are_numbers_and_nothing_else_is() -> None:
    # ported: RequestValuesTests.signedAndDecimalNumbersAreNumbersAndNothingElseIs
    for text in ("4242", "-33.8688", "+7", "151.2093", ".5"):
        assert number(text, 0, len(text)), text
    for text in ("-", ".", "1.2.3", "-x.1", "12a", "--1", ""):
        assert not number(text, 0, len(text)), text


def test_a_matched_number_is_named_numeric() -> None:
    match = RequestValues().match(info(path={"id": 4242, "name": "abcd"}), "/items/4242/abcd", "file")
    assert match.numeric == frozenset({"id"})


def test_a_text_checked_before_a_value_was_added_is_checked_again_afterwards() -> None:
    # ported: RequestValuesTests.aTextCheckedBeforeAValueWasAddedIsCheckedAgainAfterwards
    held, request = RequestValues(), info("q=first-value")
    text = "select * from t where p = 'path-value'"
    assert held.match(request, text, "file").names == ()
    assert request.scope is not None
    request.scope["path_params"] = {"p": "path-value"}
    match = held.match(request, text, "file")
    assert match.names == ("p",)
    assert match.flags == 0


class _ApplicationMap(dict[str, Any]):
    def __iter__(self) -> NoReturn:
        raise AssertionError("an application map was read")

    def __getitem__(self, key: str) -> NoReturn:
        raise AssertionError("an application map was read")

    def items(self) -> NoReturn:  # type: ignore[override]
        raise AssertionError("an application map was read")


def test_an_application_map_is_never_read_as_a_late_source() -> None:
    # ported: RequestValuesTests.anApplicationMapIsNeverReadAsALateSource
    match = RequestValues().match(info("q=query", path=_ApplicationMap(v="value")), "query", "file")
    assert match.names == ("q",)


class _Mapping(Mapping[str, Any]):
    def __getitem__(self, key: str) -> NoReturn:
        raise AssertionError("a mapping was read")

    def __iter__(self) -> Iterator[str]:
        raise AssertionError("a mapping was iterated")

    def __len__(self) -> int:
        raise AssertionError("a mapping was measured")


def test_path_params_that_are_not_a_plain_dict_are_never_iterated() -> None:
    request = info("q=query")
    assert request.scope is not None
    request.scope["path_params"] = _Mapping()
    assert RequestValues().match(request, "/srv/query", "file").names == ("q",)


class _Loud:
    def __str__(self) -> str:
        raise AssertionError("converted")


def test_a_path_value_of_another_type_is_never_converted() -> None:
    path = {"bad": _Loud(), "flag": True, "id": 4242, "u": uuid.UUID(int=7)}
    match = RequestValues().match(info(path=path), f"/x/4242/{uuid.UUID(int=7)}/True", "file")
    assert match.names == ("id", "u")


def test_path_values_keep_their_place_when_the_query_fills_max_values() -> None:
    query = "&".join(f"q{i}=query-{i:02d}" for i in range(40))
    match = RequestValues().match(info(query, path={"id": "path-value"}), "/items/path-value", "file")
    assert match.names == ("id",)


def test_the_query_stops_at_8192_characters_and_64_pairs_and_skips_a_pair_that_does_not_decode() -> None:
    head = "keep=okay&f="
    cut = head + "1" * (MAX_QUERY - len(head)) + "&late=needle"
    assert RequestValues().match(info(cut), "okay needle", "file").names == ("keep",)
    pairs = "&".join(["s=1"] * 63) + "&edge=keepme&over=dropme"
    assert RequestValues().match(info(pairs), "keepme dropme", "file").names == ("edge",)
    assert RequestValues().match(info("bad=%G1zzzz&good=fine"), "%G1zzzz fine", "file").names == ("good",)


def test_a_malformed_percent_escape_is_skipped() -> None:
    match = RequestValues().match(info("v=%ZZneedle&w=okvalue"), "%ZZneedle okvalue", "file")
    assert match.names == ("w",)


def test_a_value_whose_name_fails_to_decode_is_kept_by_position() -> None:
    match = RequestValues().match(info("%ZZ=../../etc/passwd"), "/srv/files/../../etc/passwd", "file")
    assert match.redacted == "/srv/files/{param#0000}"


def test_invalid_utf8_decodes_with_replacement_as_starlette_does() -> None:
    match = RequestValues().match(info("f=report%E9q3"), "/srv/report�q3.pdf", "file")
    assert match.names == ("f",)


def test_raw_query_bytes_are_read_as_starlette_reads_them() -> None:
    match = RequestValues().match(raw(b"q=caf\xc3\xa9"), "/srv/cafÃ©.txt", "file")
    assert match.names == ("q",)


@pytest.mark.parametrize("stage", ["_read_values", "_scan", "_redact"])
@pytest.mark.parametrize("action", ["end", "clear"])
def test_a_check_after_end_or_clear_publishes_and_inserts_nothing(
    monkeypatch: pytest.MonkeyPatch, stage: str, action: str
) -> None:
    held, request = RequestValues(), info("v=needle")
    real = getattr(values_module, stage)

    def interleaved(*args: Any) -> Any:
        result = real(*args)
        if action == "end":
            request.finished_ns = 1
            held.end(request.id)
        else:
            held.clear()
        return result

    monkeypatch.setattr(values_module, stage, interleaved)
    match = held.match(request, "/srv/needle", "file")
    assert match.names == ()
    assert held.held() == 0


def test_end_and_clear_never_wait_for_an_entry_lock() -> None:
    held = RequestValues()
    first, second = info("v=needle", request_id="a" * 16), info("v=needle", request_id="b" * 16)
    held.match(first, "warm", "file")
    held.match(second, "warm", "file")
    locked, release = threading.Event(), threading.Event()

    def hold() -> None:
        with held._entries[first.id].lock, held._entries[second.id].lock:
            locked.set()
            release.wait(10)

    holder = threading.Thread(target=hold)
    holder.start()
    try:
        assert locked.wait(10)
        ending = threading.Thread(target=lambda: (held.end(first.id), held.clear()))
        ending.start()
        ending.join(5)
        assert not ending.is_alive()
        assert held.held() == 0
    finally:
        release.set()
        holder.join()


def test_a_match_that_raises_inside_releases_the_entry_lock(monkeypatch: pytest.MonkeyPatch) -> None:
    held, request = RequestValues(), info("v=needle")

    def failing(*args: Any) -> NoReturn:
        raise RuntimeError("comparison failed")

    monkeypatch.setattr(values_module, "_scan", failing)
    with contextlib.suppress(RuntimeError):
        held.match(request, "/srv/needle", "file")
    monkeypatch.undo()
    assert held.match(request, "/srv/needle", "file").names == ("v",)


def test_a_text_is_marked_seen_only_by_mark_seen() -> None:
    held, request = RequestValues(), info("v=needle")
    first = held.match(request, "/srv/needle", "file")
    assert first.names == ("v",)
    assert not held.match(request, "/srv/needle", "file").flags & F_SEEN
    held.mark_seen(request.id, first)
    seen = held.match(request, "/srv/needle", "file")
    assert seen.flags == F_SEEN
    assert seen.redacted == "/srv/{v}"


def test_the_keyed_hash_reads_only_the_scanned_prefix_and_is_positive() -> None:
    prefix = "a" * MAX_SCAN
    assert keyed_hash(prefix + "x") == keyed_hash(prefix + "y")
    assert keyed_hash("a") != keyed_hash("b")
    assert 0 < keyed_hash("") < 2**63


def test_counters_feed_the_holder_line() -> None:
    held = RequestValues()
    request = info("".join(f"p{i}=value-{i:02d}&" for i in range(33)) + f"long={'x' * 257}")
    held.match(request, "z" * 300, "file")
    held.match(request, "z" * 300 + "y", "command")
    status = held.status()
    assert status.get("requests", 0) == 1
    assert status.get("checks", 0) == 2
    assert status.get("valuesTooLong", 0) == 1
    assert status.get("valuesOverCount", 0) == 1


def test_a_full_table_counts_table_full() -> None:
    held = RequestValues()
    for i in range(ENTRIES + 1):
        held.match(info(f"name=value{i}", request_id=f"{i + 1:016x}"), f"x/value{i}", "file")
    assert held.status().get("tableFull", 0) == 1


def test_stopped_partial_and_busy_are_counted() -> None:
    held, request = RequestValues(), info("v=needle")
    partial = held.match(request, "needle" + "x" * MAX_SCAN, "file")
    assert partial.flags & F_PARTIAL
    entry = held._entries[request.id]
    with entry.lock:
        busy = held.match(request, "needle", "file")
    assert busy.flags == F_BUSY
    for i in range(MAX_CHECKS + 1):
        held.match(request, f"text {i}", "file")
    assert held.status().get("partial", 0) == 1
    assert held.status().get("busy", 0) == 1
    assert held.status().get("stopped", 0) == 1


def test_holder_counters_never_hold_a_value_or_name() -> None:
    held = RequestValues()
    held.match(info("secretname=needle1234"), "path/needle1234", "file")
    status = held.status()
    assert status.get("requests", 0) == 1
    assert "secretname" not in repr(status)
    assert "needle1234" not in repr(status)


def test_status_keys_are_exactly_the_ones_an_output_reads() -> None:
    assert tuple(RequestValues().status()) == (
        "requests",
        "tableFull",
        "valuesTooLong",
        "valuesOverCount",
        "checks",
        "partial",
        "stopped",
        "busy",
        "notKept",
        "dropped",
    )
