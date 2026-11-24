# Issue #300: BootUI 2.5.0 API route parity

**Goal:** reconcile the route inventory with BootUI 2.5.0, add the approved missing reads and request baselines, and verify or record each partial response contract.

**Architecture:** contract records identify the HTTP method, canonical template, and evidence scenario independently. Endpoint logic uses the shared console handlers from #260, with framework-independent projections in the engine and host-specific observation at the adapter boundary. The existing HTTP API remains the delivery surface.

**Method:** one independently reviewable change per task or named panel slice. Each task starts with the specified failing assertion, checks it with `scripts/dev/red_check.py`, implements the smallest observable change, reruns the affected checks, and records the evidence with the change. Deferred product choices require a recorded maintainer decision before their implementation assertions become final.

**Source pins:** sharpit `90c2ec30` and BootUI `v2.5.0` (`c4458db8d`). The 0.9.0 [release plan](2026-11-22-sharpit-0.9.0/PLAN.md) defines R0–R3 and F2. The [route inventory](../../../tests/parity/routes_status.json) reports 23 missing and 28 partial fixture rows. Of the 23, eight name post-action evidence, and one names the existing trace detail as a literal path. Fourteen canonical GET capabilities are absent, including the raw Actuator mapping and the corrected impact-symbols path.

**Branches:** Phase 1 is a standalone contract change. Phase 2 is the first endpoint change. Phases 3–8 use separate pull requests per task or panel slice, with dependencies below. Each endpoint change waits for its #260 F2 handler batch or lands in that batch by agreement, with one owner of the affected route module at a time.

BootUI source locations below are relative to the tag. For `Controller.java`, the package root is `bootui-spring-boot-starter/src/main/java/io/github/jdubois/bootui/autoconfigure/`. Engine classes and DTOs use `bootui-engine/src/main/java/io/github/jdubois/bootui/`. Conformance citations refer to `bootui-conformance/src/main/java/io/github/jdubois/bootui/conformance/AbstractBootUiApiConformanceTest.java`. The pinned file can be read with `git -C <bootui-clone> show v2.5.0:<path>`. Sharpit paths beginning with `engine/` or `fastapi/` are under `src/sharpit/`. Source lines are anchors for the pinned baseline.

## Global constraints

- Each endpoint uses the active mount and the existing guard in order: security headers, trusted source, Host, cross-site, token, panel. Inactive mounts return 404. Sharpit rejects cross-site reads and forwarding headers under its existing policy. The enabled panel check applies to reads and actions, with Overview retaining its unscoped route.
- Reads remain available on read-only panels. Every new GET uses the `no_side_effects` fixture, plus assertions on capture and retention state where relevant. GET may project local snapshots. It performs no network connection, write, live scan, acquisition, logger level change, or environment mutation.
- Actions require an enabled, writable panel and the existing guard. A port preserves BootUI's single-flight behavior where present, including 409 busy and lock release after failures. The route and refusal sweeps in `tests/test_safety_matrix.py:343,385,704,757` cover each new entry. BootUI sources: `safety/PanelAccessFilter.java:42,64,70` and `BootUiProperties.java:404,409,722`. Port guard tests with `# ported: PanelAccessFilterTests.allowsReadOnlyPanelReadRequest` and `# ported: PanelAccessFilterTests.blocksReadOnlyPanelActionRequest`.
- DTOs emit every applicable key, including nulls, in camelCase at the root. Preserve epoch milliseconds and explicitly named duration units. Validate canonical status and reason strings with sharpit naming. Apply masking to output, errors and values before filtering. Suppress evidence from disabled source panels at read time.
- Keep runtime dependencies at `starlette` and `packaging`. Use the existing optional package boundaries. Any proposed weakening of activation, guard, masking, no-side-effects or action policy requires high-tier review before implementation. A new action without a BootUI counterpart also requires that review.
- Each adopted adaptation or omission gets one reasoned matrix row in `docs/reference/matrix-updates/0.10.0-routes-300.tsv` and corresponding generated [PARITY.md](../../reference/PARITY.md). Established deviations keep their decision record. Public route or error deviations also update §14 of the [design spec](../specs/2026-10-30-sharpit-mvp-design.md) where applicable. A pending decision leaves the canonical gap visible.

## Seams under test

| Severity | Risk | Named assertion and task |
|---|---|---|
| Critical | Hidden journal evidence leaks through a cross-panel report. | A disabled HTTP anchor returns an unavailable journal DTO, and disabling a child source removes its rows, candidates and aggregates from an otherwise visible read (Tasks 2–5). |
| Critical | A GET starts a scan, opens a connection, or acquires a thread sample. | Post-action GET succeeds with I/O blocked. Empty or expired thread inventory leaves acquisitions and retained state unchanged (Tasks 1 and 7). |
| High | A surviving reserved failure is presented as complete after child eviction. | A target or candidate at or before the loss horizon yields no comparison (Task 3). |
| High | A fixture filename or literal sample ID is mistaken for a route. | Every sample resolves to a canonical template, and `scanned` resolves to the panel root with an action precondition (Task 1). |
| High | Adapter extraction changes the guard or allows a catch-all to swallow the route. | Real requests through the normal mount, including a custom prefix, hit the same handler and refusal contract on each supported adapter (Tasks 2–8). |

