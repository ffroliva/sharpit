"""OSV client: querybatch chunking, pagination and validation, advisory fetch (ported from BootUI
OsvVulnerabilityScannerTests; the report status/message/assessment assertions of those cases belong to Task 12)."""

import http.client
import json
import time
import urllib.error
import urllib.request
from typing import Any

import pytest
from vulnfakes import FakeOpener, fixture_text, replies

from sharpit.engine.collectors.vulns.inventory import Package
from sharpit.engine.collectors.vulns.osv import OsvClient, OsvError, QueryResult

BASE = "http://osv.test"
COMPLETE = Package("complete", "1.0.0", None)
WIDGET = Package("widget", "1.0.0", None)


def client(opener: FakeOpener, timeout: float = 2.0) -> OsvClient:
    return OsvClient(BASE, timeout, opener=opener)


def failure(kind: str) -> Any:
    """BootUI's regressionFailure kinds."""
    return {
        "503": (503, "unavailable"),
        "envelope": (200, '{"results":{}}'),
        "json": (200, "{not-json"),
        "cardinality": (200, '{"results":[]}'),
        "timeout": TimeoutError("timed out"),
        "body-cap": (200, '{"results":[{}]}' + " " * (5 * 1024 * 1024)),
        "incomplete-read": (200, http.client.IncompleteRead(b"")),
        "line-too-long": http.client.LineTooLong("header line"),
        "deep-json": (200, "[" * 200000),  # json.loads raises RecursionError
    }[kind]


FAILURES = [
    "503",
    "envelope",
    "json",
    "cardinality",
    "timeout",
    "body-cap",
    "incomplete-read",
    "line-too-long",
    "deep-json",
]


# ported: OsvVulnerabilityScanner.queryBatchRequest (exact body, POST, Content-Type, timeout)
def test_request_body_exact(no_side_effects):
    opener = replies((200, '{"results":[{}]}'))

    client(opener, timeout=7.5).querybatch([Package("jinja2", "3.1.2", "/site")])

    (request,) = opener.requests
    assert request.full_url == "http://osv.test/v1/querybatch"
    assert request.get_method() == "POST"
    assert request.get_header("Content-type") == "application/json"
    assert request.data == b'{"queries":[{"package":{"name":"jinja2","ecosystem":"PyPI"},"version":"3.1.2"}]}'
    assert opener.timeouts == [7.5]


# ported: OsvVulnerabilityScanner.queryBatchChunk (ids per package, recorded querybatch shape)
def test_recorded_querybatch_maps_ids_to_packages(no_side_effects):
    jinja, markupsafe = Package("jinja2", "3.1.2", None), Package("markupsafe", "2.1.5", None)
    opener = replies((200, fixture_text("osv/querybatch.json")))

    result = client(opener).querybatch([jinja, markupsafe])

    assert result == QueryResult(
        ids={jinja: ["GHSA-h75v-3vvj-5mfj", "PYSEC-2017-9999"], markupsafe: []},
        failed=[],
        truncated=False,
        complete={jinja, markupsafe},
    )


# ported: OsvVulnerabilityScanner.queryBatch (no packages, no request)
def test_empty_input_sends_nothing(no_side_effects):
    opener = replies()
    assert client(opener).querybatch([]) == QueryResult(ids={}, failed=[], truncated=False, complete=set())
    assert opener.requests == []


# ported: OsvVulnerabilityScanner.queryBatch (transport failure on the first page is an error)
@pytest.mark.parametrize("error", [TimeoutError("timed out"), urllib.error.URLError("refused"), OSError("reset")])
def test_timeout_raises_osv_error(no_side_effects, error: BaseException):
    with pytest.raises(OsvError):
        client(replies(error)).querybatch([WIDGET])


# ported: OsvVulnerabilityScannerTests.initialPaginationFailureIsErrorWithoutCompletedQueries
@pytest.mark.parametrize("kind", FAILURES)
def test_initial_failure_raises(no_side_effects, kind: str):
    with pytest.raises(OsvError) as raised:
        client(replies(failure(kind))).querybatch([WIDGET])
    if kind == "body-cap":
        assert "Response body exceeds 5242880 bytes" in str(raised.value)


