"""OSV advisory interpretation (ported from BootUI OsvAdvisoryInterpreterTests and OsvVulnerabilityScannerTests).

Inputs are written as OSV JSON (BootUI tests built the adapter records by hand), the ecosystem is ``PyPI`` and Maven
versions are rewritten as PEP 440 versions ordered by ``packaging.version``. Each Maven-qualifier rewrite is spelled out
next to its test.
"""

import json
from pathlib import Path
from typing import Any

import pytest

from sharpit.engine.collectors.vulns.interpreter import Finding, interpret
from sharpit.engine.collectors.vulns.inventory import Package

OSV = Path(__file__).parents[2] / "fixtures" / "osv"
NAME = "example-lib"
ID = "GHSA-test-0000-0000"
LOW = {"type": "CVSS_V3", "score": "CVSS:3.1/AV:N/AC:L/PR:H/UI:N/S:U/C:L/I:L/A:N"}  # 3.8
MEDIUM = {"type": "CVSS_V3", "score": "CVSS:3.1/AV:N/AC:L/PR:N/UI:R/S:U/C:L/I:L/A:N"}  # 5.4
CRITICAL = {"type": "CVSS_V3", "score": "CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H"}  # 9.8
ZERO = {"type": "CVSS_V3", "score": "CVSS:3.0/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:N"}  # 0.0


def ev(kind: str, version: str) -> dict[str, str]:
    return {kind: version}


def rng(*events: Any, kind: str = "ECOSYSTEM") -> dict[str, Any]:
    return {"type": kind, "events": list(events)}


def entry(introduced: str, fixed: str, severity: dict[str, str]) -> dict[str, Any]:
    return {
        "package": {"ecosystem": "PyPI", "name": NAME},
        "ranges": [rng(ev("introduced", introduced), ev("fixed", fixed))],
        "severity": [severity],
    }


def ranges(*items: Any) -> dict[str, Any]:
    return {"package": {"ecosystem": "PyPI", "name": NAME}, "ranges": list(items), "severity": [LOW]}


def named(ecosystem: str, name: str, severity: dict[str, str]) -> dict[str, Any]:
    return {"package": {"ecosystem": ecosystem, "name": name}, "versions": ["1.5"], "severity": [severity]}


def explicit(versions: list[Any], severity: list[Any], ranges_: list[Any] | None = None) -> dict[str, Any]:
    item: dict[str, Any] = {"package": {"ecosystem": "PyPI", "name": NAME}, "versions": versions, "severity": severity}
    if ranges_ is not None:
        item["ranges"] = ranges_
    return item


def run(
    version: str,
    *affected: Any,
    severity: list[Any] | None = None,
    database: str | None = None,
    name: str = NAME,
) -> Finding:
    advisory: dict[str, Any] = {"id": ID, "affected": list(affected)}
    if severity is not None:
        advisory["severity"] = severity
    if database is not None:
        advisory["database_specific"] = {"severity": database}
    finding = interpret(advisory, Package(name, version, None), ID)
    assert finding is not None
    return finding


def view(f: Finding) -> tuple[str, float | None, list[str], bool]:
    return f.severity, f.score, f.fixed_versions, f.unresolved


# ported: OsvAdvisoryInterpreterTests.selectsOnlyTheInstalledBranchNotTheFirstOrMostSeverePackageEntry
def test_selects_only_the_installed_branch():
    f = run("1.5", entry("2", "2.4", CRITICAL), entry("1", "1.9", LOW))
    assert view(f) == ("LOW", 3.8, ["1.9"], False)


# ported: OsvAdvisoryInterpreterTests.takesTheMaximumSupportedScoreAcrossEveryApplicableEntryAndAssessment
def test_maximum_score_across_applicable_entries():
    f = run("1.5", entry("1", "2", LOW), explicit(["1.5"], [ZERO, CRITICAL, LOW]))
    assert (f.severity, f.score, f.fixed_versions) == ("CRITICAL", 9.8, ["2"])


