"""EPSS client (ported from BootUI OsvVulnerabilityScannerTests EPSS cases and DependencyReports helpers).

``scores`` never raises: like BootUI ``applyEpss`` it keeps the scores gathered before a failure and reports
``failed=True``, so "no data" and "enrichment failed" stay distinguishable. Choosing the best alias per finding and the
report message are Task 12's (BootUI ``DependencyReports.applyEpssScores`` and ``OsvVulnerabilityScanner.applyEpss``).
"""

import http.client
import json
import urllib.parse
import urllib.request
from typing import Any

import pytest
from vulnfakes import FakeOpener, fixture_text, replies

from sharpit.engine.collectors.vulns.epss import EpssClient, EpssResult, canonical_cve_id, epss_cve_chunks

BASE = "http://epss.test"
LONG_ONE = "CVE-2024-" + "1" * 1200
LONG_TWO = "CVE-2024-" + "2" * 1200


def client(opener: FakeOpener, timeout: float = 2.0) -> EpssClient:
    return EpssClient(BASE, timeout, opener=opener)


def ok(scores: dict[str, tuple[float, float]] | None = None) -> EpssResult:
    return EpssResult(scores or {}, failed=False)


def failed(scores: dict[str, tuple[float, float]] | None = None) -> EpssResult:
    return EpssResult(scores or {}, failed=True)


def query(request: urllib.request.Request) -> dict[str, str]:
    return dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(request.full_url).query))


# ported: OsvVulnerabilityScanner.fetchEpssPage (request URL and row parsing, recorded FIRST.org shape)
def test_recorded_response(no_side_effects):
    opener = replies((200, fixture_text("epss/CVE-2024-34064.json")))

    assert client(opener, timeout=4.0).scores(["CVE-2024-34064"]) == ok({"CVE-2024-34064": (0.00045, 0.16372)})
    (request,) = opener.requests
    assert request.full_url == "http://epss.test/data/v1/epss?cve=CVE-2024-34064&limit=1&offset=0"
    assert request.get_method() == "GET"
    assert opener.timeouts == [4.0]


# ported: OsvVulnerabilityScannerTests.epssEnrichesCveAliasedVulnerabilityWithProbabilityAndPercentile
def test_probability_and_percentile(no_side_effects):
    opener = replies((200, '{"data":[{"cve":"CVE-2021-44228","epss":"0.944500000","percentile":"0.999900000"}]}'))
    assert client(opener).scores(["CVE-2021-44228"]) == ok({"CVE-2021-44228": (0.9445, 0.9999)})
    assert "CVE-2021-44228" in opener.requests[0].full_url


# ported: OsvVulnerabilityScannerTests.malformedEpssSuccessRetainsOsvAndExplainsUnavailableEnrichment
@pytest.mark.parametrize("body", ["", "{}", "[]", "null", "{bad", '{"data":{}}', '{"data":null}'])
def test_malformed_response_fails(no_side_effects, body: str):
    assert client(replies((200, body))).scores(["CVE-2024-1001"]) == failed()


# ported: OsvVulnerabilityScannerTests.epssFailureDoesNotDegradeScanStatusOrDiscardOsvResults
@pytest.mark.parametrize(
    "reply",
    [
        (503, "unavailable"),
        TimeoutError("timed out"),
        OSError("reset"),
        (200, http.client.IncompleteRead(b"")),
        http.client.LineTooLong("header line"),
        (200, "[" * 200000),  # json.loads raises RecursionError
    ],
)
def test_transport_failure_never_raises(no_side_effects, reply: Any):
    assert client(replies(reply)).scores(["CVE-2021-44228"]) == failed()


# ported: OsvVulnerabilityScannerTests.epssNoDataIsDistinctFromReturnedZero
@pytest.mark.parametrize("zero", [False, True])
def test_no_data_is_distinct_from_zero(no_side_effects, zero: bool):
    body = (
        '{"data":[{"cve":"CVE-2024-1001","epss":"0","percentile":"0"}]}'
        if zero
        else '{"total":0,"offset":0,"limit":1,"data":[]}'
    )
    assert client(replies((200, body))).scores(["CVE-2024-1001"]) == ok({"CVE-2024-1001": (0.0, 0.0)} if zero else {})


