# Issue #300: BootUI 2.5.0 API route parity

**Goal:** reconcile the GET route inventory with BootUI `v2.5.0`, implement the request journal, same-route
baselines, cache and service-map reads, close or record the 28 partial rows, and scope Phases 5–8 behind maintainer
decisions.

**Architecture:** framework-free projections live in `src/sharpit/engine/`. HTTP route wiring mounts thin handlers in
`src/sharpit/fastapi/routes/` (or `src/sharpit/engine/console/` once extracted). Engine logic, unit tests, and Phase 4b
closures do not wait on #260; only route-registration lines for newly added endpoints coordinate with the affected
panel's #260 F2 handler extraction batch.

**Source pins:** sharpit `90c2ec30` and BootUI `v2.5.0` (`c4458db8d`). BootUI controller paths are under
`bootui-spring-boot-starter/src/main/java/io/github/jdubois/bootui/autoconfigure/`; engine classes use
`bootui-engine/src/main/java/io/github/jdubois/bootui/`; conformance tests use
`bootui-conformance/src/main/java/io/github/jdubois/bootui/conformance/AbstractBootUiApiConformanceTest.java`. Read
pinned sources with `git -C <bootui-clone> show v2.5.0:<path>`.

## Global constraints

- **Panel gate first:** `engine/guard.py:339–355` (`_panel_access`) returns `None` when `panel_for_api_path(sub_path)`
  finds no implemented `Panel` (`guard.py:348–349`). Each new route's first step is its `Panel` entry in
  `engine/panels.py` (and `engine/panels04/` flag) with BootUI's `action_capable` (`engine/panel/BootUiPanels.java`),
  with reds for disabled 403 (`PANEL_ACCESS_DENIED`) and read-only 403 (`# ported:
  PanelAccessFilterTests.allowsReadOnlyPanelReadRequest`, `# ported:
  PanelAccessFilterTests.blocksReadOnlyPanelActionRequest`).
- **Reads, contract, and gates:** every GET uses `no_side_effects` (no socket, file write, live scan, acquisition,
  logger change, or env mutation). Emit all DTO keys (nulls included) in camelCase at root with epoch ms. Mask secrets
  before filtering and before output or echoed errors/reasons. Hide disabled source panels at read time. Record
  deviations in `docs/reference/matrix-updates/0.10.0-routes-300.tsv` and regenerate `docs/reference/PARITY.md`. Run
  `/sharpit:predict` and `/sharpit:scenario` before Phase 3 (baselines) and before each of Phases 5–8 once selected.

## BootUI 2.5.0 unmounted GET route inventory