# adapted: OsvAdvisoryInterpreterTests.requiresExactEcosystemAndPackageButSupportsTheLiteralWildcard
# PyPI names compare PEP 503-normalised, so "Example_Lib" (BootUI's case-variant row) now matches; the ecosystem stays
# exact ("pypi" and "PyPI:https://..." never match) and the wildcard is the literal "*".
def test_exact_ecosystem_normalised_name_and_wildcard():
    unrelated = [
        named("npm", NAME, CRITICAL),
        named("PyPI:https://repo.example", NAME, CRITICAL),
        named("PyPI", "other-lib", CRITICAL),
        named("PyPI", "example-*", CRITICAL),
        named("pypi", NAME, CRITICAL),
    ]
    assert run("1.5", *unrelated, named("PyPI", "*", LOW)).severity == "LOW"
    assert run("1.5", *unrelated, named("PyPI", "*", LOW)).unresolved is False
    assert run("1.5", *unrelated).unresolved is True
    assert run("1.5", named("PyPI", "Example_Lib", LOW)).severity == "LOW"
    assert run("1.5", named("PyPI", "Example.Lib", CRITICAL)).severity == "CRITICAL"


# ported: OsvAdvisoryInterpreterTests.explicitVersionMembershipWorksWithoutRangesButNeverManufacturesAFix
def test_explicit_versions_never_manufacture_a_fix():
    item = explicit(["1.5"], [LOW])
    assert run("1.5", item).severity == "LOW"
    assert run("1.5", item).fixed_versions == []
    assert run("1.6", item).severity == "UNKNOWN"
    assert run("1.6", item).unresolved is True


# ported: OsvAdvisoryInterpreterTests.versionsAndRangesAreAUnionIncludingExplicitVersionsOutsideTheRange
def test_versions_and_ranges_union():
    item = explicit(["3"], [LOW], [rng(ev("introduced", "1"), ev("fixed", "2"))])
    assert run("1.5", item).severity == "LOW"
    assert run("1.5", item).fixed_versions == ["2"]
    assert run("3", item).severity == "LOW"
    assert run("3", item).fixed_versions == []


# ported: OsvAdvisoryInterpreterTests.sortsUnsortedEventsAndAssociatesFixesWithReintroducedIntervals
def test_unsorted_events_and_reintroduced_intervals():
    item = ranges(rng(ev("fixed", "4"), ev("introduced", "3"), ev("fixed", "2"), ev("introduced", "1")))
    assert run("1.5", item).fixed_versions == ["2"]
    assert run("3.5", item).fixed_versions == ["4"]
    assert run("2.5", item).severity == "UNKNOWN"
    assert run("2.5", item).unresolved is True


# adapted: OsvAdvisoryInterpreterTests.introducedZeroPrecedesEvenTheEarliestMavenPrerelease
# Maven "0-alpha" -> PEP 440 "0.dev0" (which sorts *below* "0", so only the introduced-"0" rule admits it).
def test_introduced_zero_precedes_the_earliest_prerelease():
    f = run("0.dev0", ranges(rng(ev("fixed", "1"), ev("introduced", "0"))))
    assert f.severity == "LOW"
    assert f.fixed_versions == ["1"]


# adapted: OsvAdvisoryInterpreterTests.introducedIsInclusiveAndFixedIsExclusiveUsingMavenQualifierAliases
# Maven entry("1.0-rc1", "1.0-final") -> entry("1.0rc1", "1.0"); "1.0-cr1" -> "1.0c1" (PEP 440 alias of rc1);
# "1.0-SNAPSHOT" -> "1.0rc2" (between); "1.0-ga" -> "1.0.0" (equal to the fix).
def test_introduced_inclusive_fixed_exclusive_with_pep440_aliases():
    item = entry("1.0rc1", "1.0", LOW)
    assert run("1.0c1", item).severity == "LOW"
    assert run("1.0rc2", item).fixed_versions == ["1.0"]
    assert run("1.0.0", item).severity == "UNKNOWN"
    assert run("1.0.0", item).fixed_versions == []
    assert run("1.0.0", item).unresolved is True


