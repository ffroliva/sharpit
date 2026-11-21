"""BootUI test citations stay resolvable against the pinned source inventory."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "bootui" / "2.5.0" / "bootui-tests.json"
CITATION = re.compile(r"#\s*ported:\s*([\w$]+)\.([\w$]+)")
MARKER = re.compile(r"#\s*ported:")
UNRESOLVED_CITATIONS = frozenset(
    {
        ("AdvisorScanState", "java"),
        ("AdvisorViolationException", "parseInteger"),
        ("ArchitectureRulesTests", "applicationClassesShouldNotDependOnTestFrameworks"),
        ("ArchitectureRulesTests", "assertionsShouldHaveADetailMessage"),
        ("ArchitectureRulesTests", "assertionsShouldHaveDetailMessageFlagsMessagelessAssertion"),
        ("ArchitectureRulesTests", "assertionsShouldHaveDetailMessagePassesForMessageBearingAssertion"),
        ("ArchitectureRulesTests", "classesShouldNotAccessJdkInternalApis"),
        ("ArchitectureRulesTests", "classesShouldNotAccessStandardStreams"),
        ("ArchitectureRulesTests", "classesShouldNotDirectlyInstantiateThread"),
        ("ArchitectureRulesTests", "classesShouldNotForciblyTerminateTheJvm"),
        ("ArchitectureRulesTests", "classesShouldNotHavePublicMutableStaticFields"),
        ("ArchitectureRulesTests", "classesShouldNotThrowGenericExceptions"),
        ("ArchitectureRulesTests", "classesShouldNotUseJodaTime"),
        ("ArchitectureRulesTests", "classesShouldNotUseLegacyDateAndTimeClasses"),
        ("ArchitectureRulesTests", "controllersShouldNotDependOnRepositories"),
        ("ArchitectureRulesTests", "exceptionsShouldBeNamedEndingWithException"),
        ("ArchitectureRulesTests", "internalPackagesShouldNotBeAccessedFromOtherModules"),
        ("ArchitectureRulesTests", "loggersShouldBePrivateFinalOrContainerManaged"),
        ("ArchitectureRulesTests", "packagesShouldBeFreeOfCycles"),
        ("ArchitectureRulesTests", "repositoriesShouldNotDependOnControllers"),
        ("ArchitectureRulesTests", "repositoriesShouldNotDependOnServices"),
        ("ArchitectureRulesTests", "servicesAndRepositoriesShouldNotDependOnWebRequestTypes"),
        ("ArchitectureRulesTests", "servicesShouldNotDependOnControllers"),
        ("ArchitectureScannerTests", "scanRefreshesCachedReportAndAppliesDismissals"),
        ("BootUiAutoConfiguration", "bootUiSqlTraceRecorder"),
        ("BootUiMcpServiceTests", "unknownTool"),
        ("CliService", "status"),
        ("CvssV3BaseScore", "roundUp"),
        ("DatabaseAdvisorPoolRulesTests", "aPoolLargerThanTheUsableConnectionsFiresTheCapacityRuleAndNotTheShareRule"),
        ("DatabaseAdvisorPoolRulesTests", "aPoolOverHalfTheUsableConnectionsFiresTheShareHeuristicAtLowSeverity"),
        ("DatabaseAdvisorPoolRulesTests", "thePoolShareBoundariesUseExactIntegerArithmetic"),
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
        (
            "RestApiRuleAccuracyTests",
            "documentationRecognizesTagContainersAndOperationTagsWithoutRequiringAnnotationsForGeneration",
        ),
        ("RestApiRulesTests", "documentationRulesAreSkippedWithoutSpringdocAndFireWithIt"),
        ("RestApiRulesTests", "name002DoesNotFlagUncountableNouns"),
        ("RestApiRulesTests", "phase2RulesFlagBadPhase2Controller"),
        ("RestApiRulesTests", "responseRulesFlagCreationAndScalarReads"),
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
)
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
        "name002DoesNotFlagUncountableNouns",
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
    methods: dict[str, set[str]] = {}
    for name, items in inventory.items():
        methods.setdefault(name.rsplit(".", 1)[-1], set()).update(items)
    return [
        f"{class_name}.{method}" for class_name, method in citations if method not in methods.get(class_name, set())
    ]


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
    unresolved = {tuple(item.split(".", maxsplit=1)) for item in _unresolved(citations, inventory)}
    assert unresolved == UNRESOLVED_CITATIONS
    assert labels == UNRESOLVED_LABELS


def test_unresolved_citation_names_the_missing_method() -> None:
    assert _unresolved([("PlantedTests", "missingMethod")], {"example.PlantedTests": ["presentMethod"]}) == [
        "PlantedTests.missingMethod"
    ]
