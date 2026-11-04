from __future__ import annotations

from typing import Any

from starlette.authentication import SimpleUser, UnauthenticatedUser

from sharpit.engine.capture.securitylogs import (
    AUTHENTICATION_FAILURE,
    AUTHENTICATION_SUCCESS,
    AUTHORIZATION_FAILURE,
    SecurityEventBuffer,
    clamp_max_logs,
    format_instant,
    parse_after,
    principal_of,
    security_logs_report,
)
from sharpit.engine.masking import MASK, Exposure, Masker

JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJhbGljZSJ9.c2lnbmF0dXJl"
SECOND = 1_000_000_000
T0 = 1_762_000_000 * SECOND  # 2025-11-01T12:26:40Z


def _masked() -> Masker:
    return Masker(Exposure.MASKED, True, None)


def _report(buffer: SecurityEventBuffer | None, masker: Masker | None = None, **kw: Any) -> dict[str, Any]:
    args: dict[str, Any] = {"principal": None, "type": None, "after_ns": None, "offset": None, "limit": None}
    args["unavailable_reason"] = None
    return security_logs_report(buffer, masker or _masked(), **(args | kw))


def _rejected(raw: str) -> bool:
    try:
        parse_after(raw)
    except ValueError:
        return True
    return False


# ported: SecurityLogsServiceTests.clampsMaxLogsIntoSafeRange
def test_clamps_max_logs_into_safe_range() -> None:
    assert clamp_max_logs(0) == 1, "a zero maximum must clamp up to 1"
    assert clamp_max_logs(-5) == 1, "a negative maximum must clamp up to 1"
    assert clamp_max_logs(20_000) == 10_000, "a huge maximum must clamp down to 10000"
    assert clamp_max_logs(500) == 500, "an in-range maximum must be kept"


# ported: SecurityLogsServiceTests.sortsNewestFirstSummarizesAndPages
def test_sorts_newest_first_summarizes_and_pages() -> None:
    buffer = SecurityEventBuffer(500)
    buffer.add(AUTHENTICATION_FAILURE, "alice", {}, "r-1", timestamp_ns=T0)
    buffer.add(AUTHENTICATION_SUCCESS, "alice", {}, "r-2", timestamp_ns=T0 + SECOND)
    buffer.add(AUTHENTICATION_FAILURE, "bob", {}, "r-3", timestamp_ns=T0 + 2 * SECOND)
    report = _report(buffer, offset=0, limit=2)
    assert [e["requestId"] for e in report["events"]] == ["r-3", "r-2"], "events must be newest first, then paged"
    assert report["typeSummaries"] == [
        {"type": AUTHENTICATION_FAILURE, "count": 2},
        {"type": AUTHENTICATION_SUCCESS, "count": 1},
    ], "type summaries must count every kept event, count desc then type asc"
    assert report["page"] == {"total": 3, "matched": 3, "offset": 0, "limit": 2, "returned": 2, "hasMore": True}


def test_type_summaries_tie_sorted_by_type() -> None:
    buffer = SecurityEventBuffer(500)
    buffer.add(AUTHORIZATION_FAILURE, None, {}, None, timestamp_ns=T0)
    buffer.add(AUTHENTICATION_FAILURE, None, {}, None, timestamp_ns=T0 + 1)
    assert [s["type"] for s in _report(buffer)["typeSummaries"]] == [AUTHENTICATION_FAILURE, AUTHORIZATION_FAILURE]


# ported: SecurityLogsServiceTests.masksSensitiveDataEntries
def test_masks_sensitive_data_entries() -> None:
    buffer = SecurityEventBuffer(500)
    data = {
        "password": "hunter2",
        "session-id": "s-1",
        "sessionId": "s-2",
        "remoteAddress": "10.0.0.7",
        "client_ip_address": "10.0.0.8",
        "details": f"Bearer {JWT}",
        "type": "BadCredentialsException",
    }
    buffer.add(AUTHENTICATION_FAILURE, "alice", data, None, timestamp_ns=T0)
    events = _report(buffer)["events"]
    assert len(events) == 1, "the event must be reported"
    rows = {row["name"]: row for row in events[0]["data"]}
    for name in ("password", "session-id", "sessionId", "remoteAddress", "client_ip_address"):
        assert rows[name] == {"name": name, "value": MASK, "masked": True, "truncated": False}, name
    assert JWT not in str(rows["details"]["value"]), "a bearer token inside a value must be masked"
    assert rows["details"]["masked"] is True, "a value whose text was scrubbed is flagged masked"
    assert rows["type"]["value"] == "BadCredentialsException", "a plain value stays visible"
    assert events[0]["principal"] == "alice", "the principal is shown under MASKED"