# ported: OsvAdvisoryInterpreterTests.lastAffectedIsInclusiveAndNeverAFix
def test_last_affected_inclusive_never_a_fix():
    item = ranges(rng(ev("last_affected", "2"), ev("introduced", "1")))
    assert run("2", item).severity == "LOW"
    assert run("2", item).fixed_versions == []
    assert run("2.0.1", item).severity == "UNKNOWN"


# adapted: OsvAdvisoryInterpreterTests.inclusiveSingletonsWorkInBothEventOrdersWithMavenEquivalentEndpoints
# Maven-equivalent endpoints "1.0", "1.0-final", "1.0-ga" -> PEP 440-equal "1.0", "1.0.0", "1.0.0.0".
@pytest.mark.parametrize("endpoint", ["1.0", "1.0.0", "1.0.0.0"])
def test_inclusive_singletons_in_both_orders(endpoint: str):
    introduced, last = ev("introduced", "1.0"), ev("last_affected", endpoint)
    for item in (ranges(rng(introduced, last)), ranges(rng(last, introduced))):
        assert view(run("1.0", item)) == ("LOW", 3.8, [], False)
        assert run("0.9", item).score is None
        assert run("1.0.1", item).score is None


# ported: OsvAdvisoryInterpreterTests.limitsAreExclusiveScopeBoundsNotFixesOrTimelineClosures
def test_limits_are_exclusive_scope_bounds():
    item = ranges(rng(ev("limit", "2"), ev("introduced", "0")))
    assert run("1.5", item).severity == "LOW"
    assert run("1.5", item).fixed_versions == []
    assert run("2", item).severity == "UNKNOWN"


# ported: OsvAdvisoryInterpreterTests.multipleLimitsExpandScopeAndInfinityRestoresUnboundedScope
def test_multiple_limits_and_infinity():
    limited = ranges(rng(ev("limit", "2"), ev("introduced", "0"), ev("limit", "4")))
    infinite = ranges(rng(ev("limit", "2"), ev("limit", "*"), ev("introduced", "0")))
    assert run("3", limited).severity == "LOW"
    assert run("4", limited).severity == "UNKNOWN"
    assert run("9999", infinite).severity == "LOW"
    assert run("9999", infinite).fixed_versions == []


# ported: OsvAdvisoryInterpreterTests.limitsAreIndependentOfFixedAndReintroducedStatusEvents
def test_limits_independent_of_status_events():
    item = ranges(
        rng(ev("limit", "4"), ev("fixed", "2"), ev("introduced", "0"), ev("introduced", "3"), ev("limit", "5"))
    )
    assert run("1.5", item).fixed_versions == ["2"]
    assert run("2.5", item).severity == "UNKNOWN"
    assert run("4.5", item).severity == "LOW"
    assert run("4.5", item).fixed_versions == []


# ported: OsvAdvisoryInterpreterTests.unsupportedDomainsRemainUnresolvedInsteadOfBorrowingPackageSeverityOrFixes
@pytest.mark.parametrize("kind", ["SEMVER", "GIT", "future-domain"])
def test_unsupported_domains_remain_unresolved(kind: str):
    f = run("1.5", ranges(rng(ev("introduced", "0"), ev("fixed", "2"), kind=kind)))
    assert view(f) == ("UNKNOWN", None, [], True)


# ported: OsvAdvisoryInterpreterTests.explicitMembershipCanProvePackageSeverityDespiteAnUnresolvedRange
def test_explicit_membership_despite_unresolved_range():
    item = explicit(["1.5"], [LOW], [rng(ev("introduced", "0"), ev("fixed", "abcdef"), kind="GIT")])
    f = run("1.5", item)
    assert (f.severity, f.fixed_versions, f.unresolved) == ("LOW", [], True)


