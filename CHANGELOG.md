# Changelog

All notable changes to sharpit are documented here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
and the project uses [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- Baseline entries record a digest of their test (`owner`); reports list `inconclusive` and `inconclusiveFindings`.
- Runtime Insights lists declared HTTP routes not exercised during the run, with report and agent limits and explicit limitations when recording loss, suspension, exposure, or missing templates prevent classification.

### Changed

- A baseline entry written before this release is inconclusive until the baseline is rewritten once with both `--sharpit-baseline` and `--sharpit-write-baseline` on a complete run; an older sharpit that rewrites the file drops `owner`.
- Runtime Insights reports the anonymous-data-reach and anonymous-success-on-restricted-route checks as not applicable, with the reason: sharpit observes no authorization decision, and a missing principal does not prove a request was anonymous. SEC-AUTHZ-002 and SEC-AUTHZ-001 cover part of it statically.
- Pentest reports describe Python host evidence and link to framework guidance where applicable.
- The pytest terminal summary lists all five runtime gates.
- The pytest terminal summary reports how many processes could not attach swallowed-exception capture and why.
- The pytest gate reports `unknown` when a hook of the pytest plugin or of its session sink fails before the report is written, or when a nested in-process pytest run ends capture early. A statement that has no text (`None`, bytes, a number or a query object, including one the stdlib `sqlite3` driver refuses) is counted once with empty text and does not make the run `unknown`.

### Fixed

- A baseline entry is reported fixed only when its test ran and completed, the run's evidence was whole and the test no longer shows it; such entries were reported fixed even when their test was deleted, skipped or failed early (#329).
- SEC-OAUTH-002 reports `jwt.decode` with `verify_signature` set to `False` in a literal `options=` keyword, also when an audience is passed, and its message is readable for a file named `auth.py` (#332).
- Pytest reports lazy-load, repeated-statement, and unbounded-read finding locations relative to the pytest root directory.
- HTTP exchange capture reads the request user as plain data and never runs a property, descriptor or `__getattr__` of it; a user whose name or authentication flag is computed is no longer named in HTTP Exchanges and Live Activity.

## [0.9.0] - 2026-11-23

sharpit 0.9.0 stays on BootUI 2.5.0 and closes part of the gaps recorded against it. These move to 0.10.0: the Flask
console (#260), the remaining journal sources (#299), route parity (#300), the `paged-without-order` insight (#301),
the masked exception message in swallowed-exception findings (#253, item 1) and trace and journal masking on the
matrix path (#302). The reasons are in `docs/reports/2026-11-23-0.9.0-decisions.md`.

### Added

- `sharpit docs` lists, reads, and searches documentation bundled with the installed package, with optional JSON output.
- Design decision records cover activation signals and WSGI request target validation.
- The documentation site publishes `llms.txt` with page links and offline lookup commands.
- The pytest accept marker takes a `reason=` that the terminal summary, the JSON report and SARIF carry with the
  accepted finding; `--sharpit-require-reason` (ini `sharpit_require_reason`) rejects an accepted finding without one
  (#253 item 2).
- Five BootUI 2.5.0 database rules: `DB-SCHEMA-011` (a `SET NULL` foreign key on a `NOT NULL` column), `DB-PG-006`
  (an empty partitioned table, adapted to `current_schema()`), `DB-SERVER-008` (MySQL strict SQL mode),
  `DB-MYSQL-004` (an unenforced MySQL check constraint) and `DB-POOL-005` (adapted to SQLAlchemy's `QueuePool` timeout).

### Changed

- The SQL listener costs about 7 µs less per statement (paired sandbox runs): context routing, call-site lookup,
  dialect resolution, OpenTelemetry span lookup and recorder bookkeeping do less work per statement.
- SQL Trace reports itself available only once a SQL source is wrapped, as BootUI does.
- The connection journal derives each connection's statement count when the connection is checked in; executed
  statements pay nothing for it. The count comes from the SQL Trace rows, which carry the connection, and is -1
  (unknown) when they cannot answer: no SQL Trace recorder, a paused panel, or rows that left the ring.
- Five BootUI 2.5.0 REST API rules that depend on Spring or Spring Data (`RAPI-MAP-012`, `RAPI-MAP-013`,
  `RAPI-VER-008`, `RAPI-VALID-007`, `RAPI-PAGE-004`) are recorded as not applicable, with their reasons.

### Fixed

- The MySQL, PostgreSQL and Database advisor tools cancel their read and release its lock when the caller times out,
  like the pentest tool (#285).
- On a host with several event loops, tool calls run on the requesting request's loop instead of the last recorded
  one (#287).
- Concurrent class-level SQLAlchemy listener attach and detach register each listener once.
- A failed SQLAlchemy listener attach is rolled back and reported as unrecorded SQL instead of looking recorded.
- An invalid `SHARPIT_EMAIL_MASK_CONTENT` value keeps email content masked and adds a warning.
- The reason on an accepted finding is masked in the JSON report and the terminal summary, as in SARIF.

### Internal

- The unused `is_validation_error` helper and a dead test clause are removed (#284, #286); two 0.8.0 tests now exercise
  the production code instead of a stand-in (#288).
- Exception capture moves out of `fastapi/capture.py` into its own modules, unchanged in behaviour.
- The API route inventory (`tests/parity/routes_status.json`) is rebuilt against BootUI 2.5.0.
- The console contract for the coming Flask console is in `engine/console`; nothing uses it yet.
- The session-stream test waits on events instead of fixed sleeps.

## [0.8.0] - 2026-11-22

### Added

- Application responses include `X-Sharpit-Request-Id` by default when sharpit records the HTTP exchange. Set `SHARPIT_HTTP_EXCHANGES_EXPOSE_REQUEST_ID_HEADER=false` to opt out; requests from sources that are not trusted do not receive the header (#269).
- The pytest plugin names a swallowed exception a test double raised (a `unittest.mock` frame on its traceback, or text naming `MagicMock`, `AsyncMock`, `NonCallableMock`, `PropertyMock` or `ThreadingMock`): the finding adds "a test double raised this, so this code path did not run" and keeps its severity. The exception text decides this and is never stored or written; the worker facts carry one boolean, `testDouble`. The terminal summary adds a grouped `swallowed exceptions:` block with one line per `except` clause and its test count, most tests first (`swallowed exceptions: 13 clauses, 95 tests`). Per-test findings remain in the report (#68, #254).
- The Pentesting panel (`GET {api}/pentesting`, `POST {api}/pentesting/scan`) and CLI commands (`sharpit pentest scan`, `sharpit pentest report`) probe the in-process ASGI app with one synthetic GET and one OPTIONS request, bounded in time, header count and body size (8 KiB of body), without opening a socket. They check the security response headers (`X-Content-Type-Options`, clickjacking protection, `Content-Security-Policy`, HSTS, `Referrer-Policy`, `X-XSS-Protection`, COOP and CORP), TRACE and TRACK handling, error disclosure and technology disclosure (BootUI 2.5.0 parity, #271).
- CORS pentesting checks read the same synthetic probe, using the fixed preflight origin `https://evil.example`: credentialed and broad cross-origin access (`PT-A05-007`, `PT-A05-008`), the literal `null` origin (`PT-A05-065`), any method or header allowed for a permissive origin (`PT-A05-023`) and sensitive authentication headers exposed by `Access-Control-Expose-Headers` (`PT-A05-073`). `PT-A05-069` reports that the preflight evidence was incomplete, so the dependent checks are indeterminate (BootUI 2.5.0 parity, #275).
- Opt-in per-endpoint HTTP security gate for the pytest plugin: `--sharpit-http-security` observes the requests a test sends through the `sharpit_http_observed` fixture and checks them against configured expectations (`--sharpit-required-response-header 'METHOD ROUTE=HEADER'`, `--sharpit-expected-status 'METHOD ROUTE=STATUS[,STATUS...]'`, or the matching ini options). It sends no request and opens no socket. A violated expectation is a `HIGH` finding; an expectation never observed is `UNKNOWN` (#272).
- Flask route model for the test-session gates (`sharpit.flask`): the pytest plugin reads a Flask app's routes from `app.url_map` without calling a view, so `--sharpit-app` and application detection accept Flask and the REST API advisor assesses its routes; an unreadable URL map degrades to `UNKNOWN`. The N+1 and query-budget gates work on a Flask-SQLAlchemy app. Part of #75; the Flask console continues in #260 (#261, #255).
- Runtime Insights implements `route-latency-outliers`: a route whose warm latency is a multiple above its baseline, with the child-work comparison and the masked SQL statements of the slow requests (BootUI 2.5.0 parity, #264).
- Configurable vulnerability scan deadline via `SHARPIT_VULNERABILITIES_SCAN_TIMEOUT` (default 60s, keyword `vulnerabilities_scan_timeout`): when it expires the scan stops and reports `PARTIAL`, keeping the results already read; the deadline also bounds each OSV and EPSS request. Advisory interpretation follows BootUI 2.5.0 (BootUI 2.5.0 parity, #258).
- FastAPI binding diagnostics for exception capture, extracting Pydantic validation error details (`type`, `loc`) in the adapter while redacting unknown path segments (BootUI 2.5.0 parity, #270).
- Application `basePath` from ASGI `root_path` in mappings (`GET {api}/mappings/flat`), and route selection in the HTTP Probe UI (BootUI 2.5.0 parity, #266).
- Investigation navigation in the console: HTTP Exchanges ranks routes (requests, total duration, p95, max duration, errors) and opens a route's exchanges in a drawer, and the Activity request profile steps to the previous and next profileable request (BootUI 2.5.0 parity, #267).
- Pentesting cookie checks (BootUI 2.5.0 parity): the HttpOnly, SameSite and Secure flags, the `__Host-` and `__Secure-` prefix requirements, the session cookie configuration and cacheable `Set-Cookie` responses are read from the scan's GET probe and the application's session middleware configuration; no request is added and cookie values are never kept (#277).
- Pentesting framework-exposure checks (BootUI 2.5.0 parity): `PT-A05-041` reports API documentation served by FastAPI's own handlers and `PT-A05-044` reports uvicorn's `ProxyHeadersMiddleware`, read from the application's route table and middleware configuration without a request (#279).

### Changed

- Rules `RAPI-NAME-002`, `RAPI-DOC-001` and `RAPI-DOC-002` are retired to match BootUI 2.5.0: they stay registered and return `SKIPPED`. `ARCH-CODE-004`, `ARCH-CODE-018`, `DB-POOL-004` and `DB-SERVER-002` are removed from evaluation and their ids reserved (#263).
- The 2.5.0 contract keys are emitted: the four resource-profile pinning keys (`false` or `0`, Python has no JFR pinning) and `requestId` on exception occurrences (#265).

### Fixed

- `pytest --sharpit --sharpit-app` no longer reports the REST API advisor as `PASSED` for an object whose routes it cannot read (a WSGI app, a hand-wrapped middleware, the coroutine of an `async` factory, any factory result with no stored route list): the advisor is `UNKNOWN` with the reason `"application routes cannot be inspected (<module.Class>); expected an app, a router or a zero-argument factory"`. A suite that named such an object went green before and is now `unknown` (exit 1) unless `--sharpit-allow-unknown` is passed. An explicit FastAPI or Starlette app with no routes stays the confirmed-empty `PASSED`. Contributed by @michaelegner (#207, #276).
- `--sharpit-app` accepts an `APIRouter` or a Starlette `Router`: it was called as if it were a factory and reported `"application could not load (TypeError)"`. A router's assessment covers its routes only, not the handlers an app adds around it. The named object is called only when it accepts no arguments; one that is inspectable, has a `router` attribute, needs arguments or has an unreadable signature is used as it is. Contributed by @michaelegner (#207, #276).
- Rule accuracy fixes from BootUI 2.5.0 for the REST API, database and architecture advisors, for example `DB-SCHEMA-007` recognising PostgreSQL `serial2`, duplicate-route detection normalising path-variable names, and `RAPI-MAP-007` no longer flagging POST, PUT or PATCH routes whose path starts with a domain noun (#268).
- A request that carries a forwarding or client-address header (for example `Forwarded`, `X-Forwarded-For`, `X-Forwarded-Proto`, `X-Forwarded-Host`, `X-Real-IP` or `Via`, as a local development proxy adds) is no longer a trusted source and needs the console token, even when it comes from loopback.
- Matrix parameters in recorded request paths, and sensitive values in SQL text and exception messages, are masked as the masking policy says.

### Internal

- Pinned BootUI 2.5.0 parity targets (#259, #262), repaired the BootUI capture script and re-captured 2.4.0 (#257), added regression tests pinning that SQLite double-quoted runs are hidden on every SQL surface (#273, #59), refreshed CI test shard weights and Windows runner performance (#274), added a CI DCO sign-off check (#252), and updated contributor documentation (#256).
- The test suite runs faster on CI: repeated setup work is removed from the shared fixtures and the shard weights are refreshed, with no test skipped, deselected or weakened (#278).

## [0.7.0] - 2026-11-19

### Added

- Guided agent playbooks and an AI agents guide ported from BootUI 2.4.0 (`skills/sharpit/references/playbooks/` and `website/docs/ai-agents.md`): application checkup, database efficiency, slow endpoint diagnosis, errors and hidden failures, verifying changes, and Python performance/memory. The skill and shipped plugin include playbooks with side-by-side MCP tools and `sharpit` CLI commands.
- MCP prompt guidance follows BootUI 2.4.0: all four prompts advertise optional arguments, echo masked and bounded context, and include `verify_after_change`.
- Interactive tutorial (`website/docs/tutorial.md`): step-by-step walkthrough of application inspection, issue diagnosis, and change verification with sharpit.
- The `sharpit` command-line client (`sharpit` console script): connects to a running sharpit application over HTTP without extra dependencies, executing any tool from the catalogue with BootUI 2.4.0 exit codes (0 success, 1 error, 2 refused, 3 threshold), global options (`--url`, `--api-path`, `--token`, `--timeout`, `--json`, `--no-color`, `-v`), `--fail-on` gates on finding severity (`critical`..`info`) or `insufficient` runtime evidence, `sharpit tools` listing, and `sharpit mcp status|enable|disable` controls.
- Runtime Insights implements `repeated-selects` and `unbatched-write-loop` with BootUI 2.4.0 thresholds and request counts.
- Rule SEC-STATIC-001 (BootUI 2.4.0 #1597): detects local static security analyzer declarations (Bandit, Semgrep, CodeQL, a `sonar-project.properties` file, or Ruff with `S` selected) without running them; bounded to 1 MiB per file and at most 64 workflow files, refuses symlinks and special files, evaluating to INDETERMINATE on error or oversize. Evaluated only on the security scan action (the Security panel and the CLI `sharpit security scan`; never over MCP, never on reads).

### Changed

- The CLI gives BootUI-equivalent guidance for disabled endpoints, authentication, missing tools and panel refusals. Help labels environment-backed options and required arguments; verbose failures retain redacted causes, and timeout messages preserve fractional seconds and milliseconds.
- The CLI command paths of eight tools now follow BootUI's, in `GET {api}/cli` and in the Runtime Insights next steps: `get_request_profile` `activity profile` to `request-profile`, `get_transactions` `transactions` to `tx list`, `clear_transactions` `transactions clear` to `tx clear`, `pause_transaction_recording` `transactions pause` to `tx pause`, `resume_transaction_recording` `transactions resume` to `tx resume`, `get_traces` `traces` to `traces list`, `get_security_logs` `security-logs` to `security logs`, and `get_sqlalchemy_statistics` `sqlalchemy-statistics` to `sqlalchemy-statistics list`. The tool names and the `POST {api}/cli/tools/{tool}` route are unchanged.
- MCP runtime-diagnosis, change-verification, application-review, and application-assessment guidance is adapted to sharpit evidence and available tools; CLI-only actions include their command, change verification checks both repeated-SQL insights, and unsupported previous-run comparisons are not promised. Prompt arguments follow Java whitespace and UTF-16 truncation semantics and are masked before appearing in replies or errors.
- The caught-exceptions report (`GET /sharpit/api/exceptions/caught`) emits `insufficient` and `partial` integer counters (zeros when the sensor is unavailable), and the runtime insights agent view (`get_runtime_insights`) emits `insufficient` and `partial` counts covering every observation matching the query, including rows omitted by `limit`. The MCP tool descriptions for `get_exceptions`, `get_runtime_insights`, and `get_runtime_insight` adopt BootUI 2.4.0 explanations for incomplete-evidence states (BootUI 2.4.0 #1589).
- The web UI enforces read-only panel policies across views and navigation: action buttons are disabled with their canonical refusal reasons instead of remaining interactive or hidden, panels state refusal reasons on 403 access denials without masking them as generic connection failures, and mutating actions guard execution against policy changes (BootUI 2.4.0 #1602).
- Database advisor discovery reports missing driver metadata (driver name, DBAPI version, or URL) or failed ORM model
  discovery as WARNING diagnostics with incomplete evidence coverage (`PARTIAL` scan status, never a clean `SCANNED`),
  while unconfigured or absent ORM models remain a neutral INFO skip (BootUI 2.4.0 #1600). BootUI's incomplete
  PostgreSQL relation-inventory diagnostic is not reported yet: sharpit's catalog does not observe that signal.
- Registering a capture hook twice in `HookRegistry` is idempotent: an aggregate is never counted twice (BootUI 2.4.0
  #1598).
- HTTP exchange recording failures never alter or disrupt streamed or committed HTTP responses, never mask host application exceptions, and log a warning naming the exception class only (BootUI 2.4.0 #1615).
- The advisor status enum of `sharpit-report/1` widens to include `PARTIAL` (both copies of the schema): a partly
  assessed advisor is reported as `PARTIAL`. A consumer that switches on the status should accept the new value.

### Fixed

- CLI output preserves server JSON bytes except where the token occurs: values and object keys are replaced, and a matching number literal becomes the string `"[redacted]"`. Invalid JSON also receives plain-text redaction. Terminal output escapes control characters while retaining multiline diagnostics; resolved and token-like argv values are redacted in usage errors. Expired deadlines never set a non-blocking socket timeout.
- The CLI redacts tokens that appear with JSON escapes, returns exit 1 for usage errors and broken output pipes, and reports MCP action failures after sending the request as unknown outcomes.
- The CLI redacts parser errors for built-in commands, keeps piped JSON UTF-8 and verbatim, and preserves MCP guard refusals without retrying the action.
- The CLI limits only connection establishment to 10 seconds; a tool response can use the full `--timeout`, and read timeouts are reported separately from connection and TLS failures. Server text is preserved; normal API responses are not capped at 1 MiB.
- A dismissed `sharpit.swallowed-exception` finding no longer comes back when a line above it moves (#66). The finding
  is keyed by `<path>:<scope qualified name>:<ExceptionType>#<key>` instead of the line of the `except` header. The key
  is 8 hex digits of a hash of the clause itself: its `try` body and its handler, without positions. A line added
  above the `try` or elsewhere in the function keeps the key; an edit inside the `try` body or the handler changes it,
  so the finding comes back. Swapping two `try` blocks, or moving a log call from one clause to another, cannot hand a
  dismissal to another clause. Byte-identical clauses of one scope get `.<n>/<m>` after the hash (n is the place among
  the m twins), so adding or deleting a twin changes every twin key instead of moving a dismissal. The path is
  relative to the pytest rootdir, and the message prints the key so it can be pasted into `dismissedFindings` (copy it
  from the terminal or the JSON report: the SARIF message is masked like every other output). A key that cannot be
  stored as a `dismissedFindings` entry (over 512 characters, or with a control character) is reported as such, with
  the fingerprint to list under `dismissedRules`, which covers one test only. Migration:
  - a `dismissedFindings` entry in the earlier `<path>:<line>:<ExceptionType>` form no longer dismisses anything: the
    finding comes back once, and the report warns naming the key of the clause now on that line, to replace the entry
    with if that is the clause meant (the warning matches the path relative to the rootdir and to the working
    directory);
  - the finding fingerprint follows the new key, so a baseline needs one `--sharpit-write-baseline` rewrite, a
    `dismissedRules` fingerprint for a swallowed exception is dismissed once more, and a code-scanning alert for a
    swallowed exception is reopened once (the SARIF `sharpitFingerprint/v1` key is unchanged);
  - the `FASTAPI-ERR-001` violation of the REST API advisor uses the same scope and key as its target instead of
    `module:line`: its `dismissedFindings` entries and `dismissedRules` fingerprints must be re-dismissed once with
    the new target (no line-keyed matching is kept for it), and its baseline entries rewritten.
- `pytest --sharpit` no longer exits 1 on a run with no finding when an advisor read part of an application and met
  an opaque mounted sub-app (#65). The advisor is `PARTIAL`: the run passes with a warning that names what was not
  read and says that having no finding at or above `--sharpit-fail-on` is not proof there is none, and a finding at
  or above it still fails. An unread router or exception handler, an errored scan, a rule that threw and an advisor
  with no usable routes and a limitation stay `UNKNOWN`; lost capture stays `unknown`. A partly assessed advisor does
  not count as having run for baselines: its baselined entries are neither reported fixed nor dropped.
- The pytest plugin's report and terminal line say when the REST API advisor's application was found through the modules the selected tests imported (`evidence.detectedFrom`, with `detectedBy` workers under xdist), and the skip and `--sharpit-require-app` reasons say that no application was found among the modules the tests imported, or name the candidates. Only `--sharpit-app` makes the assessed application independent of the selection; `--sharpit-require-app` turns a missing one into `unknown`. Exit codes are unchanged (#67).
- The skill `skills/sharpit/SKILL.md` named 0.5.0 as the current version.

### Not in this release

Deferred lanes from the 0.7.0 plan move to the next release:

- W0 live goldens: per-panel 2.4.0 live captures deferred until BootUI 2.4.0 is deployed in the reference application with live databases (the static 2.4.0 fixtures pin tools, rules, and properties).
- A2 (observed transaction boundaries): porting `TransactionBoundary.observed` and failed-begin reporting is deferred until transaction tracking overhead is reduced within the 30 µs budget.
- B2 (transaction journal source and kinds): `transaction` journal events, `split-transaction-writes`, and `transaction-across-remote-call` deferred pending performance audit.
- B3 (ORM journal source and kinds): SQLAlchemy session events as `orm` source and ORM flush/context insight kinds deferred pending overhead measurement.
- B4 (authorization journal source and kinds): observing FastAPI security dependencies as `authorization` source deferred pending security surface review.
- B5 (remaining insight kinds): app-event, garbage collection, and background executor insight kinds deferred pending council review and overhead evaluation.
- B6 (missing routes): 33 unserved BootUI API routes deferred for lane-by-lane implementation by panel group.
- B7 (partial routes): bringing the 28 partial routes to shape-identical parity deferred to panel-owning lanes.
- D1 (SQLAlchemy listener race): class-level listener race resolution across Engine, Pool, and Mapper deferred to the SQL capture lane.
- D2 (SQL listener per-statement path): evaluating BootUI 2.4.0 runtime event-sink capture against listener overhead deferred.
- D3 (SQL Trace panel availability): aligning SQL Trace panel availability before a data source is wrapped deferred.
- D4 (connection and SQL facts): connection statement count and recorded-SQL presence flag follow-ups deferred.
- D6 (masking double pass, the `SHARPIT_EMAIL_MASK_CONTENT` fallback): masking changes need predict, council review and a base-against-branch corpus diff.
- paged-without-order: deferred until SQL row-limit and shape analysis is ported without relying on regex approximation under masking.
- E0 / #207: a pull request from a fork; it waits for its author and a maintainer's review (handling `--sharpit-app` naming an object with no route list).

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
- Free on idle (`SHARPIT_FREE_ON_IDLE_ENABLED`, on by default as in BootUI 2.3.0; `SHARPIT_FREE_ON_IDLE_TIMEOUT`, 300 s):
  after the console has been idle for the timeout, sharpit suspends its capture hooks and releases their buffers; the
  next console request resumes them, so capture refills from live traffic. Set it to `false` to keep recording
  continuously.
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
- sharpit can mask a quoted text twice, so its masked text can differ from BootUI's, which masks it once (cosmetic;
  planned for 0.7.0).
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

[Unreleased]: https://github.com/ffroliva/sharpit/compare/v0.9.0...HEAD
[0.9.0]: https://github.com/ffroliva/sharpit/releases/tag/v0.9.0
[0.8.0]: https://github.com/ffroliva/sharpit/releases/tag/v0.8.0
[0.7.0]: https://github.com/ffroliva/sharpit/releases/tag/v0.7.0
[0.6.0]: https://github.com/ffroliva/sharpit/releases/tag/v0.6.0
[0.5.0]: https://github.com/ffroliva/sharpit/releases/tag/v0.5.0
[0.4.0]: https://github.com/ffroliva/sharpit/releases/tag/v0.4.0
[0.3.0]: https://github.com/ffroliva/sharpit/releases/tag/v0.3.0
[0.2.0]: https://github.com/ffroliva/sharpit/releases/tag/v0.2.0
[0.1.0]: https://github.com/ffroliva/sharpit/releases/tag/v0.1.0
