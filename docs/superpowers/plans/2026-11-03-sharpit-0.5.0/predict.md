# Predict: sharpit 0.5.0, full parity with BootUI 2.2.0

Run of `skills/predict/SKILL.md` on the 0.5.0 scope (2026-11-03, planning session). The five personas were written in
turn, each from `AGENTS.md`, the 0.4.0 spec (§4 anti-goals, §6 panel contract, §11 deviations), the touched contract
sections (`BOOTUI-CONTRACT-0.4-WAVE-A.md` §2, §3, §4, §6; `-WAVE-B.md` §2, §3, §4, §6, §7, §8) and the source on
`origin/main` @ `f5a7681`, without reading the others first. No subagents: the facts each persona needs were gathered
once (listed under "Evidence read") and the personas disagree enough on their own.

## Verdict: CAUTION   Confidence: 6/10

## Summary

The panel half of 0.5.0 is a known shape: 0.4.0 left a stub, a route module, a tool module, a flag and a Svelte
placeholder for every missing panel, and two of the eight are resumes with written review findings. The risk sits in
three places: `engine/sqla.py` (717 lines, four lanes want it, the 1000-line ratchet and the one-gatekeeper rule
collide), the three static-analysis advisors (security, architecture, fastapi) that read application source on POST,
and the benchmark items (memory, workload), which are not BootUI parity at all and pull in global interpreter state
(`tracemalloc`, `gc.callbacks`) and a file-writing report. Go for the panels with the mitigations below; the benchmark
lanes start only after a spike and an owner call each.

## Evidence read

- `docs/reference/PARITY.md`: 19 existing, 2 parity, 2 unverified, 1 parked, 7 not started (31 panels).
- `src/sharpit/engine/panels04/*.py`: `IMPLEMENTED = False` for architecture, database_advisor, fastapi,
  fastapi_security, mysql, security, security_logs, transactions.
- Goldens under `tests/fixtures/bootui/2.2.0/`: `mysql`, `security`, `architecture`, `database-advisor`, `fastapi`
  are the **pre-scan** shape (`NOT_READ` / `NOT_SCANNED`, empty lists). `security-logs` has one real event.
  `transactions` has real rows. `data/repositories.captured.json` has `total: 0`. `sqlalchemy-statistics` has only
  `nullable.json` (`meta.json` `uncaptured`: no Hibernate statistics bean on tiny-ledger).
- A-transactions @ `666a0ab`: review round 2 `VERDICT: CHANGES`, majors 1 (unnamed savepoints share the `None` key)
  and 2 (ring unbounded when every row is open), minors 3–10.
- B-fastapi-security: review @ `49c755d` `VERDICT: CHANGES` (blocker: `_walk` calls `effective_candidates` via
  `getattr` on custom routes; major: plain Starlette sub-app routes reported `unsecured`; major: Task 0 council not
  run). Head `12a67b5` is fix round 2, `DONE_WITH_CONCERNS`; the one failing test
  (`tests/pytest_plugin/test_plugin_reports.py::test_live_engine_driver_counts_as_covered`) is outside its May-touch
  list and the lane diff touches no `pytest_plugin` file.
- T-unbounded-read: 21 commits ahead of `origin/main`, not merged; adds 139 lines to `engine/sqla.py`.
- T-swallowed-exceptions (merged): a clause swallows when it is broad and its body neither raises nor calls a logger
  or `warnings` (`engine/testsession/swallowed.py:3`). Static, per handler, so whose logging counts (U19) is already
  "the handler's own".
- G6 (merged): autodetect, `SKIPPED` without an app, `--sharpit-require-app`, `--sharpit-verbose` (U4, U5).
- T-n-plus-one-message (merged): relationship, loader fix, first lazy-load site and masked statement in the message
  (`engine/testsession/gates.py:71-84`). A group with no relationship gets only the count (U6 gap).
- `engine/capture/activity.py:255`: `heapUsedBytes` is always `null` today.
- `sharpit-bench-spike/docs/upstream-tracker.md`: U1, U3, U4, U5, U6, U14, U17, U19. U20 is not in the tracker; it is
  the brief's proposal.

## Persona findings

### Architect: CAUTION (6/10)