# ported: OsvAdvisoryInterpreterTests.malformedEventsMissingIntroductionsAndMixedClosuresRemainUnknown
# (adapter-level malformations are JSON here: a multi-key or unknown event object, a blank version, a null element)
@pytest.mark.parametrize(
    "malformed",
    [
        None,
        {"events": [{"introduced": "0"}]},
        rng(),
        rng(ev("fixed", "2")),
        rng(ev("introduced", "0"), ev("limit", "")),
        rng(ev("introduced", "0"), {}),
        rng(ev("introduced", "0"), {"introduced": "1", "fixed": "2"}),
        rng(ev("introduced", "0"), ev("unexpected", "2")),
        rng(ev("introduced", "0"), ev("fixed", "2"), ev("last_affected", "1.9")),
        rng(ev("introduced", "0"), None),
        rng(ev("introduced", "0"), ev("fixed", "not a pep440 version")),
    ],
)
def test_malformed_events_remain_unknown(malformed: Any):
    f = run("1.5", explicit([], [LOW], [malformed]))
    assert (f.severity, f.fixed_versions, f.unresolved) == ("UNKNOWN", [], True)


# adapted: OsvAdvisoryInterpreterTests.contradictoryMavenEquivalentStatusBoundariesDoNotDependOnInputOrder
def test_contradictory_equivalent_boundaries_independent_of_order():
    first = ranges(rng(ev("introduced", "1"), ev("fixed", "1.0")))
    reversed_ = ranges(rng(ev("fixed", "1.0"), ev("introduced", "1")))
    assert run("1", first) == run("1", reversed_)
    assert run("1", first).unresolved is True
    assert run("1", first).fixed_versions == []


# ported: OsvAdvisoryInterpreterTests.emptyMissingAndMalformedEvidenceNeverBecomesAnUnaffectedVerdict
@pytest.mark.parametrize("affected", [[], [None], [{"package": {"ecosystem": "PyPI", "name": NAME}}]])
def test_empty_or_malformed_evidence_is_never_unaffected(affected: list[Any]):
    f = run("1.5", *affected, severity=[CRITICAL])
    assert (f.severity, f.fixed_versions, f.unresolved) == ("CRITICAL", [], True)


# ported: OsvAdvisoryInterpreterTests.emptyMissingAndMalformedEvidenceNeverBecomesAnUnaffectedVerdict (null cases)
def test_blank_package_name_or_missing_lists_are_unresolved():
    assert interpret({"id": ID}, Package(NAME, "", None), ID).unresolved is True  # type: ignore[union-attr]
    assert run("1.5", named("PyPI", "*", LOW), name="").unresolved is True


# ported: OsvAdvisoryInterpreterTests.usesMaximumGlobalAssessmentOnlyWhenNoApplicablePackageSeverityWasSupplied
def test_global_assessment_only_without_package_severity():
    f = run("1.5", explicit(["1.5"], []), severity=[LOW, CRITICAL, ZERO], database="LOW")
    assert (f.score, f.unresolved) == (9.8, False)
    assert run("1.5", entry("1", "2", LOW), severity=[CRITICAL]).score == 3.8


# ported: OsvAdvisoryInterpreterTests.suppliedInvalidOrUnsupportedPackageSeverityDoesNotBorrowConflictingGlobalVectors
@pytest.mark.parametrize(
    "assessment",
    [
        None,
        {},
        {"type": "CVSS_V3", "score": "9.8"},
        {"type": "CVSS_V2", "score": "AV:N/AC:L/Au:N/C:C/I:C/A:C"},
        {"type": "CVSS_V4", "score": "CVSS:4.0/AV:N"},
    ],
)
def test_invalid_package_severity_does_not_borrow_global(assessment: Any):
    item = explicit(["1.5"], [assessment])
    f = run("1.5", item, severity=[CRITICAL], database="MODERATE")
    assert (f.severity, f.score) == ("MEDIUM", None)
    assert run("1.5", item, severity=[CRITICAL]).severity == "UNKNOWN"


# ported: OsvAdvisoryInterpreterTests.knownZeroRemainsNoneAndDoesNotFallBackToADatabaseLabel
def test_known_zero_remains_none():
    f = run("1.5", entry("1", "2", ZERO), severity=[], database="CRITICAL")
    assert (f.score, f.severity) == (0.0, "NONE")


