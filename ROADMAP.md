# Roadmap: how close sharpit is to BootUI

sharpit is a Python/FastAPI port of [BootUI](https://github.com/jdubois/boot-ui), the Spring Boot developer console.
Each sharpit release targets one BootUI tag: 0.6.0 targets BootUI 2.3.0, 0.7.0 targets BootUI 2.4.0, and 0.8.0 targets BootUI 2.5.0. 0.9.0 stays on BootUI 2.5.0 and closes recorded gaps.

## Where it stands

| | sharpit 0.5.0 | sharpit 0.6.0 | sharpit 0.7.0 | sharpit 0.8.0 | sharpit 0.9.0 | BootUI 2.3.0 | BootUI 2.4.0 | BootUI 2.5.0 |
|---|---|---|---|---|---|---|---|---|
| MCP/CLI tools | 54 | 71 | 71 | 73 | 73 | 116 | 116 | 116 |
| Tools under BootUI's exact names | 45 | 62 | 62 | 64 | 64 | - | - | - |
| Panels | 31 | 48 (46 listed in the console) | 48 (46 listed in the console) | 49 (47 listed in the console) | 49 (47 listed in the console) | 65 (Spring) | 65 (Spring) | 65 (Spring) |
| Runtime insight kinds that evaluate | none | 8 of 28 registered | 10 of 28 registered | 11 of 29 registered | 11 of 29 registered | 28 | 28 | 29 |
| BootUI API routes served, of the 56 that apply to Python | not measured | 33 (5 shape-identical, 28 partial) | 33 (5 shape-identical, 28 partial) | 33 (5 shape-identical, 28 partial) | 33 (5 shape-identical, 28 partial) | 56 | not captured | not captured |

`tests/docs/test_parity_matrix.py` recomputes the sharpit 0.9.0 column from the code and the BootUI 2.5.0 fixtures
on every run. Routes remain measured against the 2.3.0 live goldens; the 2.5.0 static fixtures pin tools, properties,
and rule identifiers, while 2.5.0 live goldens await the reference app and databases. The sharpit 0.5.0, 0.6.0,
0.7.0 and 0.8.0 columns are frozen literals; BootUI columns use their respective tags.

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
- **Routes:** the BootUI 2.5.0 route inventory (`tests/parity/routes_status.json`): 97 routes, of
  which 41 are not applicable (including 10 JVM-only routes); of the other 56, 5 match BootUI's shape, 28 are served with known differences and 23 are
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

## What 0.8.0 delivered (BootUI 2.5.0)

sharpit 0.8.0 targets BootUI 2.5.0 behaviour, pentesting diagnostics and framework independence:

- **Request ID header:** application responses include `X-Sharpit-Request-Id` by default when recording HTTP exchanges ([#269](https://github.com/ffroliva/sharpit/issues/269)).
- **Swallowed exceptions from test doubles:** the pytest plugin attributes swallowed exceptions raised by test doubles in terminal summaries and reports ([#68](https://github.com/ffroliva/sharpit/issues/68), [#254](https://github.com/ffroliva/sharpit/issues/254)).
- **Pentesting panel and CLI:** synthetic in-process GET and OPTIONS probes check response headers, TRACE and TRACK handling, error disclosure, and technology disclosure without opening a socket ([#271](https://github.com/ffroliva/sharpit/issues/271)).
- **Pentesting CORS, cookie, and framework checks:** probes verify cross-origin policies, cookie security attributes and prefixes, FastAPI docs handlers, and proxy middleware exposure ([#275](https://github.com/ffroliva/sharpit/issues/275), [#277](https://github.com/ffroliva/sharpit/issues/277), [#279](https://github.com/ffroliva/sharpit/issues/279)).
- **HTTP security test gate:** opt-in pytest gate (`--sharpit-http-security`) validates observed requests against required response headers and statuses ([#272](https://github.com/ffroliva/sharpit/issues/272)).
- **Flask route inspection:** test-session gates read Flask `url_map` for the REST API advisor and enable SQLAlchemy checks without importing FastAPI ([#75](https://github.com/ffroliva/sharpit/issues/75), [#255](https://github.com/ffroliva/sharpit/issues/255), [#261](https://github.com/ffroliva/sharpit/issues/261)).
- **Route latency outliers:** Runtime Insights implements `route-latency-outliers` with baseline comparison and masked SQL statements ([#264](https://github.com/ffroliva/sharpit/issues/264)).
- **Vulnerability scan deadline:** configurable timeout bounds OSV and EPSS requests and reports partial findings on expiry ([#258](https://github.com/ffroliva/sharpit/issues/258)).
- **Binding diagnostics:** FastAPI exception capture extracts Pydantic validation error details and redacts path segments ([#270](https://github.com/ffroliva/sharpit/issues/270)).
- **Console navigation and mappings:** supports `basePath` from ASGI `root_path`, route selection in HTTP Probe, route ranking in HTTP Exchanges, and request profile stepping ([#266](https://github.com/ffroliva/sharpit/issues/266), [#267](https://github.com/ffroliva/sharpit/issues/267)).
- **Contract keys and retired rules:** emits BootUI 2.5.0 contract keys and retires or removes outdated rules ([#263](https://github.com/ffroliva/sharpit/issues/263), [#265](https://github.com/ffroliva/sharpit/issues/265)).
- **Application detection and advisor fixes:** uninspectable `--sharpit-app` objects degrade to `UNKNOWN`, routers are supported directly, and rule accuracy is improved ([#207](https://github.com/ffroliva/sharpit/issues/207), [#268](https://github.com/ffroliva/sharpit/issues/268), [#276](https://github.com/ffroliva/sharpit/issues/276)).
- **Security and masking guardrails:** forwarding headers require tokens even from loopback, and matrix parameters, SQL text, and exception messages are masked.

## What 0.9.0 delivered (BootUI 2.5.0 gaps)

sharpit 0.9.0 stays on BootUI 2.5.0 and closes part of the gaps recorded against it:

- **Housekeeping:** the 0.8.1 issues ([#284](https://github.com/ffroliva/sharpit/issues/284)–[#288](https://github.com/ffroliva/sharpit/issues/288)): database tool reads cancel on a caller timeout, host tools run on the requesting event loop, dead code removed, and two tests now exercise the production code. Exception capture moves out of `fastapi/capture.py`.
- **SQL capture hot path:** the SQL listener costs about 7 µs less per statement (paired sandbox runs), class-level listener attach is safe under concurrency, SQL Trace reports availability only when a source is wrapped, a failed listener attach is reported as unrecorded SQL, and the connection journal counts statements at check-in.
- **Route inventory:** `tests/parity/routes_status.json` is rebuilt against BootUI 2.5.0 and classifies every route.
- **2.5.0 rules:** five database rules are ported (`DB-SCHEMA-011`, `DB-PG-006`, `DB-SERVER-008`, `DB-MYSQL-004`, `DB-POOL-005`); five Spring-only REST API rules are recorded as not applicable.
- **Accepted findings:** the pytest accept marker takes a `reason=`, and `--sharpit-require-reason` makes it mandatory ([#253](https://github.com/ffroliva/sharpit/issues/253) item 2). An invalid `SHARPIT_EMAIL_MASK_CONTENT` keeps email content masked.
- **Offline documentation:** `sharpit docs` lists, reads and searches the documentation bundled with the package; the site publishes `llms.txt`.

## What is next (0.10.0)

Deferred from 0.9.0, each with a follow-up issue:

- **Flask console** ([#260](https://github.com/ffroliva/sharpit/issues/260)): the console contract is in `engine/console` (0.9.0, not wired); next come the response corpus that guards the handler move, the handler extraction one panel group at a time, `sharpit.install(app)` for Flask, request correlation and an example app.
- **Journal sources and insight kinds** ([#299](https://github.com/ffroliva/sharpit/issues/299)): transaction boundaries, transaction and ORM journal sources, authorization dependencies and the remaining kinds, within the 30 µs transaction budget.
- **API route parity** ([#300](https://github.com/ffroliva/sharpit/issues/300)): missing routes, same-route baselines and partial route differences from the 2.5.0 inventory.
- **`paged-without-order`** ([#301](https://github.com/ffroliva/sharpit/issues/301)): needs SQL row-limit and shape analysis that holds under masking.
- **Masking follow-ups:** the masked exception message in swallowed-exception findings ([#253](https://github.com/ffroliva/sharpit/issues/253) item 1) and trace and journal masking on the matrix path ([#302](https://github.com/ffroliva/sharpit/issues/302)).

## After 0.7.0: Flask

The next framework adapter is Flask ([#75](https://github.com/ffroliva/sharpit/issues/75)). The engine is already
framework-free: the adapter implements the `AppIntrospector` port (`engine/spi.py`) over Flask's `url_map`, `config`,
`extensions` and blueprints, and Flask imports live only under `sharpit/flask/`. The route model and the pytest gate
were delivered in 0.8.0 ([#75](https://github.com/ffroliva/sharpit/issues/75), [#255](https://github.com/ffroliva/sharpit/issues/255), [#261](https://github.com/ffroliva/sharpit/issues/261)):
the pytest plugin discovers Flask applications through adapter lookup, inspects routes over `url_map` for the REST API
advisor, and enables N+1 and query-budget checks on Flask-SQLAlchemy.

The console moves to 0.10.0 ([#260](https://github.com/ffroliva/sharpit/issues/260)): moving the console request
pipeline into the framework-free engine, providing `sharpit.install(app)` for Flask, request building and response translation in `sharpit.flask`,
and a `flask` extra.
