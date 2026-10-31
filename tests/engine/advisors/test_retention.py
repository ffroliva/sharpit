"""Per-scan violation retention and paging (spec §8; BootUI ``AdvisorScanState``, ``AdvisorViolationCollector``,
``AdvisorViolationException`` and ``AdvisorRuleViolationsDto``)."""

import re

import pytest

from sharpit.engine.advisors.retention import AdvisorViolationError, ViolationRetention, parse_integer

NO_SCAN = "No completed advisor scan is available. Reread the cached report before requesting details."
REPLACED = "Advisor scan has been replaced. Reread the cached report before requesting details."
NO_FINDINGS = "Advisor rule has no findings in the current scan."


def _error(status: int, message: str) -> object:
    return pytest.raises(AdvisorViolationError, match=f"^{re.escape(message)}$")


def _status(exc: pytest.ExceptionInfo[AdvisorViolationError]) -> int:
    return exc.value.status


def test_shape_keys_match_bootui():
    retention = ViolationRetention(10_000)
    scan_id = retention.store({"RAPI-A": ["v1", "v2", "v3"]})
    assert re.fullmatch(r"[0-9a-f]{16}", scan_id)
    dto = retention.page(scan_id, "RAPI-A", None, None, 1000)
    assert list(dto) == ["scanId", "ruleId", "violationCount", "retainedCount", "truncated", "violations", "page"]
    assert list(dto["page"]) == ["total", "matched", "offset", "limit", "returned", "hasMore"]
    assert dto == {
        "scanId": scan_id,
        "ruleId": "RAPI-A",
        "violationCount": 3,
        "retainedCount": 3,
        "truncated": False,
        "violations": ["v1", "v2", "v3"],
        "page": {"total": 3, "matched": 3, "offset": 0, "limit": 100, "returned": 3, "hasMore": False},
    }
    # AdvisorViolationDetailsDto
    assert retention.details() == {
        "scanId": scan_id,
        "total": 3,
        "retained": 3,
        "retentionLimit": 10_000,
        "truncated": False,
    }
    assert ViolationRetention(5).details() == {
        "scanId": None,
        "total": 0,
        "retained": 0,
        "retentionLimit": 0,
        "truncated": False,
    }


def test_retention_latest_scan_only():
    retention = ViolationRetention(10)
    first = retention.store({"RAPI-A": ["old"]})
    second = retention.store({"RAPI-A": ["new"]})
    assert first != second
    assert retention.page(second, "RAPI-A", None, None, 1000)["violations"] == ["new"]
    with _error(409, REPLACED) as exc:
        retention.page(first, "RAPI-A", None, None, 1000)
    assert _status(exc) == 409


def test_stale_scan_id():
    retention = ViolationRetention(10)
    with _error(409, NO_SCAN) as exc:
        retention.page("0123456789abcdef", "RAPI-A", None, None, 1000)
    assert _status(exc) == 409
    scan_id = retention.store({"RAPI-A": ["v"], "RAPI-EMPTY": []})
    with _error(409, REPLACED):
        retention.page("0123456789abcdef", "RAPI-A", None, None, 1000)
    for rule in ("RAPI-B", "RAPI-EMPTY"):  # a rule with no violations is not indexed (BootUI record skips 0)
        with _error(404, NO_FINDINGS) as exc:
            retention.page(scan_id, rule, None, None, 1000)
        assert _status(exc) == 404


def test_retained_cap_spans_rules_and_marks_truncation():
    retention = ViolationRetention(3)
    scan_id = retention.store({"RAPI-A": ["a1", "a2"], "RAPI-B": ["b1", "b2", "b3"], "RAPI-C": ["c1"]})
    a = retention.page(scan_id, "RAPI-A", None, None, 1000)
    b = retention.page(scan_id, "RAPI-B", None, None, 1000)
    c = retention.page(scan_id, "RAPI-C", None, None, 1000)
    assert (a["retainedCount"], a["truncated"]) == (2, False)
    assert (b["violationCount"], b["retainedCount"], b["truncated"], b["violations"]) == (3, 1, True, ["b1"])
    assert (c["violationCount"], c["retainedCount"], c["truncated"], c["violations"]) == (1, 0, True, [])
    assert retention.details() == {"scanId": scan_id, "total": 6, "retained": 3, "retentionLimit": 3, "truncated": True}


def test_limit_clamp():
    retention = ViolationRetention(5000)
    scan_id = retention.store({"RAPI-A": [f"v{i}" for i in range(1500)]})
    assert retention.page(scan_id, "RAPI-A", None, None, 1000)["page"]["limit"] == 100
    assert retention.page(scan_id, "RAPI-A", None, 5000, 2000)["page"]["limit"] == 1000
    assert retention.page(scan_id, "RAPI-A", None, 5000, 250)["page"]["limit"] == 250
    assert retention.page(scan_id, "RAPI-A", None, None, 50)["page"]["limit"] == 50  # the default is capped too
    page = retention.page(scan_id, "RAPI-A", 1490, 20, 1000)
    assert (page["violations"], page["page"]["hasMore"]) == ([f"v{i}" for i in range(1490, 1500)], False)
    assert retention.page(scan_id, "RAPI-A", 5000, 10, 1000)["violations"] == []


@pytest.mark.parametrize(
    ("rule", "scan", "offset", "limit", "message"),
    [
        ("", "s", None, None, "Advisor rule ID must not be blank."),
        ("  ", "s", None, None, "Advisor rule ID must not be blank."),
        ("RAPI-A", "", None, None, "Advisor scan ID must not be blank."),
        ("RAPI-A", None, None, None, "Advisor scan ID must not be blank."),
        ("RAPI-A", "s", -1, None, "Advisor violation offset must not be negative."),
        ("RAPI-A", "s", None, 0, "Advisor violation limit must be positive."),
    ],
)
def test_bad_input_400(rule: str, scan: str | None, offset: int | None, limit: int | None, message: str):
    with _error(400, message) as exc:
        ViolationRetention(10).page(scan, rule, offset, limit, 1000)
    assert _status(exc) == 400


# ported: AdvisorViolationException.parseInteger
def test_parse_integer():
    assert parse_integer(None, "offset") is None
    assert parse_integer("-3", "offset") == -3
    assert parse_integer("42", "limit") == 42
    for raw, name, word in [("x", "offset", "offset"), ("1.5", "limit", "limit"), ("2147483648", "q", "parameter")]:
        with _error(400, f"Advisor violation {word} must be a valid 32-bit integer."):
            parse_integer(raw, name)


def test_max_retained_must_be_positive():
    with pytest.raises(ValueError, match="Advisor violation retention limit must be positive."):
        ViolationRetention(0)