# ported: OsvAdvisoryInterpreterTests.doesNotBorrowAFixFromAnUnrelatedBranchWhenTheInstalledBranchIsOpenEnded
def test_no_fix_borrowed_from_unrelated_branch():
    f = run("1.5", ranges(rng(ev("introduced", "1"))), entry("2", "2.4", CRITICAL))
    assert (f.severity, f.fixed_versions, f.unresolved) == ("LOW", [], False)


# ported: OsvAdvisoryInterpreterTests.rejectsTargetsExplicitlyAffectedByTheSameOrAnotherEntry
def test_rejects_targets_explicitly_affected():
    assert run("1.5", entry("1", "2", LOW), explicit(["2"], [])).fixed_versions == []
    union = explicit(["2"], [LOW], entry("1", "2", LOW)["ranges"])
    assert run("1.5", union).fixed_versions == []


# ported: OsvAdvisoryInterpreterTests.rejectsOverlappingTargetsButRetainsTheFixThatClosesEveryAffectedInterval
def test_keeps_fix_that_closes_every_interval():
    assert run("1.5", entry("1", "2", LOW), entry("1.4", "3", LOW)).fixed_versions == ["3"]


# ported: OsvAdvisoryInterpreterTests.rejectsAFixReintroducedByAnotherEntryEvenIfThatEntryDoesNotMatchInstalledVersion
def test_rejects_fix_reintroduced_by_another_entry():
    f = run("1.5", entry("1", "2", LOW), entry("2", "3", CRITICAL))
    assert (f.severity, f.fixed_versions) == ("LOW", [])


# ported: OsvAdvisoryInterpreterTests.unresolvedTargetEvidenceCannotVerifyAnUpgrade
def test_unresolved_target_evidence_cannot_verify_upgrade():
    f = run("1.5", entry("1", "2", LOW), ranges(rng(ev("introduced", "3"), ev("fixed", "4"), kind="SEMVER")))
    assert (f.severity, f.fixed_versions, f.unresolved) == ("LOW", [], True)


# ported: OsvAdvisoryInterpreterTests.unrelatedOldFixesCannotConsumeTheCandidateDisplayLimit
def test_unrelated_old_fixes_do_not_consume_display_limit():
    items = [entry(f"{i}.0", f"{i}.1", CRITICAL) for i in range(1, 16)]
    f = run("20.5", *items, entry("20", "21", LOW))
    assert (f.fixed_versions, f.severity) == (["21"], "LOW")


# ported: OsvAdvisoryInterpreterTests.blankInstalledVersionPreservesUnknownAndCannotOfferAFix
def test_blank_installed_version():
    f = run(" ", entry("0", "2", LOW))
    assert (f.score, f.fixed_versions, f.unresolved) == (None, [], True)


# adapted: OsvAdvisoryInterpreterTests blank-version case (a non-PEP 440 version cannot be ordered)
def test_non_pep440_installed_version_is_unresolved_like_blank():
    f = run("not-a-version", entry("0", "2", LOW))
    assert (f.score, f.fixed_versions, f.fix_available, f.unresolved) == (None, [], False, True)


# ported: OsvAdvisoryInterpreterTests.malformedExplicitVersionsDoNotHideAProvenMatchButBlockUnverifiedTargets
def test_malformed_explicit_versions_do_not_hide_a_match():
    item = explicit(["1.5", None], [LOW], entry("1", "2", LOW)["ranges"])
    f = run("1.5", item)
    assert (f.severity, f.fixed_versions, f.unresolved) == ("LOW", [], True)


# --- advisory-level cases from OsvVulnerabilityScannerTests (spring-autoconfigure) ---


def advisory(**fields: Any) -> dict[str, Any]:
    return {"id": ID, **fields}


def widget(**fields: Any) -> dict[str, Any]:
    return {"package": {"ecosystem": "PyPI", "name": NAME}, **fields}


def pkg(version: str = "1.0.0") -> Package:
    return Package(NAME, version, None)