# ported: OsvVulnerabilityScannerTests.reportsErrorWithoutDroppingDependencyInventory
def test_http_500_raises(no_side_effects):
    with pytest.raises(OsvError, match="OSV query returned HTTP 500"):
        client(replies((500, "{}"))).querybatch([WIDGET])


# ported: OsvVulnerabilityScannerTests.reportsErrorWhenQuerybatchResultsDoNotMatchTheQueries
def test_result_cardinality_mismatch_raises(no_side_effects):
    with pytest.raises(OsvError, match="1 results for 2 queries"):
        client(replies((200, '{"results":[{}]}'))).querybatch([COMPLETE, WIDGET])


# ported: OsvVulnerabilityScannerTests.reportsErrorWhenQuerybatchContainsAVulnerabilityWithoutAnId
def test_vulnerability_without_id_raises(no_side_effects):
    with pytest.raises(OsvError, match="vulnerability without a non-blank id"):
        client(replies((200, '{"results":[{"vulns":[{}]}]}'))).querybatch([WIDGET])


# ported: OsvVulnerabilityScanner.queryBatchRequest (each response validation branch)
@pytest.mark.parametrize(
    ("body", "message"),
    [
        ("[]", "did not contain a results array"),
        ('{"results":[[]]}', "non-object result"),
        ('{"results":[{"vulns":{}}]}', "non-array vulns field"),
        ('{"results":[{"vulns":null}]}', "non-array vulns field"),
        ('{"results":[{"vulns":["GHSA-x"]}]}', "vulnerability without a non-blank id"),
        ('{"results":[{"vulns":[{"id":" "}]}]}', "vulnerability without a non-blank id"),
        ('{"results":[{"next_page_token":7}]}', "non-string next_page_token"),
    ],
)
def test_invalid_response_shapes_raise(no_side_effects, body: str, message: str):
    with pytest.raises(OsvError, match=message):
        client(replies((200, body))).querybatch([WIDGET])


# ported: OsvVulnerabilityScanner.queryBatchRequest (blank next_page_token is absent)
def test_null_or_blank_page_token_completes_the_query(no_side_effects):
    opener = replies((200, '{"results":[{"next_page_token":null},{"next_page_token":" "}]}'))
    assert client(opener).querybatch([COMPLETE, WIDGET]).failed == []
    assert len(opener.requests) == 1


# ported: OsvVulnerabilityScannerTests.retainsValidatedPagesWhenLaterPaginationFails
@pytest.mark.parametrize("kind", FAILURES)
def test_later_page_failure_keeps_earlier_pages(no_side_effects, kind: str):
    opener = replies(
        (200, '{"results":[{},{"vulns":[{"id":"V-RETAINED"}],"next_page_token":"next"}]}'),
        failure(kind),
    )

    result = client(opener).querybatch([COMPLETE, WIDGET])

    assert len(opener.requests) == 2
    (second,) = opener.bodies()[1]["queries"]
    assert second == {"package": {"name": "widget", "ecosystem": "PyPI"}, "version": "1.0.0", "page_token": "next"}
    assert result == QueryResult(
        ids={COMPLETE: [], WIDGET: ["V-RETAINED"]}, failed=[WIDGET], truncated=False, complete={COMPLETE}
    )


# ported: OsvVulnerabilityScannerTests.validTokenPageIsPartialEvenWithoutAnyCompletedQuery
@pytest.mark.parametrize("has_advisory", [False, True])
def test_valid_token_page_then_failure(no_side_effects, has_advisory: bool):
    vulns = '[{"id":"V-RETAINED"}]' if has_advisory else "[]"
    opener = replies((200, '{"results":[{"next_page_token":"next","vulns":' + vulns + "}]}"), (503, "unavailable"))

    result = client(opener).querybatch([WIDGET])

    assert len(opener.requests) == 2
    assert result == QueryResult(
        ids={WIDGET: ["V-RETAINED"] if has_advisory else []}, failed=[WIDGET], truncated=False, complete=set()
    )


# ported: OsvVulnerabilityScannerTests.followsOsvQuerybatchPaginationUntilNextPageTokenIsAbsent
def test_follows_pagination_until_token_absent(no_side_effects):
    opener = replies(
        (200, '{"results":[{"vulns":[{"id":"GHSA-PAGE-1"}],"next_page_token":"page-2"}]}'),
        (200, '{"results":[{"vulns":[{"id":"GHSA-PAGE-2"}]}]}'),
    )

    result = client(opener).querybatch([WIDGET])

    assert len(opener.requests) == 2
    assert result == QueryResult(
        ids={WIDGET: ["GHSA-PAGE-1", "GHSA-PAGE-2"]}, failed=[], truncated=False, complete={WIDGET}
    )