## Phase 1 — correct the contract inventory independently

### Task 1 — identify canonical routes and evidence scenarios

**Files:** `tests/parity/routes_status.json`, `tests/parity/test_routes_parity.py`, `tests/parity/test_parity_ratchet.py`, `tests/fixtures/bootui/2.5.0/routes.json` for comparison, and the matrix fragment and generated documentation. Runtime code, route assembly and capture providers are outside this phase. The current parity test pins 2.3.0 payloads at `test_routes_parity.py:17`. Keep the payload version explicit per fixture. Claim 2.5.0 payload equality only for evidence captured or verified against that tag. The 2.5.0 catalog includes representative request paths and omits some controller routes. Validate those records against the tag's controller declarations.

- [ ] **Red:** `test_inventory_canonical_route_and_capture_provenance` asserts that the rows below have their method, canonical template, fixture version and scenario recorded, and that the count of distinct absent canonical GETs is 14 before any approved dispositions. The current eight `/scanned` URL rows and two fixture-derived aliases fail the mapping assertions.
- [ ] **Red:** `test_existing_trace_detail_has_seeded_route_evidence` asserts R0 classifies `GET /traces/{traceId}` as registered and records a retained ID case and an unknown ID case. A direct test reaches `fastapi/routes/traces.py:46,54` with a real ID, checks `traceId` and the masked `spans` shape, and then expects 404 for a missing ID. The current inventory assertion fails. `# ported: AbstractBootUiApiConformanceTest.tracesListClearAndDetailContract`
- [ ] **Green:** fix the inventory and comparator. Each post-action fixture is a scenario of the GET below. In isolated tests, use the existing action or seed its cached outcome and assert the GET returns it with `no_side_effects`. For Memory Advisor, keep one missing GET with initial and post-action scenarios. Keep networking mocked for the vulnerability action and blocked on its GET. Preserve action enable/read-only and single-flight behavior. A seeded result proves a route exists even where the complete DTO still differs.
- [ ] **Verify:** run `uv run --extra test pytest -q -n 4 tests/parity/test_routes_parity.py tests/parity/test_parity_ratchet.py tests/docs`. Pin the verified counts and regenerate the matrix. Commit as `test: correct BootUI route inventory evidence`.

| Capture row | BootUI method and source | Sharpit baseline and test attribution |
|---|---|---|
| `architecture/scanned` | GET `/architecture` after POST `/architecture/scan`, `ArchitectureController:32,37` | Both at `fastapi/routes/architecture.py:42`. `# ported: AbstractBootUiApiConformanceTest.architectureScanLifecycleFromUnscannedToScanned` |
| `database-advisor/scanned` | GET `/database-advisor` after POST `/database-advisor/scan`, `DatabaseAdvisorController:36,41` | Both at `fastapi/routes/database_advisor.py:51`. `# ported: AbstractBootUiApiConformanceTest.databaseAdvisorPreservesPartialEvidenceAcrossScanAndCachedRead` |
| `fastapi/scanned` | GET `/spring` after POST `/spring/scan`, `SpringController:66,71` | Python counterpart uses `/fastapi` at `fastapi/routes/fastapi.py:46`. Record the path and evidence adaptation. `# ported: AbstractBootUiApiConformanceTest.scoredAdvisorReportsExposeConservativeEvidenceWithoutTriggeringScans` |
| `memory/scanned` | GET `/memory` after POST `/memory/scan`, `MemoryController:41,46` | Both absent in the assembly at `fastapi/routes/__init__.py:683`. Task 8 covers the decision. `# ported: MemoryScannerTests.initialReportIsNotScanned` |
| `postgresql/scanned` | GET `/postgresql` after POST `/postgresql/read`, `PostgresqlController:33,38` | Both at `fastapi/routes/postgresql.py:33`. `# ported: PostgresInsightServiceTests.initialReportTouchesNeitherDiscoveryNorDatabase` |
| `rest-api/scanned` | GET `/rest-api` after POST `/rest-api/scan`, `RestApiController:41,58` | Both at `fastapi/routes/__init__.py:566`. `# ported: AbstractBootUiApiConformanceTest.trackedAdvisorsCompareASecondScanWithTheFirstWithoutInventingChanges` |
| `security/scanned` | GET `/security` after POST `/security/scan`, `SecurityController:58,63` | Both at `fastapi/routes/security.py:43`. `# ported: AbstractBootUiApiConformanceTest.scoredAdvisorReportsExposeConservativeEvidenceWithoutTriggeringScans` |
| `vulnerabilities/scanned` | GET `/vulnerabilities` after POST `/vulnerabilities/scan`, `VulnerabilitiesController:100,119,135` | Both at `fastapi/routes/__init__.py:523`. Preserve the OSV gate. `# ported: AbstractBootUiApiConformanceTest.vulnerabilitiesGetHasCanonicalShape` |
| `runtime-insights/impact-symbols` | GET `/runtime-insights/impact/symbols`, `RuntimeInsightsController:202` | Missing at `fastapi/routes/runtime_insights.py:41`. `# ported: AbstractBootUiApiConformanceTest.changeImpactSymbolsSuggestNothingForAnUnknownQuery` |

