# Roadmap: how close sharpit is to BootUI

sharpit is a Python/FastAPI port of [BootUI](https://github.com/jdubois/boot-ui), the Spring Boot developer console.
Each sharpit release targets one BootUI tag: 0.6.0 targets BootUI 2.3.0, 0.7.0 targets BootUI 2.4.0, and 0.8.0 targets BootUI 2.5.0.

## Where it stands

| | sharpit 0.5.0 | sharpit 0.6.0 | sharpit 0.7.0 | sharpit 0.8.0 | BootUI 2.3.0 | BootUI 2.4.0 | BootUI 2.5.0 |
|---|---|---|---|---|---|---|---|
| MCP/CLI tools | 54 | 71 | 71 | 73 | 116 | 116 | 116 |
| Tools under BootUI's exact names | 45 | 62 | 62 | 64 | - | - | - |
| Panels | 31 | 48 (46 listed in the console) | 48 (46 listed in the console) | 49 (47 listed in the console) | 65 (Spring) | 65 (Spring) | 65 (Spring) |
| Runtime insight kinds that evaluate | none | 8 of 28 registered | 10 of 28 registered | 11 of 29 registered | 28 | 28 | 29 |
| BootUI API routes served, of the 65 that apply to Python | not measured | 33 (5 shape-identical, 28 partial) | 33 (5 shape-identical, 28 partial) | 33 (5 shape-identical, 28 partial) | 65 | not captured | not captured |

`tests/docs/test_parity_matrix.py` recomputes the sharpit 0.8.0 column from the code and the BootUI 2.5.0 fixtures
on every run. Routes remain measured against the 2.3.0 live goldens; the 2.5.0 static fixtures pin tools, properties,
and rule identifiers, while 2.5.0 live goldens await the reference app and databases. The sharpit 0.5.0, 0.6.0,
and 0.7.0 columns are frozen literals; BootUI columns use their respective tags.

How each row is counted:

- **Tools:** sharpit's MCP/CLI tool catalogue (`sharpit.engine.tools.TOOLS`) against BootUI's
  (`tests/fixtures/bootui/2.5.0/tools.json`; at BootUI's tags, `bootui-cli/src/main/resources/bootui-tools.json`).
  "Exact names" counts the sharpit tools whose name is also a BootUI tool name.
- **Panels:** sharpit's panel registry, and the panels `GET /sharpit/api/panels` lists. BootUI's count is the Spring
  sample app's (the live capture fixture, `tests/fixtures/bootui/2.5.0/panels.json`; at BootUI's tags,
  `bootui-conformance/.../expected-panels-spring.json`). Some BootUI panels are Java-only, so 48 of 65 is not a
  percentage of the work left.
- **Runtime insights:** sharpit registers all 28 of BootUI's insight kinds; 10 evaluate in 0.7.0; of the other 18, `proxy-bypass` and
  `event-loop-blocking` are recorded as not applicable (sharpit has no evidence source for them) and 16 are not
  implemented yet.
  A kind evaluates when it is implemented and every journal source it requires is one sharpit produces (all 10 do).
  BootUI counts the classes implementing `Observation`.
- **Routes:** the BootUI 2.3.0 live goldens (`tests/parity/routes_status.json`, measured against 2.3.0): 96 routes, of
  which 30 are Java-only; of the other 66, 5 match BootUI's shape, 28 are served with known differences and 33 are
  not built yet.

## The 8 insight kinds that evaluate in 0.6.0 and the 10 that evaluate in 0.7.0

0.6.0: `ai-usage-by-route`, `connections-per-request`, `errors-behind-2xx`, `exception-hotspots`,
`framework-warnings-by-route`, `lazy-sql-after-handler`, `route-time-breakdown`, `safe-method-dml`.

0.7.0 adds `unbatched-write-loop` and `repeated-selects`. `paged-without-order` remains deferred to 0.8.0 until BootUI's
SQL row-limit and shape analysis is ported without relying on regex approximation under masking.

## What 0.7.0 delivered (BootUI 2.4.0)

sharpit 0.7.0 targets BootUI 2.4.0 behaviour and engine robustness across existing features:

- **Evidence counters and descriptions (A1):** `insufficient` and `partial` counters on caught exceptions and runtime
  insights agent views, and adopted 2.4.0 tool descriptions (BootUI 2.4.0 #1589).
- **Static security analysis rule `SEC-STATIC-001` (A3):** detects local static security analyzer declarations (Bandit,
  Semgrep, CodeQL, a `sonar-project.properties` file, or Ruff with `S` selected) without execution, bounded to 1 MiB per
  file and 64 workflows (BootUI 2.4.0 #1597).
- **Database advisor incomplete discovery (A4):** missing driver metadata or failed ORM model discovery report WARNING
  diagnostics and leave advisor status `PARTIAL` rather than clean (BootUI 2.4.0 #1600); BootUI's incomplete PostgreSQL
  relation-inventory diagnostic is not reported yet.
- **Runtime journal robustness (A5a):** idempotent aggregate registration (BootUI 2.4.0 #1598); the request-profile
  timeline tie-break does not apply, since sharpit's request profile has no journal timeline.
- **UI read-only panel policy (A6):** action buttons are disabled with canonical refusal reasons, and 403 access denials
  display explicit refusal reasons rather than generic failure states (BootUI 2.4.0 #1602).
- **HTTP exchange recording resilience (A7):** recording failures never alter or disrupt streamed or committed HTTP
  responses or mask host exceptions (BootUI 2.4.0 #1615).
- **Runtime insights kinds (B1):** ports `unbatched-write-loop` and `repeated-selects` using BootUI 2.4.0 thresholds
  and request correlation.
- **`sharpit` command-line client (#60 / Track C):** standalone console script connecting over HTTP without extra
  dependencies, executing any tool from the catalogue with BootUI 2.4.0 exit codes (0 success, 1 error, 2 refused,
  3 threshold), global options (`--url`, `--api-path`, `--token`, `--timeout`, `--json`, `--no-color`, `-v`),
  `--fail-on` gates on finding severity or insufficient evidence, and MCP status/toggle commands.
- **Agent playbooks and AI-agents guide (G1):** six guided agent playbooks (`skills/sharpit/references/playbooks/`) with
  side-by-side MCP and CLI commands, plus an AI agents guide (`website/docs/ai-agents.md`).
- **MCP prompt arguments and verification (G2):** optional prompt arguments with Java whitespace and UTF-16 truncation
  semantics, masked context echoing, and the `verify_after_change` prompt.
- **Interactive tutorial (G3):** hands-on guided walkthrough (`website/docs/tutorial.md`) stepping through inspection,
  diagnosing issues, and verifying fixes with sharpit.
- **Bug fixes:** stable swallowed-exception identity hashing (#66 / E2), non-failing exit code for
  partial advisor coverage (#65 / E1), and explicit import-basis reporting for REST API app detection (#67 / E3).

## What is next (0.8.0)

Deferred lanes from 0.7.0 move to 0.8.0:

- **W0 live goldens:** capture per-panel 2.5.0 live goldens once BootUI 2.5.0 is built into the reference app with live databases; the static 2.5.0 fixtures now pin tools, properties and rule identifiers.
- **A2 (observed transaction boundaries):** port `TransactionBoundary.observed` and failed begin reporting once boundary tracking is optimized within the 30 µs budget.
- **B2 (transaction journal source and kinds):** add `transaction` journal events, `split-transaction-writes`, and `transaction-across-remote-call` after overhead audit.
- **B3 (ORM journal source and kinds):** add SQLAlchemy session events as the `orm` source and port ORM flush and context insight kinds.
- **B4 (authorization journal source and kinds):** observe FastAPI security dependencies as the `authorization` source for anonymous-access insight kinds.
- **B5 (remaining insight kinds):** classify and port or record deviations for app-event, garbage collection, and background executor insight kinds.
- **B6 (missing routes):** implement the 33 unserved BootUI API routes across scan results, runtime insights, traces, memory, and application structure.
- **B7 (partial routes):** close the 28 partial route differences or record detailed per-panel deviations.
- **D1 (SQLAlchemy listener race):** resolve class-level listener registration races across Engine, Pool, and Mapper.
- **D2 (SQL listener per-statement path):** evaluate BootUI 2.5.0 event-sink capture to reduce per-statement listener overhead.
- **D3 (SQL Trace panel availability):** align SQL Trace panel availability before a data source is wrapped.
- **D4 (connection and SQL facts):** audit follow-ups for connection statement counts and recorded-SQL presence flags.
- **D6 (masking safety):** single-pass quoted-text masking and strict fail-safe fallback for invalid email mask settings.
- **paged-without-order:** implement SQL row-limit and query shape analysis without inaccurate regex approximation under default masking.
- **E0 / #207:** handle `--sharpit-app` naming an object with no route list.

## After 0.7.0: Flask

The next framework adapter is Flask ([#75](https://github.com/ffroliva/sharpit/issues/75)). The engine is already
framework-free: the adapter implements the `AppIntrospector` port (`engine/spi.py`) over Flask's `url_map`, `config`,
`extensions` and blueprints, and Flask imports live only under `sharpit/flask/`. The gate comes first, the console
second:

1. request correlation through `before_request` and `teardown_request`, setting the existing `REQUEST` context var;
2. SQL capture through the existing SQLAlchemy listeners, so Flask-SQLAlchemy gets the same N+1 and query-budget
   checks;
3. the pytest plugin finding a Flask app through an adapter lookup instead of importing `FastApiIntrospector`;
4. then `sharpit.install(app)` for Flask, a `flask` extra and an `examples/flask_sqla` sample.