# ported: OsvVulnerabilityScannerTests.degradesToPartialWhenOsvPaginationExceedsTheSafetyBound
def test_pagination_truncated(no_side_effects):
    calls = 0

    def endless(_request: urllib.request.Request) -> tuple[int, str]:
        nonlocal calls
        calls += 1
        paged = {"vulns": [{"id": f"GHSA-INF-{calls}"}], "next_page_token": f"tok-{calls}"}
        return 200, json.dumps({"results": [{}, paged] if calls == 1 else [paged]})

    result = client(FakeOpener(endless)).querybatch([COMPLETE, WIDGET])

    assert calls == 20
    assert result.truncated is True
    assert result.failed == []
    assert result.ids[WIDGET] == [f"GHSA-INF-{i}" for i in range(1, 21)]
    assert result.complete == {COMPLETE}  # the truncated package is neither failed nor complete


# ported: OsvVulnerabilityScannerTests.partitionsQuerybatchRequestsWhenThePackageListExceedsOsvsHardBatchLimit
def test_chunks_of_1000(no_side_effects):
    pkgs = [Package(f"sample{i}", "1.0.0", None) for i in range(1500)]

    def echo(request: urllib.request.Request) -> tuple[int, str]:
        count = len(json.loads(request.data)["queries"])  # type: ignore[arg-type]
        return 200, json.dumps({"results": [{"vulns": []}] * count})

    opener = FakeOpener(echo)
    result = client(opener).querybatch(pkgs)

    assert [len(b["queries"]) for b in opener.bodies()] == [1000, 500]
    assert list(result.ids) == pkgs
    assert result.failed == []


# ported: OsvVulnerabilityScannerTests.preservesCompletedQueryChunksWhenALaterChunkFails
def test_failed_chunk_reported(no_side_effects):
    pkgs = [Package(f"sample{i}", "1.0.0", None) for i in range(1001)]
    opener = replies((200, '{"results":[' + "{}," * 999 + "{}]}"), (503, "unavailable"))

    result = client(opener).querybatch(pkgs)

    assert len(opener.requests) == 2
    assert result.failed == [pkgs[1000]]
    assert result.complete == set(pkgs[:1000])
    assert list(result.ids) == pkgs[:1000]
    assert result.truncated is False


# ported: OsvVulnerabilityScanner.queryBatch (stops at the first failed chunk)
def test_failed_chunk_also_fails_every_later_chunk(no_side_effects):
    pkgs = [Package(f"sample{i}", "1.0.0", None) for i in range(2500)]
    opener = replies((200, '{"results":[' + "{}," * 999 + "{}]}"), TimeoutError("timed out"))

    result = client(opener).querybatch(pkgs)

    assert len(opener.requests) == 2  # BootUI stops at the first failed chunk
    assert result.failed == pkgs[1000:]
    assert list(result.ids) == pkgs[:1000]


# ported: OsvVulnerabilityScanner.queryBatchChunk (later-page failure in a later chunk)
def test_failure_mid_pagination_in_a_later_chunk_fails_the_rest(no_side_effects):
    pkgs = [Package(f"sample{i}", "1.0.0", None) for i in range(1002)]
    first = {"results": [{}] * 1000}
    paged = {"results": [{"vulns": [{"id": "V-1"}], "next_page_token": "t"}, {}]}
    opener = replies((200, json.dumps(first)), (200, json.dumps(paged)), (503, "unavailable"))

    result = client(opener).querybatch(pkgs)

    assert result.failed == [pkgs[1000]]  # pkgs[1001] completed on the chunk's first page
    assert result.ids[pkgs[1000]] == ["V-1"]
    assert len(opener.requests) == 3


# ported: OsvVulnerabilityScannerTests.deduplicatesRepeatedIdsAndRejectsMismatchedAdvisoryDetails (dedupe half)
def test_repeated_ids_deduplicated(no_side_effects):
    body = '{"results":[{"vulns":[{"id":"V-DUPLICATE"},{"id":"V-DUPLICATE"},{"id":"V-MISMATCH"}]}]}'
    assert client(replies((200, body))).querybatch([WIDGET]).ids[WIDGET] == ["V-DUPLICATE", "V-MISMATCH"]


