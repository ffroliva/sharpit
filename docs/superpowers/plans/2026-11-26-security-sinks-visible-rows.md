# Security Sinks: Visible Rows Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Run `/sharpit:check` before every commit.

**Goal:** Show the `processes`, `files` and `security-sinks` sensors' rows in the Side Effects panel, over REST, MCP and the CLI, with BootUI's confirmation by a second request, its wording and its limitation lines, and never a request value or a hash.

**Architecture:** The lane wraps its journal sink in a tee: each row the journal accepts from one of the three sensors is also appended to that sensor's bounded ring, on the audit-hook thread, without a lock of its own; a full ring drops its oldest row and counts it. A framework-free store under `engine/collectors/sideeffects/` drains the rings on each read, masks each row's target and parameter name as it takes the row (BootUI masks at intake, SV:2633), keys and confirms rows as BootUI's `SideEffectsStore` does, waits for each request's route and names it from the journal's `http` events, and drops a row whose time is not after the last clear (SV:2248). The store is not thread-safe, as BootUI's is not (ST:39-40); a service in the same package serialises every store call under one lock, as BootUI's service does (`synchronized (lock)`, SV:1731), and builds BootUI's report, sensor and agent DTOs. Agent query matching reads the built row DTOs (SV:1137-1138). FastAPI only wires the routes; the Svelte view reads them. The journal's own rows and reads stay as they are.

**Predict verdict:** CAUTION 6/10. Its required mitigations are folded into the tasks: no reader takes sink rows from the journal; exposure-independent masking of targets and names; a hash and seeded-value canary over every output; the file call site measured before it is coded; modules split under 1000 lines.

**Tech Stack:** Python 3.12+ standard library, pytest, Svelte 5 with vitest (`ui/package.json`: `npm test` runs `vitest run`, `npm run check` runs `tsc --noEmit`, `npm run build` runs `vite build`). No new dependency.

**Spec:** BootUI at tag `v2.5.0` (`80a4ee22`), read as source with `git -C <bootui clone> show v2.5.0:<path>`. Short names used below:

| Short | Path |
|---|---|
| ST | `bootui-engine/src/main/java/io/github/jdubois/bootui/engine/sideeffects/SideEffectsStore.java` |
| SV | `bootui-engine/src/main/java/io/github/jdubois/bootui/engine/sideeffects/SideEffectsService.java` |
| SW | `bootui-engine/src/main/java/io/github/jdubois/bootui/engine/sideeffects/SinkWording.java` |
| SO | `bootui-engine/src/main/java/io/github/jdubois/bootui/engine/sideeffects/SideEffectOrigins.java` |
| SC | `bootui-engine/src/main/java/io/github/jdubois/bootui/engine/sideeffects/SideEffectsCatalog.java` |
| JRR | `bootui-engine/src/main/java/io/github/jdubois/bootui/engine/inventory/JournalRequestRoutes.java` |
| RV | `bootui-agent-bridge/src/main/java/io/github/jdubois/bootui/agent/bridge/RequestValues.java` |
| DTO | `bootui-engine/src/main/java/io/github/jdubois/bootui/core/dto/` |
| TST | `bootui-engine/src/test/java/io/github/jdubois/bootui/engine/sideeffects/` |
| VUE | `bootui-ui/src/main/frontend/src/views/SideEffects.vue` and `SideEffects.test.js` |

## Scope

This is the second of the four security-sinks plans; plan 1 is `2026-11-25-security-sinks-commands-files.md`. Plans 1 and 2 ship together in 0.10.0. The SQL sink (plan 3) and the outbound URL sink (plan 4) are not in 0.10.0; the release notes say that SQL and outbound URL sinks are not covered (Task 14).

In scope: the D8 row fields and holder counters plan 1 deferred, the rings and the store, BootUI's wording, confirmation, owner resolution and limitation lines for the command and file sinks, the `processes` and `files` tabs through the same store (without confirmation), `GET {api}/side-effects[/sensor]`, the `get_side_effects` MCP tool and `sharpit side-effects` CLI command, the Side Effects view, and the release documentation.

Out of scope: every other BootUI side-effects sensor (`network`, `environment`, `thread-activity`, `thread-locals`, `resources`, `blocking`), which stay listed as not available in this version (SVT `SideEffectsServiceTests.java:185-220`); the JDK checks of `security-sinks` (`SecuritySinks.java`); SQL and URL wording branches (SW:33-44, :55-57); code-inventory comparisons and buckets. There is no `request-input-in-sink` insight evaluator to port: BootUI lists it as not judged, its rows shown in their own panel (`insights/ExternalValidation.java:123-132`), and sharpit already mirrors that (`engine/collectors/insights/listing.py:37,60-63`).

## Gates before Task 1

- [x] `/sharpit:predict`: CAUTION 6/10. Its answers (a) to (f) are the decisions below.
- [x] Deviation N1 recorded as approved and N2 as a measured conditional stop; F1 to F11 recorded as adaptations.
- [x] `/sharpit:scenario` on this plan: `2026-11-26-security-sinks-visible-rows-scenario.md`. Its Critical and High tests are named in Tasks 5, 7, 8, 9, 10, 11, 12 and 13.
- [ ] Plan 1 Tasks 4 to 6 merged (command and file sinks, the setting, the lane wiring, the matrix file).
- [ ] Each item under *Open deviations* below decided and recorded as a deviation row. An item left undecided is not coded; the task step that depends on it stops.
- [x] `/sharpit:llm-council --tier high` on this plan: no finding contradicts a deviation row; its findings are folded into the tasks below, and those not folded are listed with their reason under *Review notes*.

### Decisions

- **(a) Data path.** A bounded ring per sensor (`collections.deque(maxlen=RING_CAPACITY)`: a full ring keeps the newest rows and counts each dropped one), fed by a tee once the journal accepts the row, drained into a separate store on each read; the store keeps BootUI's caps (500 rows per sensor, 2000 in all, ST:44-45), its Other row and `unconfirmedPastCap` (ST:1181-1188). Ring rows are read-only: the journal keeps the same dict without a copy (`journal.py:112-116`, `:277`), so the store copies before it changes anything. Journal eviction no longer decides what a row shows. No reader takes sink rows from the journal, whose masking would blank the hashes under `METADATA_ONLY` and mask a file target whole.
- **(a2) Serialisation.** The store is not thread-safe (ST:39-40: "Not thread-safe: its service serializes it"). The service holds one `threading.Lock` around every store call: drain, resolve, aggregate, read and the clear check (BootUI: `synchronized (lock)` around each store call, SV:1131-1132, :1731, :2060). REST handlers are sync and run in Starlette's threadpool, MCP and CLI calls run concurrently, and the idle tracker runs on its own thread, so two reads can overlap. The lock is never taken on the audit-hook thread.
- **(a3) Clear.** Ported timestamp rule: a clear records its epoch ms; a drained row whose `at` is not after it is dropped and counted (SV:2248 `record.firstMillis() <= clearedAt`), and waiting observations are dropped the same way (SV:2375). No generation counter. In sharpit the only callers of `SensorHook.discard` are the idle tracker (`fastapi/install.py:75-79`) and low-footprint suspend (`engine/lowfootprint.py:27-33`); whether they clear the store is Open deviation O6.
- **(b) Processes and files tabs.** Shown through the same store, without confirmation; their rows gain `requestId`, `at` and `callSite`.
- **(c) Owner.** Ported: an observation with a request id waits for its route (`Pending`, `PENDING_MILLIS = 30_000`, `MAX_PENDING = 10_000`, ST:46-47); past 30 s it counts under `UNKNOWN_ROUTE = "(unknown route)"` (ST:51, :1112-1113); with HTTP Exchanges disabled route rows merge under `ROUTE_HIDDEN` without request ids (ST:52, :1323-1345). The route reader is a port of JRR:35-69 over sharpit's `http` events, which carry `requestId` and `route` as `"GET /api/x"` (`engine/capture/exchanges.py:158,164`). An observation without a request id takes BootUI's unowned branch (ST:1028-1036): `startup` before `readyAt`, else its thread's family, else `(unattributed)`. Each read asks the journal for every waiting id before it applies the 30 s rule, so a row is named whenever its `http` event is still held; the effect of draining on read is recorded in F6.
- **(d) Call site.** `module:qualname`, without a line, so rows group per function as BootUI's `Class#method` does (the row key includes the call site, ST:1160-1178). One walk per event: a sink row takes it in plan 1's ownership walk, only for a row that is published; process rows use `first_application_frame`; a file row reads it once per file pattern, as BootUI does (`LIMITATION_FILES`, SV:207-213: "A call site's frames are read once per run and file pattern, so two call sites of one pattern share the first one's").
- **(e) Masking.** At intake, as BootUI masks the target when it builds the observation (`shown = SideEffectOrigins.maskPath(normalizer.target(target))`, SV:2633): a file target is masked per segment at every exposure (SO:128-141), the parameter name through N1, and the row key holds the masked values. sharpit's token and identity key are never shown (`masking.py:557-563`). Agent query matching reads the built row DTOs (SV:1137-1138 `matches(row, needle)`), never a store field. The `rawHash` and `redactedHash` never leave the store: no DTO key carries them (DTO `SideEffectsRowDto.java:74-100`), and a canary test greps every output for them.

### Deviations from BootUI

| # | BootUI | sharpit | Reason | Test (task) |
|---|---|---|---|---|
| N1 | A parameter name is any 1-64 characters of `[A-Za-z0-9_.\-\[\]]` (RV:546, :565) and is shown as is in `parameter` (SV:2648-2658) and inside `detail` (SW:31) | A name that `is_secret_value` flags is shown as `******` in `parameter`, and `detail` is built from the masked name (`` `******` ``), at every exposure. The name is masked at intake, so two secret-looking names on one target are one row | AGENTS.md safety rule 3 (secrets masked before any output) takes precedence over BootUI. `?AKIAIOSFODNN7EXAMPLE=1234` is a valid name. One row for two masked names is accepted: two rows that both read `******` would tell an agent nothing more | `test_a_secret_looking_parameter_name_is_masked_in_parameter_and_detail_at_every_exposure`, `test_rows_are_keyed_on_masked_values` (9) |
| N2 (measured conditional stop only) | A file row carries the first application frame (SV:2589, :2304-2315), read once per run and file pattern (SV:207-213) | sharpit ports the per-pattern read (Task 3). `callSite` would be `null` on `files` rows **only if** Task 3's worst-case measurement still breaks the 6 µs files-sensor budget | Budgets are never raised (AGENTS.md architecture rule 5). If the measurement fails, implementation stops before any null is coded and the outcome needs a recorded decision | `test_the_sensors_overhead_budgets_by_event_count` (3) |