def test_long_value_truncated() -> None:
    buffer = SecurityEventBuffer(500)
    buffer.add(AUTHENTICATION_FAILURE, None, {"note": "x" * 10_000}, None, timestamp_ns=T0)
    events = _report(buffer)["events"]
    assert len(events) == 1, "the event must be reported"
    assert events[0]["data"] == [{"name": "note", "value": "x" * 256 + "...", "masked": False, "truncated": True}]


def test_full_exposure_shows_values() -> None:
    buffer = SecurityEventBuffer(500)
    buffer.add(AUTHENTICATION_FAILURE, None, {"sessionId": "s-2"}, None, timestamp_ns=T0)
    events = _report(buffer, Masker(Exposure.FULL, True, None))["events"]
    assert len(events) == 1, "the event must be reported"
    assert events[0]["data"] == [{"name": "sessionId", "value": "s-2", "masked": False, "truncated": False}]


# ported: SecurityLogsServiceTests.filtersByPrincipalTypeAndAfter
def test_filters_by_principal_type_and_after() -> None:
    buffer = SecurityEventBuffer(500)
    buffer.add(AUTHENTICATION_FAILURE, "alice", {}, "r-1", timestamp_ns=T0)
    buffer.add(AUTHENTICATION_FAILURE, "alice", {}, "r-2", timestamp_ns=T0 + SECOND)
    buffer.add(AUTHENTICATION_SUCCESS, "alice", {}, "r-3", timestamp_ns=T0 + 2 * SECOND)
    buffer.add(AUTHENTICATION_FAILURE, "Alice", {}, "r-4", timestamp_ns=T0 + 3 * SECOND)
    report = _report(buffer, principal=" alice ", type=f" {AUTHENTICATION_FAILURE} ", after_ns=T0)
    assert [e["requestId"] for e in report["events"]] == ["r-2"], "exact trimmed filters, strictly after"
    blank = _report(buffer, principal="  ", type="")
    assert len(blank["events"]) == 4, "blank filters filter nothing"


# ported: SecurityLogsServiceTests.carriesTheRequestIdEachEventWasPublishedUnder
def test_carries_the_request_id_each_event_was_published_under() -> None:
    buffer = SecurityEventBuffer(500)
    buffer.add(AUTHENTICATION_FAILURE, None, {}, "r-42", timestamp_ns=T0)
    buffer.add(AUTHENTICATION_FAILURE, None, {}, None, timestamp_ns=T0 + 1)
    assert [e["requestId"] for e in _report(buffer)["events"]] == [None, "r-42"]


# ported: SecurityLogsServiceTests.passesTraceIdThroughToTheDto
def test_passes_trace_id_through_to_the_dto() -> None:
    buffer = SecurityEventBuffer(500)
    buffer.add(AUTHENTICATION_FAILURE, None, {}, "r-42", timestamp_ns=T0)
    assert [e["traceId"] for e in _report(buffer)["events"]] == ["r-42"], "traceId is the request id"


def test_buffer_bounded_newest_kept() -> None:
    buffer = SecurityEventBuffer(3)
    for i in range(50_000):
        buffer.add(AUTHENTICATION_FAILURE, None, {}, f"r-{i}", timestamp_ns=T0 + i)
    report = _report(buffer)
    assert [e["requestId"] for e in report["events"]] == ["r-49999", "r-49998", "r-49997"], "newest kept"
    assert report["maxLogs"] == 3, "maxLogs reports the bound"


