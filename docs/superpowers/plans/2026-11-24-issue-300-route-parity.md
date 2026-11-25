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
| 29 | `/dev-services/{id}/logs` | `web/DevServicesController:45` | — | `n-a` (Quarkus Dev Services, extends R0) |
| 30 | `/heap-dump/download` | `web/HeapDumpController:57` | — | Maintainer decision (Phase 1) |
| 31 | `/crac/dockerfile` | `crac/CracController:94` | — | `n-a` (JVM CRaC, `X`) |
| 32 | `/crac/entrypoint` | `crac/CracController:103` | — | `n-a` (JVM CRaC, `X`) |
| 33 | `/graalvm/dockerfile` | `graalvm/GraalVmController:124` | — | `n-a` (GraalVM, `X`) |

## Phase 1 — smallest contract inventory correction (Task 1)

**Release scope.** sharpit 0.10.0 covers Phases 1–4.

**Files** include `tests/parity/routes_status.json`, `tests/parity/test_routes_parity.py`, `tests/docs/test_parity_matrix.py`,
`README.md`, `ROADMAP.md`, and the parity matrix fragment and generated matrix. Keep 97 classified rows.
Add optional `scenario` and share one scenario dispatcher between the matched, partial, and missing GET tests.
It prepares only the selected fixture, checks action responses, resolves trace IDs to actual paths, and returns the
GET response. Keep a separate unseeded 404 assertion for an unknown trace ID. For partial rows with a failing
comparison, assert the exact `AssertionError` text, including when the message has no ` parity: ` prefix.
The two passing post-action rows use the separate Phase 4b deviation assertion. That test runs each scenario,
checks both HTTP 200 responses, verifies parity, and asserts the exact empty-list paths in the golden.

| Golden | Canonical GET | Scenario setup | Status | Exact difference |
|---|---|---|---|---|
| `architecture/scanned.captured.json` | `/architecture` | `post-scan`: Writable panel, POST /architecture/scan without configured scope | `partial` | `architecture/scanned.captured.json parity: basePackages: non-empty golden list requires a non-empty payload list` |
| `database-advisor/scanned.captured.json` | `/database-advisor` | `post-scan`: Writable panel, POST /database-advisor/scan without an engine | `partial` | Comparison passes. Pin these empty golden paths. `dataSourceNames`, `dataSources`, `diagnostics`, `results`, `suppression.findings`, `suppression.incompleteRules`, `violationDetails.locationNotes`. |
| `fastapi/scanned.captured.json` | `/fastapi` | `post-scan`: Writable panel, POST /fastapi/scan on the sample app | `partial` | `fastapi/scanned: golden list inspected has no shape information; cannot satisfy 2.3.0 or later 'matched' parity (spec §4.4)` |
| `postgresql/scanned.captured.json` | `/postgresql` | `post-read`: Writable panel, POST /postgresql/read without database configuration | `partial` | Comparison passes. Pin these empty golden paths. `databases`, `diagnostics`, `limitations`. |
| `rest-api/scanned.captured.json` | `/rest-api` | `post-scan`: Writable panel, POST /rest-api/scan on the sample app | `partial` | `rest-api/scanned.captured.json parity: evidence.limitations: non-empty golden list requires a non-empty payload list` |
| `security/scanned.captured.json` | `/security` | `post-scan`: Writable panel, POST /security/scan and GET /security on the sample app | `partial` | `security/scanned: golden list filterChains has no shape information; cannot satisfy 2.3.0 or later 'matched' parity (spec §4.4)` |
| `vulnerabilities/scanned.captured.json` | `/vulnerabilities` | `post-scan`: Writable panel, POST /vulnerabilities/scan with empty successful OSV replies and EPSS disabled | `partial` | `vulnerabilities/scanned.captured.json parity: coverage.unidentifiedArchives: non-empty golden list requires a non-empty payload list; evidence.limitations: non-empty golden list requires a non-empty payload list` |
| `traces/detail.captured.json` | `/traces/{id}` | `seeded-trace`: Add a finished local OTel span with no attributes to the span buffer and substitute its trace ID | `partial` | `traces/detail.captured.json parity: spans[].attributes: non-empty golden list requires a non-empty payload list` |

The trace-detail difference comes from the attribute-free seed. With a boolean and a string attribute on the
seeded span, the same strict comparison passes. Keep the attribute-free scenario and its exact difference
and assert attribute rendering with the populated seed.

