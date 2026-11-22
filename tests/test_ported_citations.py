"""BootUI test citations stay resolvable against the pinned source inventory."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "bootui" / "2.5.0" / "bootui-tests.json"
CITATION = re.compile(r"#\s*ported:\s*([\w$]+)\.([\w$]+)")
MARKER = re.compile(r"#\s*ported:")
UNRESOLVED_CITATION_ITEMS = {
    ("AdvisorScanState", "java"),
    ("AdvisorViolationException", "parseInteger"),
    ("ArchitectureRulesTests", "applicationClassesShouldNotDependOnTestFrameworks"),
    ("ArchitectureRulesTests", "classesShouldNotAccessJdkInternalApis"),
    ("ArchitectureRulesTests", "classesShouldNotAccessStandardStreams"),
    ("ArchitectureRulesTests", "classesShouldNotDirectlyInstantiateThread"),
    ("ArchitectureRulesTests", "classesShouldNotForciblyTerminateTheJvm"),
    ("ArchitectureRulesTests", "classesShouldNotHavePublicMutableStaticFields"),
    ("ArchitectureRulesTests", "classesShouldNotThrowGenericExceptions"),
    ("ArchitectureRulesTests", "classesShouldNotUseLegacyDateAndTimeClasses"),
    ("ArchitectureRulesTests", "controllersShouldNotDependOnRepositories"),
    ("ArchitectureRulesTests", "exceptionsShouldBeNamedEndingWithException"),
    ("ArchitectureRulesTests", "internalPackagesShouldNotBeAccessedFromOtherModules"),
    ("ArchitectureRulesTests", "loggersShouldBePrivateFinalOrContainerManaged"),
    ("ArchitectureRulesTests", "repositoriesShouldNotDependOnControllers"),
    ("ArchitectureRulesTests", "repositoriesShouldNotDependOnServices"),
    ("ArchitectureRulesTests", "servicesAndRepositoriesShouldNotDependOnWebRequestTypes"),
    ("ArchitectureRulesTests", "servicesShouldNotDependOnControllers"),
    ("ArchitectureScannerTests", "scanRefreshesCachedReportAndAppliesDismissals"),
    ("BootUiAutoConfiguration", "bootUiSqlTraceRecorder"),
    ("BootUiMcpServiceTests", "unknownTool"),
    ("CliService", "status"),
    ("CvssV3BaseScore", "roundUp"),
    ("DatabaseConnectionPoolsServiceTests", "reportsPoolLibraryPresentAndImplementation"),
    ("DependencyReports", "canonicalCveId"),
    ("DependencyReports", "epssCveChunks"),
    ("DependencyReports", "normalizeSeverity"),
    ("EvidenceRing", "add"),
    ("EvidenceRing", "lost"),
    ("ExceptionsControllerTests", "reportCarriesNullCaughtInCodeWithoutSensor"),
    ("ExceptionsService", "parseStatus"),
    ("FlywayService", "migrate"),
    ("HttpExchangesService", "matches"),
    ("HttpExchangesService", "statusFamily"),
    ("HttpExchangesServiceTests", "recordsRouteAndRetention"),
    ("HttpRouteSummaryServiceTests", "limitsTopRoutesPerCriterionAndKeepsPinnedRoute"),
    ("HttpRouteSummaryServiceTests", "summarizeGroupsByMethodAndRouteAndComputesPercentiles"),
    ("InsightsSnapshot", "of"),
    ("LiveActivityAssembler", "toSqlEntry"),
    ("LiveActivityControllerTests", "warnsWhenJournalFiltersUsedAgainstBuffers"),
    ("LiveActivityServiceTests", "requestProfileIncludes220Collections"),
    ("LogTailStoreTests", "setsMessageOmittedWhenMetadataOnly"),
    ("McpAgentViews", "INVENTORY_DEFAULT_LIMIT"),
    ("McpAgentViewsTests", "sqlTracesAndLogTailFilterAndPage"),
    ("McpAgentViewsTests", "vulnerabilitiesCompactsDependenciesAndAdvisories"),
    ("McpAgentViewsTests", "vulnerabilitiesQueryMatchesAnyDependency"),
    ("McpArguments", "normalize"),
    ("McpDispatcher", "callTool"),
    ("McpProtocolTests", "acceptsProgressTokenMeta"),
    ("McpScanSummaries", "postgresql"),
    ("McpToolCatalog", "Entry"),
    ("McpToolDescriptions", "COMMON"),
    ("MySqlComparisonTests", "changesBetweenReads"),
    ("MySqlDataSourceDetectionTests", "nonMySqlSkipped"),
    ("MySqlMariaDbTests", "mariaDbCapabilitiesDiffer"),
    ("MySqlRowLimitsTests", "rowLimitsTruncateAndFlag"),
    ("MySqlValuesTests", "performanceSchemaOffIsADiagnostic"),
    ("MySqlValuesTests", "sessionCurrentStatementMasked"),
    ("MySqlValuesTests", "statementTextMasked"),
    ("OsvVulnerabilityScanner", "fetchEpssChunk"),
    ("OsvVulnerabilityScanner", "fetchEpssPage"),
    ("OsvVulnerabilityScanner", "fetchVulnerability"),
    ("OsvVulnerabilityScanner", "queryBatch"),
    ("OsvVulnerabilityScanner", "queryBatchChunk"),
    ("OsvVulnerabilityScanner", "queryBatchRequest"),
    ("OsvVulnerabilityScanner", "stringArray"),
    ("PagedList", "java"),
    ("PostgresHelpersTests", "queryTextCollapsesWhitespaceAndTruncatesTo400Chars"),
    ("PostgresHelpersTests", "queryTextMasksSingleQuotedEscapeAndDollarQuotedLiterals"),
    ("PostgresHelpersTests", "queryTextMasksUnterminatedStringLiterals"),
    ("PostgresHelpersTests", "queryTextPreservesParameterPlaceholdersAndIdentifiers"),
    ("PostgresHelpersTests", "queryTextRespectsExposureLevel"),
    ("PostgresInsightServiceTests", "noDataSourceIsDisabled"),
    ("PostgresInsightServiceTests", "readsEverySectionFromAHealthyServer"),
    ("PostgresRowLimitsTests", "defaultLimitsMatchPropertiesContract"),
    ("PostgresRowLimitsTests", "rejectsIntegerMaxValueWhichCannotReadOneRowPastTheLimit"),
    ("PostgresRowLimitsTests", "rejectsNonPositiveLimits"),
    ("PostgresTestDataSources", "QueryKind"),
    ("RestApiScanner", "applyDismissals"),
    ("RestApiScanner", "evaluate"),
    ("RestApiScanner", "java"),
    ("RestApiScannerTests", "noControllersIsConfirmedEmpty"),
    ("RuntimeInsightsService", "java"),
    ("RuntimeInsightsService", "sqlCapture"),
    ("RuntimeInsightsService", "visibleEntries"),
    ("SecurityRulesTests", "hardcodedSecretProperty"),
    ("SecurityRulesTests", "noOpPasswordEncoder"),
    ("SecurityRulesTests", "securityDebugEnabled"),
    ("SecurityRulesTests", "securityDebugLoggingProduction"),
    ("SecurityRulesTests", "weakBcryptStrength"),
    ("SecurityRulesTests", "weakPasswordEncoder"),
    ("SeverityOrder", "occurrenceCounts"),
    ("SqlStatementNormalizerTests", "leavesAnUnterminatedDollarRunAloneRatherThanSwallowingTheStatement"),
    ("SqlTraceControllerSupport", "recording"),
    ("SqlTraceRecorder", "isSlow"),
    ("SqlTraceRecorder", "topStatements"),
    ("SqlTraceRecorder", "truncate"),
    ("SqlTraceReport", "unavailable"),
    ("SqlTraceStoreTests", "recordsDurationMicrosAndRetention"),
    ("SqlTracingProxies", "categoryOf"),
    ("StaticSecurityAnalysisDetectorTests", "ignoresAnalyzerExamplesInsideGradleStringsAndCatalogComments"),
    ("TracesControllerTests", "clearRemovesTelemetry"),
    ("TracesControllerTests", "detailReturnsTrace"),
    ("TracesControllerTests", "listDelegatesToService"),
    ("TracesControllerTests", "unknownTraceIsNotFound"),
    ("VulnerabilityReportServiceTests", "includesRuntimeReachAndAdvisorySymbolFields"),
    ("test_mysql_live_tests", "py"),
}
UNRESOLVED_CITATIONS = frozenset(UNRESOLVED_CITATION_ITEMS)
UNRESOLVED_LABELS = frozenset(
    {
        "...UnexpectedArguments",
        "ActivityEntryDto, ActivityKpiDto, LiveActivityReport, RequestProfileDto",
        "AdvisorRuleViolationsDto, AdvisorViolationDetailsDto (contract §12)",
        "AgentPluginPayloadTests (manifest shape)",
        "BoundedBodyReader 1 MiB EPSS cap",
        "CliOutcomesTests (one row per contract §11 outcome)",
        "CliService action gating (read-only refuses vulnerabilities scan)",
        "DatabaseAdvisorDriverSettingsRulesTests (a diagnostic setting that is on is one finding)",
        "DatabaseAdvisorDriverSettingsRulesTests (an absent timeout is reported, keyed by setting, not value)",
        "DatabaseAdvisorHibernateRulesTests (an explicit table name absent from complete relation metadata)",
        "DatabaseAdvisorRuntimeRulesTests (distinct texts of one shape with predicate literals are one finding)",
        "DatabaseFindingIdentityTests (identities name the physical object, never a message or value)",
        "ExceptionsReport, ExceptionGroupDto, ExceptionDetailDto, ExceptionFrameDto, ExceptionOccurrenceDto",
        "FlywayReport, FlywayDatabaseDto, FlywayMigrationDto (contract §8)",
        "HealthNodeDto (contract §7 / spec §7.8)",
        "HikariPoolsReport, HikariPoolDto, HikariPoolSnapshotDto",
        "HttpExchangeDto, HttpHeaderDto, HttpExchangesReport, PageMetadata",
        "HttpProbeResponse",
        "LOSS_HORIZON_SLACK_MILLIS = 16, inclusive",
        "LogLineDto",
        "McpRuntimeStats callCount surfaced by McpServerController",
        "McpServerController status (McpServerStatus fields, MCP tools only)",
        "McpServerState (AUTO is off so the server is never silently exposed)",
        "McpToolCatalog ENTRIES (the 24 0.2.0 rows plus the 2.2.0 capture tools, panel and action names)",
        "MySqlValuesTests (autocommit engine refused)",
        "MySqlValuesTests (verified read-only path)",
        "PagedList clamp (MAX_LIMIT=1000)",
        "PostgresqlSerializationTest (PostgresInsightReport / PostgresDatabaseDto record components)",
        "RequestCorrelationFilterTests (the HttpPayload fields: method, path, routeTemplate, operation, status)",
        "RestApiReport and RestApiScanStatusDto components (+ RESULT_KEYS for RestApiRuleResultDto)",
        "RestApiRuleResultDto (12 components; 2.2.0 adds sampleLocations)",
        "RestApiRuleResultDto (contract §12)",
        "RestApiRules severities (BootUI calibration), unchanged for sharpit",
        "RestApiRulesTests (2.2.0): RESP-011 is the one with a FastAPI analog; the other three read Spring",
        "SecurityDocumentationTests (the checks table lists exactly the registry's rules)",
        "Spring Boot SimpleStatusAggregator default order DOWN, OUT_OF_SERVICE, UP, UNKNOWN; empty -> UNKNOWN",
        "SpringRules SPRING-CONFIG-004",
        "SpringRules SPRING-WEB-004",
        "SqlTraceEntryDto, SqlTraceGroupDto record components",
        "SqlTraceReport, SqlTraceEntryDto, SqlTraceGroupDto, SqlTraceStatsDto record components",
        "StaticSecurityAnalysisDetectorTests.",
        "ThreadDumpReport, ThreadInfoDto, ThreadStateCountDto, PageMetadata",
        "`` cite says otherwise.",
        "`` cites BootUI ``HealthServiceTests`` (the guidance and DISABLED root) and Spring Boot's",
        "aRuleWriteKeepsTheFindingsSectionAndAFindingWriteKeepsTheRules",
        "acknowledgedGroupsDoNotAutoTransitionOnNewOccurrences",
        "boundsRetainedOccurrencesPerGroup",
        "bufferCapsAndReversesNewestFirst (cap)",
        "bufferCapsAndReversesNewestFirst (order)",
        "capturesCauseChainWithCommonFrameCount",
        "check-mysql-live-tests.py counters",
        "clearsState, notifiesSubscribersOnRecordAndClear..., setStatusNotifiesSubscribers",
        "completionAndTimeoutReleaseTheirSubscriptions",
        "deduplicatesTheSameThrowableInstance",
        "dropsQueryAndFragmentUnderMetadataOnlyExposure",
        "errorHandlingRulesReflectCentralizedHandling",
        "evictsOldestPastByteCapButKeepsAtLeastOne (message + thread bytes, UTF-8)",
        "evictsOldestPastLineCap",
        "evictsTheLeastRecentlySeenGroupWhenFull (ordered by ns internally: no sleep needed)",
        "groupsRepeatedFailuresWithIdenticalStacks",
        "isolatesSubscriberFailuresFromCapture",
        "manualSetStatusNeverChangesRegressionCount",
        'masksSensitiveHeadersAndDerivesStatusFamily (Authorization -> masked, "******")',
        "masksSensitiveHeadersAndDerivesStatusFamily (token=******), masksPercentEncodedSensitiveQueryNames,",
        "newGroupsDefaultToOpenStatusWithNoRegressions",
        "queueOverflowDisconnectsSlowSubscriberWithoutBlockingPublisher (a client that never reads)",
        "reentrantAppendFromSubscriberIsDroppedNotRecursive (a hook that logs while the handler runs)",
        "rejectsNonPositiveLimit",
        "resolvedGroupsAutoReopenAndIncrementRegressionCountOnANewOccurrence",
        "routingRulesFlagBadController (no method constraint -> FastAPI: GET plus a mutating method)",
        "rows cited individually above (AbstractMcpConformanceTest, BootUiMcpServiceTests)",
        "separatesDistinctExceptionTypes",
        "setStatusUpdatesAKnownGroupAndReturnsTheUpdatedSummary, setStatusReturnsNullForAnUnknownFingerprint",
        "sql-trace/insights.captured.json, BootUI's ``id`` is the lower-cased statement",
        "testMcpRejectsBatchRequests",
        "testMcpRejectsOversizedRequestBeforeParsing (cap 64 bytes here; not even valid JSON)",
        "testMcpRejectsUnsupportedProtocolVersionHeader",
        "testMcpRequiresJsonContentType (BootUI: framework 415)",
        "testMcpValidatesJsonrpc",
        "the candidate remembers whether a literal there sits in a predicate",
        "toolCallRejectsNonObject...",
        "versioningRulesFlagWildcardAndMissingVersion",
    }
)


def _unresolved(citations: list[tuple[str, str]], inventory: dict[str, list[str]]) -> list[str]:
    classes: dict[str, list[tuple[str, set[str]]]] = {}
    for name, items in inventory.items():
        classes.setdefault(name.rsplit(".", 1)[-1], []).append((name, set(items)))
    unresolved = []
    for class_name, method in citations:
        matches = classes.get(class_name, [])
        if len(matches) != 1:
            detail = "ambiguous" if matches else "unresolved"
            unresolved.append(f"{class_name}.{method} ({detail} class name)")
        elif method not in matches[0][1]:
            unresolved.append(f"{class_name}.{method}")
    return unresolved


def _allowlist_errors(unresolved: set[str], allowed: tuple[tuple[str, str], ...]) -> list[str]:
    entries = [f"{class_name}.{method}" for class_name, method in allowed]
    unresolved = {item.split(" (", maxsplit=1)[0] for item in unresolved}
    errors = [f"new unresolved citation: {item}" for item in sorted(unresolved - set(entries))]
    errors.extend(f"stale unresolved citation: {item}" for item in sorted(set(entries) - unresolved))
    errors.extend(
        f"duplicate allowlist citation: {item}" for item, count in sorted(Counter(entries).items()) if count > 1
    )
    return errors


def test_ported_citations_resolve_in_bootui_test_inventory() -> None:
    inventory = json.loads(FIXTURE.read_text("utf-8"))["testClasses"]
    citations: list[tuple[str, str]] = []
    labels: set[str] = set()
    for path in (ROOT / "tests").rglob("*.py"):
        for line in path.read_text("utf-8").splitlines():
            marker = MARKER.search(line)
            if marker is None:
                continue
            if '"""' in line[: marker.start()] or "'''" in line[: marker.start()]:
                continue
            matches = list(CITATION.finditer(line))
            if matches:
                citations.extend(match.groups() for match in matches)
            else:
                labels.add(line[marker.end() :].strip())
    unresolved = set(_unresolved(citations, inventory))
    assert not _allowlist_errors(unresolved, UNRESOLVED_CITATION_ITEMS)
    assert labels == UNRESOLVED_LABELS
    assert len(UNRESOLVED_CITATION_ITEMS) == len(UNRESOLVED_CITATIONS)