def test_metadata_only_hides_values_and_principal() -> None:
    buffer = SecurityEventBuffer(500)
    buffer.add(AUTHENTICATION_FAILURE, "alice", {"type": "BadCredentialsException"}, None, timestamp_ns=T0)
    events = _report(buffer, Masker(Exposure.METADATA_ONLY, True, None))["events"]
    assert len(events) == 1, "the event must be reported"
    assert events[0]["principal"] is None, "METADATA_ONLY hides the principal"
    assert events[0]["data"] == [{"name": "type", "value": None, "masked": False, "truncated": False}]


def test_twenty_entries_then_overflow_row() -> None:
    buffer = SecurityEventBuffer(500)
    buffer.add(AUTHENTICATION_FAILURE, None, {f"k{i:02d}": "v" for i in range(30)}, None, timestamp_ns=T0)
    events = _report(buffer)["events"]
    assert len(events) == 1, "the event must be reported"
    rows = events[0]["data"]
    assert [r["name"] for r in rows[:20]] == [f"k{i:02d}" for i in range(20)], "first 20 entries sorted by key"
    assert rows[20:] == [{"name": "...", "value": "10 more entries omitted", "masked": False, "truncated": False}]


def test_timestamp_is_iso_instant() -> None:
    assert format_instant(T0 + 120_000_000) == "2025-11-01T12:26:40.120Z", "millis print 3 digits"
    assert format_instant(T0) == "2025-11-01T12:26:40Z", "whole seconds print no fraction"
    assert format_instant(T0 + 47_998_200) == "2025-11-01T12:26:40.047998200Z", "nanos print 9 digits"
    assert format_instant(T0 + 47_998_000) == "2025-11-01T12:26:40.047998Z", "micros print 6 digits"


def test_report_timestamp_is_iso_instant() -> None:
    buffer = SecurityEventBuffer(500)
    buffer.add(AUTHENTICATION_FAILURE, None, {}, None, timestamp_ns=T0 + 120_000_000)
    assert [e["timestamp"] for e in _report(buffer)["events"]] == ["2025-11-01T12:26:40.120Z"]


def test_parse_after_requires_an_offset() -> None:
    assert parse_after("2025-11-01T12:26:40Z") == T0, "Z is UTC"
    assert parse_after("2025-11-01T14:26:40+02:00") == T0, "an explicit offset is honoured"
    assert parse_after("  ") is None, "blank means no filter"
    assert _rejected("2025-11-01T12:26:40"), "a naive datetime is rejected"
    assert _rejected("yesterday"), "garbage is rejected"


def test_unavailable_report_shape() -> None:
    report = _report(None, unavailable_reason="Request capture is unavailable")
    assert report == {
        "auditEventsPresent": False,
        "unavailableReason": "Request capture is unavailable",
        "maxLogs": 500,
        "typeSummaries": [],
        "events": [],
        "page": {"total": 0, "matched": 0, "offset": 0, "limit": 0, "returned": 0, "hasMore": False},
    }


def test_add_signals_the_change_stream() -> None:
    buffer = SecurityEventBuffer(500)
    signals: list[int] = []
    buffer.changes.signal = lambda: signals.append(1)  # type: ignore[method-assign]
    buffer.add(AUTHENTICATION_FAILURE, None, {}, None)
    assert signals == [1], "each event signals the update stream"


class _HostileUser:
    calls: list[str] = []  # noqa: RUF012 - a class-level probe the properties append to

    @property
    def identity(self) -> str:
        self.calls.append("identity")
        raise RuntimeError("identity ran")

    @property
    def display_name(self) -> str:
        self.calls.append("display_name")
        raise RuntimeError("display_name ran")

    @property
    def is_authenticated(self) -> bool:
        self.calls.append("is_authenticated")
        return True


class _PlainUser:
    def __init__(self) -> None:
        self.identity = "u-7"


def test_principal_never_runs_user_properties() -> None:
    assert principal_of(_HostileUser()) == "_HostileUser", "a property identity falls back to the type name"
    assert _HostileUser.calls == [], "no user property ever runs"
    assert principal_of(SimpleUser("alice")) == "SimpleUser", "SimpleUser.identity is a property: type name"
    assert principal_of(UnauthenticatedUser()) is None, "an unauthenticated user has no principal"
    assert principal_of(None) is None, "no user, no principal"
    assert principal_of(_PlainUser()) == "u-7", "a plain identity attribute is the principal"