The unscanned database-advisor, FastAPI, PostgreSQL and security comparisons also pass and retain their existing
`n-a` fixture classification. The memory scenario maps to `/memory` and remains `missing` (GET returns 404).
Canonicalize `/runtime-insights/impact-symbols` to `/runtime-insights/impact/symbols`. Use a route inventory check
that rejects the synthetic suffixes and a scenario fixture test that demonstrates that a literal `{id}` returns 404.
Phase 1 changes fixture counts from 5 matched / 28 partial / 23 missing / 41 n-a to 5 / 36 / 15 / 41
(41 served of 56 applicable). Freeze the published sharpit 0.9.0 column at its current values. It records 73 MCP/CLI
tools, 64 exact BootUI names, 49 panels (47 listed), 11 of 29 insight kinds evaluating, and 33 served routes
(5 shape-identical, 28 partial). Add a sharpit 0.10.0 column to `README.md` and `ROADMAP.md`. Update
`tests/docs/test_parity_matrix.py::_matrix` to assert the historical cells and compute only the new sharpit
column from current code and fixtures. Keep released values fixed in subsequent phases. `ROUTES_MATCHED_PIN`
stays at 5 and the BootUI marks stay as recorded.

**Heap download.** The Python mapping remains `P` and `/heap-dump/download` is deferred until a Python snapshot
format and guarded download design are available. The R0 JVM-only entry covers `GET /heap-dump`. Record inventory
entries #19, #29 and #31–#33 as `n-a` where their platform classification applies. Verify parity and docs.

## Phase 2 — request journal, R1 (Task 2: `GET /activity/request/{id}/journal`)

**Sources and files:** BootUI `activity/LiveActivityController.java:560–586`,
`engine/journal/RequestJournalProfiles.java:47–330,700–1010`, `core/dto/RequestJournalProfileDto.java:37–85`. Sharpit
`engine/panels.py:37`, `engine/capture/journal.py`, new `engine/capture/request_journal.py`, `fastapi/routes/activity.py`,
`tests/fastapi/test_activity_api.py`. Verify `Panel("activity", "Live Activity", False, "/activity")` returns 403
`PANEL_ACCESS_DENIED` when disabled. Add a targeted selector on `RuntimeJournal` (`engine/capture/journal.py`) that
matches `requestId` (or `executionId`), its children, same-route HTTP events (`MINIMUM_ROUTE_REQUESTS = 5`), and
trace-linked AI events under `self._clearing` then `self._lock`, following `view()`. Release the locks before masking
the selected subset with `_masked`. A retained HTTP anchor returns 200 with `available: true` when earlier children
were lost. Emit the eviction note when `evictedEvents > 0` and `oldestRetainedAt > startedAt`, or when the loss
horizon establishes partial loss. Record the loss-horizon trigger as a matrix deviation. BootUI's note uses only
the oldest-retained timestamp and eviction counters (`RequestJournalProfiles.java:275–281`). Test a retained
anchor with zero evictions and an advanced horizon from a dropped oversized child.
Any echoed caller `requestId` in `requestId` or `unavailableReason` (`:70–73,188–189`) strips control characters,
runs `ctx.masker.mask_text`, and truncates to 64 chars with `"…"` (`safeRequestId`, `:711–717`). Under
`METADATA_ONLY`, `requestId` is withheld or masked.
- [ ] **Red & Green:** reds for disabled-panel 403, unknown/retained/partially-evicted 200 shape (`# ported:
  AbstractBootUiApiConformanceTest.requestJournalProfileKeepsOneShapeForAnUnknownAndARecordedRequest`), disabled child
  panels (`# ported: RequestJournalProfilesTests.disabledChildPanelsHideTheirEvidenceFromAVisibleWebSocketExecution`),
  a zero-eviction case with `oldestRetainedAt > startedAt` and no loss horizon that emits no eviction note,
  and `METADATA_ONLY`/`MASKED`/`FULL` exposure + echoed-`requestId` sanitization. Compare the targeted response
  byte for byte with the same projection over a fully masked `RuntimeJournal.view()`, across all three exposures,
  planted secrets, and disabled sources. Include the unknown-ID response and eviction note cases in the corpus.
  Emit `baselineComparison: null` until Task 3. Record sharpit's `safeRequestId` sanitization as a matrix deviation from the
  raw upstream `requestId`. Move the `missing` journal row to `partial` with a probe and a pinned contract fixture. Adding the absent 2.3.0 fixture
  increases the on-disk fixture count from 96 to 97 and leaves the classified row count at 97. Verify with
  `no_side_effects` and commit as `feat: expose retained request journal profiles`.

