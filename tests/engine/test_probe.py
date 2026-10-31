"""HTTP Probe validation (ported from BootUI ``HttpProbeServiceTests`` / ``HttpProbeLimitsTests``)."""

from __future__ import annotations

import pytest

from sharpit.engine.paging import BadRequest
from sharpit.engine.probe import RESTRICTED_HEADERS, ProbeSlots, validate_probe


@pytest.mark.parametrize(
    ("body", "message"),
    [
        ({"method": "G" * 33, "path": "/"}, "HTTP Probe request method exceeds the maximum of 32 bytes"),
        (
            {"method": "TRACE", "path": "/"},
            "HTTP Probe request method must be one of GET, HEAD, POST, PUT, PATCH, DELETE, OPTIONS",
        ),
        ({"method": "GET", "path": "/" + "x" * 2048}, "HTTP Probe request path exceeds the maximum of 2048 bytes"),
        ({"method": "GET", "path": "owners"}, "HTTP Probe request path must start with '/'"),
        ({"method": "GET", "path": "//evil.example/a"}, "HTTP Probe request path must not include a host"),
        ({"method": "GET", "path": "/a/../b"}, "HTTP Probe request path must not contain '..' segments"),
        (
            {"method": "POST", "path": "/", "body": "x" * (64 * 1024 + 1)},
            "HTTP Probe request body exceeds the maximum of 65536 bytes",
        ),
        (
            {"method": "GET", "path": "/", "headers": {f"X-{i}": "v" for i in range(51)}},
            "HTTP Probe request exceeds the maximum of 50 request headers",
        ),
        (
            {"method": "GET", "path": "/", "headers": {"X" * 257: "v"}},
            "HTTP Probe request header name exceeds the maximum of 256 bytes",
        ),
        (
            {"method": "GET", "path": "/", "headers": {"X-Big": "v" * 8193}},
            "HTTP Probe request header value exceeds the maximum of 8192 bytes",
        ),
        (
            {"method": "GET", "path": "/", "headers": {"X-" + str(i): "v" * 4096 for i in range(8)}},
            "HTTP Probe request headers exceed the maximum total of 32768 bytes",
        ),
        ({"method": "GET", "path": "/", "headers": {"bad name": "v"}}, "HTTP Probe request header name is invalid"),
        (
            {"method": "GET", "path": "/", "headers": {"X-Test": "bad\rvalue"}},
            "HTTP Probe request header value contains a forbidden character",
        ),
    ],
)
# ported: HttpProbeServiceTests.requestBodyOverTheLimitIsRejectedWithACanonicalMessage,
# pathOverTheLimitIsRejected, methodOverTheLimitIsRejected, headerCountOverTheLimitIsRejected,
# headerNameOverTheLimitIsRejected, headerValueOverTheLimitIsRejected, combinedHeaderSizeOverTheLimitIsRejected
def test_validate_probe_limits_and_messages(body, message):
    with pytest.raises(BadRequest, match=".") as exc:
        validate_probe(body, "/sharpit")
    assert str(exc.value) == message


@pytest.mark.parametrize(
    "path",
    [
        "/sharpit/api/panels",
        "/sharpit%2Fapi/panels",
        "/%73harpit/api/panels",
        "/app/sharpit/api/panels",
    ],
)
def test_validate_probe_refuses_normalized_sharpit_paths(path):
    with pytest.raises(BadRequest, match="HTTP Probe cannot target sharpit itself"):
        validate_probe({"method": "GET", "path": path}, "/sharpit")


# ported: HttpProbeServiceTests.lowercaseMethodNormalizedToUppercase
def test_validate_probe_normalizes_method_strips_restricted_headers_and_preserves_query():
    request = validate_probe(
        {"method": "get", "path": "/owners?password=hunter2", "headers": {"X-Custom": "ok", "Host": "evil"}},
        "/sharpit",
    )
    assert request.method == "GET"
    assert request.path == "/owners?password=hunter2"
    assert request.headers == {"x-custom": "ok"}
    assert "host" in RESTRICTED_HEADERS


def test_validate_probe_ignores_null_header_values():
    request = validate_probe({"path": "/", "headers": {"X-Empty": None}}, "/sharpit")
    assert request.headers == {}


def test_probe_slots_are_bounded_and_release():
    slots = ProbeSlots()
    assert [slots.acquire() for _ in range(5)] == [True, True, True, True, False]
    assert slots.count == 4
    slots.release()
    assert slots.acquire()
    assert slots.count == 4