# adapted: OsvVulnerabilityScannerTests.enrichesDependenciesWithOsvAdvisories (recorded PyPI advisory, jinja2 3.1.2)
def test_recorded_advisory_with_a_fix():
    doc = json.loads((OSV / "GHSA-h75v-3vvj-5mfj.json").read_text(encoding="utf-8"))
    f = interpret(doc, Package("jinja2", "3.1.2", None), "GHSA-h75v-3vvj-5mfj")
    assert f is not None
    assert f.to_dto() == {
        "id": "GHSA-h75v-3vvj-5mfj",
        "summary": "Jinja vulnerable to HTML attribute injection when passing user input as keys to xmlattr filter",
        "details": doc["details"],
        "severity": "MEDIUM",
        "score": 5.4,
        "aliases": ["CVE-2024-34064"],
        "references": [
            "https://nvd.nist.gov/vuln/detail/CVE-2024-34064",
            "https://github.com/pallets/jinja/commit/0668239dc6b44ef38e7a6c9f91f312fd4ca581cb",
            "https://github.com/pallets/jinja/security/advisories/GHSA-h75v-3vvj-5mfj",
            "https://github.com/pallets/jinja",
        ],
        "fixedVersions": ["3.1.4"],
        "fixAvailable": True,
        "epssScore": None,
        "epssPercentile": None,
        "dismissed": False,
    }
    assert f.unresolved is False
    assert "unresolved" not in f.to_dto()


# adapted: OsvVulnerabilityScannerTests.excludesWithdrawnAdvisoriesFromTheReportWithoutDegradingStatus
def test_recorded_withdrawn_advisory_is_dropped():
    doc = json.loads((OSV / "PYSEC-2017-9999.json").read_text(encoding="utf-8"))
    assert interpret(doc, Package("jinja2", "3.1.2", None), "PYSEC-2017-9999") is None


# adapted: OsvVulnerabilityScannerTests.recordsPerDependencyCompletionRatherThanTreatingMissingDetailsAsClean
# (the per-outcome interpretation; the assessment/evidence bookkeeping is Task 12's)
@pytest.mark.parametrize(
    ("doc", "expected"),
    [
        (advisory(withdrawn="2024-01-01T00:00:00Z"), None),
        (advisory(withdrawn="not-a-timestamp"), None),
        ({"id": "OTHER"}, None),
        ("not an object", None),
        (advisory(affected={}), ("UNKNOWN", True)),
        (
            advisory(database_specific={"severity": "UNSUPPORTED"}, affected=[widget(versions=["1.0.0"])]),
            ("UNKNOWN", False),
        ),
        (advisory(database_specific={"severity": "HIGH"}, affected=[widget(versions=["1.0.0"])]), ("HIGH", False)),
    ],
)
def test_per_outcome_interpretation(doc: Any, expected: tuple[str, bool] | None):
    f = interpret(doc, pkg(), ID)
    assert (None if f is None else (f.severity, f.unresolved)) == expected


# ported: OsvVulnerabilityScannerTests.deduplicatesRepeatedIdsAndRejectsMismatchedAdvisoryDetails (mismatch half)
def test_mismatched_advisory_id_is_rejected():
    doc = {"id": "V-OTHER", "database_specific": {"severity": "CRITICAL"}}
    assert interpret(doc, pkg(), "V-MISMATCH") is None


# ported: OsvVulnerabilityScannerTests.versionScopedSeverityAndFixIgnoreUnrelatedSamePackageBranches
def test_version_scoped_severity_and_fix():
    doc = advisory(
        affected=[
            widget(severity=[CRITICAL], ranges=[rng(ev("introduced", "2"), ev("fixed", "3"))]),
            widget(severity=[MEDIUM], ranges=[rng(ev("fixed", "1.1"), ev("introduced", "0"))]),
        ]
    )
    f = interpret(doc, pkg(), ID)
    assert f is not None
    assert (f.score, f.severity, f.fixed_versions, f.fix_available) == (5.4, "MEDIUM", ["1.1"], True)


# ported: OsvVulnerabilityScannerTests.explicitVersionsAndRangesAreAUnion
@pytest.mark.parametrize("matches_explicit", [False, True])
def test_explicit_versions_and_ranges_union(matches_explicit: bool):
    version, introduced, fixed = ("1.0.0", "2", "3") if matches_explicit else ("2.0", "0", "1.1")
    doc = advisory(
        affected=[
            widget(
                versions=[version], severity=[MEDIUM], ranges=[rng(ev("introduced", introduced), ev("fixed", fixed))]
            )
        ]
    )
    f = interpret(doc, pkg(), ID)
    assert f is not None
    assert f.score == 5.4
    assert (f.fixed_versions, f.fix_available) == (([], False) if matches_explicit else (["1.1"], True))