The post-action naming comes from `scripts/capture_bootui_live.py:199–213`. Preserve the /trace ID template adaptation without adding a literal `/traces/detail` route. BootUI's raw `/mappings` remains a decision row in Task 8.

## Phase 2 — request journal (R1)

### Task 2 — expose a retained request as a guarded read

**Dependency:** Task 1 and #260 F2 Activity handler extraction. #299 supplies additional journal sources, including authorization evidence. The route may land before those producers, with explicit unavailable dimensions. The change that lands second extends the shared DTO test.

**Route:** `GET /activity/request/{id}/journal`.

**Sources and files:** BootUI `activity/LiveActivityController.java:560–586`, `engine/journal/RequestJournalProfiles.java:149–190,950–1001`, and `core/dto/RequestJournalProfileDto.java:37–85`. Use the extracted Activity handler from `fastapi/routes/activity.py:43`, the existing snapshot in `engine/capture/journal.py:379,409` and ownership join in `engine/collectors/insights/requests.py:39,105`. Add a framework-free projection under `engine/capture/`, test the mounted handler in `tests/fastapi/test_activity_api.py`, and extend the safety matrix.

- [ ] **Red:** `test_request_journal_has_one_shape_for_unknown_and_retained_requests` expects status 200 for each real or unknown ID. For a retained completed request it expects its ID, route and timeline; for unknown or disabled recording it expects `available is False` and the mapped reason. The missing registration returns 404. `# ported: AbstractBootUiApiConformanceTest.requestJournalProfileKeepsOneShapeForAnUnknownAndARecordedRequest`
- [ ] **Red:** `test_request_journal_hides_disabled_sources` expects a hidden anchor to return shaped unavailable, and a visible anchor to omit hidden children and related aggregates. Seed an unrelated request on the same thread and make sure it contributes no evidence. `# ported: RequestJournalProfilesTests.disabledChildPanelsHideTheirEvidenceFromAVisibleWebSocketExecution`
- [ ] **Green:** use the retained snapshot only. Expose `available, unavailableReason, requestId, route, startedAt, durationMicros, status, resources, timeline, gcPauses, routeComparison, touched, notes, orm, handoffs, lateHandoffs, authorizations, baselineComparison`. Preserve the legacy `GET /activity/request/{id}` contract. Mask input echoed in reasons, keep typed evidence bounded, and render inactive sources honestly. Emit `baselineComparison: null` until Task 3. Record each unavailable Python evidence dimension as a deviation with the applicable dependency.
- [ ] **Verify and commit:** exercise a disabled Activity panel, disabled source panels, read-only mode, custom prefix, and hostile origin through the guarded mount. Confirm no side effects and no single-flight or activation changes. Commit as `feat: expose retained request journal profiles`.

## Phase 3 — same-route baselines (R2)

### Task 3 — compare complete retained requests

**Dependency:** Task 2. This comparison uses one running journal. Cross-run history belongs to Task 6.

**Sources and files:** BootUI `LiveActivityController.java:560–574`, `engine/journal/RequestJournalProfiles.java:411–724`, `core/dto/RequestBaselineDiffDto.java:42` and `RequestBaselineCandidateDto.java:11`. Extend the journal projection and mounted tests from Task 2. Use the journal's loss boundary and the existing paired measurement procedure in [overhead-budgets.md](../../development/overhead-budgets.md).

