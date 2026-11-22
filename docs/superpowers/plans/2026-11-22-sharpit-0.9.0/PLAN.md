# sharpit 0.9.0 Implementation Plan (master)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan lane by lane. Every lane gets its own plan file in this folder
> when its predict and scenario steps have run. Run `/sharpit:status --feature 0.9.0` for the next unchecked step;
> `/sharpit:check` before every commit.

**Goal:** sharpit 0.9.0 closes the gaps recorded against BootUI 2.5.0 and the open issue list. Wave H takes the
0.8.1 issues (#284–#288), the CI scan gap and the known flakes. Four tracks follow. Track S makes the SQL capture hot
path fast. Track J adds the journal sources that need that headroom. Track R ports the missing and partial API
routes. Track M ports the ten 2.5.0 rules recorded as `missing`. Track F adds the embedded console for Flask (#260),
and Track X adds the masking follow-ups (#253, trace and journal masking).

**Architecture:** No new BootUI version is ported. BootUI has no tag after `v2.5.0` yet, so the reference stays
`v2.5.0`; the next tag becomes the pin for the release after this one. Two overhead budgets set the order. The SQL
listener budget (50 µs per statement) has the least headroom, so Track S measures and cuts it before anything adds
work to that path. The transaction budget (30 µs per transaction pair) held back the 0.7.0 transaction lanes (A2,
B2), so Track J starts from a constant-time design measured before the behaviour is ported. The safety model, the architecture rules and `sharpit-report/1` (additive changes only) stay as they are
unless a lane's predict step and council say otherwise. A change to a safety-model rule also needs the maintainer's
decision and the `AGENTS.md` change in the same pull request.

**Tech Stack:** Python ≥3.12, Starlette/FastAPI, Flask (optional, Track F), SQLAlchemy 2 (optional), pytest + xdist,
Svelte 5 + TypeScript (`ui/`), uv.

**Reference:** BootUI tag `v2.5.0` (commit `c4458db8dd18c08074119f22a79dda3e714abbda`), read in a BootUI clone with
`git show v2.5.0:<path>`. BootUI `main` after `v2.5.0` is not a reference for this release. BootUI paths below are
shortened: `E/` = `bootui-engine/src/main/java/io/github/jdubois/bootui`, `S/` =
`bootui-spring-boot-starter/src/main/java/io/github/jdubois/bootui/autoconfigure`.

**Review:** Lanes marked *predict* run `/sharpit:predict` and `/sharpit:scenario` before their plan file is written.
Lanes marked *council* also run `/sharpit:llm-council --tier high`. This master plan is reviewed by a high-tier
council before Wave H starts.

## Where 0.9.0 starts

- 0.8.0 shipped on 2026-11-22 (BootUI 2.5.0). Its recorded gaps are listed in
  `docs/reports/2026-11-22-0.8.0-decisions.md` ("Moved to the next release") and in the 0.8.0 plan ("Recorded, not in
  this release"). This plan takes every one of them. Each gap gets either a lane below or a row under "Recorded, not
  in this release" with its blocker.
- The SQL listener budget (`tests/fastapi/test_sql_trace_overhead.py`, 50 µs per statement) has thin headroom. The
  per-statement cost was 46–51 µs on the sbx fleet for both 0.7.0 and 0.8.0, and one Windows CI shard measured
  51.5 µs on the 0.8.0 release pull request. A paired audit found no regression between the two versions. The budget
  is not raised; the cost is cut.
- The 0.7.0 transaction lanes measured 26–28 µs (A2) and 31.3 µs (B2) per transaction pair against the 30 µs budget
  of `tests/fastapi/test_transactions_overhead.py`, against 10.4 µs on the base.
- `ROADMAP.md` still describes 0.8.0 as next. It is rewritten in Wave H and recomputed in the release wave.

## Global Constraints

From `AGENTS.md`; every lane's requirements include these.

- Python `>=3.12`; runtime dependencies are exactly `starlette` and `packaging`. `fastapi`, `pydantic-settings` and
  `flask` are optional and imported only inside their gatekeeper (`sharpit/fastapi/`, `sharpit/flask/`, or a
  `try/except ImportError`).
- Every contract DTO key is emitted (nulls included), camelCase, no envelope, epoch ms. Error bodies and reason strings
  are verbatim from BootUI with `BootUI`→`sharpit`.
- **Reads have no side effects**; actions follow BootUI's gates.
- Safety model 1–6 never regresses. A lane that touches activation, the guard chain, masking or introspection runs
  `/sharpit:known-issues` first. A masking change runs a base-against-branch masking corpus diff before merge, and
  only one masking lane holds the corpus base at a time.
- Architecture rules 1–6. A change to a rule happens in `tests/engine/test_import_boundary.py` and `AGENTS.md` in the
  same pull request. No module under `src/` passes 1000 lines.
- **Port BootUI, do not reinvent:** each lane reads BootUI's source at `v2.5.0` before writing code and cites each
  ported test with `# ported: <Class>.<case>`. Each adaptation is one deviation row in
  `docs/reference/matrix-updates/<lane>.tsv`.
- Each defect found becomes a regression test seen red first (`scripts/dev/red_check.py`); one condition per assert.
- Hot-path overhead budgets are never raised to pass, and a budget test is never marked slow or deselected.

## Risk register

| Severity | Risk | Mitigation |
|---|---|---|
| Critical | Moving the route modules into the engine changes a response, a guard outcome or a masking result on FastAPI | F1 records the HTTP response corpus first, with its normaliser fixed before the first recording and a planted-change row that proves the gate bites; F2 moves one panel group per pull request and keeps the corpus identical; *predict*, *council* on F0 |
| Critical | The Flask adapter skips or reorders a gate | The whole request pipeline (activation, duplicate-header denial, guard, panel access, dispatch, security headers) runs in one engine entry point that both adapters call; adapters only build the request and translate the response; the transport corpus matches across adapters with no exceptions (F3) |
| High | A WSGI server joins duplicate headers into one value, so a `Sec-Fetch-Site: same-origin,cross-site` request passes the cross-site check that FastAPI refuses | The engine receives raw header pairs; the WSGI adapter treats a comma in `Host`, `Origin` and `Sec-Fetch-Site` as a duplicate; corpus rows for duplicate and joined headers |
| High | The dev-server signal reads any `--reload` as `uvicorn --reload`: `flask run --reload` and `gunicorn --reload` enable the console under the wrong name, `flask run --debug` does not | F3 is *predict*: an activation matrix for Flask and gunicorn command lines, and safety rule 1 updated in `AGENTS.md` in the same pull request |
| High | The stream layer is asyncio-bound (`ChangeStream.subscribe`, async generators, `loop.time`), and a sync WSGI worker is held per open stream: 20 stream slots can starve a host with fewer workers | F0 decides the stream form and the WSGI capacity rule (slots against workers, overload response, disconnect cleanup), or limits streaming on Flask, before F2 moves those routes |
| High | Track R adds and changes routes while F2 moves every route module | R1 and R3 run after F2, or in F2's panel batches, never on the same module at once |
| Critical | A swallowed-exception finding prints an exception message that carries user input (#253) | X1 uses the existing exception-message scrubbing and masking; corpus rows added before the diff; *predict*, *council* |
| High | A Track J source pushes the per-statement, per-transaction or per-request cost over budget | J0 measures the transaction design before J1 and J2; nothing adds per-statement work before S2; each source has its own budget test, measured on the sbx fleet |
| High | Flask request correlation misses requests (streamed bodies, an aborting earlier hook, session cleanup, as recorded on #75) | F4 wraps `wsgi_app`, as the T1 HTTP security observer already does, instead of `before_request` and `teardown_request`; tests cover each case |
| High | New routes in Track R read state that has side effects or leaks unmasked text | Every new GET route uses the `no_side_effects` fixture and the masking path of its panel |
| Medium | Tool calls on a host with several event loops run on the wrong loop (#287), and a WSGI host has no request loop at all | H3 is *predict*, covers the WSGI case and runs before F0: BootUI has no counterpart (one JVM, no loops) |
| High | The scope is larger than one release | See "Definition of done": every deferral needs a reason, a follow-up issue and the maintainer's acceptance; the scope split is an open decision (decision 7) |

## Lanes

Status: `[ ]` not started, `[~]` in flight, `[x]` merged.

### Wave H: housekeeping (the 0.8.1 issues, CI, flakes)

- [x] **H1 Dead code** (#284, #286). Remove `is_validation_error` (`fastapi/binding_diagnostics.py`) and the dead
      `or text == ""` clause in the found-at scan test.
- [x] **H2 Cancel on caller timeout** (#285). The MySQL, PostgreSQL and Database advisor tools cancel their work on a
      caller timeout, as the pentest tool does. A red test per tool.
- [ ] **H3 Tool calls with several event loops** (#287), *predict*. A tool call runs on the loop of the request that
      issued it, not on the last recorded loop; this covers the pentest scan and the database advisor scan. The design
      also covers a WSGI host, which has no request loop, and its test includes that case. Its loop provider is an
      input to F0.
- [x] **H4 Tests on production code** (#288). The two 0.8.0 tests that use a stand-in (`_Store` stub, copied
      `run_probe` acquire and release) exercise the production code; delete the control and re-run to prove each one bites.
- [x] **H5 Flakes.** `test_session_stream_sends_sessions_then_dashboard` (intermittent on Windows CI): systematic
      debugging and a fix on the cause, never a retry or a skip.
- [ ] **H6 Scans before the release pull request.** CodeQL runs on pull requests into `release/**`, and
      `skills/release/SKILL.md` runs the code-scan ratchet and CodeQL on the ship branch before the release pull request opens. This
      is a workflow change into `main` and needs the maintainer's go.
- [~] **H7 Documents.** `ROADMAP.md` rewritten (0.8.0 delivered, 0.9.0 next, Flask); the live-verify skill uses the
      CLI's `--url` option; the 0.8.1 milestone issues move to 0.9.0.
- [~] **H8 Dependency updates.** The open Dependabot pull requests are triaged and merged or closed with a reason.
- [x] **H9 Split `fastapi/capture.py`** (908 of the 1,000-line cap), before H3, J and F4 add to it. `CaptureWiring`
      and the exception-handler wrapping move into their own modules. It is a behaviour-preserving move: the capture
      budget, the corpus rows that cover it, and the per-file C901 pin go down or stay the same.

### Track S: SQL capture hot path (runs first; nothing adds per-statement work before S2)

- [ ] **S0 Measure**, `/sharpit:perf-audit`. A per-function profile of the per-statement path on the sbx fleet and on
      a Windows runner, with the runner offset separated from split-half noise. The output is a ranked cost table and
      a headroom target that Track J's sources fit inside. No code change.
- [ ] **S1 Listener registration race** (0.7.0 D1). Class-level listener registration on Engine, Pool and Mapper is
      race-free under concurrent `install()` and test sessions.
- [ ] **S2 Per-statement path** (0.7.0 D2), *predict*. Port BootUI 2.5.0's event-sink capture where it applies, guided
      by S0's table. Done when the 50 µs budget passes on every fleet box with the headroom S0 set.
- [ ] **S3 SQL Trace panel availability** (0.7.0 D3). The panel reports available as BootUI does before a data source
      is wrapped.
- [ ] **S4 Connection and SQL facts** (0.7.0 D4). The connection statement counts and recorded-SQL presence flags
      follow BootUI.

### Track J: journal sources and insight kinds

Each source runs `/sharpit:predict` and measures its overhead before code.

- [ ] **J0 Transaction pair design**, `/sharpit:perf-audit`. A design whose begin and commit stay constant-time when no
      second transaction is open, measured on `tests/fastapi/test_transactions_overhead.py` inside the 30 µs budget
      before any behaviour is ported.
- [ ] **J1 Observed transaction boundaries** (0.7.0 A2), *predict*. Port `TransactionBoundary.observed` and failed
      begin reporting on J0's design.
- [ ] **J2 Transaction journal source** (0.7.0 B2). `transaction` events, `split-transaction-writes` and
      `transaction-across-remote-call`, inside the same budget.
- [ ] **J3 ORM journal source** (0.7.0 B3), *predict*. SQLAlchemy session events as the `orm` source; the ORM flush and
      context kinds. After S2 if it adds work per statement.
- [ ] **J4 Authorization journal source** (0.7.0 B4, BootUI #1677), *predict*, *council*. FastAPI security
      dependencies as the `authorization` source, the anonymous-access kinds and the request journal's
      `authorizations` key, which is a placeholder today. On Flask, the key stays empty and the PARITY row records the
      limit, unless the predict step finds a Flask counterpart.
- [ ] **J5 Remaining kinds** (0.7.0 B5). App-event, garbage collection and background executor kinds are each ported or
      recorded as a deviation with its reason.

### Track R: API route parity

- [ ] **R0 Route inventory against 2.5.0.** `tests/parity/routes_status.json` is built from the 2.3.0 fixture: it does
      not list `GET /activity/request/{id}/journal`, and its 32 `missing` rows include JVM-only routes (`crac`,
      `graalvm`, `jvm-tuning`, `devtools`, `dev-services`, `conditions`, `liquibase/changesets`, `heap-dump`). Rebuild
      the inventory from BootUI's 2.5.0 contract catalog (`BootUiApiContractCatalog.java`) and classify every route as
      port, `adapted` or `n-a`, each with its reason (decision 5). R1 and R3 work from this list, per route.
- [ ] **R1 Missing routes** (0.7.0 B6). Each route R0 marks as port, across scan results, runtime insights, traces,
      memory and application structure. `GET /activity/request/{id}/journal` comes first. After F2, or in F2's panel
      batches.
- [ ] **R2 Same-route baselines** (BootUI #1688), *predict*. `baselineComparison` on the request journal, after R1's
      journal route. Retention and overhead are measured.
- [ ] **R3 Partial routes** (0.7.0 B7). The partial route differences R0 lists are closed or recorded per panel, under
      the same ordering rule as R1.

### Track M: the 2.5.0 rules recorded as missing

- [ ] **M1 REST API rules: reclassify as `n-a`** (decision 5). Read at `v2.5.0`
      (`E/engine/restapi/RestApiRules.java:2366-2590`), each of the five describes a Spring or Quarkus construct that
      FastAPI does not have:
      `RAPI-MAP-012` (an unannotated Spring parameter binds as a query parameter; FastAPI binds a parameter named like
      a path token to the path), `RAPI-MAP-013` (Spring's `RequestMethodsRequestCondition.combine()` unions the
      class-level and method-level HTTP methods; neither FastAPI nor Flask has a class-level method mapping to combine
      with a route's own methods), `RAPI-VER-008` (a restrictive `consumes` condition; FastAPI has none),
      `RAPI-VALID-007` (Bean Validation skips nested objects without `@Valid`; pydantic validates nested models) and
      `RAPI-PAGE-004` (Spring Data `Page` serialization). A `docs/reference/matrix-updates/0.9.0-m1.tsv` fragment
      records each as `n-a` with its reason, a 0.9.0 section in `scripts/dev/generate_parity_deviations.py`
      regenerates `PARITY.md`, and the `#1689` row in `BOOTUI-2.5.0-DELTA.md` moves from "missing (next release)" to
      `n-a`. If FastAPI has a real counterpart defect, it is a separate sharpit rule through `/sharpit:predict`.
- [ ] **M2 Database rules: port.** Each reads the database catalog or the pool settings and applies to a Python
      application: `DB-SCHEMA-011` (`ForeignKeySetNullOnNotNullColumnRule`), `DB-PG-006`
      (`PostgresEmptyPartitionedTableRule`), `DB-SERVER-008` (`MySqlStrictSqlModeRule`), `DB-MYSQL-004`
      (`MySqlUnenforcedCheckConstraintRule`), and `DB-POOL-005` (`PoolAcquisitionTimeoutRule`), adapted from the
      HikariCP and Agroal timeouts to SQLAlchemy's pool `timeout` with BootUI's 300,000 ms threshold (one deviation row).
- [ ] **M3 `paged-without-order`**, *predict*. It needs SQL row-limit and shape analysis that holds under default
      masking; without that analysis, it is recorded with its reason, not approximated by a regex. The analysis goes in
      its own module (BootUI `SqlRowLimits`), not in `engine/sqltext/lexer.py` (940 lines).

Each rule is ported from its BootUI class at `v2.5.0`, its PARITY row moves from `missing`, and each ported test cites
its source.

### Track F: the embedded console for Flask (#260)

Design (decision 6): the whole console request pipeline moves into the framework-free engine, and FastAPI and Flask
each get a thin adapter that only builds the request and translates the response. The guard's decisions are already
in the engine (`guard.RequestFacts`, `guard.decide_guard`, `guard.is_trusted_source`). `fastapi/adapter.py:110-153`
still owns the rest of the guard step: the duplicate `Host`, `Origin` and `Sec-Fetch-Site` denial, header joining,
the API sub-path, the trusted-source flag and the websocket refusal. That moves too, so no adapter calls the guard
itself. The API is 38 route modules plus `routes/__init__.py` under `fastapi/routes/` (2,348 lines, 1,808 non-blank,
134 `Route(` entries). Their handlers take a Starlette `Request` and return a Starlette `Response`. Eight routes
stream server-sent events and one serves a file. The stream layer is asyncio-bound (`ChangeStream.subscribe` takes a
loop, `change_events` and `log_events` are async generators), and 35 handlers are `async def`.

- [ ] **F0 Console contract**, *predict*, *council*. After H3. A new `engine/console/` package (architecture rule 1
      already keeps `fastapi` and `starlette` out of `engine/`; add a `werkzeug` gatekeeper for `sharpit/flask/` and
      `pytest_plugin/http_security_flask.py`). It defines:
      - `ConsoleRequest`: method, path below the mount, root path, raw query bytes, raw header pairs (duplicates kept,
        lower-case names), a capped body reader, scheme, peer address, server host and port, the probe flag.
      - `ConsoleResponse`: status, header pairs, and one of a body, a file, or a stream (an event source, its acquired
        slot, its time cap, its close hook).
      - `Console.handle(request) -> ConsoleResponse`: the only entry point. Activation (inactive gives 404), the
        duplicate-header denial, the guard, panel access, route dispatch and the security headers all run in it.
      - An ordered route table (method, template, handler, panel, read or action), with the bare-path match
        `SharpitMount` does today. Handlers receive an engine-built call (context, path parameters, paging), never a
        scope mapping; engine code that reads ASGI scope keys today (`overview`, `mcp`, `tools`,
        `capture/correlation`) reads the request instead.
      - Host ports the adapters implement: `HostProbe` (the pentest probe, in-process ASGI today), `CaptureHooks`
        (exists), and the loop provider from H3.
      It also decides five questions in writing: where each handler runs on each adapter, and whether a console read
      on FastAPI takes a host threadpool slot (tested); the stream form, either one async source run on a private loop
      on WSGI or a thread-safe blocking form (a spike and its own pull request before F2 moves the streaming routes); the
      WSGI capacity rule (stream slots against the worker count, the overload response, cleanup on disconnect), or a
      recorded limit on streaming for Flask; route order; the request ID header.
- [ ] **F0b Flask panel availability.** One table, published in the docs and recorded in PARITY, lists every panel and
      action on Flask as works, adapted or unavailable, with its availability reason. Today HTTP exchange capture,
      exception-handler wrapping, the request ID header, the idle tracker, traces, the Threads panel's asyncio tasks and
      the pentest probe are ASGI-only.
- [ ] **F1 HTTP response corpus.** It can start now, in parallel with F0. Before anything moves, it records every
      console route's response through today's FastAPI adapter. The cases cover activation states, each guard denial
      (duplicate and joined headers included), exposure levels and read-only panels, plus each stream's whole lifecycle
      (events, time cap, disconnect, slot release). A normaliser fixed before the first recording replaces timestamps,
      uptime, memory figures and request IDs, and names each field it replaces and why. A planted-change row proves the
      gate still fails on a real change. The corpus has two parts: a **transport corpus** (denials, 404 when inactive,
      error bodies, security headers, read-only refusals) and a **panel corpus**.
- [ ] **F2 Extract the handlers**, one panel group per pull request. Each group's handlers move into `engine/console/`
      on the F0 contract, and `fastapi/routes/` keeps only translation. `routes/__init__.py` (706 lines, about 40 inline
      handlers) splits into per-panel modules on the way. After each pull request, the F1 corpus, the `no_side_effects`
      tests and the overhead budgets (capture middleware, SQL listener) stay unchanged. The safety-path rule for
      refactors applies: a step that changes any corpus byte stops and is reviewed.
- [ ] **F3 `sharpit.install` for Flask**, *predict*, *council*. A `sharpit/flask/` adapter builds `ConsoleRequest` from
      the WSGI environ and treats a comma in `Host`, `Origin` or `Sec-Fetch-Site` as a duplicate. The trusted-source
      decision keeps resting on the raw peer and the forwarding-header list. The adapter mounts at `path` by dispatching
      on the path prefix before the host's `wsgi_app`. Its parts:
      - `sharpit.install` picks the adapter by duck typing (`router` or `wsgi_app`) without importing either framework
        (a test proves it), and gives a clear error for anything else.
      - `SharpitHandle` moves to a framework-neutral module, with the lifespan optional.
      - Activation gets a matrix for `flask run`, `flask run --debug`, `flask run --reload` and `gunicorn --reload`. The
        dev-server signal names the server it saw, and safety rule 1 in `AGENTS.md` changes in the same pull request.
      - The transport corpus replayed through Flask matches FastAPI with no exceptions. The panel corpus is per adapter,
        and each difference is a PARITY deviation row.
- [ ] **F4 Request correlation.** Captured SQL and exceptions link to the Flask request that caused them, through the
      same `wsgi_app` wrapper the pytest HTTP security observer uses (`pytest_plugin/http_security_flask.py`). Tests
      cover streamed bodies, an earlier hook that aborts, and session cleanup. Its overhead budget test is bounded by
      the existing 150 µs WSGI observer row in `docs/development/overhead-budgets.md` and is never raised.
- [ ] **F5 Example application.** `examples/flask_sqla`, with a gate test like the FastAPI samples, and a
      `/sharpit:live-verify` run against it.
- [ ] **F6 Route model limits.** `strict_slashes` and subdomain or host matching are shown in the route model or
      recorded as limits.

Closes #260 when F0b and F3–F5 merge.

### Track X: masking follow-ups (one corpus base at a time)

- [ ] **X1 Exception message in swallowed-exception findings** (#253 item 1), *predict*, *council*, masking corpus
      diff. Masked like other captured text; the lane decides which exposure levels show it.
- [ ] **X2 Reason for an accepted finding** (#253 item 2). A `reason=` argument on the accept marker, and a setting that
      makes it required in CI.
- [ ] **X3 Trace and journal masking on the matrix path**, masking corpus diff. Trace masking and journal masking move
      onto the matrix masking path; the gate corpora are byte-identical before and after.
- [ ] **X4 Email mask fail-safe** (0.7.0 D6 remainder). An invalid `SHARPIT_EMAIL_MASK_CONTENT` takes the strict
      fail-safe and adds a warning.

Closes #253 when X1 and X2 merge.

### Product readiness: decided now, built later

None of these has a BootUI 2.5.0 counterpart, so each goes through `/sharpit:predict` and
`/sharpit:llm-council --tier high` in its own release. This release records them so the 0.9.0 interfaces do not block
them.

- **Action audit record.** Every action taken through the console, MCP or CLI records what, when, which channel, which
  panel and the result. It never holds a secret, and it never writes on a read. The F0 route table marks each route
  as a read or an action, so the record can hook in at one place.
- **Console API contract version.** Today only `sharpit-report/1` is versioned. The JSON API needs a version that a
  second adapter, the CLI and outside tools can check, with documented compatibility and evolution rules.
- **Export and import.** Findings, dismissals and accepted findings (with X2's reason) move between environments in a
  documented format; SARIF for the live advisors (a SARIF writer exists for test sessions in
  `engine/testsession/sarif.py`).
- **Finding lifecycle.** A finding is tracked across runs (new, still present, resolved, accepted) instead of being
  recomputed on every scan.
- **Third-adapter proof.** A test-only adapter of about 100 lines on the F0 contract shows that a third framework
  needs no engine change.

### Recorded, not in this release

Each stays a recorded gap with its blocker.

- **2.5.0 and 0.7.0 live goldens:** they need BootUI built into the reference application with its databases.
- **Instance discovery and `init`** (BootUI #1687): a deviation from safety rule 6.
- **BootUI changes after `v2.5.0`:** they are ported once a tag exists, in the release that pins it.

### Release wave

- [ ] **RW** — `ROADMAP.md` and README columns recomputed against 2.5.0; `CHANGELOG.md`; `docs/reference/PARITY.md`
      merged from the lane fragments; the code-scan ratchet and CodeQL on the ship branch (H6); `/sharpit:doc-review`;
      `/sharpit:live-verify` on a FastAPI and a Flask sample; `/sharpit:release` prepares the release and stops.

## Dependencies

```
H1-H8: start now (H6 needs the maintainer's go);  H9 ── H3
S0 ── S2;  S1, S3, S4 start now (S1 before S2 if both touch registration)
J0 ── J1 ── J2;  S2 ── J3 (if J3 adds per-statement work);  J4, J5 after their predict
R0 ── R1 ── R2;  R0 ── R3;  R1 and R3 after F2, or in F2's panel batches
M1, M2: start now;  M3 after its predict
H3 ── F0 ──┬─ F2 ── F3 ── F4 ── F5
F1 (now) ──┘   F0b with F0;  F6 any time
X1 ── X3   (one masking corpus base at a time);  X2, X4 any time
J4 and R2 both fill a request-journal key (`authorizations`, `baselineComparison`): the second to merge updates the DTO test
every lane ── RW
```

## Decisions (2026-11-22)

1. **Reference:** BootUI `v2.5.0`. BootUI has no newer tag, and the port rule reads a tag. The release after 0.9.0
   pins the next BootUI tag.
2. **No 0.8.1 release.** The 0.8.1 issues (#284–#288) are fixed in Wave H and ship in 0.9.0 with everything else.
3. **The Flask console is in scope.** On #75 (2026-11-20) the console was planned only if Flask users asked for it.
   The maintainer decided on 2026-11-22 to build it in 0.9.0 under #260, now that the route model and the gate have
   shipped.
4. **All four parity tracks are in scope** (S/J, R, M, F). Tracks S and J0 run first, because the lanes after them
   need their measured headroom.
5. **What applies is ported; what differs is recorded.** Every BootUI 2.5.0 rule, route, source or key that applies to
   a Python application is ported. Every one that does not apply, or applies with a difference, gets a deviation row
   (`n-a` or `adapted`) with its reason in the lane's matrix fragment, so `PARITY.md` tracks each one. The five
   Spring-specific REST API rules in M1 are the first such rows.
6. **The console core moves into the engine.** Of the three ways to serve the console on Flask, the decision is the one
   that keeps a single implementation of the console. The other two were a bridge that runs the Starlette console on
   its own event loop inside the WSGI host, and re-serving the API through Flask routes, which would put the guard
   chain in two places. The routing and handlers move to `engine/console/`, and FastAPI and Flask are thin adapters
   over them, matching the engine's ports-and-adapters design. Because this refactor sits on a safety path, it is
   gated by a byte-identical HTTP response corpus (F1, F2). The whole request pipeline, guard step included, runs in
   one engine entry point, so no adapter calls the guard itself.
7. **Scope split: open.** The council judged the release too large to ship as one. Its options: (a) ship Wave H, S,
   J0–J2, M, X, R0–R1 and F0, F0b and F1 in 0.9.0, and move F2–F6, J3–J5, R2–R3 and the Flask console to 0.10.0 on
   top of the contract and the corpus; (b) keep Track F whole and move Track R after it; (c) keep everything and
   accept a longer release. The maintainer decides.

## Definition of done

- [ ] Every lane is merged, or deferred with a reason, a linked follow-up issue and the maintainer's acceptance
      recorded in the release decisions report. A deferral is "release accepted with a gap", never "parity complete".
- [ ] `PARITY.md`, regenerated from the lane fragments, has no `missing` row without a follow-up issue, and every
      `n-a` and `adapted` row has its reason (decision 5).
- [ ] The full CI matrix (Python 3.12–3.14, Windows, `lowest-direct`, UI build drift) and the sbx fleet are green on the
      ship head; no ratchet goes up; no overhead budget is raised.
- [ ] The F1 corpus is unchanged on FastAPI, and the transport corpus matches on Flask.
- [ ] `/sharpit:live-verify` passes on a FastAPI and a Flask sample.
- [ ] The code-scan ratchet and CodeQL are clean on the ship branch before the release pull request (H6).