# ported: OsvVulnerabilityScannerTests.unsupportedRangesRetainQueryFindingWithoutBorrowingPackageClaims
@pytest.mark.parametrize("global_severity", [False, True])
def test_unsupported_ranges_retain_finding(global_severity: bool):
    doc = advisory(
        affected=[
            widget(ranges=[rng(ev("introduced", "0"), ev("fixed", "abcdef123456"), kind="GIT")]),
            widget(versions=["9.0"], severity=[CRITICAL]),
        ]
    )
    if global_severity:
        doc["severity"] = [MEDIUM]
    f = interpret(doc, pkg(), ID)
    assert f is not None
    assert f.id == ID
    assert (f.severity, f.score) == (("MEDIUM", 5.4) if global_severity else ("UNKNOWN", None))
    assert (f.fixed_versions, f.fix_available, f.unresolved) == ([], False, True)


# ported: OsvVulnerabilityScannerTests.unsupportedRangeAlongsideMavenRangeCannotVerifyAFix
@pytest.mark.parametrize("kind", ["GIT", "SEMVER"])
def test_unsupported_range_alongside_ecosystem_range_cannot_verify_fix(kind: str):
    doc = advisory(
        database_specific={"severity": "HIGH"},
        affected=[
            widget(
                ranges=[
                    rng(ev("introduced", "0"), ev("fixed", "1.1")),
                    rng(ev("introduced", "0"), ev("fixed", "2.0"), kind=kind),
                ]
            )
        ],
    )
    f = interpret(doc, pkg(), ID)
    assert f is not None
    assert (f.severity, f.fixed_versions, f.fix_available, f.unresolved) == ("HIGH", [], False, True)


# ported: OsvVulnerabilityScannerTests.parsesARealCvssV3VectorIntoANumericScoreAndDerivedSeverity
def test_real_cvss_vector_scores():
    f = interpret(advisory(affected=[widget(versions=["1.0.0"])], severity=[CRITICAL]), pkg(), ID)
    assert f is not None
    assert (f.score, f.severity) == (9.8, "CRITICAL")


# ported: OsvVulnerabilityScannerTests.fallsBackToDatabaseSpecificSeverityWhenNoCvssScoreCanBeParsed
def test_cvss_v4_only_falls_back_to_database_label():
    doc = advisory(
        affected=[widget(versions=["1.0.0"])],
        database_specific={"severity": "MODERATE"},
        severity=[{"type": "CVSS_V4", "score": "CVSS:4.0/AV:N/AC:L/AT:N/PR:N/UI:N/VC:N/VI:N/VA:N/SC:N/SI:L/SA:N"}],
    )
    f = interpret(doc, pkg(), ID)
    assert f is not None
    assert (f.score, f.severity) == (None, "MEDIUM")


# ported: OsvVulnerabilityScannerTests.usesOnlyTypedCvssV3EntriesAndChoosesTheHighestScore
def test_only_typed_cvss_v3_and_highest():
    doc = advisory(
        affected=[widget(versions=["1.0.0"])],
        severity=[
            {"type": "Ubuntu", "score": "9.9"},
            {"type": "CVSS_V2", "score": "10.0"},
            MEDIUM,
            CRITICAL,
        ],
    )
    f = interpret(doc, pkg(), ID)
    assert f is not None
    assert (f.score, f.severity) == (9.8, "CRITICAL")


# ported: OsvVulnerabilityScannerTests.prefersPackageLevelSeverityOverTopLevelSeverity
def test_package_level_severity_wins():
    f = interpret(advisory(severity=[MEDIUM], affected=[widget(versions=["1.0.0"], severity=[CRITICAL])]), pkg(), ID)
    assert f is not None
    assert (f.severity, f.score) == ("CRITICAL", 9.8)