- `engine/sqla.py` is 717 lines on `main`; T-unbounded-read adds 139, A-transactions' fix added a connection-event
  slot, MySQL needs a read-only session wrapper for its dialect, database-advisor needs catalog reads. Four lanes, one
  file, a 1000-line cap and Architecture rule 4 ("SQLAlchemy only in `engine/sqla.py`"). Either the gatekeeper becomes
  a package (`engine/sqla/`, every submodule a gatekeeper) or the lanes serialise on one file and the last one breaks
  the ratchet. This is a rule change: `tests/engine/test_import_boundary.py` + AGENTS.md in one PR, with
  `/sharpit:llm-council --tier high`.
- The three advisors that read source (security static checks, architecture import graph, fastapi rules) share an AST
  layer. Contract §7 says "build §6's AST layer first and this drops to M". That layer belongs in the engine
  (`engine/appsource.py`, stdlib `ast` only), built once in the foundation, not by whichever advisor lane lands first.
- Rule-based advisors (security, architecture, fastapi, database-advisor) share BootUI's advisor contract (WAVE-B §1:
  GET cached report, POST scan single-flight, GET `rules/{id}/violations` paged). `engine/advisors/` already holds
  registry, dismissals, findings and retention for rest-api. Foundation extracts the scan/report/violations part so
  four lanes do not write four copies.