def test_new_unresolved_citation_is_rejected_by_allowlist() -> None:
    assert _allowlist_errors({"PlantedTests.missingMethod"}, (("ExistingTests", "knownGap"),)) == [
        "new unresolved citation: PlantedTests.missingMethod",
        "stale unresolved citation: ExistingTests.knownGap",
    ]


def test_stale_unresolved_citation_is_rejected_by_allowlist() -> None:
    assert _allowlist_errors(set(), (("NowResolvedTests", "wasMissing"),)) == [
        "stale unresolved citation: NowResolvedTests.wasMissing"
    ]


def test_duplicate_allowlist_entry_is_reported() -> None:
    entries = (("RepeatedTests", "gap"), ("RepeatedTests", "gap"))
    assert _allowlist_errors({"RepeatedTests.gap"}, entries) == ["duplicate allowlist citation: RepeatedTests.gap"]


def test_duplicate_simple_class_name_is_ambiguous() -> None:
    assert _unresolved(
        [("SqlTraceSerializationTests", "onlyInQuarkus")],
        {
            "io.bootui.autoconfigure.sqltrace.SqlTraceSerializationTests": ["serialize"],
            "io.bootui.quarkus.sqltrace.SqlTraceSerializationTests": ["onlyInQuarkus"],
        },
    ) == ["SqlTraceSerializationTests.onlyInQuarkus (ambiguous class name)"]


def test_unresolved_citation_names_the_missing_method() -> None:
    assert _unresolved([("PlantedTests", "missingMethod")], {"example.PlantedTests": ["presentMethod"]}) == [
        "PlantedTests.missingMethod"
    ]