# ported: OsvVulnerabilityScannerTests.epssMaximumAliasAndMatchingPercentileAreIndependentOfOrder (client half:
# every alias's probability and its own percentile come back, whatever the row order)
@pytest.mark.parametrize("reversed_", [False, True])
def test_every_alias_scored_independent_of_order(no_side_effects, reversed_: bool):
    low = {"cve": "CVE-2024-1003", "epss": "0.1", "percentile": "0.2"}
    top = {"cve": "CVE-2024-1001", "epss": "0.8", "percentile": "0.9"}
    tie = {"cve": "CVE-2024-1002", "epss": "0.8", "percentile": "0.7"}
    rows = [tie, top, low] if reversed_ else [low, top, tie]
    cves = (
        ["CVE-2024-1003", "CVE-2024-1002", "CVE-2024-1001"]
        if reversed_
        else ["CVE-2024-1001", "CVE-2024-1002", "CVE-2024-1003"]
    )

    assert client(replies((200, json.dumps({"data": rows})))).scores(cves) == ok(
        {"CVE-2024-1001": (0.8, 0.9), "CVE-2024-1002": (0.8, 0.7), "CVE-2024-1003": (0.1, 0.2)}
    )


# ported: OsvVulnerabilityScannerTests.epssPaginationIsBoundedAndRetainsEarlierPageScores
@pytest.mark.parametrize(
    "ending",
    ["complete", "503", "no-progress", "offset", "total", "limit", "unrequested", "invalid", "missing-metadata"],
)
def test_pagination_validated(no_side_effects, ending: str):
    row = {"cve": "CVE-2024-1002", "epss": "0.8", "percentile": "0.9"}
    second: Any = {
        "503": (503, "unavailable"),
        "no-progress": (200, '{"total":2,"offset":1,"limit":1,"data":[]}'),
        "offset": (200, '{"total":2,"offset":0,"limit":1,"data":[]}'),
        "total": (200, '{"total":2000,"offset":1,"limit":1,"data":[]}'),
        "limit": (200, '{"total":2,"offset":1,"limit":0,"data":[]}'),
        "missing-metadata": (200, '{"data":[]}'),
        "unrequested": (200, json.dumps({"data": [{**row, "cve": "CVE-2024-9999"}]})),
        "invalid": (200, json.dumps({"data": [{**row, "epss": "NaN"}]})),
    }.get(ending, (200, json.dumps({"total": 2, "offset": 1, "limit": 1, "data": [row]})))
    opener = replies(
        (200, '{"total":2,"offset":0,"limit":1,"data":[{"cve":"CVE-2024-1001","epss":"0.4","percentile":"0.6"}]}'),
        second,
    )

    result = client(opener).scores(["CVE-2024-1001", "CVE-2024-1002"])

    assert len(opener.requests) == 2
    assert [query(r)["offset"] for r in opener.requests] == ["0", "1"]
    assert {query(r)["limit"] for r in opener.requests} == {"2"}
    page_one = {"CVE-2024-1001": (0.4, 0.6)}
    assert result == (ok({**page_one, "CVE-2024-1002": (0.8, 0.9)}) if ending == "complete" else failed(page_one))


# ported: OsvVulnerabilityScannerTests.epssLaterChunkFailureRetainsSuccessfulChunkScores
def test_later_chunk_failure_keeps_earlier_chunk_scores(no_side_effects):
    def first_then_down(request: urllib.request.Request) -> tuple[int, str]:
        if len(opener.requests) == 1:
            cve = query(request)["cve"]
            return 200, json.dumps({"data": [{"cve": cve, "epss": "0.4", "percentile": "0.6"}]})
        return 503, "unavailable"

    opener = FakeOpener(first_then_down)

    assert client(opener).scores([LONG_ONE, LONG_TWO]) == failed({LONG_ONE: (0.4, 0.6)})
    assert len(opener.requests) == 2


# ported: OsvVulnerabilityScannerTests.missingFirstAliasDoesNotHideAnotherAliasesAvailableScore
def test_missing_alias_does_not_hide_another(no_side_effects):
    opener = replies((200, '{"data":[{"cve":"CVE-2024-1002","epss":"0.4","percentile":"0.6"}]}'))
    assert client(opener).scores(["CVE-2024-1001", "CVE-2024-1002"]) == ok({"CVE-2024-1002": (0.4, 0.6)})


# ported: OsvVulnerabilityScannerTests.advisoryWithoutCveDoesNotRequestEpss
@pytest.mark.parametrize("ids", [[], ["GHSA-xxxx-yyyy-zzzz"], ["PYSEC-2024-1", " "]])
def test_no_cve_no_request(no_side_effects, ids: list[str]):
    opener = replies()
    assert client(opener).scores(ids) == ok()
    assert opener.requests == []


# ported: OsvVulnerabilityScannerTests.epssUsesCveRecordIdsAndSplitsRequestsAtTheDocumentedCharacterLimit
# (BootUI's stub answers both chunks with CVE-2024-1234; the second chunk did not request it, so that page fails)
def test_splits_requests_at_the_character_limit(no_side_effects):
    def same_row(request: urllib.request.Request) -> tuple[int, str]:
        cve_parameter = urllib.parse.urlsplit(request.full_url).query.split("&", 1)[0].removeprefix("cve=")
        assert len(cve_parameter) <= 2000
        return 200, '{"data":[{"cve":"CVE-2024-1234","epss":"0.125","percentile":"0.75"}]}'

    opener = FakeOpener(same_row)

    result = client(opener).scores(["cve-2024-1234", LONG_ONE, LONG_TWO])

    assert result == failed({"CVE-2024-1234": (0.125, 0.75)})
    assert len(opener.requests) == 2


