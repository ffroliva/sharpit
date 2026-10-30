"""CVSS v3 base score and severity buckets (ported from BootUI CvssV3BaseScoreTests / DependencyReports)."""

import math

import pytest

from sharpit.engine.collectors.vulns.cvss import cvss3_base_score, parse_score, severity_for, severity_from_text

BASE_METRICS = "AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"
OPTIONAL = {
    "E": "XUPFH",
    "RL": "XOTWU",
    "RC": "XURC",
    "CR": "XHML",
    "IR": "XHML",
    "AR": "XHML",
    "MAV": "XNALP",
    "MAC": "XLH",
    "MPR": "XNLH",
    "MUI": "XNR",
    "MS": "XUC",
    "MC": "XHLN",
    "MI": "XHLN",
    "MA": "XHLN",
}


# ported: CvssV3BaseScoreTests.matchesNvdPublishedScoreForCve202011619ScopeUnchanged
def test_nvd_cve_2020_11619_scope_unchanged():
    assert cvss3_base_score("CVSS:3.1/AV:N/AC:H/PR:N/UI:N/S:U/C:H/I:H/A:H") == pytest.approx(8.1, abs=0.001)


# ported: CvssV3BaseScoreTests.matchesNvdPublishedScoreForCve202145046ScopeChanged
def test_nvd_cve_2021_45046_scope_changed():
    assert cvss3_base_score("CVSS:3.1/AV:N/AC:H/PR:N/UI:N/S:C/C:H/I:H/A:H") == pytest.approx(9.0, abs=0.001)


# ported: CvssV3BaseScoreTests.matchesNvdPublishedScoreForLog4Shell
def test_log4shell_is_ten():
    assert cvss3_base_score("CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H") == pytest.approx(10.0, abs=0.001)


# ported: CvssV3BaseScoreTests.computesTheCommonCriticalNetworkVector
def test_common_critical_network_vector():
    assert cvss3_base_score("CVSS:3.1/" + BASE_METRICS) == pytest.approx(9.8, abs=0.001)


# ported: CvssV3BaseScoreTests.computesARealModerateSeverityVectorObservedOnOsvDev
def test_real_moderate_vector():
    assert cvss3_base_score("CVSS:3.1/AV:N/AC:L/PR:N/UI:R/S:U/C:L/I:L/A:N") == pytest.approx(5.4, abs=0.001)


# ported: CvssV3BaseScoreTests.returnsZeroWhenThereIsNoConfidentialityIntegrityOrAvailabilityImpact
def test_zero_without_impact():
    assert cvss3_base_score("CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:N") == 0.0


# ported: CvssV3BaseScoreTests.supportsTheCvss30PrefixWithTheIdenticalFormula
def test_cvss30_prefix():
    assert cvss3_base_score("CVSS:3.0/" + BASE_METRICS) == pytest.approx(9.8, abs=0.001)


# ported: CvssV3BaseScoreTests.ignoresTrailingTemporalMetricsWhenComputingTheBaseScore
def test_ignores_trailing_temporal_metrics():
    assert cvss3_base_score("CVSS:3.1/" + BASE_METRICS + "/E:P/RL:O/RC:C") == pytest.approx(9.8, abs=0.001)


# ported: CvssV3BaseScoreTests.toleratesMetricsInNonPreferredOrder
def test_metrics_in_any_order():
    assert cvss3_base_score("CVSS:3.1/S:U/AV:N/AC:L/PR:H/UI:N/C:L/I:L/A:N") == pytest.approx(3.8, abs=0.001)


# ported: CvssV3BaseScoreTests.returnsNullForACvss40Vector
def test_cvss40_is_none():
    assert cvss3_base_score("CVSS:4.0/AV:N/AC:L/AT:N/PR:N/UI:N/VC:N/VI:N/VA:N/SC:N/SI:L/SA:N") is None


# ported: CvssV3BaseScoreTests.returnsNullForNull
def test_none_is_none():
    assert cvss3_base_score(None) is None


# ported: CvssV3BaseScoreTests.returnsNullWhenTheVectorHasNoCvssPrefix
def test_unprefixed_v2_is_none():
    assert cvss3_base_score("AV:N/AC:L/Au:N/C:P/I:P/A:P") is None


# ported: CvssV3BaseScoreTests.returnsNullWhenAMandatoryBaseMetricIsMissing
def test_missing_base_metric_is_none():
    assert cvss3_base_score("CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H") is None


# ported: CvssV3BaseScoreTests.returnsNullWhenAMetricValueIsNotRecognized
def test_unrecognised_value_is_none():
    assert cvss3_base_score("CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:X/C:H/I:H/A:H") is None


# ported: CvssV3BaseScoreTests.returnsNullForAMalformedSegmentWithNoColon
def test_segment_without_colon_is_none():
    assert cvss3_base_score("CVSS:3.1/AV:N/GARBAGE/PR:N/UI:N/S:U/C:H/I:H/A:H") is None


# ported: CvssV3BaseScoreTests.returnsNullWhenAMetricAppearsMoreThanOnce
def test_duplicate_metric_is_none():
    assert cvss3_base_score("CVSS:3.1/AV:N/AV:L/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H") is None