# ported: OsvVulnerabilityScannerTests.fallsBackToTopLevelSeverityWhenAffectedEntryHasNoPackageLevelSeverity
def test_top_level_severity_fallback():
    f = interpret(advisory(severity=[MEDIUM], affected=[widget(versions=["1.0.0"])]), pkg(), ID)
    assert f is not None
    assert (f.severity, f.score) == ("MEDIUM", 5.4)


# ported: OsvVulnerabilityScannerTests.lastAffectedIsNotMisrepresentedAsAFixedVersion
def test_last_affected_is_not_a_fixed_version():
    doc = advisory(
        database_specific={"severity": "HIGH"},
        affected=[widget(ranges=[rng(ev("introduced", "0"), ev("last_affected", "1.0.0"))])],
    )
    f = interpret(doc, pkg(), ID)
    assert f is not None
    assert (f.fixed_versions, f.fix_available) == ([], False)


# adapted: OsvVulnerabilityScannerTests.selectsOnlyTheFixClosingTheInstalledQualifierBranch
# Maven (introduced "1.0", fixed "1.0-sp1") + (introduced "0", fixed "1.0-rc1") -> PEP 440 "1.0.post1" / "1.0rc1".
def test_selects_only_the_fix_closing_the_installed_branch():
    doc = advisory(
        database_specific={"severity": "HIGH"},
        affected=[
            widget(
                ranges=[
                    rng(ev("introduced", "1.0"), ev("fixed", "1.0.post1")),
                    rng(ev("introduced", "0"), ev("fixed", "1.0rc1")),
                ]
            )
        ],
    )
    f = interpret(doc, pkg("0.9"), ID)
    assert f is not None
    assert (f.fixed_versions, f.fix_available) == (["1.0rc1"], True)


# ported: OsvVulnerabilityScannerTests.fixAvailableIsFalseWhenTheCurrentVersionIsAlreadyAtOrAboveEveryFixedVersion
def test_fix_unavailable_when_already_above():
    doc = advisory(
        database_specific={"severity": "HIGH"},
        affected=[widget(ranges=[rng(ev("introduced", "0"), ev("fixed", "1.0.0"))])],
    )
    f = interpret(doc, pkg("1.2.0"), ID)
    assert f is not None
    assert (f.fixed_versions, f.fix_available, f.unresolved) == ([], False, True)


# ported: OsvVulnerabilityScannerTests.prefersAnAdvisoryReferenceOverWebOrFixReferencesAsTheCanonicalFirstLink
def test_advisory_reference_first_then_fix_then_original_order():
    doc = advisory(
        database_specific={"severity": "HIGH"},
        references=[
            {"type": "WEB", "url": "https://example.com/web"},
            {"type": "FIX", "url": "https://example.com/fix"},
            {"type": "ADVISORY", "url": "https://example.com/advisory"},
            {"type": "REPORT", "url": "https://example.com/report"},
        ],
        affected=[widget(versions=["1.0.0"])],
    )
    f = interpret(doc, pkg(), ID)
    assert f is not None
    assert f.references == [
        "https://example.com/advisory",
        "https://example.com/fix",
        "https://example.com/web",
        "https://example.com/report",
    ]


# ported: OsvVulnerabilityScanner.stringArray / references (MAX_ALIASES and the 20-reference cap)
def test_aliases_and_references_are_unique_non_blank_and_capped():
    doc = advisory(
        aliases=["CVE-2024-0001", "CVE-2024-0001", " ", 7, *[f"ALIAS-{i}" for i in range(30)]],
        references=[
            {"url": "https://a"},
            {"url": "https://a"},
            {"type": "WEB"},
            *[{"url": f"https://r/{i}"} for i in range(30)],
        ],
        affected=[widget(versions=["1.0.0"])],
    )
    f = interpret(doc, pkg(), ID)
    assert f is not None
    assert f.aliases[:2] == ["CVE-2024-0001", "ALIAS-0"] and len(f.aliases) == 20
    assert f.references[:2] == ["https://a", "https://r/0"] and len(f.references) == 20