- [ ] **Red:** `test_request_journal_explicit_comparison_selects_a_complete_same_route_request` expects `baselineComparison.baselineRequestId == baseline_id` for a retained explicit match. Task 2 returns null. `# ported: AbstractBootUiApiConformanceTest.requestJournalProfileKeepsOneShapeForAnUnknownAndARecordedRequest`
- [ ] **Red:** `test_request_journal_auto_baseline_excludes_the_cold_first_request` expects the exact closest eligible warm candidate for a seeded slow or failed request. Include exact-tie recency, normal fast requests, self-selection, another route and unknown IDs. `# ported: RequestJournalProfilesTests.comparesASlowOrFailedRequestWithTheClosestWarmRetained2xxBaselineAndExcludesTheColdFirstRequest`
- [ ] **Red:** `test_request_journal_baseline_refuses_incomplete_retained_evidence` has a positive complete comparison control and asserts null plus the applicable refusal note at the loss horizon, including a reserved anchor that survives child eviction. A separate seeded control asserts disabled or unverified SQL dimensions are null while verified SQL yields a delta. `# ported: RequestJournalProfilesTests.lossHorizonAndRecordedColdRequestIdProtectBaselinesWhenAnOlderReservedFailureSurvives` and `# ported: RequestJournalProfilesTests.preparationOnlySqlAndDisabledPanelsKeepBaselineDimensionsNull`
- [ ] **Green:** accept optional `compareWith` on the same GET. Use complete, retained same-route evidence and BootUI's automatic ranking, limit the candidate DTO to 20 entries and distinguishing SQL to five literal-free shapes. Emit all upstream delta keys; unsupported dimensions stay null with a reasoned matrix entry. Preserve source visibility and the read-only path. If cold-request identity cannot be established after loss, record the conservative behavior as a deviation.
- [ ] **Verify and commit:** compare read latency and retained bytes on empty, full and evicting journals. Run existing capture budgets with paired measurements before adding any capture-side state. Preserve the existing guard, do no I/O, and add no lock that serializes ordinary requests. Commit as `feat: compare retained requests with same-route baselines`.

## Phase 4 — existing local evidence and R3 closure

### Task 4a — Cache report and Service Map

**Routes and dependencies:** `GET /cache` depends on Task 1 and the #260 Cache handler batch. `GET /activity/service-map` follows the first endpoint change in Task 2 and needs the #260 Activity handler batch. Each route lands in a separate slice. Service Map can start with supported local sources and add approved outbound or broker evidence later.

- [ ] **Red (Cache):** `test_cache_report_reads_registered_snapshot` expects GET 200, the registered manager name and accurate counts under `no_side_effects`. The current route assembly at `fastapi/routes/cache.py:44` provides the clear action only. `# ported: SpringCacheControllerTests.cacheReportListsManagersCachesMetricsAndAnnotatedOperations`
- [ ] **Green (Cache):** apply `web/SpringCacheController.java:37,42` and `core/dto/CacheReport.java:19` using the local `CacheProvider.managers` seam in `engine/collectors/cache/clear.py:79`. Extend `tests/fastapi/test_cache_clear_route.py` with read tests or add `tests/fastapi/test_cache_report.py` if the slice is separate. Record unavailable JVM tier or annotation metadata. A provider that needs network I/O cannot back the GET. The existing clear action retains its own gate and confirmation. Commit as `feat: report registered cache snapshots`.
- [ ] **Red (Service Map):** `test_service_map_uses_only_visible_safe_local_identities` expects GET 200, an application node and a seeded edge. An independent case disables that source and expects the edge absent. A seeded SQL literal and URL query must be absent from output. `# ported: AbstractBootUiApiConformanceTest.serviceMapIsBoundedAndCarriesOnlySafeIdentities` and `# ported: ServiceMapAssemblerTests.omitsEvidenceFromDisabledSourcePanels`
- [ ] **Green (Service Map):** apply `activity/LiveServiceMapController.java:62` and `core/dto/ServiceMapReport.java:27` through the extracted Activity handler; extend `tests/fastapi/test_activity_api.py`. Use bounded counts and existing in-process evidence. Keep origins coarse, avoid statement text and bindings, and record each unsupported source as a deviation until its producer lands. The Activity gate applies to the route and source panel visibility applies to each contribution. Commit as `feat: report a service map from local evidence`.

### Task 4b — close or record all 28 partial rows

**Dependency:** Task 1 and each panel's #260 F2 batch. Activity, journal and runtime evidence work may follow Tasks 2, 3 or 5 when it needs their projections. Memory resources and thread quality wait for Tasks 7–8 where the field requires a new producer.

**Files and steps:** extend `tests/parity/test_routes_parity.py` and the existing mounted panel tests under `tests/fastapi/` for each panel slice. Add the expected seeded projection or an accepted deviation assertion first. For a sample-only difference that already reaches green, first assert the inventory still lacks the new evidence scenario, then prove the seeded assertion bites by removing the input or mutating the expected projection. Record the reason for any accepted null, empty collection or platform-only field. A comparison against an empty sample cannot prove a non-empty row shape. Verify each slice through the GET safety sweep and update the matrix. Commit each slice as `test: verify <panel> route parity` or `fix: align <panel> report contract`.

The last column gives the red assertion for the panel slice. Every row inherits the read gates above. `# ported: AbstractBootUiApiConformanceTest.availablePanelsMatchTheirDtoFamilyContracts` covers shared DTO family assertions. More specific cases are listed where applicable.