Ported behaviour that an earlier revision listed as open:

| # | BootUI | sharpit | Test (task) |
|---|---|---|---|
| O1 (ported) | A process row is built with the seven-argument `Observation`, so its `origin` is `null` (SV:2272-2280, ST:281-289; `SideEffectsRowDto.java:81`: origin "for files and environment ... null otherwise"). A file row's origin is `SideEffectOrigins.origin` (SO:79-100): no frame outside the runtime gives `application` when an application frame exists, else `unknown`; a frame outside the runtime gives `application` when an application frame exists, else `library` | Process and security-sinks rows: `origin` `null`. File rows: the per-pattern walk (Task 3) finds the first frame outside the standard library and sharpit (`outside`) and the first application frame, and applies SO:92-100 | `test_a_process_row_has_no_origin`, `test_a_file_rows_origin_follows_its_frames` (3) |
| O2 (ported) | A process or file row carries `normalizer.threadFamily(threadName)` (SV:2280 processes, :2317 files); the family keeps safe characters, turns each digit run into `{n}` and removes secret-looking parts (`agent/bridge/SideEffects.java:1266-1291`); an unowned row after readiness counts under its family (`scope: "thread"`, ST:1033-1034) | A row without a request id records `threading.current_thread().name` on the hook thread; the store turns it into the family at drain with a port of `threadFamily`. Read inside the measured budget (Task 3); if that budget fails, implementation stops for a recorded decision | `test_a_row_without_a_request_id_carries_its_thread_name` (3), `test_an_unowned_row_after_readiness_counts_under_its_thread_family` (8) |

Adaptations forced by Python or by the approved scope (one matrix line each, no further approval):

