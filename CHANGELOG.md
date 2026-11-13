# Changelog

All notable changes to sharpit are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.6.0] - 2026-11-13

### Fixed

- Runtime insights leave out, and count in the check's reason and the report's limitations, a request that started before events the journal evicted or cleared (BootUI's `LEFT_OUT_BEFORE_LOSS`): a request that lost its statements is no longer reported clean, including one whose statement was larger than the journal's whole byte bound, and the window's request count and the coverage no longer include a left-out request or its events, and a trace-only event of one joins no later request that shares its trace.
- The log handler no longer holds its own lock across the journal offer: a GC finalizer logging on a thread that held the journal lock could deadlock against another logging thread, and hang interpreter exit. The pytest plugin's exception handler no longer holds its own lock across the sink's, and the log tail buffer's `append` and `clear` and the exception-mark lock drop a finalizer's record on a thread that already holds them, never wait on it. The finalizer's record on a thread holding the journal lock is counted `reentrant`.
- Runtime insights treat SQL capture that is switched off as a state, not a clean result (BootUI `SqlCapture.DISABLED`). SQL trace flag off, sql-trace panel on: a check that requires SQL evidence (`safe-method-dml`) is UNAVAILABLE with the capture reason, and a check that reads it optionally is evaluated and carries the caveat. sql-trace panel off, flag on or off: a check that requires SQL evidence is NOT_APPLICABLE (the disabled-panel reason wins), and an optional reader carries the caveat. Both on: unchanged. Whether SQL is recorded at all is one per-context fact (BootUI `SqlCapture.of`, `hasWrappedDataSource`): a SQLAlchemy engine registered with the context, or any SQL statement routed to it (write-once, so a paused or suspended capture keeps it). With neither, a SQL-reading check is UNAVAILABLE (`NOT_RECORDED`); with the hook of one database in use suspended it is evaluated with a caveat naming what is missed; with every such hook suspended it is UNAVAILABLE. The sql-trace panel off with the flag on no longer names the flag. The SQL Trace panel and its reads keep their availability (BootUI makes them unavailable until a DataSource is wrapped: a deviation row).
- Runtime journal: an offer made while the same thread holds the journal lock (a garbage-collection finalizer that logs during `records`, `view`, `status` or an append) is refused and counted `reentrant`, instead of raising "deque mutated during iteration" or running host code under the lock. The host copy of an offered event now runs before the lock is taken, and an offer made from inside that copy is refused and counted `reentrant` as before.
- Runtime Insights counts a journal source as evidence only while its panel is enabled (BootUI `visible()`/`available()`): a disabled panel reads as absent evidence and the check names it; with the http-exchanges panel off, a kind that examines requests answers not applicable for its unit-of-work evidence.
- The live BootUI capture rejects every request outside GET and the allow-listed POSTs, keys uncaptured routes individually, and confines raw output outside git work trees. Machine identity values, including short logins and home path variants, are retained by the artifact leak gate.
- In test fixtures, `golden._folder()` honours `fixture_version` when `ROOT` has been patched, selecting the versioned fixture folder instead of an unversioned one.
- BootUI 2.3.0 test catalog lists test classes outside `src/test`, including abstract base classes in the `bootui-conformance` module (`AbstractMcpConformanceTest`, `AbstractBootUiApiConformanceTest`, `AbstractCliConformanceTest`, `AbstractCorrelationCoverageTest`).
- MCP negotiates only protocol revision `2025-06-18`, while retaining BootUI's supported-version list in status. A `2026-07-28` header is now refused as BootUI refuses it (it used to be accepted).
- Email dev trap: an `aiosmtplib` imported after `install()` (inside a handler or a background task) is now wrapped the moment it loads, so the trap holds and its mail is captured; while a dev trap is on, an `aiosmtplib` the hook cannot wrap (a loader it cannot patch, a failed wrap, a registry lock still busy after 5 s, no wrapped `connect`) is not imported: `import aiosmtplib` raises `ImportError` naming the dev trap and none of the package stays loaded, instead of sending real mail unwrapped (BootUI fails open here; with no trap on the module loads as before); a non-ASCII address no longer makes the capture fail.

### Added

- Runtime insights `safe-method-dml` (a GET or HEAD request that executed an INSERT, UPDATE, DELETE or MERGE, one finding per route naming the verb, never the statement); `lazy-sql-after-handler` answers not applicable because sharpit marks no handler end.
- Email panel (GET /email, /email/{id}, /email/{id}/eml, DELETE /email, get_emails, CLI mail): outgoing mail captured at `smtplib` and `aiosmtplib` `sendmail`, bounded, with SHARPIT_EMAIL_MAX_ENTRIES, _MAX_BODY_LENGTH, _DEV_TRAP and _MASK_CONTENT; secret-shaped text is masked even when content is shown, unless the exposure is FULL; the dev trap never connects.
- Internal: a shared class-method wrap helper for capture integrations (`engine/capture/wraps.py`).
- Runtime journal `sql` source: one literal- and parameter-free event per executed statement (BootUI `SqlPayload`), joined to its request by `requestId` or `traceId`; the runtime insights now treat `sql` as recorded when enabled.
- Runtime journal `connection` source: one event per logical connection the application releases (BootUI `ConnectionPayload`: data source, held time, monotonic checkout time; `statements` is always -1, unknown, so no statement pays for a count), joined to its request by `requestId`; `waitNanos` is always 0 because SQLAlchemy reports no wait.
- Runtime insights `connections-per-request` (BootUI `ConnectionsPerRequest`): a route whose request held two or more connections of one data source at the same time, from the `connection` journal events' checkout time and held time, with the hold-and-wait pool estimate when the pool's maximum size is known (a queue pool's size plus overflow); a connection with no data source name is counted apart and named in the check reason.
- Agent sensors `processes` and `files` (`SHARPIT_AGENT_SENSORS`, off by default): one resident, inert `sys.addaudithook` dispatcher records the commands the app starts (file name only) and the files it opens, deletes, moves and copies (path patterns only) into the runtime journal; the `files` sensor switches through the Java Agent sensor action.
- Runtime journal `exception` source: the exception store offers one metadata-only event per captured exception (class, group id, line-free signature, class chain up to 8 causes deep; never the message, `args` or a frame; BootUI `ExceptionPayload`), so the insights treat `exception` as recorded when enabled.
- Runtime journal `log` source: the log handler offers one event per WARN-or-above record (logger, `WARN`/`ERROR`, the unformatted `msg` template masked and cut at 500 characters, exception class), so `framework-warnings-by-route` and `errors-behind-2xx` see them whenever `log` is in `runtime_journal_sources`, even with the Log Tail and Exceptions panels off (as BootUI installs its journal appender with the journal). An argument never enters the journal, but an f-string (or `str(exc)` concatenated into the message) IS `msg`: it is shown masked at MASKED and unmasked at FULL, withheld at METADATA_ONLY (BootUI `LogPayload` has the same limit).
- Exceptions panel: an exception's detail lists up to 8 causes, as BootUI 2.3.0 (`ExceptionStore.MAX_CAUSE_DEPTH`); it was 5.
- Runtime journal `http` source: the capture middleware offers one metadata-only event per finished request (method, masked path, route template, status, duration, request and trace id; BootUI `RequestCorrelationFilter.publish`), so `ai-usage-by-route` (the only insight reading real requests today) sees them when `http` is in `runtime_journal_sources`.
- Alembic panel: `POST /alembic/migrate` runs `python -m alembic upgrade heads` in a child process (confirm must be `true`, single-flight, gated like BootUI's Flyway migrate).
- Alembic panel: `POST /alembic/clean` runs `python -m alembic downgrade base` in a child process, off by default (`SHARPIT_ALEMBIC_CLEAN_ENABLED=true`, checked before `confirm: true`); it shares migrate's single-flight and the report's `cleanEnabled` is now real.
- Cache clear action (REST POST {api}/cache/clear, BootUI parity) behind confirmation and SHARPIT_CACHE_CLEAR_ENABLED (off by default) for functools and cachetools caches; reachable once the Cache read panel lands.
- GitHub dashboard (`GET /github`, `get_github_dashboard`, CLI `github`): local repository identity and cached report, read without network access.
- GitHub refresh action (`POST /github/refresh`, REST only): calls the GitHub REST API with `GITHUB_TOKEN`, `GH_TOKEN` or `gh auth token`, never follows redirects, refused when the panel is read-only.
- Scheduled Tasks panel (GET /scheduled, get_scheduled_tasks, CLI scheduled): in-memory APScheduler 3 jobs and arq cron jobs, never a remote job store.
- SQL Trace `requestPhase` is `STARTUP` or `SHUTDOWN` for statements outside a request while sharpit observes the host's lifespan in that phase; null (unknown) otherwise.
- `pytest --sharpit-sarif=PATH` (ini `sharpit_sarif`) writes the findings as SARIF 2.1.0: masked text, root-relative URIs, location-free fingerprints, baselined findings as suppressions; written by the xdist controller only.
- REST API error contract (GET /rest-api/error-contract): the app's exception handlers by type, scope and declared status, read from declarations only (BootUI 2.3.0).
- REST API rules RAPI-ERR-004, -005, -007, -008, -010 on the error contract; RAPI-ERR-011 kept as retired (BootUI 2.3.0).
- Runtime Insights panel slot (`runtime-insights`), the registry of BootUI's 28 insight kinds (each a stub until ported), and SHARPIT_RUNTIME_INSIGHTS_AI_TOKEN_THRESHOLD and SHARPIT_RESOURCES_JFR_MAX_DURATION.
- Runtime Insights engine: the journal projected into a snapshot, a report of per-kind checks, coverage and window over the sources a merged producer publishes (a kind reading an unproduced source is not applicable), and BootUI's per-kind default-listing outcomes. No route or tool yet.
- Runtime Insights is served: `GET {api}/runtime-insights`, `GET {api}/runtime-insights/insights/{id}`, MCP `get_runtime_insights` and `get_runtime_insight` (CLI `insights list` and `insights show`), and the Profile resources floor (`GET`/`POST {api}/runtime-insights/resource-profile` and `/stop`): sharpit has no resource sampler, so it answers `UNAVAILABLE` and starts nothing.
- Runtime insight `ai-usage-by-route` (model calls, agent loops, input growth, length-limited stops and tokens per route, read from `ai` events joined to http requests by request or trace id; reads `SHARPIT_RUNTIME_INSIGHTS_AI_TOKEN_THRESHOLD`) and `work-after-response`, which stays not applicable because no `agent.executors` producer exists.
- Runtime insight `route-time-breakdown` (a route's warm requests split into SQL and unattributed time, cold request apart, overlapping statements counted once; statements are placed on the request by the monotonic clocks the http and sql events carry, and sharpit records no handler, authentication, connection, REST client or authorization phases).
- Runtime insight `errors-behind-2xx` (2xx requests behind a rolled-back transaction, an exception, an ERROR log or a failed downstream call): it reads `transaction`, `exception`, `log` and `rest-client` events that no sharpit producer writes yet, so it answers not applicable.
- Runtime insights `exception-hotspots` (exception groups per route, a specific check for well-known SQLAlchemy exceptions, groups seen only behind 4xx counted in one row) and `framework-warnings-by-route` (WARN and ERROR events from uvicorn, starlette, fastapi, sqlalchemy and other framework loggers, per route, plus framework ERRORs with no request id): both read only journal fields, never an argument or message, and say so when METADATA_ONLY withholds the request ids.
- Profile Diff panel (GET /profile-diff, get_profile_diff, CLI profile diff): the app's .env.<profile> files, masked like Configuration.
- Copilot panel (GET /copilot/*, get_copilot_sessions, CLI sessions copilot): local Copilot CLI sessions, allow-listed fields only, no watcher thread; raw reveal off by default.
- Claude Code panel (GET /claude-code/*, get_claude_code_sessions, CLI sessions claude) and the session streams (GET /copilot/stream, /claude-code/stream), polled per stream with no background thread.
- AI Framework panel (GET /ai/overview, /ai/chats, /ai/chats/{spanId}, /ai/tokens, get_ai_overview, CLI ai overview): GenAI spans from the app's own OpenTelemetry SDK; prompt and completion content hidden unless SHARPIT_EXPOSE_VALUES=FULL.
- Agent-sensor panel floor (Java Agent, Code Inventory, Code Paths, Side Effects; get_agent_status, enable/disable_agent_sensor, CLI agent status): BootUI's shapes, unavailable with the reason; sensor actions refused as BootUI refuses them without the agent.
- Runtime journal records ai events (operation, provider, model, tokens, finish reason) from GenAI spans.
- Startup Timeline panel (GET /startup, get_startup_timeline, CLI startup) with SHARPIT_STARTUP_ENABLED and SHARPIT_STARTUP_CAPACITY: host lifespan startup timing.
- Low-footprint controls on the Live Memory panel, CLI, and guarded API; idle capture suspension uses a lifespan-managed daemon timer.
- Metrics panel (GET /metrics, /metrics/detail, get_metrics, CLI metrics) over the host's prometheus_client registry, label values masked.
- Config overrides actions (`POST {api}/config/overrides`, `DELETE {api}/config/overrides/{name}`), REST only, behind the guard, the Configuration panel gate and read-only; the config report now flags overridden properties (`override`, `overrideCount`, `overridesOnly`).
- W8 action groundwork: the Configuration panel is action-capable as in BootUI (read-only now reports and refuses its writes), Cache and Dev Services panel slots, and SHARPIT_OVERRIDES_FILE, SHARPIT_ALEMBIC_CLEAN_ENABLED, SHARPIT_DEV_SERVICES_RESTART_ENABLED, SHARPIT_CACHE_CLEAR_ENABLED.
- BootUI 2.3.0 parity tests for the security advisor rules with location-only assertions and leak prevention.
- Production-gated the five security rules BootUI suppresses outside production and added a partial local JWT audience check.
- BootUI 2.3.0 parity tests and tracker markers for architecture advisor rules (`ARCH-*`) in `tests/parity/test_rules_architecture_23.py`.
- Architecture rules ARCH-CODE-009 (uses of PEP 702 deprecated application symbols, incl. same-module and relative imports) and ARCH-SPRING-015 (mutable pydantic `BaseSettings` fields, per field, subclasses included), Python analogues of BootUI's rules.
- BootUI 2.3.0 rule markers and source citations for existing REST API fire/pass tests.
- BootUI 2.3.0 REST API rule parity tests (`tests/parity/test_rules_rapi_23.py`): fire and pass cases per rule, 2.3.0 severities, handler locations, and a planted-secret leak test.
- REST API RAPI-VER-001 no longer counts generated documentation routes (`/v3/api-docs`, `swagger-ui`) as API handlers (BootUI 2.3.0 `isNonApiEndpoint`).
- BootUI tracker row markers on matched property and MCP/CLI parity tests.

- Attempt-1 CI critical-path table measurement tool (`scripts/ci/ci_walls.py`) reproducing metrics (a) and (b), queue wait, step timings, and noise gain calculations per spec §7.1.
- Panel GET route parity tests and classification against BootUI 2.3.0 live goldens, excluding fixtures with empty lists from matched parity (W3 lane C1).
- Live BootUI 2.3.0 capture runner (`scripts/capture_bootui_live.py`) with a hard allow-list covering advisor scans and database reads, forbidding raw reveals and destructive actions, and recording uncaptured endpoints with status.
- Machine values leak gate generator (`scripts/dev/machine_values.py`) collecting workstation identifiers and environment secrets to gate fixture commits via `scripts/ci/artifact_scan.py --values-file`.
- Sanitised BootUI 2.3.0 live goldens with route completeness and empty-list metadata.

- A bounded in-memory runtime journal behind a `JournalSink` port (`NULL_SINK` when off), with the
  `runtime-journal.enabled/max-events/max-bytes/queue-capacity/sources` settings (BootUI defaults; `max-bytes` is a
  fixed 32 MiB), drop counters by source, read-time masking, and a live `GET /activity/journal` status. It is a
  capture-hook registry entry (`runtime-journal`): suspending it refuses events and counts them.

### Changed

- `import sharpit` no longer imports `sharpit.fastapi` or FastAPI: `sharpit.install`, `attach_sql_sources`,
  `detach_sql_sources` and `record_security_event` are imported on first access, so the pytest plugin starts faster.
- Added an engine-owned capture-hook registry and low-footprint suspend/resume service; each capture hook the FastAPI wiring installs (middleware recording, exception handlers, log handler, security-log hook, SQLAlchemy and sqlite3 listeners, traces and transactions lanes) is its own registry entry, suspended and resumed alone.
- MCP method dispatch now uses a method-to-handler table while preserving existing response construction.
- The golden sanitiser now validates nested capture versions from the source, rejects encoded and provider token variants, and limits 2.3.0 raw enum snapshots to 64 enum constants per key path; versioned shaping retains the 0.6.0 default for existing callers.
- CI can be dispatched manually for attempt-1 noise measurements, and an always-running `live-check` now aggregates
  every live leg. The workflow must first reach the default branch for GitHub to dispatch it.
- The Ubuntu 3.14 test-shard and masking-gates legs install the `full-extras` dependency group and publish JUnit evidence
  under the artifact names the reader already accepts; the live legs install the same locked driver versions through
  that group.
- Every CI artifact upload is scanned for planted canary values before upload; an artifact carrying a canary in any
  form (raw, URL-encoded, JSON-escaped, base64) is withheld and skips the upload.
- The masking linearity gate reuses first-attempt timings across adjacent size steps.
- The masking mutant gate computes each unmutated baseline once per surface and seed set in each worker.

### Documentation

- Added user documentation for pytest gate failures, exit statuses, fail-closed unknown results, report-only mode and baselines.
- Every MCP tool and every setting is documented, and the installation page has the panel to library to extra table: the MCP page lists the 37 read tools and, separately, the 17 action tools (CLI endpoint only, never MCP); the settings page lists the 28 settings it was missing (`SHARPIT_APP_PACKAGE`, `SHARPIT_TRANSACTIONS_*`, `SHARPIT_POSTGRESQL_MAX_*`, `SHARPIT_MYSQL_MAX_*`, `SHARPIT_DATABASE_ADVISOR_MAX_*`, `SHARPIT_ARCHITECTURE_MAX_*`, `SHARPIT_SECURITY_LOGS_MAX_LOGS`, `SHARPIT_ACTIVITY_UNBOUNDED_READ_FACTOR`) and all 31 panel ids; `tests/test_tracker_docs.py` fails when a registered tool, a setting or an extra is missing from the docs.

### Known limitations

- SQLAlchemy's class-level listeners (`Engine` statement events, `Pool` checkout and checkin, `Mapper` load, the
  transactions panel's checkin) are added and removed at runtime when a hook is first attached, suspended, resumed or
  uninstalled. A host call that SQLAlchemy is dispatching at that moment on another thread can fail with "deque
  mutated during iteration". This was already true in 0.5.0; a fix for every class-level listener is planned for 0.7.0.
- `connection` journal events: `statements` is always -1 (unknown, so no SQL statement pays for a count; only BootUI's
  `ConnectionReacquisition`, not built yet, reads it) and `waitNanos` is always 0 (SQLAlchemy reports no pool wait).
- The SQL Trace panel, its report, insights and MCP/CLI reads stay available before any database is in use; BootUI
  makes them unavailable until a DataSource is wrapped (planned for 0.7.0).
- Runtime insights: after a SQLAlchemy listener attach that failed (or after `uninstall_capture()`) with an engine
  registered, a SQL-reading check still reads as recorded.
- On SQLite, a double-quoted run that names no column is a string, so with parameter capture off sharpit can show a
  literal value it reads as an identifier (#59, unchanged since 0.4.0).
- Masking a quoted text twice can mask it differently from BootUI, which masks it once (cosmetic; planned for 0.7.0).
- The transactions journal source (P-transaction) is not in this release (planned for 0.7.0).

## [0.5.0] - 2026-11-08

### Added

- Scheduled Tasks panel (GET /scheduled, get_scheduled_tasks, CLI scheduled): in-memory APScheduler 3 jobs and arq cron jobs, never a remote job store.
- `transactions` panel: SQLAlchemy transactions per request (status, duration, savepoint depth, connection hold time) in a bounded ring, with slow-transaction and connection-hold thresholds; error messages masked; MCP read tool. Settings `transactions_*`.
- `mysql` panel: MySQL and MariaDB vital signs, sessions, statements, indexes, tables, lock waits, replication and settings, read on an explicit `POST {api}/mysql/read` through a verified read-only session with statement and lock timeouts and row limits; statement text normalised, masked and truncated at 400 characters. Settings `mysql_max_*`. `asyncmy` and `mysqlclient` are untested.
- `security-logs` panel: 401 and 403 responses recorded as `AUTHENTICATION_FAILURE` / `AUTHORIZATION_FAILURE`, filterable by principal, type and time, with a stream and MCP `get_security_logs`. Needs the capture middleware.
- `sharpit.record_security_event(type, principal=None, data=None)`: records an audit event (for example `AUTHENTICATION_SUCCESS`) for the current request. It never raises and does nothing outside a request, with sharpit inactive or with the panel disabled.
- `fastapi-security` panel (BootUI's `spring-security`): routes, their security dependencies and scopes, and an explain view for a path.
- `security` advisor: 27 rules (21 ported, 6 sharpit-only) over CORS, trusted hosts, auth dependencies, configuration and source literals; the catalogue and the 33 dropped BootUI rules with reasons are in `docs/security-advisor-checks.md`.
- `database-advisor`: 33 checks over the bounded schema catalog, SQLAlchemy engine and pool settings, mapped models (`install(models=...)`), the SQL Trace window and PostgreSQL/MySQL vendor catalogs; read in one read-only transaction; the 15 dropped BootUI checks are listed with reasons in `docs/database-advisor-checks.md`. Settings `database_advisor_max_*`.
- `architecture` advisor: 20 `ARCH-*` rules over the application's import graph (package cycles, module isolation, layering, coding practices, `pyproject.toml` import-linter contracts). Settings `architecture_max_files`, `architecture_max_file_bytes`.
- `fastapi` advisor (BootUI's `spring`): 10 rules over route handlers and the app (blocking calls in async handlers, background tasks, Pydantic models, response models, events, exception handlers); catalogue in `docs/fastapi-advisor-checks.md`.
- Each advisor scans on `POST {api}/<advisor>/scan` or through the HTTP CLI tool (`POST {api}/cli/tools/<advisor>_scan`, with `-` as `_`; sharpit ships no console script); `GET` returns the last scan, violations page per rule; MCP tools are read-only.
- SQL Trace insights: `GET {api}/sql-trace/insights`, statement rankings and per-route attribution (top 20 routes, by masked path, joined on the request id); MCP `get_sql_trace_insights` and CLI `sql-trace insights` (sharpit-only). With HTTP exchange capture off, route attribution is unavailable and the rankings stay.
- `install(app_package=...)` (env `SHARPIT_APP_PACKAGE`): the dotted package the advisors and config scan read, resolved through `sys.modules` only, never imported. Source reads go through one bounded index (file count, size and time limits, no symlinks followed).
- `sharpit.unbounded-read` gate: during a test, an ORM read that loads at least twice the bound page size in a request to an endpoint with paging parameters is a finding; marker `@pytest.mark.sharpit(allow_unbounded_read=True)` relaxes it. Needs `sharpit.install`.
- BootUI 2.2.0 capture drift: `http-exchanges` rows carry `route`, `routeSource` (`FRAMEWORK_TEMPLATE` or `MASKED_PATH`) and `requestId`, the report carries `retention`, `GET {api}/http-exchanges?route=` filters by route and `GET {api}/http-exchanges/routes` rolls up per-route counts, errors and p50/p95/p99 (MCP `get_http_routes`, CLI `http routes`); `sql-trace` entries carry `durationMicros`, `requestId`, `executionId`, `threadKind` and `requestPhase` (the last three null) and the report `retention`; `exceptions` groups carry `lastRequestId` and `lastExecutionId` (null); `log-tail` lines carry `messageOmitted`; `GET {api}/exceptions/caught` answers `available: false` (sharpit has no caught-exception sensor); `activity` gains the 2.2.0 profile keys, entry `badges` (empty) and `exceptionGroupId`, the KPIs `latencySampleCount` and `slowestEndpointRoute`, `slowestEndpointRouteId`, `slowestEndpointRouteSource`, `GET {api}/activity/journal` and `GET {api}/activity/resources` (both report unavailable: sharpit keeps no runtime journal and samples no memory or CPU) and MCP `get_request_profile` (CLI `activity profile`); `get_live_activity`, `get_sql_traces` and `get_log_tail` take a query and a limit. Memory keys, the journal clear route and compacted default limits for these tools are not built.
- BootUI 2.2.0 drift for `vulnerabilities`, `mcp-server` and `rest-api`: the vulnerabilities report and its dependencies carry `runtimeReach`, `advisorySymbols` and `advisorySymbolSource` (reported unavailable, empty and `NONE`), and `get_vulnerabilities_report` returns a compacted view (default limit 10); the `mcp-server` status lists protocol `2026-07-28` ahead of `2025-06-18` and gains `cancellations` (counts `notifications/cancelled`; calls are synchronous, so a cancel cannot stop one) and `progressDropped` (always 0, sharpit sends no progress notifications); the `rest-api` advisor ports `RAPI-RESP-011` (a GET whose declared response is `X | None` with the default status) and does not port `RAPI-RESP-010`, `RAPI-VALID-006` and `RAPI-VER-007`: the reasons are in the rule registry, and no report or panel lists them. CVSS v4.0 score selection and `sampleLocations` are not done: the score falls back to the database label and `sampleLocations` stays `[]`.
- N+1 findings on a repeated statement that is not a relationship lazy load now give the application line of the repeat.
- `database-connection-pools` gains `poolLibraryPresent` and `implementation`; `readOnly`/`autoCommit` are nullable; `get_threads` defaults to 25 entries (BootUI 2.2.0).
- The `pytest --sharpit` terminal summary says which gates and advisors the run checked and which it did not, plus routes and SQL the tests did not exercise and that sharpit does no security testing.

### Changed

- The docs site uses the console's neutral palette and ochre accent; `design/` holds the tokens and rules every surface shares.

- `sql-trace` entry `timestamp` is epoch milliseconds, as the contract says; it was an ISO-8601 string. This also applies to the `sql` rows of a request profile.
- Advisor rule results use BootUI's status values: `VIOLATION`, `PASS`, `SKIPPED`, `ERROR` (were `FAILED` and `PASSED` in the `rest-api` panel). A rule whose every finding is dismissed reports `PASS`. `sharpit-report/1` (`PASSED/FAILED/UNKNOWN/SKIPPED`) is unchanged.
- `pytest --sharpit` is about 1.24x the plain run on a query-heavy suite (was about 1.48x): the test-session sink memoises the masked SQL fingerprint of each repeated statement per sink, which halved the suite overhead (2.05 s to 1.02 s on a 12,343-statement suite) and cut the per-statement hook cost from about 50 µs to about 11 µs. Masked output is unchanged, and the memo is never shared across sinks or masker settings.
- `sharpit.swallowed-exception` gate: a PEP 249 database error (`DatabaseError`, `OperationalError`, `IntegrityError`, `DataError`, `InternalError`, `ProgrammingError`, matched by class name) handled by a broad `except` that neither re-raises nor logs now fails the test, as programming errors already did; it was an INFO note in 0.4.0. `programmingError` in the report stays `false` for these. This widens the 0.4.0 rule.
- `sharpit.swallowed-exception` gate: a method call counts as logging only on a logger receiver (`log`, `logger`, `logging`, `warnings`, a `getLogger(...)` result, chained structlog loggers, and similar); passing the caught exception to a recognised sink or to a one-level helper in the same module counts as handled. Bare `log(...)`/`warn(...)` calls still count.
- `beans`: a provider class's `resource` comes from the class object (`__firstlineno__` on Python 3.13+, the first method's line on 3.12) instead of reading the source file; on 3.12 the line can differ by a few lines.
- `fastapi-security`: scopes are de-duplicated (FastAPI 0.115 accumulates `security_scopes` down the tree).
- `config`: explicit `config_scan` module names are also found on `sys.path` without importing them; undecodable bytes in a source file are replaced instead of being recorded as a limitation.
- SQLite test-session baselines use a machine-local identity key by default; set `SHARPIT_IDENTITY_KEY` to the same secret in CI jobs that compare a committed baseline.
- An unregistered engine that reports the wrong database name in an application using a different single family is read as the name it reports; a comment that family keeps can therefore remain visible.
- Test-session group keys are built from masked text, so a key changes for a statement the masker edits (`password = ?` reads `password = ****** where id = ?`). N+1 baselines and dismissals on those groups re-flag after an upgrade: 1,396 of 20,000 generic rows and 2,048 of 20,000 MySQL rows in the corpus change.
- A statement whose database family is unknown or in conflict shows nothing past a `#`, on any line: it is a comment on MySQL, an operator on PostgreSQL and a variable on SQLite.
- The SQL dialect is resolved per event from what the connection or exception proves; an application using a single database family applies that family to unwired events.
- A database driver exception shows its class, one structured code, the masked `[SQL: ...]` statement, and `[parameters: ******]` when parameters were bound, and never the driver's free-text message.
- A statement of an unsupported database family shows `[statement hidden: unsupported database]` at every exposure level, and parameter capture does not reveal it.
- Under `METADATA_ONLY` exposure, no statement text or database error text is shown; SQL Trace groups keep the masked statement shape (`SELECT ? FROM users WHERE id = ?`), never more than `MASKED` shows.

### Fixed

- Phone layout of the rail and fluid tables, heading styles, and Retry on load errors.

- Route introspection (mappings, rest-api, fastapi-security, beans) no longer drops routes of an `APIRoute` subclass set through `route_class`, no longer raises on an app object without `__dict__`, and classifies an `APIRoute` inside a plain Starlette sub-app as `unknown` instead of inspectable.
- `sharpit.swallowed-exception`: a handler that passes the exception to a helper that logs it is no longer a finding; an `error(...)` call on a non-logger object no longer counts as logging.
- A lazy load with no application frame on the stack (for example during FastAPI response serialisation) names the relationship's declaration line instead of "unknown".

### Security

- Introspection reads route, mount and router attributes from the instance `__dict__` and matches route types with `issubclass(type(route), ...)`, so a property or `__class__` defined by the application is never evaluated by a GET or MCP read.
- MySQL/MariaDB and SQLite reads run only after the session is verified read-only, and are refused on an `AUTOCOMMIT` connection.
- The database advisor reads only URL key names from an allow-list (`connect_timeout`, `charset`, `sslmode`), never a value and never the password.
- `security-logs` masks event values when they are read (keys, secret values, `Bearer`, `Basic` and `Token` credentials, `token=` text) and caps stored strings. A value over the length cap is masked at record time, before the cut, so it stays masked under `FULL` exposure; a shorter one follows the exposure setting.
- In the compacted `get_vulnerabilities_report` view, the scan message and advisory summaries and details are masked, because an OSV failure message can carry proxy credentials.
- Literals inside square brackets (`ARRAY['x']`, `ARRAY [lower($$x$$)]`, `doc['x']`, `items[3]`, `a[1][2]`) are normalised in SQL Trace and everywhere else the statement scan runs. A bracket that opens with a letter or underscore, holds only word characters and spaces and is no subscript stays readable (`[col name]`). Any other bracket is scanned as a value: `[2024 sales]` shows `[? sales]`, and the apostrophe in `[it's]` opens a string, so the statement reads `[it?` from there on.
- `mask_text` matches `Bearer`, `Basic` and `Token` in any case, takes the word `token` after a scheme (`bearer token abc123`), and masks the whole value after an `Authorization` key.
- Masking and the trace error scan no longer take quadratic time on a crafted value (runs of quotes after `token`, closing punctuation at a word's end, repeated `eyJ`, `BEGIN` or `[SQL: `, unclosed `[` or `(` after a key), so a logged client value cannot freeze the host.
- With parameter capture off, an error with an `[SQL: ` marker is masked, normalised from the marker on and masked again on every surface that shows it: `exceptions`, `log-tail`, `transactions`, `http-probe`, `health`, `alembic`, `postgresql`, `mysql`, `data`, traces, SQL Trace (also for an error raised for another statement) and the test-session report, so `[SQL: SELECT a[1], 'x']` no longer shows `'x'`. The first mask reads the raw text, because the scan turns a key or a token into `?`. They kept its literals before. Quoted values on the message's first line and the lines between it and the block (a `DETAIL:` line) are dropped there too; SQL Trace drops them before the first mask, as 0.4.0 did. An OpenTelemetry statement and the `mysql` panel's query text are masked, normalised and masked the same way.
- `mask_text` runs the 0.4.0 text pipeline first and a stricter pass over its output, so whatever either masks stays masked: a quoted value spanning lines and a secret inside a token as in 0.4.0, and a sensitive value to the end of its line, so a value with a space, a nested bracket or a closer inside a string no longer shows its tail.
- `SHARPIT_VULNERABILITIES_OSV_BASE_URI` and `SHARPIT_VULNERABILITIES_EPSS_BASE_URI` accept only `http` and `https`, because the default opener also reads `file:` and `ftp:`. Any other value takes the default and adds a warning that does not repeat the value, as a URI can carry credentials.
- ruff's `S` (security) rules run on `src/` in CI.

### Known limitations

- Post-scan or post-read goldens are absent (they need captures only the owner can make), so the parity test for each of these panels checks the pre-scan golden and skips the post-scan one: `security`, `database-advisor`, `architecture`, `fastapi`, `mysql` (a post-read golden needs a MySQL datasource on the reference app) and `vulnerabilities` (its golden is a failed-scan capture, so items are unchecked). `data` and `sqlalchemy-statistics` stay unverified: BootUI's golden list for `data` is empty and the reference app has no Hibernate statistics. `docs/reference/PARITY.md` has the per-panel table.
- `fastapi` advisor: six rules are not built (`docs/fastapi-advisor-checks.md`, "Not yet"): FASTAPI-ASYNC-003, FASTAPI-ASYNC-004, FASTAPI-DEP-001, SPRING-WEB-001, SPRING-CONFIG-002, SPRING-DATA-001. `functools.partial` and library handlers are skipped.
- `security` advisor: the masker turns `allow_credentials=True` into `******` in the CORS message; any `key="..."` keyword argument of 8 or more characters is a HIGH SEC-SRC-001 false positive.
- `sharpit.swallowed-exception` matches a database error by class name: a non-database exception named `DataError` or `InternalError` can fail a test, and a driver exception with another name that is not wrapped is missed.
- `transactions`: a connection held idle after `commit()` adds the idle time to the transaction until the next pool check-in, `begin` or `rollback`.
- `database-advisor`: models mapped to a view are reported by DB-HIB-002 (the catalog lists no views); tables outside the default schema are not compared; DB-HIB-005 is skipped on SQLite.
- `app_package` is not honoured by every advisor: `rest-api` ignores it and reads the app's routes. A package that is not imported leaves `fastapi` at `PARTIAL` with 0 handlers.
- `app_package` widens a dotted name to its top-level package, so the advisors scan sibling subpackages; only the first directory of a namespace package is scanned; `config` may pick a different root than the advisors when `install()` runs outside the package and `app_package` is unset.
- MariaDB read-only verification is tested with fakes only; the leased test checks MySQL 8.4.
- SQL Trace insights groups routes by masked path, not by route template; thread and time-window correlation are not offered.
- `pytest --sharpit` still adds about 11 µs per repeated statement (rule filtering, normalisation and counters), about 1.24x the plain run on a query-heavy suite.
- `GET {api}/activity/service-map`, `GET {api}/activity/request/{id}/journal` and `GET {api}/rest-api/error-contract` are not built: they answer 404. The BootUI goldens for the first and last stay unchecked.
- `activity` merges requests, SQL and exceptions only, so `typeCounts` never has `TRANSACTION`, `SECURITY`, `MESSAGING` or `MARKER` keys.
- `fastapi-security` reports a route guarded by `HTTPBearer(auto_error=False)` plus a check in a dependency as `secured: false` / `permitAll` with `bestEffort: true`, and drops its scopes: an anonymous request passes the scheme, and sharpit does not read the dependency's body.
- The 2.2.0 capture drift reports `activity` journal and resources, caught exceptions and the reserved retention share as unavailable (null with a reason).
- Every sharpit read through a pool that shares one connection (`StaticPool`, `SingletonThreadPool`, `AssertionPool`) is refused before the checkout, because returning that connection would roll back the host's open transaction. An in-memory SQLite host gets `SHARED_CONNECTION_REFUSED`: its health ping is `UNKNOWN`, Alembic reports the database unavailable, and the `postgresql` and `mysql` panels and advisor scans that read the database report it as an error. A connection shared through `creator=` on an ordinary pool cannot be detected.
- MySQL-aware statement normalisation applies where the dialect is known: the `mysql` panel, SQLAlchemy statements in SQL Trace, activity, insights and the test-session report (from the engine's dialect), OpenTelemetry spans that carry `db.system` or `db.system.name`, and on any span a SQL error whose text names a MySQL driver (`pymysql`, `MySQLdb`, `asyncmy`, `mariadb`, `mysql.connector`). Raw `sqlite3` statements, other text on spans without either attribute and the unbounded-read shape of a `Session` built on a binds map keep the generic scan, and their text still goes through the masker.
- `mask_text` masks a sensitive value to the end of its line: sharpit does not guess where a value ends, so whatever follows it on that line is hidden too, other keys and closing quotes or brackets included, and JSON on one line stops being valid after the first sensitive key. A quoted value is masked whole across lines, as in 0.4.0; an unquoted sensitive value stops at its line. A key's bracketed value is treated as one value up to 256 characters, a bound 0.4.0 did not have; past it the strict pass still masks a sensitive value to the end of its line.
- A driver error with no `[SQL: ...]` block keeps its values (`Key (email)=(bob@example.com) already exists`), and a MySQL replication error's `Query: '...'` text goes through `mask_text` only. Key-named secrets and credential shapes are masked in both; other literals are not.
- An error with an `[SQL: ` marker is masked, normalised and masked again. Everything after the marker is normalised, not only the statement: `[parameters: ...]` and the `Background` link too, digits and quoted text read `?`, line breaks collapse, and text past 20,000 characters is dropped. The statements stored by SQL Trace, the test session and the N+1 messages are normalised and then masked, as in 0.4.0.
- `mask_text` masks the word after `basic` or `bearer` in any case, also in English or SQL (`basic usage` shows `basic ******`, `SELECT basic FROM t` shows `SELECT basic ****** t`), and does not mask `Digest` parameter lists. With no key before it, an ordinary word or a punctuation-only value after `token` stays readable (`Token expired`, `FROM Token WHERE`), so a credential of 16 letters or fewer in one case, or of punctuation alone, is not masked there.
- On FastAPI 0.16x an `include_router` prefix cannot be recovered from the route, so those routes report `MASKED_PATH` instead of a template.
- A driver error read from text alone keeps an unquoted driver value visible in four shapes: a SQLite `ATTACH` path or a trigger's `RAISE` message on a driver line with no quote, a chain line planted by a value on the driver line, and a docs-link line planted by a value in a `StatementError` that has no link of its own. Quoted values, the `[SQL: ...]` block and its parameters stay masked.
- Text an application writes as a statement is read as SQL.
- In free text, a value with no key name before it can be shown.
- An unquoted value after `PASSWORD` or `IDENTIFIED BY` is shown as written: PostgreSQL and MySQL reject it as a syntax error, so it appears only on a mistyped, failed statement. A quoted value is hidden.
- An unproven event from a second database that sharpit has not seen is read as the application's one registered family.
- Database forks (such as Percona or Aurora) are read as their parent family; no fork runs in the live tests.
- SQL Server and Oracle statements are hidden (`[statement hidden: unsupported database]`): sharpit has no verified rules for them.
- On SQLite a `"..."` run is hidden: SQLite reads it as a name, or as a string when no column matches.
- Live fuzzing with MySQL's ANSI_QUOTES session mode is deferred past 0.5.0.

## [0.4.0] - 2026-11-02

### Added

- Scheduled Tasks panel (GET /scheduled, get_scheduled_tasks, CLI scheduled): in-memory APScheduler 3 jobs and arq cron jobs, never a remote job store.
- `traces` panel: OpenTelemetry spans from the application's own SDK `TracerProvider`, with SQL literals in `db.statement` normalised and masked; MCP `get_traces`. sharpit never imports OpenTelemetry or installs a provider, it attaches one span processor to the provider the app already set up.
- `data` panel: SQLAlchemy 2.0 mapped classes (table, primary-key type, relationships) from the new `install(models=...)` keyword (a declarative base, registry, or a list of them or of mapped classes); MCP `get_data_repositories`. sharpit never configures mappers or runs SQL to read them.
- `postgresql` panel: vital signs, sessions, statements, indexes, tables, vacuum, replication and settings, read on an explicit `POST {api}/postgresql/read` in one read-only transaction with statement and lock timeouts, a read budget and row limits; query text masked (numbers and comments too). `GET` returns the last read; MCP `get_postgresql_report`. `pg_stat_statements` created but not preloaded makes that section `SKIPPED`.
- `sqlalchemy-statistics` panel (BootUI's `hibernate-statistics`): statement counts from SQL Trace's lifetime totals, the slowest statement and N+1 candidates per route; Hibernate-only counters are `null` with a reason; MCP `get_sqlalchemy_statistics`.
- Per-finding dismissal: `GET`, `POST` and `DELETE {api}/dismissed-findings` (BootUI 2.2.0), stored under `dismissedFindings` in `sharpit.yml`; mutations check the owning panel is enabled and writable.
- Report-only mode (`--sharpit-report-only`, ini `sharpit_report_only`): findings never fail the build, any unknown reason still does. The report gains `mode` and `unknownReasons`.
- Baselines: `--sharpit-baseline=PATH` (ini `sharpit_baseline`) and `--sharpit-write-baseline=PATH`. A baselined finding is `existing` and does not fail, an unlisted one is `new`, a missing one `fixed`; a count gate above its baselined count is `new`. Writing refuses a partial run or one with unknown reasons. Vulnerability findings are not baselined.
- GitHub Action (`action.yml` at the repository root) that runs pytest with sharpit, report-only by default, and writes a findings summary to the job summary; `python -m sharpit.report summary <report.json>` renders that Markdown.
- `sharpit.swallowed-exception` gate: during a test, an exception handled by a broad `except` in application code that neither re-raises nor logs is a finding. It fails the test for programming errors (`AttributeError`, `TypeError`, `NameError`, `ImportError`, `UnboundLocalError`) and is an INFO note otherwise; marker `@pytest.mark.sharpit(allow_swallowed=True)` relaxes it.
- N+1 findings caused by a SQLAlchemy lazy load name the relationship (`Player.performances lazy-loaded 1018 times`), suggest `selectinload` or `joinedload`, and give the application line of the first lazy load and the masked statement. Fingerprints are unchanged.
- App autodetection for `pytest --sharpit`: the one FastAPI or Starlette app already imported by the suite is used without `--sharpit-app`; `--sharpit-require-app` (ini `sharpit_require_app`) restores the 0.3.0 fail-closed behaviour.
- `--sharpit-verbose` (or `-vv`) lists every advisor note in the terminal.
- Overview run metadata from BootUI 2.2.0.
- `SECURITY.md`: supported versions, private reporting, and the network-egress statement (only the OSV and EPSS clients use the network).

### Changed

- With no single app (none, several, or one without routes), the `rest-api` advisor is `SKIPPED` rather than `unknown`, so a clean suite passes; the advisor run status gains `SKIPPED` (additive in `sharpit-report/1`).
- The terminal gate counts list only findings that fail the gate; other advisor notes become one count line pointing at the report. The JSON and JUnit reports are unchanged.
- A test-runtime gate finding that failed its test is a JUnit `<failure>` under any `--sharpit-fail-on`.
- INFO findings never fail a gate, at any `--sharpit-fail-on`.
- Finding identities in `sharpit.yml` may contain inner spaces; existing entries still parse.
- The overview view is titled Scorecard, as in BootUI 2.2.0. MCP no longer suggests config property names.

### Security

- With parameter capture off, SQL Trace, traces and the test report no longer show a double-quoted SQL value or
  secret. The leak affected 0.3.0; upgrade (#41).

## [0.3.0] - 2026-11-01

### Added

- Scheduled Tasks panel (GET /scheduled, get_scheduled_tasks, CLI scheduled): in-memory APScheduler 3 jobs and arq cron jobs, never a remote job store.
- Finding contract (`Finding`, `AdvisorRun`) and advisor registry with pass/fail/unknown status semantics (#19).
- `pytest --sharpit` plugin with test-id tagging, unattributed bucket, phase split, xdist merge, and JSON (`sharpit-report/1`) and JUnit reports (#20). Count gates (queries per test with `--sharpit-max-queries`, N+1, swallowed exceptions) fail the test; advisor findings at or above `--sharpit-fail-on` fail the run; `unknown` fails it unless `--sharpit-allow-unknown` (limit for unattributed SQL: `--sharpit-max-unattributed`).
- Per-test budget marker `@pytest.mark.sharpit(max_queries=..., allow_n_plus_one=..., max_exceptions=...)` (#21).
- REST API advisor on the contract, per-finding dismissal via fingerprint in `sharpit.yml`, and panel detail action (#22).
- Raw `sqlite3` SQL source, unified source dispatcher, and public `attach_sql_sources()` / `detach_sql_sources()` helpers (#23).
- `SHARPIT_SQL_TRACE_SQLITE3_ENABLED` (`sql_trace_sqlite3_enabled`, default `true`) controls the raw `sqlite3` source in the console; `pytest --sharpit` always attaches it.

### Changed

- REST API scanner evidence for an app with no routes reports `usable: false, coverageComplete: true` (confirmed-empty scope), matching BootUI.
- REST API finding targets now name the handler (`<METHOD> <path> <module:qualname>`), so two handlers on one route stay two findings; fingerprints of 0.3.0 REST API findings depend on it.
- The test-session SQL filter treats migration tables (`alembic_version`, `schema_migrations`, `flyway_schema_history`, `django_migrations`, `knex_migrations`) as noise, not only `alembic_version`.
- A rule whose every occurrence is dismissed by fingerprint stays `dismissed: false` with a count of 0.
- The JUnit report fails only non-dismissed findings at or above `--sharpit-fail-on`.
- Secret values matching vendor token prefixes (`sk_live_`, `sk_test_`, `ghp_`, `glpat-`, `xoxb-`, `AIza`, `sk-ant-`, `sk-proj-`, and related keys) are masked.

## [0.2.0] - 2026-10-31

### Added

- Scheduled Tasks panel (GET /scheduled, get_scheduled_tasks, CLI scheduled): in-memory APScheduler 3 jobs and arq cron jobs, never a remote job store.
- F1 (HTTP Exchanges): `http-exchanges` panel and endpoint with a ring buffer of recent HTTP requests, duration, headers, status code, and path masking.
- F2 (Exceptions): `exceptions` panel and endpoints capturing unhandled errors from middleware, wrapped handlers, and log records, grouped by class and innermost application frame.
- F3 (SQL Trace): `sql-trace` panel, endpoints, and live SSE stream capturing SQLAlchemy queries via class-level events with statement categorization, normalized SQL, and slow query alerts.
- F4 (Live Activity): `activity` panel and live SSE stream correlating HTTP requests, SQL queries, and exceptions with N+1 query detection.
- F5 (Log Tail): `log-tail` panel, endpoints, and live SSE stream buffering recent logs with a 1 MiB memory cap and resume token support.
- F6 (Migrations): `alembic` panel inspecting Alembic migrations in Flyway-compatible format, with database versions read on POST `alembic/refresh`.
- F7 (Database Connection Pools): `database-connection-pools` panel and endpoint reporting SQLAlchemy pool sizes, active checkouts, and overflow status.
- F8 (Health): `health` panel and endpoint checking registered database engines via dialect ping and running custom checks on POST `health/check`.
- F9 (Threads and asyncio tasks): `threads` panel and endpoint dumping active threads and running asyncio tasks with request correlation.
- F10 (REST API advisor): `rest-api` advisor panel and endpoints running static analysis checks over FastAPI routes with severity scoring and violation paging.
- F11 (Shared advisor plumbing): shared rule definitions, single-flight scans, violation retention endpoint, and per-panel dismissal gates.
- F12 (HTTP Probe): `http-probe` panel and endpoint executing in-process ASGI calls against local routes with loopback protection and response masking.
- MCP and CLI tools for the new panels: `get_http_exchanges`, `get_exceptions`, `get_exception_detail`, `get_sql_traces`,
  `get_live_activity`, `get_log_tail`, `get_alembic_migrations`, `get_database_connection_pools`, `get_health`, `get_threads`,
  `get_rest_api_report`, `get_rest_api_rule_violations`.
- Documentation site (MkDocs Material) published to GitHub Pages; the README links to it.
- `fastapi_sqla` sample app for trying the SQL panels against a real FastAPI app.

### Changed

- Rule dismissals now check the owning panel's enabled and read-only state (`RAPI-` for `rest-api`, `::pypi:` for `vulnerabilities`), returning 403 when the panel is read-only or disabled.
- Client disconnect before response completion records status 499 in HTTP exchanges.
- Exception fingerprints group by exception class and innermost application frame rather than top stack frames.
- SQL trace uses SQLAlchemy class-level listeners rather than JDBC proxies; SQL literals are normalized and masked when parameter capture is disabled.
- Live streams (SSE) close every 3 seconds (`SHARPIT_STREAM_MAX_SECONDS`) with a retry hint to prevent blocking uvicorn reload or lifespan shutdown.
- Total concurrent live streams across all panels are capped at 20, returning HTTP 503 when full.
- Alembic database-version reads and database health checks run on POST requests (`alembic/refresh`, `health/check`) and serve cached results on GET to ensure GET requests have no side effects.
- Database connection pool reports strip query strings from database connection URLs (emitted in `jdbcUrl` for BootUI parity) to prevent secret leakage.
- Threads panel includes asyncio tasks with request correlation; OS thread states are inferred as RUNNABLE or WAITING without JVM CPU or lock metrics.
- HTTP probe executes directly via in-process ASGI calls without opening network sockets, refusing paths under the sharpit mount.
- Release workflow uploads only `.whl` and `.tar.gz` assets to GitHub Releases.
- The default branch is `main` (was `master`); CI, docs, skills and badges point at it.

## [0.1.0] - 2026-10-31

First release: an embedded, local-only developer console for FastAPI apps, ported from
[BootUI](https://github.com/jdubois/boot-ui) (Julien Dubois, Apache-2.0).

### Added

- Scheduled Tasks panel (GET /scheduled, get_scheduled_tasks, CLI scheduled): in-memory APScheduler 3 jobs and arq cron jobs, never a remote job store.
- `sharpit.install(app, settings=..., **options)` mounts the console at `/sharpit` and a BootUI-compatible JSON API at
  `/sharpit/api`. `settings=` takes pydantic-settings instances so the Config panel can show each value's source.
- Panels: Overview, Configuration (environment, `.env`, pydantic-settings and `os.getenv` keys, masked), Mappings,
  Loggers (runtime level changes), Beans (dependency providers, middleware, lifespan), Vulnerabilities (OSV scan with
  EPSS scores, on explicit request; dismissable rules in `.sharpit/sharpit.yml`), MCP Server and CLI.
- Read-only MCP endpoint (`POST /sharpit/api/mcp`, off by default; `SHARPIT_MCP_ENABLED=ON`) with the tools
  `get_overview`, `get_config`, `get_mappings`, `get_loggers`, `get_beans` and `get_vulnerabilities_report`; the CLI
  HTTP endpoint (`/sharpit/api/cli`) offers the same catalogue plus the vulnerability scan.
- Configuration through `SHARPIT_*` environment variables and `install()` keywords; the environment wins. Invalid values
  fall back to a fail-safe value and record a warning.
- Fail-closed activation: on for `SHARPIT_ENABLED=ON`, a dev profile, `uvicorn --reload` or `fastapi dev`; a `prod`
  profile switches it off unless `SHARPIT_ENABLED=ON` forces it. When off, the mount stays in place (as in BootUI) and
  every path under it answers a plain 404 from the host's 404 handler; a host with a catch-all or authenticate-first
  route answers those paths differently, so the mount can be told apart. `path="/"` and a trailing slash are refused.
- Request guard: loopback-only by default, `Host` allow-list, full-origin (API paths) and `Sec-Fetch-Site` cross-site checks on
  every method, bearer token with `HttpOnly` session cookie for untrusted sources.
- Secret masking of values, defaults and suggestions in API, MCP and CLI output, including pydantic `SecretStr` and any URL with userinfo.
- Extras `sharpit[fastapi]` and `sharpit[settings]`; typed package (`py.typed`); prebuilt UI in the wheel, so end users
  never need Node.

### Deviations from BootUI

Listed in section 14 of the design spec. The main ones:

- FastAPI only; Django and Flask are out of scope.
- A new Svelte UI instead of BootUI's Vue UI, over the same JSON contract.
- Activation uses profile variables and a dev-server signal read from the command line (no DevTools equivalent);
  `uvicorn.run(..., reload=True)` from a script is not detected.
- The cross-site check applies to every method, compares the full origin on API paths, and any forwarded header makes a caller
  untrusted unless a trusted proxy is configured.
- `defaultValue` is masked as well, because Python defaults come from code.
- Beans are dependency providers, middleware and lifespan rather than an IoC container.
- Deferred: config overrides, health, profile diff and the `sharpit` command-line client (the HTTP endpoint ships).

### Known limitations

- State (token, MCP switch, logger levels, scan cache) is per process under `--workers` and `--reload`.
- Behind a TLS-terminating proxy, uvicorn needs `--proxy-headers` for the Origin check to pass.
- Masking is name- and shape-based: vendor-prefixed tokens under harmless names (`sk_live_...`, `ghp_...`) can show.

[Unreleased]: https://github.com/ffroliva/sharpit/compare/v0.6.0...HEAD
[0.6.0]: https://github.com/ffroliva/sharpit/releases/tag/v0.6.0
[0.5.0]: https://github.com/ffroliva/sharpit/releases/tag/v0.5.0
[0.4.0]: https://github.com/ffroliva/sharpit/releases/tag/v0.4.0
[0.3.0]: https://github.com/ffroliva/sharpit/releases/tag/v0.3.0
[0.2.0]: https://github.com/ffroliva/sharpit/releases/tag/v0.2.0
[0.1.0]: https://github.com/ffroliva/sharpit/releases/tag/v0.1.0