| Route | BootUI Java → sharpit Python | Red evidence, deviation or safety check |
|---|---|---|
| `/activity` | `LiveActivityController:344` → `fastapi/routes/activity.py:43` | Seeded `entries`, LOG/SQL/TRANSACTION counts and available cached KPIs must appear. Any persistence projection is pending a decision. Mask before search. `# ported: AbstractBootUiApiConformanceTest.liveActivityServesTheFeedRenderedFromTheJournalOnRequest` |
| `/activity/journal` | `LiveActivityController:507` → `fastapi/routes/activity.py:44` | `oldestRetainedAt` and the recorded keys of actually seeded sources match. No fabricated counters for unrecorded sources. `# ported: AbstractBootUiApiConformanceTest.runtimeJournalReportsOneShapeAndClearingItNeedsConfirmation` |
| `/activity/resources` | `LiveActivityController:513` → `fastapi/routes/activity.py:45` | Given a supported sample, assert its `families`, `points` and consistent `totals`. For unsupported sources assert the approved unavailable reason. `# ported: AbstractBootUiApiConformanceTest.runtimeResourcesReportOneShapeWithABalancedLedger` |
| `/architecture` | `ArchitectureController:32` → `fastapi/routes/architecture.py:42` | Seeded scan scope is present in `basePackages` or its approved Python projection; safe names only. |
| `/config` | `ConfigController:37` → `fastapi/routes/__init__.py:160` | Configured `activeProfiles` match; search by a planted secret returns no hit. |
| `/database-connection-pools/pools` | `DatabaseConnectionPoolsController:41` → `fastapi/routes/__init__.py:485` | Registered pool appears with zero connections opened by the read. |
| `/email` | `EmailController:53` → `fastapi/routes/email.py:43` | Trap-off or unsupported mode yields the expected `unavailableReason`; active mode preserves recipient and message masking. |
| `/exceptions` | `ExceptionsController:105` → `fastapi/routes/__init__.py:380` | Seeded exception group appears; sensitive text stays absent. Preserve local 400 handling from controller `:136` where applicable. |
| `/fastapi-security/endpoints` | `SpringSecurityController:81` → `fastapi/routes/fastapi_security.py:35` | Declared Python metadata populates `description`; undeclared descriptions use an approved nullable deviation. |
| `/github` | `GitHubController:44` → `fastapi/routes/github.py:32` | Equivalent disconnected state returns the expected reason with no network call and no credential disclosure. |
| `/health` | `HealthController:27` → `fastapi/routes/__init__.py:466` | Cached `components` appear while the live probe call count remains zero. |
| `/http-exchanges` | `HttpExchangesController:132` → `fastapi/routes/http_exchanges.py:36` | Seeded `reserved`, `reservedCapacity` and `slowThresholdMillis` reconcile with actual retention, or an approved deviation records the unsupported field. `# ported: AbstractBootUiApiConformanceTest.captureBuffersReportReconcilingRetention` |
| `/java-agent` | `JavaAgentController:33` → `fastapi/routes/java_agent.py:44` | The Python setup report asserts the accepted disposition for `setup.jarPath` and `snippets`. `# ported: AbstractBootUiApiConformanceTest.theJavaAgentPanelReportsNotAttachedWithSetupSnippetsWhenTheJvmRunsWithoutTheAgent` |
| `/log-tail/recent` | `LogTailController:101` → `fastapi/routes/__init__.py:208` | Seeded log appears and its planted secret remains absent. `# ported: AbstractBootUiApiConformanceTest.logTailMasksSecretAssignmentsInTheSnapshotAndTheStream` |
| `/metrics` | `MetricsController:26,47` → `fastapi/routes/metrics.py:44` | Supported metric group supplies its `baseUnits`, `interpretation` and `catalogueVersion`. Malformed query gets the canonical 400. `# ported: AbstractBootUiApiConformanceTest.metricsContractIsBoundedAndValidatesQueriesCanonically` |
| `/overview` | `OverviewController:43` → `fastapi/routes/__init__.py:159` | Seeded profiles and context path match; gate the dispositions for default profiles and management port. `# ported: AbstractBootUiApiConformanceTest.overviewEndpointServesShellContract` |
| `/profile-diff` | `ProfileDiffController:24` → `fastapi/routes/profile_diff.py:21` | Seeded `activeProfiles` and `profileSources` appear with masked values. |
| `/rest-api` | `RestApiController:41` → `fastapi/routes/__init__.py:566` | Explicit scan scope yields seeded `basePackages` or the accepted Python scope projection. |
| `/rest-api/error-contract` | `RestApiController:50` → `fastapi/routes/__init__.py:567` | A declared error adds a matching `entries` row with zero host handler executions. `# ported: AbstractBootUiApiConformanceTest.errorContractEndpointReturnsAStableDeclarationOnlyCatalogue` |
| `/runtime-insights` | `RuntimeInsightsController:181` → `fastapi/routes/runtime_insights.py:41` | Seeded `coverage`, `limitations`, `notExercised`, `observations` and event timestamp bounds match held evidence, with source visibility preserved. `# ported: AbstractBootUiApiConformanceTest.runtimeInsightsProjectTheJournalIntoObservationsWithStableIdsAndEvidence` |
| `/scheduled` | `ScheduledController:34` → `fastapi/routes/scheduled.py:23` | In-memory supported scheduler exposes an expected `tasks` row. Task is never executed by inspection. |
| `/sql-trace` | `SqlTraceController:86` → `fastapi/routes/__init__.py:248` | Seeded `entries` and `topStatements` appear. `reserved` counters reconcile, and literals/bindings remain masked. `# ported: AbstractBootUiApiConformanceTest.captureBuffersReportReconcilingRetention` |
| `/sql-trace/insights` | `SqlTraceController:99` → `fastapi/routes/sql_trace.py:20` | Seeded `statements` and oldest/newest timestamps match observed evidence. `# ported: AbstractBootUiApiConformanceTest.sqlTraceInsightsAreBoundedAndDiscloseTheirCorrelationTiers` |
| `/startup` | `StartupController:39` → `fastapi/routes/startup.py:23` | A supported observed lifecycle step appears in `steps`, or the accepted deviation identifies unavailable lifecycle timing. |
| `/threads` | `ThreadDumpController:53` → `fastapi/routes/__init__.py:502` | Supported `quality` and `hiddenBootUiThreads` reflect real observations. Assert the approved null semantics for unavailable CPU and user times. |
| `/traces` | `TracesController:47` → `fastapi/routes/traces.py:53` | Seeded `traces` includes the retained host trace and excludes the console trace and planted secret. `# ported: AbstractBootUiApiConformanceTest.traceDataFollowsTheLiveValueExposurePolicy` |
| `/transactions` | `TransactionsController:68` → `fastapi/routes/transactions.py:51` | Seeded SQLAlchemy transaction appears in `entries` with its masked evidence. |
| `/vulnerabilities` | `VulnerabilitiesController:100` → `fastapi/routes/__init__.py:523` | Assert the approved Python distribution counterpart or deviation for `coverage.unidentifiedArchives`. GET produces zero requests. |