# ported: CvssV3BaseScoreTests.returnsNullWhenASegmentContainsMoreThanOneColon
def test_segment_with_two_colons_is_none():
    assert cvss3_base_score("CVSS:3.1/AV:N:EXTRA/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H") is None


# ported: CvssV3BaseScoreTests.validatesEveryOptionalMetricValueWithoutChangingTheBaseScore
def test_every_optional_metric_value_validated():
    for prefix in ("CVSS:3.0/", "CVSS:3.1/"):
        for metric, values in OPTIONAL.items():
            for value in values:
                vector = f"{prefix}{metric}:{value}/{BASE_METRICS}"
                assert cvss3_base_score(vector) == 9.8, vector
            invalid = f"{prefix}{BASE_METRICS}/{metric}:Z"
            assert cvss3_base_score(invalid) is None, invalid


# ported: CvssV3BaseScoreTests.acceptsACompleteEnvironmentalVectorButStillComputesOnlyBaseMetrics
def test_complete_environmental_vector_scores_base_only():
    optional = "/E:U/RL:O/RC:U/CR:L/IR:L/AR:L/MAV:P/MAC:H/MPR:H/MUI:R/MS:C/MC:N/MI:N/MA:N"
    assert cvss3_base_score("CVSS:3.1/" + BASE_METRICS + optional) == 9.8
    assert cvss3_base_score("CVSS:3.0/" + BASE_METRICS + optional) == 9.8


# ported: CvssV3BaseScoreTests.rejectsEmptySegmentsUnknownMetricsMalformedOptionalValuesAndDuplicates
@pytest.mark.parametrize(
    "vector",
    [
        "CVSS:3.1/" + BASE_METRICS + "/",
        "CVSS:3.1//" + BASE_METRICS,
        "CVSS:3.1/" + BASE_METRICS.replace("/AC:", "//AC:"),
        "CVSS:3.1/" + BASE_METRICS + "/UNKNOWN:N",
        "CVSS:3.1/" + BASE_METRICS + "/E:",
        "CVSS:3.1/" + BASE_METRICS + "/E:UP",
        "CVSS:3.1/" + BASE_METRICS + "/E:p",
        "CVSS:3.1/" + BASE_METRICS + "/E:P/E:H",
        "CVSS:3.1/" + BASE_METRICS + "/E:P:extra",
        "CVSS:3.1/" + BASE_METRICS + "/MS:H",
        "CVSS:3.1/" + BASE_METRICS + "/RL:O ",
        "CVSS:3.1/",
    ],
)
def test_rejects_malformed_vectors(vector: str):
    assert cvss3_base_score(vector) is None


# ported: CvssV3BaseScoreTests.optionalMetricsCannotSubstituteForMissingBaseMetrics
def test_optional_metrics_cannot_substitute_base_metrics():
    assert cvss3_base_score("CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/MA:H") is None
    assert cvss3_base_score("CVSS:3.1/" + BASE_METRICS.replace("AV:N", "AV:X")) is None


# ported: CvssV3BaseScore.roundUp (Java Math.round is half-up)
def test_roundup_is_half_up_not_bankers():
    # Java Math.round is half-up; Python round() is banker's. 8.1 (CVE-2020-11619) and 3.8 depend on it.
    assert cvss3_base_score("CVSS:3.1/AV:N/AC:L/PR:H/UI:N/S:U/C:L/I:L/A:N") == 3.8


# ported: DependencyReports.normalizeSeverity(double) (thresholds used by every scanner test)
@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (10.0, "CRITICAL"),
        (9.0, "CRITICAL"),
        (8.99, "HIGH"),
        (7.0, "HIGH"),
        (6.9, "MEDIUM"),
        (4.0, "MEDIUM"),
        (3.9, "LOW"),
        (0.1, "LOW"),
        (0.0, "NONE"),
        (-0.1, "UNKNOWN"),
        (10.1, "UNKNOWN"),
        (math.nan, "UNKNOWN"),
        (math.inf, "UNKNOWN"),
        (None, "UNKNOWN"),
    ],
)
def test_severity_for_bootui_thresholds(score: float | None, expected: str):
    assert severity_for(score) == expected


# ported: DependencyReports.normalizeSeverity(String)
# (OsvVulnerabilityScannerTests.fallsBackToDatabaseSpecificSeverity...)
@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("MODERATE", "MEDIUM"),
        (" moderate ", "MEDIUM"),
        ("high", "HIGH"),
        ("CRITICAL", "CRITICAL"),
        ("LOW", "LOW"),
        ("NONE", "NONE"),
        ("UNSUPPORTED", "UNKNOWN"),
        ("", "UNKNOWN"),
        (None, "UNKNOWN"),
    ],
)
def test_severity_from_text(label: str | None, expected: str):
    assert severity_from_text(label) == expected


# ported: OsvVulnerabilityScannerTests.usesOnlyTypedCvssV3EntriesAndChoosesTheHighestScore (parseScore half)
def test_parse_score_only_reads_typed_cvss_v3():
    assert parse_score("Ubuntu", "9.9") is None
    assert parse_score("CVSS_V2", "10.0") is None
    assert parse_score("CVSS_V3", "9.8") is None
    assert parse_score("CVSS_V3", None) is None
    assert parse_score("CVSS_V3", "CVSS:3.1/" + BASE_METRICS) == 9.8