| # | BootUI | sharpit | Reason |
|---|---|---|---|
| F1 | `LIMITATION_SECURITY_SINKS` (SV:240-251), the coverage reason (`javaagent/JavaAgentService.java:289-336`) and the `get_side_effects` description (`mcp/McpToolDescriptions.java:423`) name SQL, URLs, R2DBC, managed executors and `bootui.agent.security-sinks.request-values` | They name the command and file sinks only, restate the hand-off clause per plan 1's D1, and name `SHARPIT_AGENT_SECURITY_SINKS_REQUEST_VALUES` (texts in Task 10) | SQL and URL are out of 0.10.0; the env-name rule |
| F2 | The unconfirmed line names "a value outside an SQL literal" (SV:1750) | That clause is dropped | No SQL sink |
| F3 | `callSite` is `Class#method` | `module:qualname` | Python has no classes for every function; `co_qualname` is the nearest name |
| F4 | `holderLine` counts requests that held values (SV:1772-1790); `dropped` is the agent's ring full; `RequestValues.status()` has 25 keys (RV:1397-1429) | "requests held values" counts requests that reached a sink check (values are read at the first check, plan 1 D4); `dropped` is the sensor's ring full; `status()` keeps only the keys an output reads: `requests, checks, valuesTooLong, valuesOverCount, tableFull, stopped, partial, busy, notKept, dropped` (`notKept` stays 0: sharpit keeps no intern table) | No output surface reads the other keys; plan 1's D8 row is updated to say so |
| F5 | A process row carries exit status and lifetime | `failed, completed, nonZeroExits, totalMillis, maxMillis, leftRunning` are 0 and `lastExitStatus` is `null` | The audit hook has no process-exit event |
| F6 | A drain thread moves the agent ring into the store and resolves routes every `RESOLVE_MILLIS` (SV:2190-2225) | The store drains and resolves on read; each ring holds the newest `RING_CAPACITY = 10_000` rows (the store's `MAX_PENDING`, ST:46), a full ring drops its oldest row and counts it as `dropped` for its sensor, as BootUI counts drops per sensor (`agent/bridge/SideEffects.java:53`). Effect: a row's wait is measured from its event time (ST:967), so on the first read after a quiet period a row older than 30 s is named if its `http` event is still held and counts under `(unknown route)` if that event was evicted | The journal already records the no-drain-thread adaptation (`engine/capture/journal.py:3-7`); no thread is started in the host |
| F7 | A row's attribution is the route as named (SV:770-784 masks only a pending owner of run evidence) | The attribution is masked per segment at output | Stricter than BootUI; an untemplated route is a request path |
| F8 (was O3) | An unowned row counts under `startup` when its first occurrence precedes `readyAt`, set by `ApplicationReadyEvent` (ST:1030-1031) | `readyAt` is the epoch ms at which the host's lifespan startup completes (`fastapi/install.py:236-239`, where `startup_time_ms` is set); without a lifespan (in practice a `TestClient` used without `with`) no row counts under `startup` | Starlette has no application-ready event |
| F9 (was O4) | The `security-sinks` catalogue label names SQL, URLs, deserialization, weak algorithms and trust managers (`engine/sensors/floor.py:67-72`) | `"Request input reaching commands and file paths"` | Same reason as F1: the label sits on an available tab and must not claim checks 0.10.0 does not make (`mcp.py:233-234`: agents never infer safety) |
| F10 | `SideEffectOrigins.origin` also yields `jdk`, `logging` and `class-path` from the JDK context and package lists (SO:79-99) | Only `application`, `library` and `unknown` are emitted | Python's `logging` is in the standard library, and there is no JDK context or class path |
| F11 | `LIMITATION_VALUES` names the exit status and lifetime (SV:198-205); `LIMITATION_FILES` (SV:207-214) and `LIMITATION_ATTRIBUTION` (SV:225-229) name JVM files, class loaders and executions no request owns | Adapted texts in Task 10: the process sentence says the exit is not recorded (F5); the files line names the interpreter's own files; the attribution line names route, startup and thread family | sharpit has no class loader, no process-exit event and no execution owner |

### Open deviations (need approval before coding)

1. **O5, a secret-looking name inside a target (conditional).** A file target holds `{name}` placeholders. Under `MASKED` the files sensor masks the segment before collapsing it (`files.py:246-247`); under `FULL` only the collapse (`files.py:78-97`) and Task 9's per-segment mask stand between the name and the output. `test_a_secret_looking_parameter_name_never_reaches_a_target_at_any_exposure` (Task 9) runs over every secret shape of the masking corpus (`tests/test_masking_corpus.py:45-50`) that is a valid parameter name. If it is red after Task 9's mask, the fix (a secret-looking name's placeholder written as `{******}` at redaction) is ruled under safety rule 3, as N1 was, and recorded as a row before it is coded.
2. **O6, what clears the store.** BootUI clears Side Effects only when the journal is cleared: `RuntimeJournal.clear()` (`engine/journal/RuntimeJournal.java:947`) calls `listener.onClear()` (`:982`), and `AgentEvidence.onClear` clears every store (`engine/journal/AgentEvidence.java:302-317`); low-footprint only pauses recording, "the retained events stay until cleared" (`RuntimeJournal.java:804-815`). sharpit has no user-facing journal clear; `SensorHook.discard` runs only on idle suspend (`fastapi/install.py:75-79`) and low-footprint suspend (`engine/lowfootprint.py:27-33`), which also discard the journal (`journal.py:435-444`). No existing matrix row covers that discard. Proposed: the store's rows are dropped with the journal on idle and low-footprint suspend, and `RECORDING_CLEARED` is listed after it (its text stays true); pinned by `test_an_idle_suspend_drops_the_rows_and_lists_recording_cleared` (Task 10). The alternative, faithful to BootUI, keeps the rows through a suspend, so `RECORDING_CLEARED` is never listed. Task 5 Step 3 does not wire `SensorHook.discard` to the clear until decided.
3. **O7, the journal's source filter.** BootUI's store is fed from the agent's ring by its drainer (`SideEffectsService.java:2223`, `accept(long[] raw)`), not from the journal, so no journal setting empties a tab. sharpit's tee appends only a row the journal accepted, and the journal refuses a source outside `runtime_journal_sources` (`journal.py:329-331`; `settings_registry.py:107-113`): narrowing `SHARPIT_RUNTIME_JOURNAL_SOURCES` empties the tabs while the sensor reads `recording`. No existing matrix row covers it. Proposed: a sensor whose source the journal does not accept reads state `disabled` with the reason `"The runtime journal does not record <source>: add it to SHARPIT_RUNTIME_JOURNAL_SOURCES to see its rows."`; pinned by `test_a_sensor_whose_journal_source_is_off_says_so` (Task 10). The alternative, faithful to BootUI, tees before the journal's source filter (a suspended journal still refuses). Task 10 Step 3 stops before the sensor state for that case until decided.

## Global Constraints

- Python `>=3.12`; runtime deps exactly `starlette` and `packaging`; `engine/` never imports `fastapi`, `starlette` or `flask`; dependencies point inward; a collector never imports another collector.
- **Reads have no side effects:** no GET route and no read MCP or CLI tool may open a socket, write a file, change a logger level or change `os.environ`. A drain and an owner resolution on read change only in-memory state, as BootUI's reads do. No action is added.
- **Secrets masked before filtering and before any output (JSON, errors, MCP, CLI).** No request value, raw hash or redacted hash in any DTO, limitation, log or exception text. Targets and parameter names are masked when the store takes a row (SV:2633). `get_side_effects` query matching reads the built row DTOs (SV:1137-1138) and compares the keys BootUI compares (SV:1416-1430), never `detail`, never a hash, never a store field.
- **One service lock.** Every store call (drain, resolve, aggregate, read, clear check) runs under the service's one `threading.Lock` (ST:39-40, SV:1731). The audit-hook append into a ring takes no lock of its own and never calls into the store.
- **The clear compares timestamps.** A drained row or waiting observation whose time is not after the last clear is dropped and counted (SV:2248, :2375); no generation counter.
- Every contract DTO key is emitted, nulls included, camelCase, no envelope, epoch ms; key order as the DTO records (`SideEffectsReport`, `SideEffectsSensorReport`, `SideEffectsSensorDto` 10 keys, `SideEffectsRowDto` 26 keys, `SideEffectsAgentReport` 8 keys).
- User-facing strings verbatim from BootUI with `BootUI`→`sharpit` and `bootui.`→`SHARPIT_`, except the F1 and F2 texts given in Task 10.
- The audit hook never raises, blocks or logs; the tee adds no lock of its own (the journal's `offer` keeps its existing lock) and never calls into the store.
- No module under `src/` over 1000 lines (`tests/test_code_shape.py`); ruff C901 counts per file pinned in `tests/complexity_baseline.json`, never raised; a new file passes C901 10 per function.
- Overhead budgets in `tests/engine/test_sensors_overhead.py` stay at 6 µs per event; a budget is never raised, never marked slow, and runs with `-n 0`.
- Each ported test cites its source: `# ported: SecuritySinksStoreTests.<method>`. An adapted test says `# adapted from:` and what changed. A test with no BootUI source says nothing.
- One condition per assert; a red is the assertion that names the defect, never an import or collection error. Before each `test:` commit: `uv run python scripts/dev/red_check.py <node ids>`.
- pytest runs with `-n` chosen from machine load (`-n auto` by default); the chosen value is written in the task report. Never the full suite locally: CI runs the whole tree.
- Commits: conventional prefix, explicit `git add` paths, `git commit -s`, no AI attribution.

### Gates every task runs

`uv run ruff check`, `uv run ruff format --check`, `uv run pyright`, `uv run pytest -q -n auto tests/test_code_shape.py tests/engine/test_import_boundary.py tests/safety`, plus the task's own tests. A task that changes a hot path (Tasks 2, 3, 4, 5) also runs `uv run pytest -q -n 0 tests/engine/test_sensors_overhead.py`.

## Review Focus

1. A request value, a raw hash or a redacted hash in any REST, MCP or CLI output at any exposure. (Tasks 9, 12)
2. A file flood between two reads drops `processes` or `files` rows, counted, and never a `security-sinks` row. (Task 5)
3. A row whose time is not after a clear is not shown, even when a hook thread appends it after the clear (timestamp rule, SV:2248). (Tasks 5, 7)
4. Under `METADATA_ONLY` rows keep their confirmation and their route; under `FULL` a secret segment is still masked. (Tasks 8, 9)
5. The tee and the counters add no lock of their own and no wait on the audit-hook thread; the per-pattern file call site and the thread name stay under 6 µs in the worst case (64 frames, no application frame) or the plan stops (N2, O2). (Tasks 3, 4, 5)
6. `get_side_effects` is advertised on MCP and in the live CLI catalogue only while a side-effects sensor records, and a CLI call answers 404 otherwise; the bundled `cli/tools.json` lists it always, as BootUI's does. (Task 11)
7. Row text in the view is text, never HTML. (Task 13)
8. Two reads and a clear at once lose and duplicate nothing: every store call is under the service lock. (Task 10)
9. A query holding a masked parameter name or path segment matches no row: matching reads the DTOs. (Task 11)
10. Limitation lines follow BootUI's order: fixed lines (SV:1650-1663), then routes hidden, Other, cleared, holder, unconfirmed (SV:1727-1753). (Task 10)

## File Structure

| File | Responsibility |
|---|---|
| `src/sharpit/engine/capture/frames.py` (modify) | `first_application_frame` (the walk, greenlet parent included) and `call_site_label` (`module:qualname`) |
| `src/sharpit/engine/capture/sqltrace.py` (modify) | `call_site` uses `first_application_frame`; output unchanged |
| `src/sharpit/fastapi/sink_ownership.py` (modify) | `owner(scope) -> str \| None` (ownership and call site in one walk); `owned` kept as `owner(scope) is not None` |
| `src/sharpit/engine/sensors/sinks/values.py`, `matcher.py` (modify) | Holder counters and `status()`; `Match.unreported`; sink rows gain `callSite`, `positionUnknown`, `at` |
| `src/sharpit/engine/sensors/processes.py`, `files.py` (modify) | Rows gain `requestId`, `at`, `callSite`, and `threadName` when there is no request id; file rows gain the per-pattern call site and origin |
| `src/sharpit/engine/sensors/rows.py` (create) | `SensorRows` (per-sensor rings keeping the newest rows, drops, clear times) and `TeeSink` (the whole `JournalSink` protocol) |
| `src/sharpit/engine/sensors/lane.py` (modify) | Wrap the sink in the tee; `SensorHook.discard` wiring per O6 |
| `src/sharpit/engine/capture/journal.py` (modify) | `request_routes(ids)`: routes of retained `http` events, raw, the JRR port; copies only `http` events under the lock |
| `src/sharpit/engine/collectors/sideeffects/__init__.py` (create) | Public interface of the package |
| `.../sideeffects/wording.py` (create) | SW port: `detail`, `SEEN_ONCE`, `OTHER` (command and file branches) |
| `.../sideeffects/store.py` (create) | ST port, three sensors' branches: row key, confirmation, caps, Other, ordering, exemplars, drain, timestamp clear; not thread-safe |
| `.../sideeffects/pending.py` (create) | ST port: waiting observations, `resolve`, `UNKNOWN_ROUTE`, unowned branch, `thread_family` |
| `.../sideeffects/display.py` (create) | Exposure-independent masking: target and parameter (N1) at intake, attribution at output (F7); the DTO row builder |
| `.../sideeffects/limitations.py` (create) | Fixed lines (adapted `VALUES`, `FILES`, F1, `ATTRIBUTION`), the agent's per-sensor filter, and the run-specific lines in BootUI's order |
| `.../sideeffects/service.py` (create) | The one lock; `report`, `sensor`, `agent_report`; sensor DTOs and states; the floor's shape when no store exists |
| `src/sharpit/engine/sensors/floor.py` (modify) | The not-available sensors and the F9 label; no dependency on the collector |
| `src/sharpit/fastapi/routes/side_effects.py`, `fastapi/capture.py`, `fastapi/install.py` (modify) | Wiring: the routes call the service; the store on the capture; `readyAt` (F8) |
| `src/sharpit/engine/tools04/side_effects.py`, `engine/panels04/side_effects.py`, `engine/tools.py`, `engine/tool_dispatch.py`, `engine/mcp.py` (modify) | `get_side_effects`, the context-aware advertising gate for MCP and the live CLI catalogue, the agent guidance |
| `src/sharpit/cli/tools.json` (generated) | `side-effects` command, by `scripts/dev/gen_cli_manifest.py` |
| `ui/src/views/SideEffects.svelte`, `ui/src/App.svelte`, `ui/tests/component/sideEffects.test.ts` (create/modify) | The view and its vitest test |
| `src/sharpit/ui/static/` (rebuilt) | Committed build output |

No module above is expected past 400 lines; `store.py` and `pending.py` are split so that ST's 1635 lines never land in one file.

---

### Task 1: One frame walk, two labels

**Files:**
- Modify: `src/sharpit/engine/capture/frames.py`, `src/sharpit/engine/capture/sqltrace.py:116-138`
- Test: `tests/engine/capture/test_frames.py` (create; mirror the package)

**Interfaces:**
- Produces: `first_application_frame(frame: FrameType | None, limit: int = 64) -> FrameType | None` (walks `f_back`, then the greenlet parent's `gr_frame` chain as `sqltrace.call_site` does today, never importing `greenlet`, keeping no frame reference after return); `call_site_label(frame: FrameType) -> str` = `f"{frame.f_globals.get('__name__', '?')}:{frame.f_code.co_qualname}"`.
- Consumes: `is_application_frame` (`frames.py:20-28`).

- [ ] **Step 1: Write the failing tests:**
  - `test_the_first_application_frame_skips_the_stdlib_installed_packages_and_sharpit`
  - `test_the_call_site_label_is_module_and_qualname_without_a_line` (a method of a nested class reads `tests.engine.capture.test_frames:Outer.Inner.method`)
  - `test_an_async_session_statement_finds_its_frame_in_the_parent_greenlet` (`pytest.importorskip("greenlet")`)
  - `test_sql_call_site_output_is_unchanged`: the existing `sqltrace.call_site` answer (`module:function:line`) for three stacks is byte-identical before and after.
- [ ] **Step 2: Stub** `first_application_frame` returning `None` and `call_site_label` returning `""`; run `uv run pytest -q -n auto tests/engine/capture/test_frames.py`. Expected: assertion failures.
- [ ] **Step 3: Implement.** Move the walk out of `sqltrace.call_site` into `first_application_frame`; `call_site` keeps its own formatter. One walk per event: sink rows use plan 1's ownership walk (Task 2), process and file rows use `first_application_frame`.
- [ ] **Step 4: Run** the new file and `tests/engine/capture/` (SQL trace tests unchanged). Expected: pass.
- [ ] **Step 5: Commit** `refactor: share the application frame walk`.

### Task 2: Sink row fields: call site, unknown position, time

**Files:**
- Modify: `src/sharpit/fastapi/sink_ownership.py`, `src/sharpit/engine/sensors/sinks/values.py` (`Match`), `src/sharpit/engine/sensors/sinks/matcher.py`, `src/sharpit/engine/sensors/lane.py` (`build_lane(..., owner=...)`), `src/sharpit/fastapi/capture.py` (`_arm_sensors` passes `owner`)
- Test: `tests/engine/sensors/test_sink_matcher.py`, `tests/fastapi/test_sink_ownership.py`

**Interfaces:**
- Produces: `owner(scope: Mapping[str, Any]) -> str | None` in `sink_ownership.py`: `None` when not owned; otherwise the `call_site_label` of the first application frame met on the way to the owning frame, else of the owning frame itself (an endpoint installed under `site-packages`). One walk. `owned(scope)` stays, as `owner(scope) is not None`, so plan 1's tests keep their meaning.
- `SinkMatcher(..., owner: Callable[[Mapping[str, Any]], str | None] = lambda scope: None)` replaces `owns`.
- `Match.unreported: frozenset[str]`: names none of whose spans is among the reported ones (BootUI `publishEach` sets `POSITION_UNKNOWN` when `!reported(spans, i)`, RV:792-795, `reported` RV:801).
- A sink row becomes `{source, kind, target, parameter, numeric, positionUnknown, callSite, at, requestId, rawHash, redactedHash}`; `at` is epoch ms (`time.time_ns() // 1_000_000`), as BootUI's `R_FIRST_MILLIS = R_LAST_MILLIS = now` (RV:873-874).

- [ ] **Step 1: Write the failing tests:**
  - `test_position_unknown_past_eight_spans`: `?a=aaaa&b=bbbb`, text `"aaaa " * 8 + "bbbb"`; the `b` row has `positionUnknown is True`, the `a` row `False`.
  - `test_call_site_is_the_first_application_frame_without_a_line`: through a real FastAPI endpoint calling a helper in another test module that opens the path; `callSite` is `"<helper module>:<helper qualname>"`.
  - `test_the_call_site_comes_from_the_ownership_walk`: patch `first_application_frame` to raise; the row still carries its call site (no second walk is made).
  - `test_a_call_site_in_the_parent_greenlet_is_found_by_the_ownership_walk` (`pytest.importorskip("greenlet")`): the owning frame sits in the parent greenlet (`sink_ownership.py:168-181`); `callSite` names the application frame there.
  - `test_a_row_carries_its_epoch_millisecond_time`.
  - `test_not_owned_work_publishes_no_row_and_takes_no_call_site`: `owner` returns `None`; `rows(...) == ()`.
  - In `test_sink_ownership.py`: `test_owner_and_owned_agree_on_every_case`, parametrized over plan 1's `OWN + NOT_OWN` cases.
- [ ] **Step 2: Stub** `owner` as `return None`, `unreported` as `frozenset()`; run both files with `-n auto`. Expected: assertion failures.
- [ ] **Step 3: Implement.** In the ownership walk remember the first frame for which `is_application_frame(f_code.co_filename)` holds, and return its label at the owning frame. The matcher calls `owner` once per published match, as it called `owns`.
- [ ] **Step 4: Run** both files, `tests/engine/sensors/`, and `uv run pytest -q -n 0 tests/engine/test_sensors_overhead.py`. Expected: pass; record plan 1's reported owned-match number again in the task report.
- [ ] **Step 5: Commit** `feat: give each security-sinks row its call site, position flag and time`.

### Task 3: Process and file row fields, and the file call-site budget

**Files:**
- Modify: `src/sharpit/engine/sensors/processes.py`, `src/sharpit/engine/sensors/files.py` (`_row`, `_seen`, the module docstring's origin sentence at `:6`), `tests/engine/test_sensors_overhead.py`
- Test: `tests/engine/sensors/test_sink_sensors.py`, `tests/engine/test_sensors_audit.py`

**Interfaces:**
- Produces: process and file rows gain `requestId` (`REQUEST.get().id` when its `context_id` is the lane's, else `None`; handed-off work keeps its request, as BootUI's owner slots do), `at` (epoch ms), and `threadName` (`threading.current_thread().name`, read only when `requestId` is `None`, else `None`; O2).
- Process rows: `callSite` = `call_site_label(first_application_frame(sys._getframe(1)))`, or `None` when no frame is found; no `origin` key (O1: `null` in the DTO).
- File rows: the call site and origin are read once per file pattern (SV:207-213). On a `_seen` miss (`files.py:216-225`) the pattern is resolved as today; a bounded `pattern -> (callSite, origin)` map, cleared when full as `_seen` is (`# shortcut: a cleared map re-reads a pattern's call site; BootUI keeps one per run, bound it per run if rows ever disagree`), answers a known pattern without a walk; an unknown pattern walks once, finding `outside` (the first frame outside the standard library and sharpit) and the first application frame, and sets `origin` per SO:92-100 (F10). A `_seen` hit walks nothing.

- [ ] **Step 1: Extend the overhead test first.** Add three measurements of the files sensor against `FILES_SENSOR_BUDGET` (6.0e-6, unchanged): a new pattern from a stack of 64 frames with no application frame (the worst case: a library opening a file at startup, so the walk never stops early), a new pattern with an application frame near the top, and a `_seen` hit; and the processes sensor with its walk from the same 64-frame stack against `PROCESSES_SENSOR_BUDGET` (6.0e-6, unchanged). Each runs outside a request, so the thread-name read is included. Run `uv run pytest -q -n 0 tests/engine/test_sensors_overhead.py` on the stub (Step 2) and on the implementation (Step 3).
- [ ] **Step 2: Write the failing tests** and stub the fields as absent:
  - `test_a_process_row_names_its_request_time_and_call_site`
  - `test_a_file_row_names_its_request_time_and_call_site`
  - `test_a_row_outside_a_request_has_no_request_id`
  - `test_a_row_of_another_install_has_no_request_id` (another `context_id`)
  - `test_two_call_sites_of_one_pattern_share_the_first_ones` (`# adapted from: SideEffectsService.LIMITATION_FILES`, SV:207-213; two helpers open `report-1.csv` and `report-2.csv`: both rows carry the first helper's call site)
  - `test_a_file_rows_origin_follows_its_frames` (`# adapted from: SideEffectOrigins.origin`, SO:79-100): application frame present gives `application`; a non-stdlib library frame and no application frame gives `library`; only standard-library frames gives `unknown`
  - `test_a_process_row_has_no_origin` (SV:2272-2280, ST:281-289)
  - `test_a_row_without_a_request_id_carries_its_thread_name` and `test_a_request_row_reads_no_thread_name`
  - Update the parametrized row-shape tests in `test_sensors_audit.py` to the new keys.
- [ ] **Step 3: Implement** the process fields, then the file fields.
- [ ] **Step 4: N2 and O2 gate.** Run the overhead test at `-n 0` three times. If any files or processes measurement passes 6.0e-6 in any run, **stop**: report the numbers and do not code a fallback; the outcome (N2: `callSite` null on file rows; O2: no thread name) needs a recorded decision. If all pass, N2 is not used; say so in the task report.
- [ ] **Step 5: Run** the three test files. Expected: pass.
- [ ] **Step 6: Commit** `feat: give process and file rows their request, time and call site`.

### Task 4: Holder counters

**Files:**
- Modify: `src/sharpit/engine/sensors/sinks/values.py`, `src/sharpit/engine/sensors/sinks/__init__.py`
- Test: `tests/engine/sensors/test_sink_values.py`

**Interfaces:**
- Produces: `RequestValues.status() -> dict[str, int]` with exactly the F4 keys, in BootUI's relative order (RV:1397-1429): `requests, tableFull, valuesTooLong, valuesOverCount, checks, partial, stopped, busy, notKept, dropped` (`dropped` is filled by the service from the ring, Task 10; the holder reports 0).
- Counters are plain integers incremented where the event happens, without a new lock: `# shortcut: an increment racing another may be lost; the line is advisory (BootUI uses LongAdder); move to per-entry counters if an exact count is ever asserted under concurrency`.

- [ ] **Step 1: Write the failing tests** (no BootUI test pins the holder status, SV:1772 has none):
  - `test_counters_feed_the_holder_line`: one request reaching two checks, one value of 257 characters, 33 values: `requests == 1`, `checks == 2`, `valuesTooLong == 1`, `valuesOverCount == 1`.
  - `test_a_full_table_counts_table_full` (129 requests).
  - `test_stopped_partial_and_busy_are_counted`.
  - `test_holder_counters_never_hold_a_value_or_name`: after a match on `?secretname=needle1234`, neither string is in `repr(status())`.
  - `test_status_keys_are_exactly_the_ones_an_output_reads`.
- [ ] **Step 2: Stub** `status()` returning `{}`; run with `-n auto`. Expected: assertion failures.
- [ ] **Step 3: Implement.** `requests` is counted when an entry is inserted (F4).
- [ ] **Step 4: Run** the file and the overhead test at `-n 0`. Expected: pass.
- [ ] **Step 5: Commit** `feat: count what the request-value holder skipped`.

### Task 5: Rings and the tee

**Files:**
- Create: `src/sharpit/engine/sensors/rows.py`
- Modify: `src/sharpit/engine/sensors/lane.py` (`build_lane` wraps the sink; `SensorLane.rows`; `SensorHook.discard`)
- Test: `tests/engine/sensors/test_rows.py`, `tests/fastapi/test_w6_audit_sensors.py`

**Interfaces:**
- Produces:

```python
RING_CAPACITY = 10_000  # the store's MAX_PENDING (ST:46)
RINGED = ("processes", "files", "security-sinks")


class SensorRows:
    def append(self, row: dict[str, object]) -> None: ...  # hook thread: no lock of its own
    def drain(self, sensor: str) -> list[dict[str, object]]: ...  # at most RING_CAPACITY rows
    def dropped(self, sensor: str) -> int: ...
    def cleared_at(self, sensor: str) -> int: ...  # epoch ms of the last clear, 0 if none
    def clear(self, sensor: str, now: int) -> None: ...


class TeeSink:  # the whole JournalSink protocol (journal.py:46-55)
    def __init__(self, journal: JournalSink, rows: SensorRows) -> None: ...
    def offer(self, event: Event) -> bool: ...
    def offer_flat(
        self, event: dict[str, str | int | bool | None], size: int | None = None, started: int = -1
    ) -> bool: ...
    def records(self, source: str) -> tuple[dict[str, object], ...]: ...  # delegated
    def accepts(self, source: str) -> bool: ...  # delegated
    def count_dropped(self, key: str) -> None: ...  # delegated
```

- One `collections.deque(maxlen=RING_CAPACITY)` per sensor: a full ring drops its oldest row; `append` counts a drop when the ring is full before appending (`# shortcut: two racing appends may count one drop twice or not at all; the count is advisory, as the holder counters are`). `TeeSink` appends only a row the journal accepted, and only for a source in `RINGED` (O7 may change the accepted-source condition). A ring row is the journal's own dict and is never changed: the store copies before it annotates. `clear` empties the ring and records `now`; a row a hook thread appends after the clear but whose `at` is not after `now` is dropped by the store (Task 7). The wiring of `SensorHook.discard` to `clear` waits on O6.

- [ ] **Step 1: Write the failing tests:**
  - `test_an_accepted_row_reaches_its_sensors_ring`
  - `test_a_row_the_journal_refused_reaches_no_ring` (journal suspended)
  - `test_a_full_ring_keeps_the_newest_rows_and_counts_dropped`
  - `test_a_file_flood_never_drops_a_security_sinks_row`: fill the `files` ring past capacity, then one sink row; it drains, and `dropped("files") > 0` while `dropped("security-sinks") == 0` (scenario row 9).
  - `test_a_read_racing_appends_loses_and_duplicates_nothing`: 4 threads append 2 000 numbered rows each while a reader drains in a loop; the union of drains has each row exactly once (scenario row 14).
  - `test_the_tee_answers_every_journal_sink_call`: `records`, `accepts` and `count_dropped` reach the wrapped journal.
  - `test_the_recording_clear_empties_the_ring_and_records_its_time`
  - `test_a_row_queued_before_a_clear_is_never_shown_after_it` (rings half: a row with `at` before the clear, appended after it, is still in the ring and `cleared_at` is later than its `at`; the store half is in Task 7) (scenario row 10).
- [ ] **Step 2: Stub** `append` as a no-op and `drain` as `[]`; run with `-n auto`. Expected: assertion failures.
- [ ] **Step 3: Implement**, then wire the lane (without the `discard` call until O6 is decided).
- [ ] **Step 4: Run** the new file, `tests/fastapi/test_w6_audit_sensors.py`, and the overhead test at `-n 0` (the tee is on the hot path). Expected: pass, budgets unchanged.
- [ ] **Step 5: Commit** `feat: keep each sensor's accepted rows in a bounded ring`.

### Task 6: Wording

**Files:**
- Create: `src/sharpit/engine/collectors/sideeffects/__init__.py`, `src/sharpit/engine/collectors/sideeffects/wording.py`
- Test: `tests/engine/collectors/sideeffects/test_wording.py` (with `__init__.py`)

**Interfaces:**
- Produces: `SEEN_ONCE`, `OTHER` (SW:14, :17-18, verbatim), `detail(kind: str, parameter: str | None, target: str | None, confirmed: bool) -> str` with the command branch (SW:45-51, `ARGUMENT = ^(.*), argument (\d+)$` SW:20, `command()` SW:25-27), the file-path branch (SW:52-54) and the generic fallback (SW:58-61). `kind` is BootUI's display kind: `"command"` or `"file path"` (SC:109-110). No SQL or URL branch.

- [ ] **Step 1: Write the failing tests** (no BootUI test calls `detail` for these kinds; each is `# adapted from: SinkWording.java:<lines>`):
  - `test_an_argument_of_a_named_command`: `("command", "name", "convert, argument 1", True)` gives `` "Request input reached this command unchanged: the value of `name` appeared in argument 1 of `convert`. Check that it is validated." ``
  - `test_an_argument_of_the_executable`: target `(the executable), argument 2` reads `of the executable`.
  - `test_the_executable_alone`: target `(the executable)` reads `appeared in it. Check that it is validated.`
  - `test_a_file_path`
  - `test_a_missing_name_reads_a_parameter`: `` `a parameter` ``.
  - `test_an_unconfirmed_row_ends_seen_once`: suffix toggled by `confirmed`.
  - `test_an_unknown_kind_takes_the_generic_sentence`
- [ ] **Step 2: Stub** `detail` returning `""`; run with `-n auto`. Expected: assertion failures.
- [ ] **Step 3: Implement** by translating SW:30-63 line by line.
- [ ] **Step 4: Run.** Expected: pass.
- [ ] **Step 5: Commit** `feat: word security-sinks rows as BootUI does`.

### Task 7: The store

**Files:**
- Create: `src/sharpit/engine/collectors/sideeffects/store.py`
- Test: `tests/engine/collectors/sideeffects/test_store.py`

**Interfaces:**
- Consumes: `SensorRows` (Task 5), `wording` (Task 6).
- Produces: `SideEffectsStore(rows: SensorRows, intake: Callable[[Mapping[str, object]], dict[str, object]] = dict, clock: Callable[[], int] = epoch_ms)` with `drain() -> None`, `rows_of(sensor: str) -> list[StoreRow]`, `counts(sensor) -> tuple[int, int]` (rows, occurrences), `unconfirmed() -> int`, `folded() -> int`, `clears() -> int`, `cleared() -> int`, `clear(now: int) -> None`. `intake` returns a new dict (the ring row is never changed); Task 9 supplies the masking one. The class docstring says it is not thread-safe and that the service serialises it (ST:39-40). Constants from ST: `MAX_ROWS_PER_SENSOR = 500`, `MAX_ROWS = 2_000`, `EXEMPLARS = 3`, `CONFIRMATIONS = 4` (ST:44-48, :391). Flag rule from SC:93-99: for command and file rows the position is always 0, so only `numeric` and `positionUnknown` make a row wait (`standsAlone`, ST:401-416).
- Port, restricted to the three sensors: the row key (ST:1160-1178; fields sharpit has: scope, attribution, sensor, kind, target, callSite, location, parameter), `remember` (ST:564-586: four pairs; a zero hash or no request id is never remembered; a pair already remembered adds nothing), `confirmed` (ST:592-603: equal redacted hash, different raw hash, different request), `shown` (ST:605-608), `visible` (ST:1604-1609), `unconfirmed` (ST:1573-1581), the caps and Other row with `unconfirmedPastCap` (ST:1181-1195), ordering (ST:1373-1376: Other last, then `count + completed` descending, then `lastSeen` descending), exemplar request ids (at most 3). Clear (SV:2248): on `drain`, a sensor whose `rows.cleared_at` is later than the store's last seen clear time drops its rows and its waiting observations first and counts one clear (`clears()`, which feeds `RECORDING_CLEARED`, SV:1738-1739); then each drained row whose `at` is not after the latest clear time is skipped and counted in `cleared()`. Every row passes through `intake` before it is keyed, so the key holds the masked target and parameter.

- [ ] **Step 1: Write the failing tests:**
  - `test_repeated_texts_never_fill_the_confirmations_and_a_different_value_confirms` (`# ported: SecuritySinksStoreTests.repeatedTextsNeverFillTheConfirmationsAndADifferentValueConfirms`, kind command)
  - `test_past_the_caps_an_unconfirmed_match_is_not_shown_and_the_other_row_counts_it` (`# adapted from: SecuritySinksStoreTests.pastTheCapsAnUnconfirmedMatchIsNotShownAndTheOtherRowClaimsNoLiteral`, the literal assertion dropped)
  - `test_a_match_whose_redacted_text_was_not_kept_is_never_confirmed` (`# ported: SecuritySinksStoreTests.aMatchWhoseRedactedTextWasNotKeptIsNeverConfirmed`)
  - `test_a_number_and_an_unknown_position_wait_and_a_plain_value_stands_alone` (`# adapted from: SecuritySinksStoreTests.aValueInsideTrueFalseOrANumberWaitsAndOneCrossingALiteralStandsAlone`, literal cases dropped)
  - `test_a_sensor_past_its_cap_counts_the_rest_in_its_other_row_which_sorts_last` (`# ported: SideEffectsStoreTests.aSensorPastItsCapCountsTheRestInItsOtherRowWhichSortsLast`, sensor files)
  - `test_clear_recording_drops_rows` (`# adapted from: SideEffectsStoreTests.clearRecordingDropsRowsAndWaitingObservations`; the waiting half is Task 8)
  - `test_the_same_request_twice_never_confirms` and `test_the_same_raw_text_from_two_requests_never_confirms` (ST:592-603)
  - `test_a_row_queued_before_a_clear_is_never_shown_after_it` (store half: the row a hook thread appended after the clear, with `at` before it, is skipped and `cleared() == 1`; `# adapted from: SideEffectsService.java:2248`; scenario row 10)
  - `test_a_row_after_a_clear_is_shown`: `at` one millisecond after the clear time is kept.
  - `test_the_store_never_changes_a_ring_row`: the drained dicts compare equal to copies taken before the drain.
  - `test_rows_survive_journal_eviction`: rows drained, then the journal evicts every event; `rows_of` is unchanged.
  - `test_a_process_or_file_row_is_shown_from_one_occurrence`: no confirmation for those sensors.
- [ ] **Step 2: Stub** every method returning empty values; run with `-n auto`. Expected: assertion failures.
- [ ] **Step 3: Implement** by translating the cited lines. Observations with a request id are passed to `pending` (Task 8) through one call; until Task 8 lands, the stub attributes them at once.
- [ ] **Step 4: Run** the file; `wc -l store.py` under 1000; C901 per function at most 10. Expected: pass.
- [ ] **Step 5: Commit** `feat: aggregate and confirm side-effects rows as BootUI's store does`.

### Task 8: Owners: waiting rows and the route reader

**Files:**
- Create: `src/sharpit/engine/collectors/sideeffects/pending.py`
- Modify: `src/sharpit/engine/capture/journal.py` (`request_routes`), `src/sharpit/engine/collectors/sideeffects/store.py`
- Test: `tests/engine/collectors/sideeffects/test_pending.py`, `tests/engine/capture/test_journal.py`

**Interfaces:**
- Produces: `RuntimeJournal.request_routes(ids: AbstractSet[str]) -> dict[str, str]`: copies only the retained `http` events under the lock, as `records()` filters by source there (`journal.py:379-382`), then, outside it, maps each event whose `requestId` is asked for to its `route`, stopping once every id is named (JRR:35-69). Raw (unmasked): the attribution is masked at output (Task 9, F7).
- `Pending(reader: Callable[[AbstractSet[str]], dict[str, str]], ready_at: Callable[[], int | None])`: `add(observation, request_id)`, `resolve(now)` (ST:1072-1115, without the REST-capture grace, which no ringed sensor has), `clear(cleared_at)` (drops waiting observations whose time is not after it, SV:2375). Constants `PENDING_MILLIS = 30_000`, `MAX_PENDING = 10_000`, `UNKNOWN_ROUTE`, `ROUTE_HIDDEN` (ST:46-52); a reader retry after `READ_RESOLVE_MILLIS = 250` (SV:75, `resolve(read=True)` SV:2206-2219). Every `resolve` asks the reader for all waiting ids before it applies the 30 s rule (ST:1089, :1110-1112), so a row whose `http` event is still held is named however old it is (F6).
- Unowned observations (ST:1028-1036): `startup` when `at` precedes `readyAt` (F8), else the thread family (`scope: "thread"`) when the row carries `threadName`, else `(unattributed)` (ST:55).
- `thread_family(name: str | None) -> str | None`: a port of `SideEffects.threadFamily` (`agent/bridge/SideEffects.java:1266-1291`): secret-looking parts removed first, the name cut to `MAX_THREAD_FAMILY`, each digit run written `{n}`, and every character outside `a-z A-Z . _ - : / space [ ]` written `?`.

- [ ] **Step 1: Write the failing tests:**
  - `test_a_request_the_journal_never_names_counts_under_an_unknown_route_once_it_waited_long_enough` (`# ported: SideEffectsServiceTests.aRequestTheJournalNeverNamesCountsUnderAnUnknownRouteOnceItWaitedLongEnough`)
  - `test_waiting_observations_are_bounded_and_dropped_past_the_bound` (`# ported: SideEffectsStoreTests.waitingObservationsAreBoundedAndDroppedPastTheBound`)
  - `test_clear_recording_drops_waiting_observations` (`# adapted from: SideEffectsStoreTests.clearRecordingDropsRowsAndWaitingObservations`)
  - `test_a_running_requests_rows_wait_for_its_route`: no `http` event yet; at 29 s the row is not shown, then the event arrives and the row is attributed to its route (scenario row 13).
  - `test_a_request_whose_http_event_was_evicted_counts_under_unknown_route` (scenario row 12)
  - `test_metadata_only_keeps_confirmation_and_routes`: a journal masker at `METADATA_ONLY`; `request_routes` still names the route, and a two-request confirmation still confirms (scenario row 11).
  - `test_a_row_older_than_the_wait_is_named_while_its_http_event_is_held`: a row 40 s old at the first read, its `http` event still retained, is attributed to its route, not to `(unknown route)` (F6).
  - `test_request_routes_copies_only_http_events_under_the_lock`
  - `test_one_read_at_the_caps_sorts_and_resolves_in_bounded_time` (scenario row 18): 2 000 rows and 10 000 waiting observations, one read under the existing route test timeout.
  - `test_a_row_before_readiness_counts_under_startup` and `test_an_unowned_row_after_readiness_counts_under_its_thread_family` (`# adapted from: SideEffectsStore.attributeUnowned`, ST:1028-1036)
  - `test_an_unowned_row_with_no_thread_name_is_unattributed`
  - `test_a_thread_family_collapses_digit_runs_and_keeps_only_safe_characters` (`# adapted from: SideEffects.threadFamily`, `agent/bridge/SideEffects.java:1266-1291`): `pool-3-thread-12` gives `pool-{n}-thread-{n}`; `a=b&c` gives `a?b?c`.
  - `test_a_thread_name_holding_a_secret_never_reaches_its_family`
- [ ] **Step 2: Stub** `request_routes` as `{}` and `resolve` as a no-op; run both files with `-n auto`. Expected: assertion failures.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run.** Expected: pass.
- [ ] **Step 5: Commit** `feat: name each side-effects row's route from the journal`.

### Task 9: Display masking

**Files:**
- Create: `src/sharpit/engine/collectors/sideeffects/display.py`
- Test: `tests/engine/collectors/sideeffects/test_display.py`

**Interfaces:**
- Produces: `mask_segments(path: str, masker: Masker) -> str`: the never-shown replacement of `masker.mask_path`, then every non-empty `/` segment that `is_secret_value` flags replaced by `MASK`, whatever the exposure and the secret-mask setting (SO:128-141); `display_parameter(name: str | None, masker: Masker) -> str` (N1; `None` reads `"(name not kept)"`, SV:2658); `intake(masker: Masker) -> Callable[[Mapping[str, object]], dict[str, object]]`: the store's intake (Task 7), returning a copy whose `target` went through `mask_segments` for a file or file-path row and through the never-shown check for a command row (SV:2631-2639, applied where BootUI applies it, SV:2633), and whose `parameter` went through `display_parameter`; `row_dto(row: StoreRow, masker: Masker) -> dict[str, object]`, the 26 keys of `SideEffectsRowDto` in order, `kind` mapped `"file-path"`→`"file path"` (SC:110), `attribution` through `mask_segments` (F7), `detail` from `wording.detail` with the displayed parameter, `origin` from the file row and `null` for process and security-sinks rows (O1; `SideEffectsRowDto.java:81`), `location` from the `files` sensor's row and `null` on every security-sinks row (SV:2640-2647 sets it only for `KIND_SINK_SQL`), `insideMethod`, `client`, `capture`, `capturedBy` `null` (BootUI without the inventory sensor and outside the network sensor).

- [ ] **Step 1: Write the failing tests**, each parametrized over `MASKED`, `METADATA_ONLY` and `FULL`:
  - `test_segments_and_names_that_look_like_secrets_are_masked` (`# ported: SideEffectOriginsTests.segmentsAndNamesThatLookLikeSecretsAreMasked`)
  - `test_a_secret_looking_parameter_name_is_masked_in_parameter_and_detail_at_every_exposure` (N1; scenario row 1)
  - `test_rows_are_keyed_on_masked_values`: two secret-looking names on one target give one row (N1); a secret segment never reaches the store's key.
  - `test_every_security_sinks_row_has_no_location`: command and file-path rows read `location: null`; a `files` sensor row keeps its place.
  - `test_a_secret_looking_parameter_name_never_reaches_a_target_at_any_exposure`: parametrized over every secret shape of the masking corpus (`tests/test_masking_corpus.py:45-50`: the sentinel, the JWT, the Stripe, AWS and GitHub keys) that is a valid parameter name, through the files sensor's own redaction and collapse; no `target` holds the name or a recognisable part of it (scenario row 1; if red, see O5 and stop).
  - `test_every_exposure_masks_secret_segments_and_never_blanks_a_row`: no key is `None` that BootUI fills (scenario row 6).
  - `test_the_console_token_in_a_path_is_never_shown` (scenario row 7)
  - `test_row_keys_follow_the_dto_order` (26 keys, copied from DTO `SideEffectsRowDto.java:74-100`)
  - `test_no_row_key_holds_a_hash`
- [ ] **Step 2: Stub** the functions as identity; run with `-n auto`. Expected: assertion failures.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run.** Expected: pass.
- [ ] **Step 5: Commit** `feat: mask side-effects rows whatever the exposure`.

### Task 10: Service, limitations and REST

**Files:**
- Create: `src/sharpit/engine/collectors/sideeffects/limitations.py`, `src/sharpit/engine/collectors/sideeffects/service.py`
- Modify: `src/sharpit/engine/sensors/floor.py` (the F9 label; no import of the collector), `src/sharpit/fastapi/routes/side_effects.py` (calls the service instead of the floor), `src/sharpit/fastapi/capture.py` (build `SideEffectsStore` beside the lane: `ctx.capture.side_effects`, with `display.intake`), `src/sharpit/fastapi/install.py:236-239` (`readyAt`, F8)
- Test: `tests/engine/collectors/sideeffects/test_service.py`, `tests/fastapi/test_side_effects_api.py`, `tests/fastapi/test_w6_sensor_floor_api.py:120,130`

**Interfaces:**
- Produces: `report(capture, masker) -> dict`, `sensor(capture, masker, sensor_id, offset, limit) -> dict` (keeping the verbatim 400 texts and bounds of `floor.py:365-383`, SV:1087), with `available` true while the lane is attached with a ringed sensor; sensor DTOs ported from `sensorDto` (SV:1589-1620); every sensor outside `RINGED` is `not-available` with `"Not available in this version."` (SC:256). Without a lane, every read answers today's unavailable shape (SVT `withoutTheAgentEveryReadIsUnavailableWithItsReason`): the service returns the floor's shape when no store exists, so `engine/sensors` never depends on the collector.
- The service owns one `threading.Lock` and takes it around every store call in `report`, `sensor` and `agent_report` (drain, resolve, aggregate, read, the clear check), as BootUI's service holds `synchronized (lock)` (SV:1131-1132, :1731, :2060).
- Limitation lines, in BootUI's order. First the fixed lines (SV:1650-1663) for what sharpit records: `LIMITATION_SCOPE`, `LIMITATION_VALUES` (adapted, F11), `LIMITATION_NETWORK` (the three lines of `floor.py:75-81`, in that order), `LIMITATION_FILES` (adapted, F11), `LIMITATION_SECURITY_SINKS` (F1), `LIMITATION_ATTRIBUTION` (adapted, F11). Then the run-specific lines (SV:1727-1753): `LIMITATION_ROUTES_HIDDEN` (SV:236-238), the Other line (`"<n> operation is|operations are counted in an Other row: a sensor keeps at most 500 rows and the run 2000."`), `RECORDING_CLEARED` (SV:233-234) once `store.clears() > 0`, the holder line (SV:1772-1790, emitted whenever the setting is on, zero counts included; `dropped` = the `security-sinks` ring's drops), the unconfirmed line (F2).
- F11 texts. The process sentence appended to sharpit's `LIMITATION_VALUES` line: `"A process row records the start only: its exit status and lifetime are not recorded."` `LIMITATION_FILES`: `"Files: the interpreter's own files (imports) and sharpit's own state are counted, not recorded per route. A call site's frames are read once per run and file pattern, so two call sites of one pattern share the first one's. A file opened without an audit event, as native code may, is not seen. A move or a copy records its source and its destination."` `LIMITATION_ATTRIBUTION`: `"A row is attributed to its request's route as HTTP Exchanges names it, else to startup, or to its thread's family. Work handed to another thread without sharpit's request context shows under its thread's family."`
- F1 limitation text:

```text
Security sinks: request input is matched only while SHARPIT_AGENT_SECURITY_SINKS_REQUEST_VALUES is on, against the current request's query and path parameter values of 4 to 256 characters, at most 32 of them, never form values, headers, or bodies, and only verbatim: a value encoded, trimmed, or changed in case is not seen. The values are compared, never stored, and forgotten when the response completes. A command is checked where the processes sensor sees it start; a file path only with the files sensor; SQL text and outbound URLs are not checked. Work the request hands off, to a thread, a task, a background task, or a streamed body, is checked so that its own rows are redacted, but publishes no security-sinks row: only the request's own endpoint and its dependencies do. A row's target is the redacted text, the value replaced by the parameter's name; when a text was scanned only in part or held more matches than could be redacted, no text is kept. A value made of digits only, or one whose place in the text is not known, is shown once a second request confirms the text varies with it.
```

- F1 coverage reasons for the `security-sinks` sensor: off: state `disabled`, `"Request-value matching is off: set SHARPIT_AGENT_SECURITY_SINKS_REQUEST_VALUES=true and restart the application to check whether request input reaches a command or a file path."`; on: state `recording`, `"Checks commands through the processes sensor"` or `"; not commands: the processes sensor is off"`, then `"; file paths through the files sensor."` or `"; not file paths: the files sensor is off."` (`JavaAgentService.java:289-336`).
- F2 unconfirmed line: `"<n> security-sinks match is|matches are not shown yet: a number, or one whose place in the text is not known may be a word the text always holds, until a second request confirms the text varies with it."`

- [ ] **Step 1: Write the failing tests:**
  - `test_every_sensor_is_listed_in_tab_order_and_those_not_shipped_say_so` (`# ported: SideEffectsServiceTests.everySensorIsListedInTabOrderAndThoseNotShippedSaySo`)
  - `test_an_unknown_sensor_or_a_negative_page_is_rejected` (`# ported: SideEffectsServiceTests.anUnknownSensorOrANegativePageIsRejected`)
  - `test_without_the_lane_every_read_is_unavailable_with_its_reason` (`# ported: SideEffectsServiceTests.withoutTheAgentEveryReadIsUnavailableWithItsReason`)
  - `test_a_requests_failed_start_is_a_row_of_its_route_with_the_commands_file_name_only` (`# adapted from: SideEffectsServiceTests.aRequestsFailedStartIsARowOfItsRouteWithTheCommandsFileNameOnly`, start only, F5)
  - `test_a_report_written_outside_the_temporary_directory_is_an_application_write_of_its_route_by_pattern_only` (`# ported: SideEffectsServiceTests.aReportWrittenOutsideTheTemporaryDirectoryIsAnApplicationWriteOfItsRouteByPatternOnly`, its `origin` assertion included, O1)
  - `test_while_http_exchanges_is_hidden_route_rows_are_merged_without_request_ids` (`# ported: SideEffectsServiceTests.whileHttpExchangesIsHiddenRouteRowsAreMergedWithoutRequestIds`)
  - `test_a_second_request_with_another_value_confirms_the_row` (`# adapted from: SecuritySinksServiceTests.aSecondRequestWithAnotherValueConfirmsTheRow`, a file path)
  - `test_a_digits_only_argument_waits_for_confirmation` (`# adapted from: SecuritySinksServiceTests.aDigitsOnlyValueInsideALiteralAlsoWaitsForConfirmation`)
  - `test_a_text_with_more_matches_than_can_be_redacted_keeps_no_text` (`# adapted from: SecuritySinksServiceTests.aStatementWithMoreMatchesThanCanBeRedactedKeepsNoText`, nine spans, target `"(text not kept)"`, SV:273)
  - `test_a_file_row_reads_file_path_and_its_sentence` (scenario row 17; asserts `location is None` on the security-sinks row)
  - `test_the_holder_line_is_shown_whenever_the_setting_is_on` and `test_no_holder_line_without_the_setting`
  - `test_the_security_sinks_limitation_names_only_commands_and_file_paths` (F1, exact text)
  - `test_limitation_lines_follow_bootuis_order`: the six fixed lines, then routes hidden, Other, cleared, holder and unconfirmed, with every run-specific condition true (SV:1650-1663, :1727-1753).
  - `test_the_files_and_attribution_lines_are_the_adapted_texts` (F11, exact text)
  - `test_the_security_sinks_label_names_commands_and_file_paths` (F9, exact text)
  - `test_two_reads_and_a_clear_at_once_lose_and_duplicate_nothing`: two threads call `report` and `sensor` in a loop while a third clears and hook threads append; no exception, and every appended row is counted once, shown or cleared (scenario row 28).
  - `test_ready_at_is_when_the_host_lifespan_startup_completed` and `test_without_a_lifespan_no_row_counts_under_startup` (F8; scenario row 26)
  - `test_an_idle_suspend_drops_the_rows_and_lists_recording_cleared` (O6, written once O6 is decided; its alternative is `test_an_idle_suspend_keeps_the_rows`)
  - `test_a_sensor_whose_journal_source_is_off_says_so` (O7, written once O7 is decided)
  - `test_report_keys_follow_the_dto_order`, `test_sensor_report_keys_follow_the_dto_order`, `test_sensor_dto_keys_follow_the_dto_order`
  - `test_an_inactive_console_builds_no_ring_or_store_and_answers_404`: `enabled="OFF"`, the setting and the three sensors configured; `capture.side_effects is None` and every side-effects path answers 404 (scenario row 4).
  - Update `test_side_effects_lists_every_sensor_unavailable` and `test_side_effects_sensor_answers_its_shape` (`tests/fastapi/test_w6_sensor_floor_api.py:120,130`) to the not-available state of the sensors outside `RINGED`, without the lane unchanged.
- [ ] **Step 2: Stub** the service with today's unavailable shapes; run the new files with `-n auto`. Expected: assertion failures.
- [ ] **Step 3: Implement.** Stop before the `discard` wiring (O6) and the refused-source sensor state (O7) until each is decided.
- [ ] **Step 4: Run** the new files, `tests/fastapi/test_w6_sensor_floor_api.py` (including `test_sensor_reads_have_no_side_effects`, `:249`) and `tests/safety`. Expected: pass.
- [ ] **Step 5: Commit** `feat: report side-effects rows over REST`.

### Task 11: `get_side_effects` on MCP and the CLI

**Files:**
- Modify: `src/sharpit/engine/tools04/side_effects.py`, `src/sharpit/engine/panels04/side_effects.py`, `src/sharpit/engine/tools.py` (`on_mcp` stays static), `src/sharpit/engine/tool_dispatch.py` (advertising gate in `_find_tool` `:167-176` and `cli_status` `:243`), `src/sharpit/engine/mcp.py` (`tools/list` at `:431`, `:515`; guidance at `:233-234`), `src/sharpit/cli/tools.json` (regenerated), `docs/reference/matrix-updates/w6-S2.tsv:8,16,17,18,37`
- Test: `tests/engine/collectors/sideeffects/test_agent_report.py`, `tests/fastapi/test_side_effects_tools.py`, `tests/cli/test_manifest_drift.py`

**Interfaces:**
- Produces: `agent_report(capture, masker, query, limit) -> dict` (SV:1115-1170: `query` trimmed; a sensor id lists that sensor; otherwise BootUI builds the row DTOs and filters them, `rowsOf(...)` then `matches(row, needle)` (SV:1137-1138), comparing per SV:1416-1430 attribution, target, parameter, kind, callSite, insideMethod, sensor, client and exemplar ids of the built DTO, never `detail`; sorted by `count + completed` descending; default limit 20, DTO `SideEffectsAgentReport.java:30`; the "No row matched" line with the request-id clause). The agent's limitation lines pass BootUI's per-sensor filter (`LIMITATION_SENSORS` and `agentLimitations`, SV:1170-1202, restricted to the lines sharpit lists, with `LIMITATION_AGENT_OMITTED`). A `Tool("get_side_effects", ..., schema QUERY_LIMIT, panel "side-effects", action False)` (BootUI `McpToolCatalog.java:320,337`), its description the F1 cut of `McpToolDescriptions.java:423`.
- Advertising: `Tool.on_mcp` has no context (`tools.py:131-134`), so a helper `advertised(ctx, tool) -> bool` replaces the bare `on_mcp` filter at `mcp.py:431`, `mcp.py:515`, `tool_dispatch.py:171` and in `cli_status`. It answers `False` for a tool in `AGENT_SENSOR_TOOLS` (`floor.py:41-42`) unless the lane is attached with a ringed sensor on. BootUI gates the live CLI catalogue the same way: "The MCP tools, and their CLI commands, a stack advertises only while the agent's sensor records" (`bootui-conformance/.../JavaAgentPresence.java:12-14`), and without it `GET /cli` does not list `get_side_effects` and invoking it answers 404 naming the tool (`AbstractCliConformanceTest.java:237-257`). So: MCP `tools/list`, `GET {api}/cli` and `POST {api}/cli/tools/get_side_effects` list and serve it only then; otherwise MCP keeps today's unavailable-tool answer (`tool_dispatch.py:155-164`) and the CLI keeps today's 404 (`w6-S2.tsv:16`). Only the bundled `cli/tools.json` lists `side-effects` always, as `bootui-tools.json:1352-1354` does.
- Guidance: `mcp.py:233-234` no longer says sharpit records no request-input-in-sink observations; it says security-sinks rows are checks to perform, not verdicts, and that request-value matching is off by default.

- [ ] **Step 1: Write the failing tests:**
  - `test_the_agent_report_filters_rows_and_clear_recording_drops_them` (`# ported: SideEffectsServiceTests.theAgentReportFiltersRowsAndClearRecordingDropsThem`)
  - `test_agents_get_the_fixed_limitations_of_the_sensors_they_see_and_every_run_specific_one` (`# ported: SideEffectsServiceTests.agentsGetTheFixedLimitationsOfTheSensorsTheySeeAndEveryRunSpecificOne`)
  - `test_request_input_in_sink_is_a_check_to_perform_and_its_sensor_is_opt_in` (`# ported: McpGuidanceTests.requestInputInSinkIsACheckToPerformAndItsSensorIsOptIn`)
  - `test_a_query_holding_the_seeded_value_matches_no_row`: the raw value, its upper-case form and a substring of it each give `matched == 0` (scenario row 3).
  - `test_a_query_by_parameter_name_finds_its_row`
  - `test_a_query_holding_a_masked_parameter_name_or_segment_matches_no_row`, at `MASKED`, `METADATA_ONLY` and `FULL`: `AKIAIOSFODNN7EXAMPLE` as a parameter name and as a file segment gives `matched == 0` (scenario row 29).
  - `test_get_side_effects_is_listed_only_while_a_side_effects_sensor_records` (scenario row 15)
  - `test_the_live_cli_catalogue_lists_side_effects_only_while_a_sensor_records_and_404s_otherwise` (`# adapted from: AbstractCliConformanceTest.testCliAgentCommandsSayTheAgentIsNotAttachedAndTheOthersAreNotServed`, the side-effects tool only; scenario row 15)
  - `test_mcp_and_cli_side_effects_answer_the_same_rows` (scenario row 16)
  - `test_the_limit_is_clamped_and_a_negative_one_takes_the_default`
  - `tests/cli/test_manifest_drift.py` stays green after `uv run python scripts/dev/gen_cli_manifest.py`.
- [ ] **Step 2: Stub** the tool returning the unavailable report; run with `-n auto`. Expected: assertion failures.
- [ ] **Step 3: Implement**, regenerate `cli/tools.json`, update the five `w6-S2.tsv` rows from "not advertised" to their new state (row 16: listed and served only while a sensor records, 404 otherwise).
- [ ] **Step 4: Run** the new files, `tests/cli/`, `tests/fastapi/test_w6_sensor_floor_tools.py`. Expected: pass.
- [ ] **Step 5: Commit** `feat: serve side-effects rows to agents and the CLI`.

### Task 12: Safety: canary and reads

**Files:**
- Create: `tests/safety/test_security_sinks_rows_safety.py`
- Modify: `tests/fastapi/test_w6_sensor_floor_api.py` (`test_sensor_reads_have_no_side_effects`, `:249`), `tests/safety/README.md` (one line)

- [ ] **Step 1: Write the tests** (they pass if Tasks 9 to 11 are right; each is first run against a planted defect to see it red: a `rawHash` key added to `row_dto`, the raw name passed to `detail`):
  - `test_a_seeded_value_and_the_hashes_reach_no_side_effects_output_at_any_exposure`: an app with the setting and the three sensors on; one request carries a canary query value `cnry7Q4x` and opens a path holding it, starts a command with it as an argument, and a second request carries another value to confirm the row. At `MASKED`, `METADATA_ONLY` and `FULL`, read `GET side-effects`, `GET side-effects/sensor?sensor=` for each of the nine sensors and for pages 0 and 1, `get_side_effects` over MCP with no query, each sensor id, the parameter name and the canary, and `sharpit side-effects` through the CLI endpoint with the same queries. No body holds the canary, the strings `rawHash` or `redactedHash`, or the decimal form of any hash the store holds (scenario row 2).
  - `test_a_seeded_value_reaches_no_route_log_or_error`, plan 1's all-routes canary, parametrized over `MASKED`, `METADATA_ONLY` and `FULL` and run after plan 2's row shape: Tasks 2 and 3 add `callSite`, `requestId`, `at`, `positionUnknown` and `threadName` to journal rows, which the journal's readers (`insights/snapshot.py:140`) also serve (scenario row 30).
  - `test_no_seeded_value_reaches_any_report_or_row_even_a_four_character_one` (`# adapted from: SecuritySinksServiceTests.noSeededValueReachesAnyReportOrRowEvenAFourCharacterOne`, command and file sinks)
  - `test_side_effects_reads_have_no_side_effects`: each read above under the `no_side_effects` fixture, after rows are queued so the read drains and resolves (scenario row 5).
  - `test_a_cross_site_or_forwarded_read_of_side_effects_rows_is_refused`: with rows queued, `Sec-Fetch-Site: cross-site`, a foreign `Origin` and an `X-Forwarded-For` header each get the guard's refusal on both routes, and the body holds no row (scenario row 8).
- [ ] **Step 2: Run** `uv run pytest -q -n auto tests/safety tests/fastapi/test_w6_sensor_floor_api.py`. Expected: pass; the planted defects were seen red.
- [ ] **Step 3: Commit** `test: prove no request value or hash leaves the side-effects store`.

### Task 13: The Side Effects view

**Files:**
- Create: `ui/src/views/SideEffects.svelte`, `ui/tests/component/sideEffects.test.ts`
- Modify: `ui/src/App.svelte` (register the view as the other views are), `src/sharpit/ui/static/` (rebuilt)

**Interfaces:**
- Consumes: `GET {api}/side-effects` and `GET {api}/side-effects/sensor?sensor=<id>&offset&limit`.
- Port of VUE: tabs by sensor in catalogue order (`SideEffects.vue:25`); a not-available sensor shows its reason without a fetch; the security-sinks columns `{target: 'Sink (value redacted) or check', count: 'Times', parameter: true, origin: true}` (`:136`); the parameter in `<code class="side-effects-parameter">` (`:726`); the detail line `.side-effects-detail` (`:723`); limitations in a `<details>` (`:525`); the empty-state texts (`:148-149`). Every row string is rendered with Svelte's text interpolation, never `{@html}`.

- [ ] **Step 1: Write the failing vitest tests** (jsdom, as the other files in `ui/tests/component/`):
  - `shows security-sinks rows with the parameter name and the fact, never as a vulnerability` (`// adapted from: SideEffects.test.js:873`, a command row: `.side-effects-parameter` is `name`, the detail holds `Check that it is validated.`, no `vulnerab` in the table text)
  - `renders the sensor tabs and not-available sensors without sensor fetches` (`// adapted from: SideEffects.test.js:153`)
  - `shows file rows by pattern and location` (`// adapted from: SideEffects.test.js:757`)
  - `renders row text as text, never as HTML`: a target `<img src=x onerror=alert(1)>` appears as text and adds no element (scenario row 25).
  - `shows the empty state and the limitations`
- [ ] **Step 2: Run** `npm test` in `ui/` (background). Expected: failures, the view missing its content (create the file with an empty component first so the red is an assertion).
- [ ] **Step 3: Implement** the view; run `npm run check` and `npm test`.
- [ ] **Step 4: Build** with `npm run build` in `ui/` (background) and commit the changed files under `src/sharpit/ui/static/`; the CI UI build-drift job must pass.
- [ ] **Step 5: Commit** `feat: show side-effects rows in the console`.

### Task 14: Documentation and release notes

**Files:**
- Modify: `CHANGELOG.md` (`[Unreleased]`), `website/docs/settings.md:90` and the `SHARPIT_AGENT_SECURITY_SINKS_REQUEST_VALUES` row plan 1 added, `skills/sharpit/SKILL.md:162`, `SECURITY.md` (the paragraph plan 1 added), `docs/reference/matrix-updates/0.10.0-security-sinks.tsv` (append; created by plan 1)

- [ ] **Step 1: Write** the changelog entry for plans 1 and 2 together: the opt-in security-sinks sensor, the Side Effects panel with the `processes`, `files` and `security-sinks` tabs, `get_side_effects` and `sharpit side-effects`; and, verbatim: "SQL statements and outbound URLs are not checked: the security-sinks sensor covers commands and file paths only."
- [ ] **Step 2: Update** the settings rows (the three sensors now feed the Side Effects panel), the `skills/sharpit` table line (the panel shows rows; `get_side_effects` is listed while a sensor records), and `SECURITY.md`: rows hold no request value; the hashes stay in memory inside the store and leave it in no output; secret-looking path segments and parameter names are masked at every exposure; a request with no route template is attributed to its path as the capture already reduces it before the journal (`route_of`, for example `/static/{value}`), then masked per segment.
- [ ] **Step 3: Append** one matrix line each for N1, N2 (with its outcome from Task 3), the ported O1 and O2 rows, F1 to F11, and every *Open deviation* as decided; update plan 1's D8 line per F4.
- [ ] **Step 4: Run** `uv run pytest -q -n auto tests/test_*.py tests/docs tests/cli/test_docs.py`, `uv run ruff check`, `uv run ruff format --check`. Expected: clean.
- [ ] **Step 5: Commit** `docs: describe the side-effects rows and what they do not cover`, then run `/sharpit:check`, `/sharpit:live-verify` (an endpoint that opens a requested path and starts a command; the panel, the REST routes and the tool show the row; a second request confirms a digits-only one), `/sharpit:branch-review`, and `/sharpit:llm-council --tier high`.

## Definition of done

- [ ] All steps checked; every Critical and High scenario row has its named test, seen red first.
- [ ] `/sharpit:check` green; overhead budgets unchanged at 6 µs; no module over 1000 lines; no C901 baseline raised.
- [ ] N2's outcome recorded; every open deviation decided before its code landed.
- [ ] Matrix lines appended; `w6-S2.tsv` rows updated; release notes say SQL and outbound URL sinks are not covered.
- [ ] `/sharpit:live-verify` evidence for the routes, the tool and the view.

## Review notes

A design review of this plan raised findings that are folded into the tasks above. The ones not folded, and the reason:

- A review proposed naming each request's route at request end, on the request thread, through a bounded id-to-route map. The plan keeps BootUI's waiting observations and resolves them on every read from the events the journal still holds; F6 records the effect on rows whose `http` event was evicted.
- A review noted that with the lane attached and every ringed sensor off, the unavailable-tool answer names the panel's fixed reason, not the sensor to switch on. Not folded: the answer is BootUI's (`McpDispatcher.unavailableTool`, ported at `tool_dispatch.py:155-164`), and a sensor-specific text has no BootUI source.
- A review noted that two secret-looking names on one target cannot be told apart. Accepted under N1: masking at intake makes them one row.
- A review asked for `test_the_tee_takes_no_lock`, which inspected the bytecode, to be dropped: it could not fail for a real defect. Dropped; the overhead budget test is the control.
- A review noted that the insights snapshot reads only `PRODUCED_SOURCES` (`insights/snapshot.py:26`), which excludes `security-sinks`. No change is needed.
- A review noted that an untemplated route is already reduced before it reaches the journal, so scenario row 19 exposes less than first written. Task 14's `SECURITY.md` sentence says so.
- The lock-free ring append and the advisory counters are not verified on free-threaded CPython; they are listed under *Not checked* in the scenario file.