## Phase 5 — runtime change impact and symbols

### Task 5 — project impact and suggest searchable symbols

**Dependency:** Task 1 and #260 Runtime Insights extraction. Reuse retained evidence from Task 2 where it supplies ownership. Establish the supported Python symbol families before promising method-level or outbound reach.

**Sources and files:** `insights/RuntimeInsightsController.java:196,202`, `engine/insights/ChangeImpactService.java:182,1059`, `core/dto/RuntimeChangeImpactDto.java:41`, and `RuntimeImpactSymbolsDto.java:15`. Extend `engine/collectors/insights/`, the extracted handlers from `fastapi/routes/runtime_insights.py:41`, and `tests/fastapi/test_runtime_insights_api.py`.

- [ ] **Red:** `test_impact_distinguishes_observed_unexercised_and_unknown` expects 200 for known and unknown symbols, only supported route evidence in the known case, and no guessed routes for unknown or ambiguous names. Both GETs are absent today. `# ported: AbstractBootUiApiConformanceTest.changeImpactNeverGuessesAnUnknownSymbol`
- [ ] **Red:** `test_impact_symbols_searches_visible_display_names` expects a known visible suggestion, an empty list for an unknown query, and no match for a hidden or masked source. Use `/runtime-insights/impact/symbols?query=`. `# ported: AbstractBootUiApiConformanceTest.changeImpactSymbolsSuggestNothingForAnUnknownQuery` and `# ported: ChangeImpactServiceTests.disabledSourceFactsStayOutOfImpactAndSuggestionsEvenWhenThePolicyChangesWithoutNewEvents`
- [ ] **Green and verify:** add two guarded GETs over bounded local evidence. Preserve shaped 200 outcomes for missing, ambiguous and unavailable evidence. Cap inputs and output where upstream does; apply source gates and display masking before matching. Record unsupported method or platform symbol families and conservative reach states in separate deviation rows. No capture starts from either read. Commit as `feat: report runtime change impact and symbols`.

## Phase 6 — cross-run comparison

### Task 6 — compare approved application-scoped run summaries

**Route:** `GET /runtime-insights/comparison?run=<id>`. The default compares with the newest kept run.

**Dependency:** Task 1, #260 Runtime Insights extraction, and maintainer approval of the history source, lifetime and disclosure rules. Task 3's in-run baseline is independent. The current journal returns no previous runs in `engine/capture/journal.py:474`.