def test_stored_event_strings_are_bounded() -> None:
    buffer = SecurityEventBuffer(500)
    huge = "z" * 100_000
    data = {f"{huge}{i:03d}": huge for i in range(50)}
    buffer.add(huge, huge, data, None, timestamp_ns=T0)
    stored = buffer.snapshot()
    assert len(stored) == 1, "the event is stored"
    event = stored[0]
    assert len(event.principal or "") <= 256, "the stored principal is cut to 256 characters"
    assert len(event.type) <= 256, "the stored type is cut to 256 characters"
    assert len(event.data) <= 20, "at most 20 data entries are stored"
    assert max(len(row[0]) for row in event.data) <= 256, "stored key names are cut to 256 characters"
    assert max(len(row[1] or "") for row in event.data) <= 259, "stored values are cut to 256 characters plus '...'"


def test_long_values_are_masked_before_they_are_cut() -> None:
    buffer = SecurityEventBuffer(500)
    data = {"note": "x" * 240 + f" Bearer {JWT}", "a" * 300 + "_password": "hunter2"}
    buffer.add(AUTHENTICATION_FAILURE, None, data, None, timestamp_ns=T0)
    stored = buffer.snapshot()
    assert len(stored) == 1, "the event is stored"
    values = [row[1] or "" for row in stored[0].data]
    assert not any(JWT[:12] in v for v in values), "a token straddling the cut is masked, never stored half"
    assert "hunter2" not in values, "a long sensitive key name masks its value before the name is cut"
    shown = _report(buffer)["events"][0]["data"]
    assert [r["masked"] for r in shown] == [True, True], "both rows are reported masked"


def test_a_secret_principal_is_masked_when_stored() -> None:
    buffer = SecurityEventBuffer(500, masker=_masked())
    buffer.add(AUTHENTICATION_SUCCESS, JWT, {}, None, timestamp_ns=T0)
    assert buffer.snapshot()[0].principal == MASK


def test_a_secret_principal_is_masked_in_a_buffer_without_a_masker() -> None:
    buffer = SecurityEventBuffer(500)
    buffer.add(AUTHENTICATION_SUCCESS, JWT, {}, None, timestamp_ns=T0)
    assert buffer.snapshot()[0].principal == MASK


def test_a_plain_principal_stays_readable() -> None:
    buffer = SecurityEventBuffer(500, masker=_masked())
    buffer.add(AUTHENTICATION_SUCCESS, "alice", {}, None, timestamp_ns=T0)
    assert _report(buffer)["events"][0]["principal"] == "alice"


def test_the_filter_cannot_confirm_a_raw_secret_principal() -> None:
    buffer = SecurityEventBuffer(500, masker=_masked())
    buffer.add(AUTHENTICATION_SUCCESS, JWT, {}, None, timestamp_ns=T0)
    assert _report(buffer, principal=JWT)["events"] == []


def test_a_principal_is_masked_before_it_is_cut() -> None:
    # past 256 characters the header alone is left: cut first, half a token is stored unmasked
    long_jwt = "eyJ" + "a" * 300 + ".eyJzdWIiOiJhbGljZSJ9.c2lnbmF0dXJl"
    buffer = SecurityEventBuffer(500, masker=_masked())
    buffer.add(AUTHENTICATION_SUCCESS, long_jwt, {}, None, timestamp_ns=T0)
    assert buffer.snapshot()[0].principal == MASK


def test_a_principal_under_full_exposure_is_shown_as_exchanges_show_it() -> None:
    buffer = SecurityEventBuffer(500, masker=Masker(Exposure.FULL, True, None))
    buffer.add(AUTHENTICATION_SUCCESS, JWT, {}, None, timestamp_ns=T0)
    assert buffer.snapshot()[0].principal == JWT


def test_metadata_only_stores_no_principal_for_the_filter_to_confirm() -> None:
    masker = Masker(Exposure.METADATA_ONLY, True, None)
    buffer = SecurityEventBuffer(500, masker=masker)
    buffer.add(AUTHENTICATION_SUCCESS, "alice", {}, None, timestamp_ns=T0)
    assert _report(buffer, masker, principal="alice")["events"] == []