# ported: OsvVulnerabilityScanner.fetchVulnerability (GET, timeout, recorded advisory)
def test_vuln_fetches_recorded_advisory(no_side_effects):
    opener = replies((200, fixture_text("osv/GHSA-h75v-3vvj-5mfj.json")))

    doc = client(opener, timeout=3.0).vuln("GHSA-h75v-3vvj-5mfj")

    assert doc["id"] == "GHSA-h75v-3vvj-5mfj"
    (request,) = opener.requests
    assert request.full_url == "http://osv.test/v1/vulns/GHSA-h75v-3vvj-5mfj"
    assert request.get_method() == "GET"
    assert opener.timeouts == [3.0]


# ported: OsvVulnerabilityScanner.fetchVulnerability (id path-encoded)
def test_vuln_id_is_url_encoded(no_side_effects):
    opener = replies((200, '{"id":"A B/C?"}'))
    client(opener).vuln("A B/C?")
    assert opener.requests[0].full_url == "http://osv.test/v1/vulns/A%20B%2FC%3F"


# ported: OsvVulnerabilityScannerTests.degradesToPartialInsteadOfErrorWhenOneOfSeveralAdvisoryFetchesFails
# ported: OsvVulnerabilityScannerTests.degradesToPartialInsteadOfThrowingWhenAnAdvisoryResponseIsMalformedJson
@pytest.mark.parametrize(
    "reply",
    [
        (503, "unavailable"),
        (200, "{bad"),
        (200, "[]"),
        (200, "{}" + " " * (1024 * 1024)),
        TimeoutError("timed out"),
    ],
)
def test_vuln_failures_raise_osv_error(no_side_effects, reply: Any):
    with pytest.raises(OsvError):
        client(replies(reply)).vuln("V-FAIL")


# new: opener=None builds urllib's opener on first use, not at definition time
def test_default_opener_is_built_lazily(no_side_effects, monkeypatch: pytest.MonkeyPatch):
    built: list[FakeOpener] = []

    def build_opener() -> FakeOpener:
        built.append(replies((200, '{"results":[{}]}')))
        return built[-1]

    monkeypatch.setattr(urllib.request, "build_opener", build_opener)
    osv = OsvClient(BASE, 1.0)
    osv.querybatch([WIDGET])

    assert len(built) == 1
    assert len(built[0].requests) == 1


# new (code review #8, spec §14): the base URI's path is kept, so a mirror under a path prefix works
@pytest.mark.parametrize("base", ["http://osv.test/mirror", "http://osv.test/mirror/"])
def test_base_uri_path_is_kept(no_side_effects, base: str):
    opener = replies((200, '{"results":[{}]}'), (200, '{"id":"X-1"}'))
    client = OsvClient(base, 1.0, opener=opener)
    client.querybatch([WIDGET])
    client.vuln("X-1")
    assert [r.full_url for r in opener.requests] == [
        "http://osv.test/mirror/v1/querybatch",
        "http://osv.test/mirror/v1/vulns/X-1",
    ]


# ported: OsvVulnerabilityScannerTests.preservesCompletedQueryChunksWhenALaterChunkFails (each failure type)
@pytest.mark.parametrize("kind", FAILURES)
def test_later_chunk_failure_of_any_kind_is_reported(no_side_effects, kind: str):
    pkgs = [Package(f"sample{i}", "1.0.0", None) for i in range(1001)]
    opener = replies((200, '{"results":[' + "{}," * 999 + "{}]}"), failure(kind))

    result = client(opener).querybatch(pkgs)

    assert result.failed == [pkgs[1000]]
    assert pkgs[1000] not in result.complete


# new: id dedupe stays linear (a set per package, not a list scan)
def test_many_ids_on_one_page_are_deduplicated_quickly(no_side_effects):
    vulns = [{"id": f"GHSA-{i:06d}"} for i in range(50_000)]
    body = json.dumps({"results": [{"vulns": vulns + vulns[:10]}]})

    started = time.perf_counter()
    result = client(replies((200, body))).querybatch([WIDGET])

    assert time.perf_counter() - started < 2.0
    assert len(result.ids[WIDGET]) == 50_000