# ported: OsvVulnerabilityScanner.fetchEpssChunk row validation (an invalid row fails the page)
@pytest.mark.parametrize(
    "rows",
    [
        [{"cve": "CVE-2024-1001", "epss": "1.5", "percentile": "0.6"}],  # outside 0..1
        [{"cve": "CVE-2024-1001", "epss": "0.4", "percentile": "-0.1"}],
        [{"cve": "CVE-2024-1001", "epss": "inf", "percentile": "0.6"}],
        [{"cve": "CVE-2024-1001", "epss": 0.4, "percentile": "0.6"}],  # BootUI reads string fields only
        [{"cve": "not-a-cve", "epss": "0.4", "percentile": "0.6"}],
        ["CVE-2024-1001"],
    ],
)
def test_invalid_rows_fail(no_side_effects, rows: list[Any]):
    assert client(replies((200, json.dumps({"data": rows})))).scores(["CVE-2024-1001"]) == failed()


# ported: OsvVulnerabilityScanner.fetchEpssChunk (valid rows of a page are kept even when another row is invalid)
def test_invalid_row_keeps_the_pages_valid_rows(no_side_effects):
    row = {"cve": "CVE-2024-1001", "epss": "0.4", "percentile": "0.6"}
    unrequested = {"cve": "CVE-2024-9999", "epss": "0.1", "percentile": "0.1"}
    later = {"cve": "CVE-2024-1002", "epss": "0.2", "percentile": "0.3"}
    body = json.dumps({"data": [row, row, unrequested, later]})

    assert client(replies((200, body))).scores(["CVE-2024-1001", "CVE-2024-1002"]) == failed(
        {"CVE-2024-1001": (0.4, 0.6), "CVE-2024-1002": (0.2, 0.3)}
    )


# ported: OsvVulnerabilityScanner.fetchEpssChunk pagination metadata validation (rows are stored before the check)
@pytest.mark.parametrize("field", ["total", "offset", "limit"])
@pytest.mark.parametrize("value", ["1", 1.5, -1, True, None])
def test_pagination_metadata_must_be_non_negative_integers(no_side_effects, field: str, value: Any):
    body = {"total": 1, "offset": 0, "limit": 1, "data": [{"cve": "CVE-2024-1001", "epss": "0.4", "percentile": "0.6"}]}
    body[field] = value
    assert client(replies((200, json.dumps(body)))).scores(["CVE-2024-1001"]) == failed({"CVE-2024-1001": (0.4, 0.6)})


# ported: BoundedBodyReader 1 MiB EPSS cap
def test_body_cap_fails(no_side_effects):
    body = '{"data":[]}' + " " * (1024 * 1024)
    assert client(replies((200, body))).scores(["CVE-2024-1001"]) == failed()


# ported: DependencyReports.canonicalCveId
@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("CVE-2021-44228", "CVE-2021-44228"),
        (" cve-2021-44228 ", "CVE-2021-44228"),
        ("CVE-2021-123", None),
        ("CVE-21-44228", None),
        ("GHSA-jfh8-c2jp-5v3q", None),
        ("CVE-2021-44228x", None),
        (None, None),
    ],
)
def test_canonical_cve_id(value: str | None, expected: str | None):
    assert canonical_cve_id(value) == expected


# ported: DependencyReports.epssCveChunks
def test_chunks_dedupe_canonicalise_and_respect_2000_chars():
    assert epss_cve_chunks([]) == []
    assert epss_cve_chunks(["cve-2024-0001", "CVE-2024-0001", "bad", "CVE-2024-0002"]) == [
        ["CVE-2024-0001", "CVE-2024-0002"]
    ]
    assert epss_cve_chunks(["CVE-2024-1234", LONG_ONE, LONG_TWO]) == [["CVE-2024-1234", LONG_ONE], [LONG_TWO]]
    too_long = "CVE-2024-" + "9" * 2000
    assert epss_cve_chunks([too_long]) == []
    many = [f"CVE-2024-{i:05d}" for i in range(400)]
    chunks = epss_cve_chunks(many)
    assert [c for chunk in chunks for c in chunk] == many
    assert all(len(",".join(chunk)) <= 2000 for chunk in chunks)
    assert len(",".join(chunks[0])) + len(many[len(chunks[0])]) + 1 > 2000
