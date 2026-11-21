"""BootUI test citations stay resolvable against the pinned source inventory."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "bootui" / "2.5.0" / "bootui-tests.json"
CITATION = re.compile(r"#\s*ported:\s*([\w$]+)\.([\w$]+)")
UNRESOLVED_CITATIONS = frozenset(
    {
        ('AdvisorScanState', 'java'),
        ('AdvisorViolationException', 'parseInteger'),
        ('ArchitectureRulesTests', 'applicationClassesShouldNotDependOnTestFrameworks'),
        ('ArchitectureRulesTests', 'assertionsShouldHaveADetailMessage'),
        ('ArchitectureRulesTests', 'assertionsShouldHaveDetailMessageFlagsMessagelessAssertion'),
        ('ArchitectureRulesTests', 'assertionsShouldHaveDetailMessagePassesForMessageBearingAssertion'),
        ('ArchitectureRulesTests', 'classesShouldNotAccessJdkInternalApis'),
        ('ArchitectureRulesTests', 'classesShouldNotAccessStandardStreams'),
        ('ArchitectureRulesTests', 'classesShouldNotDirectlyInstantiateThread'),
        ('ArchitectureRulesTests', 'classesShouldNotForciblyTerminateTheJvm'),
        ('ArchitectureRulesTests', 'classesShouldNotHavePublicMutableStaticFields'),
        ('ArchitectureRulesTests', 'classesShouldNotThrowGenericExceptions'),
        ('ArchitectureRulesTests', 'classesShouldNotUseJodaTime'),
        ('ArchitectureRulesTests', 'classesShouldNotUseLegacyDateAndTimeClasses'),
        ('ArchitectureRulesTests', 'controllersShouldNotDependOnRepositories'),
        ('ArchitectureRulesTests', 'exceptionsShouldBeNamedEndingWithException'),
        ('ArchitectureRulesTests', 'internalPackagesShouldNotBeAccessedFromOtherModules'),
        ('ArchitectureRulesTests', 'loggersShouldBePrivateFinalOrContainerManaged'),
        ('ArchitectureRulesTests', 'packagesShouldBeFreeOfCycles'),
        ('ArchitectureRulesTests', 'repositoriesShouldNotDependOnControllers'),
        ('ArchitectureRulesTests', 'repositoriesShouldNotDependOnServices'),
        ('ArchitectureRulesTests', 'servicesAndRepositoriesShouldNotDependOnWebRequestTypes'),
        ('ArchitectureRulesTests', 'servicesShouldNotDependOnControllers'),
        ('ArchitectureScannerTests', 'scanRefreshesCachedReportAndAppliesDismissals'),
        ('BootUiAutoConfiguration', 'bootUiSqlTraceRecorder'),
        ('BootUiMcpServiceTests', 'unknownTool'),
        ('CliService', 'status'),
        ('CvssV3BaseScore', 'roundUp'),
        ('DatabaseAdvisorPoolRulesTests', 'aPoolLargerThanTheUsableConnectionsFiresTheCapacityRuleAndNotTheShareRule'),
        ('DatabaseAdvisorPoolRulesTests', 'aPoolOverHalfTheUsableConnectionsFiresTheShareHeuristicAtLowSeverity'),
        ('DatabaseAdvisorPoolRulesTests', 'thePoolShareBoundariesUseExactIntegerArithmetic'),
        ('DatabaseConnectionPoolsServiceTests', 'reportsPoolLibraryPresentAndImplementation'),
        ('DependencyReports', 'canonicalCveId'),
        ('DependencyReports', 'epssCveChunks'),
        ('DependencyReports', 'normalizeSeverity'),
        ('EvidenceRing', 'add'),
        ('EvidenceRing', 'lost'),
        ('ExceptionsControllerTests', 'reportCarriesNullCaughtInCodeWithoutSensor'),
        ('ExceptionsService', 'parseStatus'),
        ('FlywayService', 'migrate'),
        ('HttpExchangesService', 'matches'),
        ('HttpExchangesService', 'statusFamily'),
        ('HttpExchangesServiceTests', 'recordsRouteAndRetention'),
        ('HttpRouteSummaryServiceTests', 'limitsTopRoutesPerCriterionAndKeepsPinnedRoute'),
        ('HttpRouteSummaryServiceTests', 'summarizeGroupsByMethodAndRouteAndComputesPercentiles'),
        ('InsightsSnapshot', 'of'),
        ('LiveActivityAssembler', 'toSqlEntry'),
        ('LiveActivityControllerTests', 'warnsWhenJournalFiltersUsedAgainstBuffers'),
        ('LiveActivityServiceTests', 'requestProfileIncludes220Collections'),
        ('LogTailStoreTests', 'setsMessageOmittedWhenMetadataOnly'),
        ('McpAgentViews', 'INVENTORY_DEFAULT_LIMIT'),
        ('McpAgentViewsTests', 'sqlTracesAndLogTailFilterAndPage'),
        ('McpAgentViewsTests', 'vulnerabilitiesCompactsDependenciesAndAdvisories'),
        ('McpAgentViewsTests', 'vulnerabilitiesQueryMatchesAnyDependency'),
        ('McpArguments', 'normalize'),
        ('McpDispatcher', 'callTool'),
        ('McpProtocolTests', 'acceptsProgressTokenMeta'),
        ('McpScanSummaries', 'postgresql'),
        ('McpToolCatalog', 'Entry'),
        ('McpToolDescriptions', 'COMMON'),
        ('MySqlComparisonTests', 'changesBetweenReads'),
        ('MySqlDataSourceDetectionTests', 'nonMySqlSkipped'),
        ('MySqlMariaDbTests', 'mariaDbCapabilitiesDiffer'),
        ('MySqlRowLimitsTests', 'rowLimitsTruncateAndFlag'),
        ('MySqlValuesTests', 'performanceSchemaOffIsADiagnostic'),
        ('MySqlValuesTests', 'sessionCurrentStatementMasked'),
        ('MySqlValuesTests', 'statementTextMasked'),
        ('OsvVulnerabilityScanner', 'fetchEpssChunk'),
        ('OsvVulnerabilityScanner', 'fetchEpssPage'),
        ('OsvVulnerabilityScanner', 'fetchVulnerability'),
        ('OsvVulnerabilityScanner', 'queryBatch'),
        ('OsvVulnerabilityScanner', 'queryBatchChunk'),
        ('OsvVulnerabilityScanner', 'queryBatchRequest'),
        ('OsvVulnerabilityScanner', 'stringArray'),
        ('PagedList', 'java'),
        ('PostgresHelpersTests', 'queryTextCollapsesWhitespaceAndTruncatesTo400Chars'),
        ('PostgresHelpersTests', 'queryTextMasksSingleQuotedEscapeAndDollarQuotedLiterals'),
        ('PostgresHelpersTests', 'queryTextMasksUnterminatedStringLiterals'),
        ('PostgresHelpersTests', 'queryTextPreservesParameterPlaceholdersAndIdentifiers'),
        ('PostgresHelpersTests', 'queryTextRespectsExposureLevel'),
        ('PostgresInsightServiceTests', 'noDataSourceIsDisabled'),
        ('PostgresInsightServiceTests', 'readsEverySectionFromAHealthyServer'),
        ('PostgresRowLimitsTests', 'defaultLimitsMatchPropertiesContract'),
        ('PostgresRowLimitsTests', 'rejectsIntegerMaxValueWhichCannotReadOneRowPastTheLimit'),
        ('PostgresRowLimitsTests', 'rejectsNonPositiveLimits'),
        ('PostgresTestDataSources', 'QueryKind'),
        ('RestApiRuleAccuracyTests', 'documentationRecognizesTagContainersAndOperationTagsWithoutRequiringAnnotationsForGeneration'),
        ('RestApiRulesTests', 'documentationRulesAreSkippedWithoutSpringdocAndFireWithIt'),
        ('RestApiRulesTests', 'name002DoesNotFlagUncountableNouns'),
        ('RestApiRulesTests', 'phase2RulesFlagBadPhase2Controller'),
        ('RestApiRulesTests', 'responseRulesFlagCreationAndScalarReads'),
        ('RestApiScanner', 'applyDismissals'),
        ('RestApiScanner', 'evaluate'),
        ('RestApiScanner', 'java'),
        ('RestApiScannerTests', 'noControllersIsConfirmedEmpty'),
        ('RuntimeInsightsService', 'java'),
        ('RuntimeInsightsService', 'sqlCapture'),
        ('RuntimeInsightsService', 'visibleEntries'),
        ('SecurityRulesTests', 'hardcodedSecretProperty'),
        ('SecurityRulesTests', 'noOpPasswordEncoder'),
        ('SecurityRulesTests', 'securityDebugEnabled'),
        ('SecurityRulesTests', 'securityDebugLoggingProduction'),
        ('SecurityRulesTests', 'weakBcryptStrength'),
        ('SecurityRulesTests', 'weakPasswordEncoder'),
        ('SeverityOrder', 'occurrenceCounts'),
        ('SqlStatementNormalizerTests', 'leavesAnUnterminatedDollarRunAloneRatherThanSwallowingTheStatement'),
        ('SqlTraceControllerSupport', 'recording'),
        ('SqlTraceRecorder', 'isSlow'),
        ('SqlTraceRecorder', 'topStatements'),
        ('SqlTraceRecorder', 'truncate'),
        ('SqlTraceReport', 'unavailable'),
        ('SqlTraceStoreTests', 'recordsDurationMicrosAndRetention'),
        ('SqlTracingProxies', 'categoryOf'),
        ('StaticSecurityAnalysisDetectorTests', 'ignoresAnalyzerExamplesInsideGradleStringsAndCatalogComments'),
        ('TracesControllerTests', 'clearRemovesTelemetry'),
        ('TracesControllerTests', 'detailReturnsTrace'),
        ('TracesControllerTests', 'listDelegatesToService'),
        ('TracesControllerTests', 'unknownTraceIsNotFound'),
        ('VulnerabilityReportServiceTests', 'includesRuntimeReachAndAdvisorySymbolFields'),
        ('test_mysql_live_tests', 'py'),
    }
)


def _unresolved(citations: list[tuple[str, str]], inventory: dict[str, list[str]]) -> list[str]:
    methods: dict[str, set[str]] = {}
    for name, items in inventory.items():
        methods.setdefault(name.rsplit(".", 1)[-1], set()).update(items)
    return [f"{class_name}.{method}" for class_name, method in citations if method not in methods.get(class_name, set())]


def test_ported_citations_resolve_in_bootui_test_inventory() -> None:
    inventory = json.loads(FIXTURE.read_text("utf-8"))["testClasses"]
    citations = [
        match.groups()
        for path in (ROOT / "tests").rglob("*.py")
        for match in CITATION.finditer(path.read_text("utf-8"))
    ]
    unresolved = {tuple(item.split(".", maxsplit=1)) for item in _unresolved(citations, inventory)}
    assert unresolved == UNRESOLVED_CITATIONS


def test_unresolved_citation_names_the_missing_method() -> None:
    assert _unresolved([("PlantedTests", "missingMethod")], {"example.PlantedTests": ["presentMethod"]}) == [
        "PlantedTests.missingMethod"
    ]
