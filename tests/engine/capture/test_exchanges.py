"""``HttpExchangeBuffer`` and ``exchange_row`` (F1, spec §7.1).

Ported from BootUI ``HttpExchangesServiceTests`` (cited per test): ``masksSensitiveHeadersAndDerivesStatusFamily``,
``bufferCapsAndReversesNewestFirst``, ``masksPercentEncodedSensitiveQueryNames``,
``dropsQueryAndFragmentUnderMetadataOnlyExposure``, ``leavesAnOrdinaryUriUnchanged``.
Dropped, with reason: the userinfo and fragment cases (an ASGI scope has neither), the captured-span trace id and the
b3 / X-Amzn-Trace-Id fallbacks (sharpit reads only W3C ``traceparent``, spec §7.1), ``suspendForIdle`` (no idle
suspension in sharpit) and ``excludesSelfTrafficAndCounts`` (self traffic is never stored here; the middleware counts
it, see ``test_hidden_self_counts_sharpit_requests``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from sharpit.engine.capture.exchanges import DTO_KEYS, HttpExchangeBuffer, exchange_row, status_family
from sharpit.engine.masking import MASK, Exposure, Masker

JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJyZXNldCJ9.c2lnbmF0dXJlLWJ5dGVz"
MASKED = Masker(Exposure.MASKED, True)


def _row(masker: Masker = MASKED, **kw: Any) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "request_id": "r1",
        "started_epoch_ns": 1_704_067_200_123_456_789,
        "method": "GET",
        "path": "/api",
        "query_string": b"",
        "status": 200,
        "duration_ms": 12,
        "size": 42,
        "client": ("127.0.0.1", 50000),
        "user": None,
        "request_headers": [],
        "response_headers": [],
        **kw,
    }
    return exchange_row(masker, **fields)


def _header(row: dict[str, Any], side: str, name: str) -> dict[str, Any]:
    return next(h for h in row[side] if h["name"] == name)


def test_status_family():
    # ported: HttpExchangesService.statusFamily (masksSensitiveHeadersAndDerivesStatusFamily asserts 503 -> 5xx)
    assert [status_family(s) for s in (101, 200, 302, 404, 499, 503, 99, 600)] == [
        "1xx", "2xx", "3xx", "4xx", "4xx", "5xx", "unknown", "unknown"
    ]  # fmt: skip
    assert _row(status=503)["statusFamily"] == "5xx"


def _filled() -> HttpExchangeBuffer:
    buffer = HttpExchangeBuffer(10)
    buffer.add(_row(request_id="a", method="GET", path="/owners", status=200))
    buffer.add(_row(request_id="b", method="POST", path="/owners", query_string=b"page=2", status=201))
    buffer.add(_row(request_id="c", method="GET", path="/pets", status=404))
    buffer.add(
        _row(request_id="d", method="DELETE", path="/x", status=500, request_headers=[(b"traceparent", _tp("ab" * 16))])
    )
    return buffer


def _tp(trace: str) -> bytes:
    return f"00-{trace}-{'1' * 16}-01".encode()


def _ids(report: dict[str, Any]) -> list[str]:
    return [e["id"] for e in report["exchanges"]]


def test_filters_method_status_class_q():
    # ported: HttpExchangesService.matches / matchesQuery (path, query, uri, traceId; never the method)
    buffer = _filled()
    assert _ids(buffer.report(None, "get", None, None, None)) == ["c", "a"]
    assert _ids(buffer.report(None, None, "2xx", None, None)) == ["b", "a"]
    assert _ids(buffer.report("pets", None, None, None, None)) == ["c"]  # path
    assert _ids(buffer.report("page=2", None, None, None, None)) == ["b"]  # query and uri
    assert _ids(buffer.report("abab", None, None, None, None)) == ["d"]  # traceId
    assert _ids(buffer.report("delete", None, None, None, None)) == []  # not the method
    report = buffer.report("owners", "POST", "2xx", None, None)
    assert _ids(report) == ["b"]
    assert (report["total"], report["page"]["total"], report["page"]["matched"]) == (4, 4, 1)


def test_newest_first():
    # ported: bufferCapsAndReversesNewestFirst (order)
    assert _ids(_filled().report(None, None, None, None, None)) == ["d", "c", "b", "a"]
    page = _filled().report(None, None, None, 1, 2)
    assert (_ids(page), page["page"]["hasMore"]) == (["c", "b"], True)


def test_ring_cap():
    # ported: bufferCapsAndReversesNewestFirst (cap)
    buffer = HttpExchangeBuffer(2)
    for rid in "abc":
        buffer.add(_row(request_id=rid))
    report = buffer.report(None, None, None, None, None)
    assert (_ids(report), report["total"]) == (["c", "b"], 2)
    assert buffer.get("a") is None
    assert buffer.get("c") is not None


def test_header_value_cut():
    row = _row(request_headers=[(b"x-long", b"v" * 5000)], response_headers=[(b"x-short", b"ok")])
    value = _header(row, "requestHeaders", "x-long")["values"][0]
    assert (len(value), value[-1]) == (1024, "…")
    assert _header(row, "responseHeaders", "x-short")["values"] == ["ok"]


def test_path_query_and_header_count_caps():
    headers = [(f"x-h{i:03d}".encode(), b"v") for i in range(80)]
    row = _row(
        path="/" + "p" * 5000, query_string=b"a=" + b"q" * 5000, request_headers=headers, response_headers=headers
    )
    assert len(row["path"]) == 2048
    assert row["path"].endswith("…")
    assert len(row["query"]) == 2048
    assert row["query"].endswith("…")
    assert len(row["requestHeaders"]) == len(row["responseHeaders"]) == 50


def test_path_secret_segment_masked():
    row = _row(path=f"/reset/{JWT}/confirm", query_string=b"page=1")
    assert row["path"] == f"/reset/{MASK}/confirm"
    assert row["uri"] == f"/reset/{MASK}/confirm?page=1"


def test_query_pairs_masked():
    # ported: masksSensitiveHeadersAndDerivesStatusFamily (token=******), masksPercentEncodedSensitiveQueryNames,
    # leavesAnOrdinaryUriUnchanged
    assert _row(query_string=b"token=abc&page=2")["query"] == f"token={MASK}&page=2"
    assert _row(query_string=b"%70assword=hunter2&page=2")["query"] == f"%70assword={MASK}&page=2"
    assert _row(query_string=f"next={JWT}".encode())["query"] == f"next={MASK}"  # by value
    assert _row(query_string=JWT.encode())["query"] == MASK  # a bare part with no "=" is masked by value
    assert _row(query_string=f"a&{JWT}&b=1".encode())["query"] == f"a&{MASK}&b=1"
    token = Masker(Exposure.MASKED, True, "sharpit-own-token")
    assert _row(token, query_string=b"sharpit-own-token")["query"] == MASK
    plain = _row(path="/orders", query_string=b"page=2&sort=asc")
    assert (plain["path"], plain["query"], plain["uri"]) == ("/orders", "page=2&sort=asc", "/orders?page=2&sort=asc")
    assert _row(query_string=b"")["query"] is None


def test_authorization_header_masked():
    # ported: masksSensitiveHeadersAndDerivesStatusFamily (Authorization -> masked, "******")
    row = _row(
        request_headers=[(b"authorization", b"Bearer x"), (b"cookie", b"sid=1"), (b"accept", b"*/*")],
        response_headers=[(b"set-cookie", b"sid=2"), (b"content-type", b"text/plain")],
    )
    for side, name in (
        ("requestHeaders", "authorization"),
        ("requestHeaders", "cookie"),
        ("responseHeaders", "set-cookie"),
    ):
        assert _header(row, side, name) == {"name": name, "values": [MASK], "masked": True}
    assert _header(row, "requestHeaders", "accept") == {"name": "accept", "values": ["*/*"], "masked": False}


def test_metadata_only_hides_query_and_header_values():
    # ported: dropsQueryAndFragmentUnderMetadataOnlyExposure
    row = _row(Masker(Exposure.METADATA_ONLY, True), query_string=b"page=2", request_headers=[(b"accept", b"*/*")])
    assert (row["query"], row["uri"]) == (None, "/api")
    assert row["requestHeaders"] == [{"name": "accept", "values": [], "masked": False}]


def test_traceparent_valid_used_else_request_id():
    trace = "4bf92f3577b34da6a3ce929d0e0e4736"
    assert _row(request_headers=[(b"traceparent", _tp(trace))])["traceId"] == trace
    for bad in (_tp("0" * 32), b"01-" + _tp(trace)[3:], _tp(trace[:-1]), b"garbage"):
        assert _row(request_id="rid", request_headers=[(b"traceparent", bad)])["traceId"] == "rid", bad
    assert _row(request_id="rid")["traceId"] == "rid"


@dataclass
class _User:
    display_name: str
    is_authenticated: bool = True


def test_principal_from_scope_user():
    assert _row(user=_User("alice"))["principal"] == "alice"
    assert _row(user=_User("alice", is_authenticated=False))["principal"] is None
    assert _row(user=None)["principal"] is None
    assert _row(Masker(Exposure.METADATA_ONLY, True), user=_User("alice"))["principal"] is None


def test_remote_address_none_client():
    assert _row(client=None)["remoteAddress"] is None
    assert _row(client=("10.0.0.5", 1))["remoteAddress"] == "10.0.0.5"


def test_shape_keys_match_bootui():
    # ported: HttpExchangeDto, HttpHeaderDto, HttpExchangesReport, PageMetadata
    assert DTO_KEYS == (
        "id", "timestamp", "method", "path", "query", "uri", "status", "statusFamily", "durationMs",
        "responseSizeBytes", "remoteAddress", "principal", "sessionId", "traceId", "requestHeaders", "responseHeaders",
    )  # fmt: skip
    buffer = HttpExchangeBuffer(5)
    buffer.add(_row(request_headers=[(b"accept", b"*/*")]))
    report = buffer.report(None, None, None, None, None)
    assert list(report) == ["total", "recorded", "hiddenSelf", "exchanges", "page", "unavailableReason"]
    assert list(report["page"]) == ["total", "matched", "offset", "limit", "returned", "hasMore"]
    dto = report["exchanges"][0]
    assert tuple(dto) == DTO_KEYS
    assert list(dto["requestHeaders"][0]) == ["name", "values", "masked"]
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z", dto["timestamp"])
    assert dto["timestamp"] == "2024-01-01T00:00:00.123Z"
    assert dto["sessionId"] is None
    assert (report["total"], report["recorded"], report["hiddenSelf"]) == (1, 1, 0)
    buffer.count_hidden_self()
    assert buffer.report(None, None, None, None, None)["recorded"] == 2
    buffer.unavailable_reason = "nope"
    unavailable = buffer.report(None, None, None, None, None)
    assert (unavailable["exchanges"], unavailable["unavailableReason"]) == ([], "nope")
    assert list(unavailable) == list(report)