## Phase 3 — same-route baselines, R2 (Task 3: `baselineComparison`)

**Pre-implementation gate:** run `/sharpit:predict` and `/sharpit:scenario` before Task 3.
**Sources and files:** BootUI `LiveActivityController.java:560–574`,
`engine/journal/RequestJournalProfiles.java:411–724`, `core/dto/RequestBaselineDiffDto.java:42`,
`RequestBaselineCandidateDto.java:11`. Engine logic in `engine/capture/request_journal.py` (no #260 block). Under
`RuntimeJournal`'s single FIFO ring (`reservedEvents: 0`, `engine/capture/journal.py:464`), child events offered during
a request evict before the completion-time HTTP anchor. Refuse that anchor as a baseline or target when
`startedAt <= lossHorizon`, or when `evictedEvents > 0` and `startedAt < oldestRetainedAt`. This adapts BootUI's
reserved-failure survival case (`RequestJournalProfiles.java:431–436,511–514,701–705`). Exclude the cold first
request only when the retained history proves it is present. The journal exposes no clear counter.
Use the loss horizon for recorded loss and treat cold-request identity across clears or evictions as unverified.
Record that limitation as a deviation. Sanitize, mask
(`mask_text`), and cap echoed `compareWith` at 64 chars (`safeRequestId`, `:500,711–717`). Cap candidates at 20 and
`distinguishingSqlShapes` at 5.
- [ ] **Red & Green:** reds for explicit `compareWith` + echoed-ID sanitization, auto-baseline excluding cold first
  request (`# ported: RequestJournalProfilesTests`
  `.comparesASlowOrFailedRequestWithTheClosestWarmRetained2xxBaselineAndExcludesTheColdFirstRequest`), FIFO anchor
  outliving children + disabled/unverified SQL null deltas + per-exposure (`METADATA_ONLY`/`MASKED`/`FULL`) SQL shapes
  (`# ported: RequestJournalProfilesTests.partiallyEvictedRequestsAreNeverUsedAsBaselinesOrComparedAsCompleteTargets`,
  `# ported: RequestJournalProfilesTests.preparationOnlySqlAndDisabledPanelsKeepBaselineDimensionsNull`). For same-route reads, project allow-listed
  numeric fields after existing masking and visibility checks. A direct numeric projection requires a byte-identical
  gate-corpus comparison against the fully masked projection across all exposures, planted secrets and disabled
  sources. Run paired overhead checks and commit as `feat: compare retained requests with same-route baselines`.

## Phase 4 — `GET /cache`, `GET /activity/service-map`, and R3 partial closure

### Task 4a — `GET /cache` and `GET /activity/service-map`

**Sources and files** include BootUI `web/SpringCacheController.java:37`, `engine/cache/CacheService.java:81–195,249–350`
and `activity/LiveServiceMapController.java:62`. Sharpit changes cover `engine/panels.py`, `engine/panels04/cache.py`,
`engine/collectors/cache/clear.py`, new `engine/servicemap/*`, and the cache and activity routes and tests.

- [ ] **Cache.** Flip `engine/panels04/cache.py` to `IMPLEMENTED = True` to engage the panel gate, with disabled-panel
  403 and read-only GET 200 reds. Update the `cache: False` pin in `tests/engine/test_panels.py:212`. Verify read-only
  `POST /cache/clear` returns 403 after the flip. Refresh the 0.10.0 panel counts in `README.md` and `ROADMAP.md`
  from the registered and listed panel checks. With no provider, return 200 with `cacheAvailable: false`, zero counts
  and empty lists. Port the `CacheReport` bounds from `CacheService.java:46–55` (`MAX_MANAGERS = 100`,
  `MAX_CACHES_PER_MANAGER = 500`, `MAX_TIERS_PER_CACHE = 20`) and assert the truncation flag and masked warnings.
  With an internal test provider, mask names and use the native `cache_info()` only on exact local functools cache
  wrappers. List cachetools caches using registration metadata alone. Keep `len()`, iteration, `currsize`, `repr()`,
  and all other native-object access out of their GET path. `register` accepts supported objects tagged `is_remote`.
  Add a red for a supported remote cache that fails on any stats access. GET lists its registration metadata.
  Add a red using a fake clock and an expired `TTLCache` entry, with cachetools installed only for tests. Assert the
  entry is still physically retained after GET using an inspection that does not expire it. Reading `currsize` or `len()` can evict it, and `no_side_effects`
  does not detect that in-memory mutation. Use the fixture for GETs as well. Update `test_get_never_clears` in
  `tests/fastapi/test_cache_clear_route.py` to expect 200 on `GET /cache`, retain the non-200 check on
  `GET /cache/clear`, and preserve the cache-size assertion for both.
- [ ] **Service map.** Project bounded nodes and edges from visible local sources. Cap dependency nodes and their
  edges at 28 each (`ServiceMapLimits.java:18`, `ServiceMapAssembler.java:147–165`). The optional inbound node
  and its edge allow 29 entries in each array, with the application node carried separately (`:167–191`). Cap
  each edge's recent interactions at 6 (`ServiceMapLimits.java:24`). Omit disabled sources and strip SQL literals
  and query strings. Port `serviceMapIsBoundedAndCarriesOnlySafeIdentities` and `omitsEvidenceFromDisabledSourcePanels`.
- [ ] **Inventory.** Both GETs currently return 404. Move their `missing` rows to `partial` on mounting and record
  verified gaps, including the empty-list golden constraints. Update the status counts and served matrix with Phase 2.

**Cache registration.** The provider remains internal in 0.10.0. The default install serves the unavailable report.
Provider-present scenarios use the internal test seam.

### Task 4b — disposition of the 28 partial rows and Phase 1 scenarios

The table covers the 28 existing partial rows. The probe compares the real sample app against the 2.3.0 fixtures
with `matched=True`. The residual column lists what remains after temporarily allowing the reported nulls in
memory. `nullable.json` is valid only for real platform-nullable fields (see `tests/golden.py:_compare`). Missing
keys, non-empty-list requirements and shapeless golden lists get explicit matrix deviations. The seeded checks
below are implementation acceptance tests. The probe uses an unseeded app except where stated.

| Golden | Residual probe result | Default status and closing evidence |
|---|---|---|
| `activity/captured.json` | `entries`, `typeCounts.LOG`, `typeCounts.SQL`, `typeCounts.TRANSACTION` | `partial` — Record SQL with a registered local engine and verify a sanitized `SQL` entry and count. Record `LOG` and `TRANSACTION` as unproduced by `/activity` and assert both counts are absent (`engine/capture/activity.py:190,215,239`). |
| `activity/journal.captured.json` | `recorded.connection`, `recorded.gc`, `recorded.lifecycle`, `recorded.log`, `recorded.sql`, `recorded.transaction` | `partial` — Seed connection, log and SQL. Record gc, lifecycle and transaction as unproduced by PRODUCED_SOURCES. |
| `activity/resources.captured.json` | `families`, `points` | `partial` — Record families and points as unavailable without a local resource sampler. |
| `architecture/captured.json` | `basePackages` | `partial` — Configure scan scope and assert basePackages. |
| `config/captured.json` | `activeProfiles` | `partial` — Seed a profile and verify masked search. |
| `database-connection-pools/pools.captured.json` | `pools` | `partial` — Register a local engine and assert pool shape. |
| `email/captured.json` | PASS | `partial` — Cover trap state and masking. Record shapeless messages. |
| `exceptions/captured.json` | `groups` | `partial` — Seed a masked exception and assert group shape. |
| `fastapi-security/endpoints.captured.json` | PASS | `partial` — Cover declared descriptions and the null case. Record shapeless roles. |
| `github/captured.json` | PASS | `partial` — Cover connected and disconnected reasons. Record shapeless lists. |
| `health/captured.json` | `components` | `partial` — Register a local check before the action. Seeded comparison passes, but the golden contains empty lists. |
| `http-exchanges/captured.json` | PASS | `partial` — Verify FIFO retention semantics. Record the shapeless exchanges golden. |
| `java-agent/captured.json` | `setup.snippets` | `partial` — Assert Python's `setup.jarPath: null` and empty `setup.snippets` as JVM setup deviations. Keep `setup.jarPath` out of `nullable.json` because BootUI always returns a path or placeholder (`JavaAgentSetupDto.java:8–15` and `AgentSetupSnippets.java:51–57`). |
| `log-tail/recent.captured.json` | `<root>` | `partial` — Record and mask a log event before GET. |
| `metrics/captured.json` | `groups[].baseUnits` | `partial` — Record baseUnits list gap and assert local catalogue metadata. |
| `overview/captured.json` | `activeProfiles`, `defaultProfiles` | `partial` — Seed profiles and record Spring-only fields and remaining list shape gaps. |
| `profile-diff/captured.json` | `activeProfiles`, `profileSources` | `partial` — Seed profiles and a local env file, then assert masked sources. |
| `rest-api/captured.json` | `basePackages` | `partial` — Assert `basePackages: []` before scanning and record the unscanned value as a deviation. After `POST /rest-api/scan` returns 200, assert `basePackages: ["examples"]` for the sample app (`engine/collectors/restapi/service.py::_scope`). |
| `rest-api/error-contract.captured.json` | `entries` | `partial` — Seed declared errors and verify declaration-only GET. |
| `runtime-insights/captured.json` | `coverage`, `limitations`, `notExercised`, `observations` | `partial` — Seed journal events and record missing lists and window semantics. |
| `scheduled/captured.json` | `tasks` | `partial` — Register an in-memory job and verify task shape. |
| `sql-trace/captured.json` | `entries`, `topStatements` | `partial` — Emit zero for `retention.reserved` and `retention.reservedCapacity` on sharpit's own FIFO recorder. BootUI reserves null for application-managed recorders and uses zero for a disabled reservation (`CaptureRetentionDto.java:15–25`). Keep both paths out of `nullable.json` for this fixture, seed SQL, and record remaining list gaps. |
| `sql-trace/insights.captured.json` | `statements` | `partial` — Allow `window.oldestTimestamp` and `window.newestTimestamp` in `nullable.json` for an empty window (`SqlTraceWindowDto.java:15–16,29–30`). Seed SQL and verify statements and populated timestamps. |
| `startup/captured.json` | `steps` | `partial` — Seed lifespan startup steps and verify their shape. |
| `threads/captured.json` | `hiddenBootUiThreads`, `quality` | `partial` — Record both missing fields as deviations. Allow `threads[].cpuTimeMillis` and `threads[].userTimeMillis` separately in `nullable.json` when the platform lacks per-thread CPU or user timing (`ThreadInfoDto.java:8–10,19–20`). |
| `traces/captured.json` | `traces` | `partial` — Record a local span and verify trace list, ID lookup and masking. |
| `transactions/captured.json` | `entries` | `partial` — Record a local SQLAlchemy transaction and verify entries. |
| `vulnerabilities/captured.json` | `coverage.unidentifiedArchives` | `partial` — Record unidentifiedArchives as a platform list deviation for Python distributions. |

Keep an exact failing comparison for each residual gap that still raises. If the probe passes after approved nulls
or seeding, use a separately identified deviation assertion that checks the successful comparison and the exact
empty-list paths in the golden. Keep the matched test and its empty-list prohibition intact. A structural gap
that disappears under seeding gets an explicit seeded assertion plus a documented limitation of the unseeded evidence.
Reprobe each changed scenario before recording the final difference. Phase 1 supplies the exact post-action and
trace-detail evidence. Retain all eight partial classifications, including the two passing post-action comparisons,
the REST evidence limitation and the shapeless FastAPI and security lists. An empty reply from the advisory service
leaves both `coverage.unidentifiedArchives` and `evidence.limitations` as gaps after scan. Use an offline advisory stub.

**Served classification.** Served rows remain applicable. The 28 existing partial rows and the eight Phase 1
scenarios stay `partial`, including passing comparisons with shapeless goldens. The matched pin and BootUI
marks stay at their Phase 1 values. With the three new served rows in Phases 2 and 4a, the projected 0.10.0
fixture counts are 5 matched / 39 partial / 12 missing / 41 n-a, or 44 served of 56 applicable.

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
- [ ] `GET /cache` and `GET /activity/service-map` pass parity and safety checks, and all 28 partial rows and eight served scenarios
  have verified dispositions in Task 4b without waiting on #260 for `engine/` work.
- [ ] Plan verification: `uv run --extra test pytest -q -n 2 tests/docs tests/test_agent_workflow.py tests/parity`.