**Sources and files:** `insights/RuntimeInsightsController.java:226`, `engine/insights/RunComparisonService.java:171,476–545`, `engine/journal/RunBaselineFile.java:59`, and `core/dto/RuntimeRunComparisonDto.java:30`. Extend the current engine insights and route family at `fastapi/routes/runtime_insights.py:41` and `tests/fastapi/test_runtime_insights_api.py`.

- [ ] **Red:** `test_run_comparison_uses_only_the_current_app_history` expects a seeded, comparable prior summary to yield 200 `COMPARED`, another application's run to yield a shaped unavailable result, and no kept run to preserve the same DTO keys. The current route is absent. Test with the no-side-effects guard. `# ported: AbstractBootUiApiConformanceTest.theRunComparisonComparesTheCurrentRunWithAKeptOneOrSaysWhyNot`
- [ ] **Green and verify:** read preloaded bounded summaries. Persisted evidence, if approved, is loaded or written at an explicitly approved lifecycle boundary. A GET starts no database connection or write. Apply current panel visibility and masking to historical data. Record the history-source difference, absent JVM restart/side-effect fields and any unsupported comparison dimensions in separate deviation rows. A persistence or exposure change needs high-tier review before implementation. Commit as `feat: compare retained application run summaries`.

## Phase 7 — retained thread captures

### Task 7 — retain an explicitly acquired snapshot and list it

**Routes:** `GET /threads/captures` and the required acquisition action, `POST /threads/captures`.

**Dependency:** Task 1, #260 Threads extraction, maintainer approval of Python snapshot and disclosure limits, and review of the action-gate change. Current `engine/panels.py:45` sets `action_capable=False` for Threads; `fastapi/routes/__init__.py:502` mounts only the live read.

**Sources and files:** `web/ThreadDumpController.java:80–95,170`, `engine/threads/ThreadAnalysisService.java:104,108,331,594,639`, and `ThreadDumpService.java:211`. Use `engine/collectors/threads.py` as the existing inspection seam and test the extracted route through `tests/fastapi/test_threads_api.py`.

- [ ] **Red:** `test_thread_capture_list_never_acquires_or_mutates_snapshots` expects GET 200 with an empty or seeded list, filters expired evidence, and checks the store and acquisition counts before and after. `# ported: ThreadAnalysisServiceTests.passiveReadsNeverAcquireAndPagingKeepsTheOriginalCapture`
- [ ] **Red:** `test_thread_capture_action_respects_read_only_and_single_flight` expects a seeded POST to return a capture ID, list it through GET, reject a second in-flight capture with canonical 409, and reject read-only POST before acquisition. A subsequent action succeeds after a simulated acquisition failure. `# ported: AbstractBootUiApiConformanceTest.threadActionsRejectCrossSiteRequestsBeforeResourceLookup` and `# ported: AbstractBootUiApiConformanceTest.threadCapturesHaveStableEvidenceAndFiniteExplicitObservationsOnEveryStack`
- [ ] **Green and verify:** make explicit POST acquisition the sole source of snapshots for the initial slice. Apply the enabled/read-only checks, a single-flight acquisition and bounded count, bytes and TTL. A GET projects only visible retained data and never purges or cancels work. Put pruning and policy transition effects on an approved mutation boundary. Record that deviation from `ThreadAnalysisService.java:594–620`, and each unsupported JVM lock/CPU field. Apply masking to frames and names before retention and before output as required by the exposure contract. Preserve relevant 409/503 outcomes. Detail, export, clear and observation workflow remain separate scope. Commit as `feat: retain and list explicit thread captures`.

## Phase 8 — platform-dependent endpoint decisions

### Task 8 — resolve each provider or record the platform deviation

**Dependency:** Task 1 plus the corresponding #260 handler batch for any approved port. Decisions may be resolved while earlier phases run. Each port is a separate panel slice using the extracted console handler and a mounted `tests/fastapi/test_<panel>_route.py` test. An omitted route changes only its inventory row, matrix and contract test. Each test starts with either the listed failing GET assertion for a port, or a failing assertion that the inventory records the approved omission, cites the source and preserves the supported counterpart. The proposed omissions below remain pending.