- Memory (U20) and workload (U17) are not panels. Memory fits `activity` (its `heapUsedBytes`/`heapMaxBytes`/journal
  `gc` keys are BootUI's and null today) plus a test-session fact. Workload is a CLI action that writes a report; it
  belongs next to `pytest_plugin`/CLI, never in a GET.

### Security: CAUTION (6/10)

- Advisors that read source files on POST read **the app package only** (resolved from the installed app's module
  `__file__`, bounded file count and size), never follow symlinks out, never import or execute it. A GET serves the
  cached report. Source snippets in violations are masked (a hardcoded secret in a reviewed file is exactly what a
  security rule finds; the message names the rule, the location, never the value).
- B-fastapi-security's blocker is the pattern to forbid everywhere: introspection may read `__dict__`/`vars()` of
  known Starlette/FastAPI route classes, never `getattr` a name on an unknown class (a property is user code). A
  planted trap-property test for every introspecting lane (security advisor, fastapi advisor reuse the walker).
- `security-logs` stores principal names and request data. Principal is user data, not a secret, but `data[].value`
  goes through the masker; a JWT in a `details` string must come out masked.
- Memory: `tracemalloc.start()` and `gc.callbacks.append` change global interpreter state; on a GET that is a side
  effect. They may run only inside a pytest session (like `sys.monitoring` in T-swallowed) or behind an explicit POST
  action that the read-only flag blocks. `memray` writes a capture file: action only, CLI-only, never MCP, path under
  `SHARPIT_STATE_DIR`.
- Reading `/proc/self/status` or `/sys/fs/cgroup/memory.max` on GET is "read a file outside the app" (0.4.0 spec §4).
  Allowed only in the existing background sampler with the value cached, and only if the owner rules that a sampler
  read is not a GET read. Open question.
- Workload: in-process ASGI only (no socket), against an app the user named, never on GET; the report file is an
  explicit output path; the report is masked like every other output.

### Contract parity: CAUTION (5/10)

- Five of the remaining goldens are pre-scan shapes. Parity on them proves the empty report and nothing about rules,
  data sources or violations. "Golden parity" for security, architecture, fastapi, database-advisor and mysql is
  honest only as "pre-scan parity; post-scan unverified" until post-scan goldens are captured from
  tiny-ledger-bootui (POST scan, then GET). MySQL needs a MySQL datasource in the capture app; tiny-ledger runs
  PostgreSQL.
- `sqlalchemy-statistics` can get a golden: BootUI's Hibernate statistics need
  `spring.jpa.properties.hibernate.generate_statistics=true` on tiny-ledger-bootui. `data` can get a non-empty golden
  if the capture app declares a Spring Data repository. Both are owner calls on the reference app.
- Rule ids: keep BootUI ids where an analogue exists (`SEC-*`, `ARCH-*`, `DB-*`), new ids for Python-only rules
  (`FASTAPI-*`), each logged in spec §14 with "N" (new) or "P" (ported). Rule text verbatim where ported.
- The workload report and memory facts have no BootUI contract. They extend `sharpit-report/1` additively (no
  fingerprint change), never a contract DTO.

### Host-app compatibility: CAUTION (6/10)

- `gc.callbacks` runs on every collection in the host; a callback that allocates or takes a lock can stall the app.
  Budget test, callback does an integer add only, attached only in a test session.
- `tracemalloc` costs 2–4x on allocation-heavy code. Per-route allocation only on demand (a test marker or a CLI
  workload run), never always-on.
- MySQL: `pymysql`, `mysqlclient`, `asyncmy`, `aiomysql` and MariaDB differ in `SET SESSION TRANSACTION READ ONLY`
  and `max_execution_time` support. Fail closed: no read-only guarantee → `unavailableReason`, as PostgreSQL does for
  AUTOCOMMIT.
- Database advisor on SQLite, PostgreSQL, MySQL; vendor rules skip with a reason on other dialects. Bounds from
  WAVE-A §4 (300 tables, 300 columns, 100 indexes/table, 20 s cooperative).
- Architecture on a namespace package, a `src/` layout, an app built by a factory in `create_app()`: the package root
  is resolved from the app object's module; no module found → `NOT_SCANNED` with the reason.

### Devil's Advocate: CAUTION (5/10)

- "Full parity" with eight panels, two resumes, four benchmark items and three patch items is three releases. The
  0.4.0 night parked 2 of its 6 panel lanes. Ship the panels as 0.5.0; split the benchmark items (U20 memory, U17
  workload) into their own release unless their spikes come back small.
- U4 and U5 are shipped (G6). U6 is shipped for ORM lazy loads. U19 is satisfied by the static handler rule. These are
  verify-and-pin tasks (one test each against the bench twin cases), not lanes. Planning them as features would build
  what exists.
- U3/U14 beyond paged routes needs the response item count, which means reading the response body in the capture
  middleware: a hot-path cost for every request. A spike decides whether `len()` of a JSON array at the end of the
  body is cheap enough; if not, the honest answer is "paged routes only", logged.
- The simpler path the others missed: the post-scan golden recapture (one G0 lane on the reference stack) turns five
  "unverified" panels into checkable ones for less effort than any of the rule lanes. Do it first.

## High-confidence risks (2+ personas)

1. `engine/sqla.py` contention and the 1000-line ratchet (Architect, Host-app, Devil's Advocate).
2. Pre-scan goldens prove little; post-scan parity needs a recapture (Contract, Devil's Advocate).
3. Global interpreter state from memory instrumentation (Security, Host-app).
4. Introspection calling user code through `getattr` (Security, Architect; the B-fastapi-security blocker).
5. Scope too large for one release (Devil's Advocate, Contract).

## Conflicts resolved

- Architect wants the memory work inside `activity`; Security says the cgroup/proc reads violate the GET rule.
  Resolved: the background sampler reads, the GET serves the cached value, and the owner rules on whether a sampler
  read is allowed (open question O3). Until then the keys stay `null` with a reason on platforms without
  `resource`/`psutil`-free stdlib access.
- Devil's Advocate wants the benchmark items out of 0.5.0; the brief asks to plan them. Resolved: they are planned as
  gated lanes (spike first, owner call), at the end of the order, and the release can ship without them.

## Required mitigations (CAUTION)

1. Foundation lane F5 makes `engine/sqla/` a gatekeeper package (or the owner rules otherwise) **before** any lane
   that edits SQLAlchemy code starts; `/sharpit:llm-council --tier high` on the rule change.
2. G0 recaptures post-scan goldens before the advisor lanes reach their parity task; until then a lane's parity test
   is pre-scan only and its PARITY row says "unverified (post-scan)".
3. Every introspecting lane carries `test_introspection_never_reads_or_calls_custom_route_attributes` (trap property).
4. `tracemalloc`, `gc.callbacks`, `sys.monitoring`, `memray`: test session or explicit action only; a
   `no_side_effects`-style assertion that a GET leaves `tracemalloc.is_tracing()` and `gc.callbacks` unchanged.
5. U17/U20/U3-extension start with `/sharpit:spike` and stop for an owner call.
6. Lane gate refuses a lane flagged council-required without `council.md` (the B-fastapi-security major 3).

## Recommended next step

Run `/sharpit:scenario` on the panel lanes and the benchmark lanes separately, then plan with F5 and G0 first.