BootUI `v2.5.0` starter controllers (`*Controller.java` and `web/AdvisorViolationsEndpoint.java:12`) and
`BootUiApiContractCatalog.java` (`tests/fixtures/bootui/2.5.0/routes.json`) declare **143** real API GET routes (plus
`GET /mcp` at `mcp/BootUiMcpController.java:194`, which returns 405 and matches Starlette's `POST /mcp`). Sharpit
mounts **100** (93 identical templates + 7 Python path adaptations: `/fastapi`, `/fastapi/rules/{rule_id}/violations`,
`/fastapi-security`, `/fastapi-security/explain`, `/fastapi-security/endpoints`, `/sqlalchemy-statistics`, and
`/alembic/migrations`). Of the **43** unmounted GET routes, **10** are already `n-a` in
`tests/parity/routes_status.json` and `docs/reference/matrix-updates/0.9.0-r0.tsv` (`/conditions`, `/crac`,
`/dev-services`, `/devtools`, `/graalvm`, `/graalvm/metadata`, `/graalvm/scan/progress` [spelled
`/graalvm/scan-progress` in 2.3.0], `/heap-dump`, `/jvm-tuning`, `/liquibase/changesets`), leaving **33** unmounted
GET routes:

| # | Canonical GET route | BootUI v2.5.0 source | Catalog | Disposition |
|---|---|---|---|---|
| 1 | `/activity/request/{id}/journal` | `activity/LiveActivityController:560` | `reads` | Port (Phase 2) |
| 2 | `/activity/service-map` | `activity/LiveServiceMapController:62` | — | Port (Phase 4a) |
| 3 | `/cache` | `web/SpringCacheController:37` | `reads` | Port (Phase 4a) |
| 4 | `/runtime-insights/impact` | `insights/RuntimeInsightsController:196` | `reads` | Scope (Phase 5) |
| 5 | `/runtime-insights/impact/symbols` | `insights/RuntimeInsightsController:202` | `reads` | Scope (Phase 5) |
| 6 | `/runtime-insights/comparison` | `insights/RuntimeInsightsController:226` | `reads` | Decision (Phase 6) |
| 7 | `/threads/captures` | `web/ThreadDumpController:85` | — | Scope (Phase 7) |
| 8 | `/threads/captures/{id}` | `web/ThreadDumpController:90` | — | Scope (Phase 7) |
| 9 | `/threads/captures/{id}/contention` | `web/ThreadDumpController:90` | — | Scope (Phase 7) |
| 10 | `/threads/captures/{id}/threads` | `web/ThreadDumpController:98` | — | Scope (Phase 7) |
| 11 | `/threads/captures/{id}/threads/{observationId}` | `web/ThreadDumpController:111` | — | Scope (Phase 7) |
| 12 | `/threads/captures/{id}/locks/{lockId}` | `web/ThreadDumpController:119` | — | Decision (Phase 7) |
| 13 | `/threads/observations/{id}` | `web/ThreadDumpController:155` | — | Decision (Phase 7) |
| 14 | `/mappings` | `web/ActuatorMappingsController:32` | — | Decision (Phase 8) |
| 15 | `/http-sessions` | `web/HttpSessionsController:39` | `reads` | Decision (Phase 8) |
| 16 | `/fault-tolerance` | `web/FaultToleranceController:30` | `reads` | Decision (Phase 8) |
| 17 | `/kafka` | `kafka/KafkaController:49` | `reads` | Decision (Phase 8) |
| 18 | `/rabbitmq` | `rabbit/RabbitController:50` | `reads` | Decision (Phase 8) |
| 19 | `/jms` | `jms/JmsController:40` | `reads` | `n-a` (Phase 1/8, `X`) |
| 20 | `/websockets` | `websocket/WebSocketController:59` | `reads` | Decision (Phase 8) |
| 21 | `/websockets/stream` | `websocket/WebSocketController:75` | — | Decision (Phase 8) |
| 22 | `/rest-client-trace` | `restclienttrace/RestClientTraceController:63` | `reads` | Decision (Phase 8) |
| 23 | `/rest-client-trace/stream` | `restclienttrace/RestClientTraceController:82` | — | Decision (Phase 8) |
| 24 | `/live-memory` | `web/LiveMemoryController:39` | `reads` | Decision (Phase 8) |
| 25 | `/memory` | `memory/MemoryController:41` | `reads` | Decision (Phase 8) |
| 26 | `/memory/rules/{ruleId}/violations` | `web/AdvisorViolationsEndpoint:12` | — | Decision (Phase 8) |
| 27 | `/hibernate` | `hibernate/HibernateController:39` | `reads` | Decision (Phase 8) |
| 28 | `/hibernate/rules/{ruleId}/violations` | `web/AdvisorViolationsEndpoint:12` | — | Decision (Phase 8) |
| 29 | `/dev-services/{id}/logs` | `web/DevServicesController:45` | — | `n-a` (`0.9.0-r0`) |
| 30 | `/heap-dump/download` | `web/HeapDumpController:57` | — | `n-a` (`0.9.0-r0`) |
| 31 | `/crac/dockerfile` | `crac/CracController:94` | — | `n-a` (JVM CRaC, `X`) |
| 32 | `/crac/entrypoint` | `crac/CracController:103` | — | `n-a` (JVM CRaC, `X`) |
| 33 | `/graalvm/dockerfile` | `graalvm/GraalVmController:124` | — | `n-a` (GraalVM, `X`) |

## Phase 1 — smallest contract inventory correction (Task 1)

**Files:** `tests/parity/routes_status.json`, `tests/parity/test_routes_parity.py`, `tests/docs/test_parity_matrix.py`,
`ROADMAP.md`, `README.md`, `docs/reference/matrix-updates/0.10.0-routes-300.tsv`, `docs/reference/PARITY.md`. No
multi-version schema and no live scan. Keep `len(_ROUTES) == 97` (`tests/parity/test_routes_parity.py:104`) and add an
optional `"scenario"` field. Point the eight `*/scanned.captured.json` rows (`architecture`, `database-advisor`,
`fastapi`, `memory`, `postgresql`, `rest-api`, `security`, `vulnerabilities`) at `/sharpit/api/<panel>` with
`"scenario": "post-scan"` (`"post-read"` for `postgresql`; `memory` stays `missing` until Phase 8). Point
`traces/detail.captured.json` at `/sharpit/api/traces/{id}` (`fastapi/routes/traces.py:46,54`,
`"scenario": "seeded-trace"`). Fix `runtime-insights/impact-symbols.captured.json` to
`/sharpit/api/runtime-insights/impact/symbols`. Four served panels (`database-advisor`, `fastapi`, `postgresql`,
`security`) have an unscanned `captured.json` row marked `n-a` due to `emptyLists` and a `scanned.captured.json`
scenario on the same canonical GET: all 97 fixture rows remain in `_ROUTES`, while the seven served post-action rows
and `traces/detail.captured.json` become `partial`. In `tests/docs/test_parity_matrix.py`, merge rows sharing a
canonical `route` when computing route-level doc totals (a served `partial`/`matched` scenario supersedes an unscanned
`n-a` empty-list row) or update `routes_status.json["counts"]`, `ROADMAP.md`, and `README.md` together. **Phase 4b
(Task 4b)** is the closing owner for all seven post-action differences and `GET /traces/{id}`.
- [ ] **Red & Green:** assert no `route` in `routes_status.json` ends with `/scanned`, `/traces/detail`, or
  `/impact-symbols`, `len(_ROUTES) == 97`, and `GET /traces/{id}` returns 200 when seeded and 404 when unknown
  (`# ported: AbstractBootUiApiConformanceTest.tracesListClearAndDetailContract`). Record `#19, #29–#33` as `n-a` in
  `0.10.0-routes-300.tsv`. Verify `uv run --extra test pytest -q -n 4 tests/parity tests/docs` and commit as
  `test: map post-action and trace detail fixtures to canonical routes`.

## Phase 2 — request journal, R1 (Task 2: `GET /activity/request/{id}/journal`)

**Sources and files:** BootUI `activity/LiveActivityController.java:560–586`,
`engine/journal/RequestJournalProfiles.java:47–330,700–1010`, `core/dto/RequestJournalProfileDto.java:37–85`. Sharpit
`engine/panels.py:37`, `engine/capture/journal.py`, `engine/capture/request_journal.py`, `fastapi/routes/activity.py`,
`tests/fastapi/test_activity_api.py`. Verify `Panel("activity", "Live Activity", False, "/activity")` returns 403
`PANEL_ACCESS_DENIED` when disabled. Add a targeted selector on `RuntimeJournal` (`engine/capture/journal.py`) that
matches `requestId` (or `executionId`), its children, same-route HTTP events (`MINIMUM_ROUTE_REQUESTS = 5`), and
trace-linked AI events under `self._lock`, and masks (`_masked`) only that matched subset (no full-journal `view()` or
`RequestIndex` per read, and no capture-time route aggregates). A retained HTTP anchor whose earlier children were
evicted (`oldestRetainedAt > startedAt` or `startedAt <= lossHorizon`) still returns 200 with `available: true` and
BootUI's eviction note (`RequestJournalProfiles.java:276–281`). Any echoed caller `requestId` in `requestId` or
`unavailableReason` (`:70–73,188–189`) strips control characters, runs `ctx.masker.mask_text`, and truncates to 64
chars with `"…"` (`safeRequestId`, `:711–717`); under `METADATA_ONLY`, `requestId` is withheld/masked.
- [ ] **Red & Green:** reds for disabled-panel 403, unknown/retained/partially-evicted 200 shape (`# ported:
  AbstractBootUiApiConformanceTest.requestJournalProfileKeepsOneShapeForAnUnknownAndARecordedRequest`), disabled child
  panels (`# ported: RequestJournalProfilesTests.disabledChildPanelsHideTheirEvidenceFromAVisibleWebSocketExecution`),
  and `METADATA_ONLY`/`MASKED`/`FULL` exposure + echoed-`requestId` sanitization. Emit `baselineComparison: null` until
  Task 3. Verify with `no_side_effects` and commit as `feat: expose retained request journal profiles`.

## Phase 3 — same-route baselines, R2 (Task 3: `baselineComparison`)

**Pre-implementation gate:** run `/sharpit:predict` and `/sharpit:scenario` before Task 3.
**Sources and files:** BootUI `LiveActivityController.java:560–574`,
`engine/journal/RequestJournalProfiles.java:411–724`, `core/dto/RequestBaselineDiffDto.java:42`,
`RequestBaselineCandidateDto.java:11`. Engine logic in `engine/capture/request_journal.py` (no #260 block). Under
`RuntimeJournal`'s single FIFO ring (`reservedEvents: 0`, `engine/capture/journal.py:464`), child events offered during
a request evict before the completion-time HTTP anchor. An anchor outliving its children (`startedAt <= lossHorizon` or
`startedAt < oldestRetainedAt`) replaces BootUI's reserved-failure survival case and is refused as a baseline or target
(`RequestJournalProfiles.java:431–436,511–514`). Without capture-time aggregates, exclude the cold first request when
`evictedEvents == 0` and no clear occurred; record post-eviction cold-request identity as a deviation. Sanitize, mask
(`mask_text`), and cap echoed `compareWith` at 64 chars (`safeRequestId`, `:500,711–717`). Cap candidates at 20 and
`distinguishingSqlShapes` at 5.
- [ ] **Red & Green:** reds for explicit `compareWith` + echoed-ID sanitization, auto-baseline excluding cold first
  request (`# ported: RequestJournalProfilesTests`
  `.comparesASlowOrFailedRequestWithTheClosestWarmRetained2xxBaselineAndExcludesTheColdFirstRequest`), FIFO anchor
  outliving children + disabled/unverified SQL null deltas + per-exposure (`METADATA_ONLY`/`MASKED`/`FULL`) SQL shapes
  (`# ported: RequestJournalProfilesTests.partiallyEvictedRequestsAreNeverUsedAsBaselinesOrComparedAsCompleteTargets`,
  `# ported: RequestJournalProfilesTests.preparationOnlySqlAndDisabledPanelsKeepBaselineDimensionsNull`). Run paired
  overhead checks and commit as `feat: compare retained requests with same-route baselines`.

## Phase 4 — `GET /cache`, `GET /activity/service-map`, and R3 partial closure

### Task 4a — `GET /cache` and `GET /activity/service-map`

**Sources and files:** BootUI `web/SpringCacheController.java:37`, `engine/cache/CacheService.java:81–195,249–350`,
`activity/LiveServiceMapController.java:62`. Sharpit `engine/panels.py:37,79`, `engine/collectors/cache/clear.py`.
Assert disabled-panel 403 (`PANEL_ACCESS_DENIED`) for `cache` (`action_capable=True`, `panels.py:79`) and `activity`
(`panels.py:37`), plus read-only 200 on `GET /cache` and read-only 403 on `POST /cache/clear`.
- [ ] **Cache (`GET /cache`):** (1) no-provider (`provider is None` or unavailable) returns 200 with `available: false`,
  zero counts, and empty lists (`# ported:
  SpringCacheControllerTests.cacheReportIsStableWhenNoCacheManagersArePresent`); (2) remote-provider refusal: zero
  network I/O on GET (`no_side_effects`), non-local objects refused by `InProcessCacheProvider.register`; (3) mask
  manager names, cache names, and truncation warnings via `ctx.masker.mask_text`; (4) read live counts and stats
  (`cache_info().currsize/hits/misses/maxsize` for `functools`, `len(cache)/maxsize` for `cachetools.Cache`) in
  `InProcessCacheProvider.managers()` (`# ported:
  SpringCacheControllerTests.cacheReportListsManagersCachesMetricsAndAnnotatedOperations`). Commit as
  `feat: report registered cache snapshots`.
- [ ] **Service Map (`GET /activity/service-map`):** project bounded nodes/edges from visible local sources, omit
  disabled source panels, and strip SQL literals and query strings (`# ported:
  AbstractBootUiApiConformanceTest.serviceMapIsBoundedAndCarriesOnlySafeIdentities`, `# ported:
  ServiceMapAssemblerTests.omitsEvidenceFromDisabledSourcePanels`). Commit as
  `feat: report a service map from local evidence`.

### Task 4b — close all 28 partial rows, 7 post-action scenarios, and `GET /traces/{id}`

All Task 4b work lives in `src/sharpit/engine/`, `tests/fixtures/bootui/2.3.0/*/nullable.json`, and `tests/parity/`, so
**none of Task 4b is blocked on #260**. Every row has **exactly one outcome**:

#### (a) Platform-nullable / deviation rows (7 rows — close via `nullable.json` + matrix row + unit test)

| Route | Gap in `routes_status.json` | Single closing outcome |
|---|---|---|
| `/email` | `unavailableReason` null | Add to `email/nullable.json`; test trap-on/off + masking. |
| `/fastapi-security/endpoints` | `endpoints[].description` null | Add to `nullable.json`; test docstring vs null. |
| `/github` | `unavailableReason` null | Add to `github/nullable.json`; test connected vs off. |
| `/http-exchanges` | `retention.reserved*`, `slow*` | Add FIFO nulls to `nullable.json` + matrix row. |
| `/java-agent` | `setup.jarPath`, `snippets` | Record W6 sensor floor deviation in `nullable.json`. |
| `/overview` | `contextPath`, `managementPort` | Add Spring-only fields to `nullable.json`; seed profiles. |
| `/vulnerabilities` (`post-scan`) | `unidentifiedArchives` empty | Record `.dist-info` deviation; test initial+scan. |

#### (b) Seeded conformance rows (16 rows + 6 `post-scan` scenarios + `GET /traces/{id}` — seeded parity test)

| Route (+ scenario) | Unseeded gap | Single closing outcome (`assert_parity` seeded) |
|---|---|---|
| `/activity/journal` | `oldestRetainedAt`, `recorded.*` | Seed journal sources; assert timestamp and keys. |
| `/architecture` (`post-scan`) | `basePackages` empty; `post-scan` | Seed scope, run `/architecture/scan`, test GET. |
| `/config` | `activeProfiles` empty | Seed active profile + secret; test masked search. |
| `/database-advisor` (`post-scan`) | Initial `n-a`; `post-scan` diff | Seed engine, run `/database-advisor/scan`. |
| `/database-connection-pools/pools` | `pools` empty | Register SQLAlchemy engine; assert `pools` shape. |
| `/exceptions` | `groups` empty | Seed exception with secret; assert `groups` shape. |
| `/fastapi` (`post-scan`) | Initial `n-a`; `post-scan` diff | Run `POST /fastapi/scan`; assert `post-scan` GET. |
| `/health` | `components` empty | Run `POST /health/check`; assert cached GET. |
| `/log-tail/recent` | `<root>` empty | Log secret assignment; assert list and masking. |
| `/postgresql` (`post-read`) | Initial `n-a`; `post-read` diff | Seed cached snapshot; assert GET touches no DB. |
| `/profile-diff` | `activeProfiles`, `profileSources` | Seed `.env` files; assert masked `profileSources`. |
| `/rest-api` (+ `post-scan`) | `basePackages` empty; `post-scan` | Seed scope, run `POST /rest-api/scan`, test GETs. |
| `/rest-api/error-contract` | `entries` empty | Seed declared errors; assert declaration-only GET. |
| `/runtime-insights` | `coverage`, `observations`, `window` | Seed journal events; assert lists and `window`. |
| `/scheduled` | `tasks` empty | Seed in-memory scheduler job; assert `tasks` row. |
| `/security` (`post-scan`) | Initial `n-a`; `post-scan` diff | Run `POST /security/scan`; assert `post-scan` GET. |
| `/sql-trace/insights` | `statements`, `window.*` | Record SQL statements; assert `statements` shape. |
| `/startup` | `steps` empty | Seed lifespan startup steps; assert `steps` shape. |
| `/traces` (+ `/traces/{id}`) | `traces` empty; `detail` scenario | Seed host trace with secret; test list + `{id}`. |
| `/transactions` | `entries` empty | Seed SQLAlchemy transaction; assert `entries` row. |

Ported conformance attributions for (a) and (b): `captureBuffersReportReconcilingRetention`,
`theJavaAgentPanelReportsNotAttachedWithSetupSnippetsWhenTheJvmRunsWithoutTheAgent`,
`overviewEndpointServesShellContract`, `vulnerabilitiesGetHasCanonicalShape`,
`runtimeJournalReportsOneShapeAndClearingItNeedsConfirmation`, `architectureScanLifecycleFromUnscannedToScanned`,
`databaseAdvisorPreservesPartialEvidenceAcrossScanAndCachedRead`,
`scoredAdvisorReportsExposeConservativeEvidenceWithoutTriggeringScans`,
`logTailMasksSecretAssignmentsInTheSnapshotAndTheStream`,
`PostgresInsightServiceTests.initialReportTouchesNeitherDiscoveryNorDatabase`,
`trackedAdvisorsCompareASecondScanWithTheFirstWithoutInventingChanges`,
`errorContractEndpointReturnsAStableDeclarationOnlyCatalogue`,
`runtimeInsightsProjectTheJournalIntoObservationsWithStableIdsAndEvidence`,
`sqlTraceInsightsAreBoundedAndDiscloseTheirCorrelationTiers`, `traceDataFollowsTheLiveValueExposurePolicy`.

#### (c) Real DTO or collector gaps (5 rows — fix in `src/sharpit/engine/` + test)

| Route | Engine defect in `src/sharpit/engine/` | Single closing outcome |
|---|---|---|
| `/activity` | `activity.py`: 0-count `typeCounts` & KPIs | Emit `LOG`/`SQL`/`TRANSACTION`, KPIs, `nullable.json`. |
| `/activity/resources` | `activity.py`: `families`, `points`, `totals` | Project local CPU/memory or record gap. |
| `/metrics` | `metrics/`: `catalogueVersion`, `baseUnits` | Populate catalogue metadata; nulls in `nullable.json`. |
| `/sql-trace` | `sqltrace.py`: `retention.reserved*` null | Reconcile `reserved*` (`0` or `nullable.json`) + SQL. |
| `/threads` | `threads.py`: `hiddenBootUiThreads`, `quality` | Emit both in `threads_report`; CPU in `nullable.json`. |

## Phases 5–8 — scope tables pending maintainer selection

Phases 5–8 require `/sharpit:predict` and `/sharpit:scenario` before writing task scripts. Each port registers its
`Panel` in `engine/panels.py` with BootUI's `action_capable` (`BootUiPanels.java:94–170`) and asserts disabled 403 and
read-only 403 first. Per `docs/reference/BOOTUI-PYTHON-MAPPING.md` and `0.9.0` PLAN Decision 5
(`docs/superpowers/plans/2026-11-22-sharpit-0.9.0/PLAN.md:330–333`), the recorded mapping (`P`, `A`, `X`) is the
default; departures (including marking `P` or `A` rows `n-a`) require a maintainer decision with options and cost.

| Phase & route | Source & panel gate | Deps | Options (A = mapping, * = rec) & cost |
|---|---|---|---|
| P5 `/runtime-insights/impact*` | `RuntimeInsights:196,202` (`True`) | `predict`, T2 | A*: journal (Med) / B: AST |
| P6 `/runtime-insights/comparison` | `RuntimeInsights:226` (`True`) | `predict` | A*: run ring (Low) / B: file (High) |
| P7 `/threads/captures*`, `/observations/*` | `ThreadDump:80–170` (`True`) | `predict` | A*: captures (Med) / B: all |
| P8 `/mappings` | `ActuatorMappings:32` (`False`) | `predict` | A: wrapper (Low) / B*: `n-a` (0) |
| P8 `/http-sessions` (`A:69`) | `HttpSessions:39` (add `True`) | `predict` | A*: local seam (Med) / B: `n-a` (0) |
| P8 `/fault-tolerance` (`A:62`) | `FaultTolerance:30` (add `False`) | `predict` | A*: `tenacity` (Med) / B: `n-a` (0) |
| P8 `/kafka`, `/rabbitmq` (`A:65`) | `Kafka:49`, `Rabbit:50` (`True`) | `predict` | A*: registry (Med) / B: `n-a` (0) |
| P8 `/jms` (`X:66`) | `JmsController:40` (omitted) | Phase 1 | A* (`X`): `n-a`, no Python JMS (0) |
| P8 `/websockets*` (`A:63`) | `WebSocket:59,75` (`True`) | `predict`, F0 | A*: ASGI+SSE (Med) / B: `n-a` (0) |
| P8 `/rest-client-trace*` (`A:55`) | `RestClientTrace:63,82` (`True`) | `predict` | A*: `httpx` (Med) / B: `n-a` (0) |
| P8 `/live-memory` (`P:17`) | `LiveMemory:39` (`True`, `:48`) | `predict` | A* (`P`): `gc`/RSS (Low) / B: `n-a` (0) |
| P8 `/memory`, `/rules/*` | `MemoryController:41` (`True`) | `predict` | A: Python rules (High) / B*: `n-a` (0) |
| P8 `/hibernate`, `/rules/*/violations` | `Hibernate:39` (`A:39`) | `predict` | A: ORM routes (Med) / B*: `n-a` (0) |

- **Engine sources & #260:** P5 uses `engine/insights/ChangeImpactService.java:182,1059` (A: journal route/SQL/table
  impact + masked symbols, ~250 LOC; B: static call graph). P6 uses `engine/insights/RunComparisonService.java:171` and
  `engine/journal/RunBaselineFile.java:59` (A: in-process reload ring, ~180 LOC; B: disk file after high-tier review).
  Route wiring for selected P5–P8 ports coordinates with that panel's #260 F2 extraction batch.
- **Phase 7 requirements:** flip `Panel("threads", ..., action_capable=True, "/threads")` in `engine/panels.py:45`
  (`BootUiPanels.java:107`). Initial slice bundles `GET /threads/captures`, `POST /threads/captures`,
  `POST /threads/captures/clear`, low-footprint `suspend`/`discard` (`CaptureHooks`), and `uninstall_capture` teardown
  (`close`), with single-flight 409 and read-only 403 refusal (`engine/threads/ThreadAnalysisService.java:104–765`,
  `ThreadDumpService.java:207`). Option A marks `/threads/captures/{id}/locks/{lockId}` `n-a` and defers
  `/threads/observations/{id}` (~300 LOC). Expiry either evicts on `readAccess()` (`:612–620`, Option E1) or filters
  passively on GET and purges on write/low-footprint/teardown (Option E2, recommended). Ported tests:
  `ThreadAnalysisServiceTests.passiveReadsNeverAcquireAndPagingKeepsTheOriginalCapture`,
  `ThreadDumpServiceTests.concurrentLiveReadFailsFastInsteadOfWaitingOrBecomingUnavailable`,
  `ThreadAnalysisServiceTests.offloadDuringAcquisitionPreventsLatePublication`,
  `ThreadAnalysisServiceTests.lowFootprintStopsExistingWorkButPermitsNewExplicitWorkBeforeResuming`,
  `ThreadAnalysisServiceTests.repeatedCapturesPlateauWithinCountAndByteBudgets`.
- **Phase 8 option details:** `/mappings` B marks raw Actuator `/mappings` `n-a` in favor of `/mappings/flat`.
  `/http-sessions` A ports a bounded local store seam with masked IDs and unavailable 200 for cookie-only apps (~160
  LOC). `/fault-tolerance` A observes `tenacity`/`pybreaker` (~200 LOC). `/kafka` and `/rabbitmq` A report registered
  clients with hashed keys and zero broker I/O on GET (~220 LOC each). `/websockets` (+ `/stream`) A observes ASGI
  websocket scopes (~250 LOC). `/rest-client-trace` (+ `/stream`) A records passive `httpx`/OTel spans with URL/header
  masking (~260 LOC). `/live-memory` A projects `gc.get_stats()`, `tracemalloc`, and RSS (~150 LOC). `/memory` and
  `/hibernate` B mark those routes `n-a` matching `0.7.0` Track C (`hibernate` is covered by `/database-advisor` and
  `/sqlalchemy-statistics`).

## Definition of done

- [ ] Inventory pins all 143 BootUI `v2.5.0` GET routes (100 mounted, 10 existing `n-a`, 33 above) and Phase 1 updates
  `routes_status.json`, `test_routes_parity.py` (`len(_ROUTES) == 97`), `test_parity_matrix.py`, `ROADMAP.md`, and
  `README.md`.
- [ ] Every new route registers its `Panel` entry with BootUI's `action_capable` first and passes disabled 403,
  read-only 403, and `no_side_effects`.
- [ ] Request journal and baselines use targeted reads with bounded masking, return retained FIFO-partially-evicted
  anchors with the eviction note, refuse incomplete baselines, enforce `METADATA_ONLY`/`MASKED`/`FULL` masking, and
  sanitize/mask/truncate echoed `requestId` and `compareWith`.
- [ ] `GET /cache` and `GET /activity/service-map` pass parity and safety checks, and all 28 partial rows + 7
  post-action scenarios + `GET /traces/{id}` close in Task 4b without waiting on #260 for `engine/` work.
- [ ] Plan verification: `uv run --extra test pytest -q -n 4 tests/docs tests/test_agent_workflow.py`.