| Canonical GET and source | Current sharpit evidence | Maintainer decision, red assertion and ported test |
|---|---|---|
| `/mappings`, `web/ActuatorMappingsController.java:32–39` | Portable `/mappings/flat` at `fastapi/routes/__init__.py:162`. BootUI portable version is `MappingsController.java:30`. | **Candidate for omission.** The raw descriptor represents Spring Actuator contexts and MVC registrations. Decide whether the Python contract needs a counterpart. For omission, assert an approved `n-a` row with the reason and retained flat-route coverage. For a port, assert a real supported provider returns its descriptor and absence returns 204. `# ported: ActuatorMappingsControllerTests.returnsNoContentWhenEndpointBeanAbsent` |
| `/http-sessions`, `web/HttpSessionsController.java:39,56` | No host inventory in `fastapi/routes/__init__.py:683`. | **Candidate for omission.** A client-held cookie store cannot enumerate active clients, and an external store may require a connection. Approve only a known bounded local provider and explicit attributes/ID masking, or record the difference. Red expects a registered entry with a masked identifier and an untouched read sentinel, or an approved omission row. Clear/invalidate are separate scope. `# ported: HttpSessionsControllerTests.sessionsReportListsBoundedSessionsWithMaskedIdsAndAttributes` |
| `/fault-tolerance`, `web/FaultToleranceController.java:30` | No adapter or provider in `fastapi/routes/__init__.py:683`. | **Candidate for omission.** Python has no default provider equivalent to the upstream policy catalog. Approve a specific local observer or record the difference. Red expects shaped unsupported 200 plus a seeded policy when its provider is present. The BootUI panel offers reads only. `# ported: FaultToleranceControllerTests.servesTheStablePolicyAndEventShape` |
| `/kafka`, `kafka/KafkaController.java:49,59` | No registered capture provider in `fastapi/routes/__init__.py:683`. | **Candidate for omission.** BootUI observes registered clients; no Python client boundary is approved. Red expects a shaped unavailable 200 without a provider and bounded hashed/omitted keys from a seeded passive provider. No broker traffic on GET. DELETE clear is separate scope. `# ported: KafkaControllerTests.reflectsDisabledCaptureAndKeyHashingOnTheReport` |
| `/rest-client-trace`, `restclienttrace/RestClientTraceController.java:63,68,73` | `engine/capture/activity.py:401` reports no outbound recorder. | Approve a specific passive recorder, its URL/credential/header policy and instrumentation overhead, or record that the Python integration is omitted. Red expects an unavailable 200 without a provider and a sanitized bounded call row with one. GET issues no outbound request; companion clear and recording actions are separate scope. `# ported: RestClientTraceControllerTests.suppressesQueryStringAndHeadersUnderMetadataOnlyExposure` |
| `/live-memory`, `web/LiveMemoryController.java:39,51,57` | GET/POST `/live-memory/footprint` at `fastapi/routes/lowfootprint.py:79`. | **Candidate for omission of JVM-only dimensions.** Approve Python counters, output fields and disclosure policy. Red expects 200 from a supported snapshot, typed-query validation, and zero sampling or collection on read. JVM flags and tuning advice require separate deviations. Offload remains separate scope. `# ported: LiveMemoryControllerTests.liveMemoryRouteProjectsReport` |
| `/memory`, `memory/MemoryController.java:41,46`, `engine/memory/MemoryScanner.java:58` | Advisor and scan absent in `fastapi/routes/__init__.py:683`. | **Candidate for omission of JVM-only rules.** Approve Python measurements and rule dispositions. Red expects initial 200 with `scan.status == "NOT_SCANNED"` and post-action GET returning the retained result. If POST is approved, assert read-only refusal and a second scan returning 409 while acquisition is held. A GET starts no sampling. `# ported: MemoryScannerTests.initialReportIsNotScanned` and `# ported: MemoryScannerTests.duplicateScanDoesNotQueueOrAdvanceTrendState` |

- [ ] **Green:** for each approved port, emit the upstream DTO keys and shaped unavailable behavior for absent optional capabilities. Apply the guards and no-side-effects checks above, including any approved action's BootUI single-flight behavior. Record separate deviation rows for each platform field, unavailable producer or omission. A proposed process-wide hook, interception, identity disclosure or new side-effect path goes through high-tier review before implementation.
- [ ] **Verify and commit:** record the maintainer decision and its evidence. Commit each port as `feat: add <panel> report parity`, or record the approved omission as `docs: record <panel> route deviation`.

## Definition of done

- [ ] The canonical inventory accounts for all 23 original missing fixture rows, the 28 partial rows, and the approved outcome of each absent canonical capability.
- [ ] Compared responses and recorded deviations have pinned-source tests, including unavailable paths, no-side-effects reads, canonical guard refusals, and affected actions' busy behavior.
- [ ] The request profile and baseline share one stable DTO and cover evicted, cross-route, same-route, masked and source-disabled cases. Retention and overhead results are recorded.
- [ ] Both supported mount paths pass the applicable corpus and real requests with configured prefixes and panel policy after #260. Existing capture budgets and route ratchets pass unchanged.
- [ ] Every omitted route or unsupported evidence field has a maintainer decision and a reasoned matrix or design row. The docs checks pass.

Plan-document check: `uv run --extra test pytest -q -n 4 tests/docs tests/test_agent_workflow.py`.
