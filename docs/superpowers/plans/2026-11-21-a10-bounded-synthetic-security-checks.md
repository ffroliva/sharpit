# A10 Bounded Synthetic Security Checks Implementation Plan

> Run `/sharpit:status --feature a10-bounded-synthetic-security-checks` for the next unchecked step. Complete one task at a time and run `/sharpit:check` before each commit.

**Goal:** Add an explicitly invoked pentesting scan that evaluates bounded synthetic host-app evidence without opening a socket or exposing raw response data.

**Architecture:** Keep rule evaluation and DTO construction in the framework-free pentesting engine package; the FastAPI adapter invokes the outermost host ASGI application with synthetic requests and captures bounded response metadata. The probe runs as a cooperative async task on the request event loop; its caller acquires `SingleFlight.try_acquire()` and releases in `finally` after cancellation. Synchronous code that blocks that loop stalls the host and cannot be interrupted or given a hard deadline. GET returns initial or cached output; POST, MCP scan, and CLI scan are actions.

**Tech Stack:** Python 3.12+, Starlette/FastAPI ASGI interfaces, existing sharpit engine utilities, pytest, and sanitized BootUI fixtures.

**Review gate:** Complete the required high-tier review of this plan and record its disposition before implementation begins. The gate covers host-code execution by synthetic requests, action gates, transport limits, and the synchronous-call limitation above.

## Open question

- Does this design satisfy the required high-tier review gate? Record the disposition before implementation begins.

## Global Constraints

- Reads have no side effects; no GET route or read MCP/CLI tool opens a socket, writes a file, changes a logger level, or changes `os.environ`.
- Actions follow BootUI: matching POST/DELETE, MCP, and CLI actions pass enablement, guard, enabled-panel, non-read-only, and applicable single-flight gates.
- Secrets are masked before output; probe bodies, exception text, and unsafe header values are not returned.
- Python `>=3.12`; runtime dependencies exactly `starlette` and `packaging`; FastAPI remains optional outside `sharpit/fastapi/`.
- Every ported test cites its BootUI source with `# ported: <Class>.<method>`.
- No module under `src/` exceeds 1000 lines; ratchets only go down.

## Risk register

| Severity | Risk | Mitigation |
|---|---|---|
| Critical | Host response or exception leaks a credential | Drop raw body, exception text, and unsafe header values; test secret-bearing inputs. |
| Critical | Action runs from a read or bypasses panel/guard gates | Apply the same gates to route, MCP, and CLI actions; prove GET purity and refusals. |
| High | ASGI evidence is mistaken for listener or TLS evidence | Mark listener-only observations incomplete; state the ASGI boundary in report and docs. |
| High | TrustedHost rejects the synthetic Host with a 400 | Use BootUI's loopback Host; recognize rejection as incomplete before evaluating response headers. |
| High | A catch-all route answers the fixed missing path | Require status 404 for error-page evidence; any other status makes dependent error checks indeterminate and records the status. |
| High | Probe blocks or times out | Run on the request event loop with a cooperative async deadline; acquire `SingleFlight.try_acquire()` and release in `finally` after cancellation. Blocking synchronous host code stalls the host and cannot be interrupted. |
| High | Output limits drift from BootUI | Pin limits and no-follow redirect semantics from `PentestingLocalHttpResponse.java` and `JavaPentestingLocalHttpClient.java`; evaluate a returned 3xx as BootUI does rather than treating it as incomplete by itself. |
| Medium | PT findings cannot be dismissed | Add pentesting rule ownership and apply dismissals to initial, cached, and scanned reports. |

## File map

- `src/sharpit/engine/collectors/pentesting/`: bounded evidence, rules, report DTO, and service.
- `src/sharpit/fastapi/pentesting_probe.py`: ASGI request construction and response capture.
- `src/sharpit/fastapi/routes/pentesting.py`: report and scan route handlers; compose from `routes/__init__.py` without growing that file's route logic.
- `src/sharpit/engine/advisors/registry.py` and dismissal service: PT rule ownership and dismissal application.
- `src/sharpit/engine/tools04/`, CLI catalog/dispatch: BootUI report and scan tools with standard action gates.
- `tests/engine/collectors/pentesting/`, `tests/fastapi/`, and CLI/MCP tests: unit, integration, purity, and action-gate coverage.
- `tests/fixtures/bootui/2.5.0/pentesting/`: BootUI contract projection for rule fields and order; keep it separate from the hand-derived ASGI transport golden used for exact comparison.
- `tests/parity/routes_status.json`, `docs/reference/PARITY.md`, and `docs/reference/matrix-updates/0.8.0-a10.tsv`: parity and adaptations.
- `docs/superpowers/specs/2026-10-30-sharpit-mvp-design.md` §14: final deviations.

### Task 1: Freeze the BootUI probe and retention contract

**Commit:** `test: define bounded pentesting probe contract`

**Files:** probe and FastAPI tests; `docs/reference/matrix-updates/0.8.0-a10.tsv`.

**Interfaces:** Defines the GET/OPTIONS evidence consumed by Tasks 2–4.

- [ ] **Step 1:** Assert exactly GET then OPTIONS at `/__bootui_pentesting__/missing-resource`; GET has `Accept: text/html`; OPTIONS has `Origin: https://evil.example` and `Access-Control-Request-Method: GET`. Port the request-order assertion from `PentestingScannerTests.java:563` and add the `# ported:` citation to the pytest case.
- [ ] **Step 2:** Pin the 8 KiB body byte budget (`BoundedBodyReader.java`), 8,192 decoded body-character ceiling, 64 header names, 128 values, 256 characters per name, 4,096 per value, 16 KiB total header characters, 2-second BootUI connect/request timeout, and `Redirect.NEVER`. Cite `PentestingLocalHttpResponse.java`, `JavaPentestingLocalHttpClient.java`, and the bounded reader beside tests; the ASGI adapter has no connect phase or redirects to follow.
- [ ] **Step 3:** Assert overflow, Host rejection, and cooperative timeout become incomplete evidence; pin returned 3xx behavior to the BootUI rules (a 3xx alone is not incomplete). Include a synchronous blocker limitation test that does not claim in-process interruption.
- [ ] **Step 4:** Run the named tests and `uv run python scripts/dev/red_check.py <node ids>`; commit tests and matrix rows with explicit `git add` and `git commit -s`.

### Task 2: Implement the bounded in-process ASGI probe

**Commit:** `feat: add bounded in-process pentesting probe`

**Files:** `engine/collectors/pentesting/`, `fastapi/pentesting_probe.py`, focused tests.

**Interfaces:** Adapter returns framework-neutral bounded evidence; engine imports no Starlette/FastAPI.

- [ ] **Step 1:** Confirm Task 1 failures are named behavior assertions.
- [ ] **Step 2:** Implement fixed GET then OPTIONS requests with BootUI headers and limits, literal loopback Host, redirects inapplicable to direct ASGI, and no socket use.
- [ ] **Step 3:** Call the outermost host ASGI application as served, so host middleware runs; sharpit's mount `GuardMiddleware` is not on the fixed probe path. Test both facts. Classify `TrustedHostMiddleware` rejection and unavailable listener-added headers as incomplete, never clean. Preserve root path; treat unsupported streaming/response behavior as incomplete.
- [ ] **Step 4:** Acquire single-flight with `SingleFlight.try_acquire()` for the async request lifetime. Apply BootUI's 2-second request budget to cooperative async work and cancel it on expiry; release the acquisition in `finally`. Test that an awaited handler exceeding the deadline is cancelled and a subsequent scan succeeds. State that synchronous code blocking the event loop stalls the host and cannot be interrupted in-process; do not promise a hard elapsed-time bound.
- [ ] **Step 5:** Run focused tests and commit with explicit paths and `git commit -s`.

### Task 3: Port checks, report DTO, and dismissals

**Commit:** `feat: add BootUI pentesting checks`

**Files:** pentesting engine, `engine/advisors/registry.py`, dismissal/report service, tests, sanitized golden.

**Interfaces:** Consumes bounded evidence; produces BootUI-compatible report with sharpit's masking and dismissal behavior.

- [ ] **Step 1:** Add registry order assertion against `PentestingCheckRegistry.java:35-64`; exclude retired IDs.
- [ ] **Step 2:** Port active checks and named BootUI cases for headers, CSP, HSTS, framing, error disclosure, and technology disclosure. Add `# ported:` citations at test definitions.
- [ ] **Step 3:** Assert complete DTO keys, nulls, camelCase, IDs, titles, severities, remediation, and stable order against a BootUI-derived contract projection. Unobserved listener headers and incomplete probes must not yield clean no-finding results. Keep the exact-comparison ASGI golden hand-derived because the BootUI listener capture includes socket/server-layer evidence absent from in-process ASGI.
- [ ] **Step 4:** Require status 404 for the fixed missing-resource path. A non-404 status makes PT-A05-006 and other error-body-derived checks indeterminate and includes the status in evidence; add `test_non_404_synthetic_response_makes_error_rules_indeterminate`.
- [ ] **Step 5:** Add PT ownership and test dismissal of an initial, cached, and scanned finding. `advisor_for()` currently owns only registered advisors (`engine/advisors/registry.py:52-74`); unknown IDs are refused by `owning_panel()` (`engine/advisors/dismissals.py:91-96`).
- [ ] **Step 6:** Create separate hand-derived ASGI and BootUI rule-contract fixtures using fixture conventions; keep response secrets and live host content out. Run red check and focused tests, then commit.

### Task 4: Wire GET and gated scan actions

**Commit:** `feat: expose gated pentesting scan`

**Files:** focused pentesting route module and route composition, panel registry, FastAPI/MCP/CLI routes and catalogs, `src/sharpit/cli/fail_on.py`, `tests/cli/test_fail_on.py`, `tests/parity/test_tools_parity.py`, tests.

**Interfaces:** GET returns initial/cached report without invoking host code. POST returns the full report DTO; MCP `pentest_scan` and CLI `pentest scan` invoke the same action but return BootUI's compact scan summary (including `reportTool`, `scan`, `findingsFound`, `severityCounts`, `topFindings` capped at 10, `moreFindings`, and `evidence`). Report reads expose `get_pentest_report` and `pentest report`.

- [ ] **Step 1:** Add tests for inactive 404, guard rejection, disabled/read-only refusal, GET purity using `no_side_effects`, and host call counts.
- [ ] **Step 2:** Add MCP-off refusal, MCP read-only refusal, CLI action gates, and action catalogue/schema parity. Dispatch async probe work with the established `ctx.capture.loop` plus `asyncio.run_coroutine_threadsafe` pattern when the host loop is running; only use `asyncio.run` when no host loop exists. Assert `test_pentest_tools_are_classified_for_cli_fail_on_and_bootui_parity` through the existing fail-on and tool parity checks. BootUI entries are `tests/fixtures/bootui/2.5.0/tools.json` (including the compact scan response in `McpScanSummaries.java`); both MCP tools and CLI report/scan commands exist.
- [ ] **Step 3:** Add overlap and failure-release tests; match BootUI single-flight behavior for cooperative probes. When MCP/CLI runs the scan from a worker, submit to the host loop and let the coroutine own and release its single-flight acquisition.
- [ ] **Step 4:** Implement routes in `fastapi/routes/pentesting.py`, route composition, MCP and CLI parity using existing tools patterns. Add both tools to `ADVISOR_TOOLS` and tool parity membership/BootUI markers.
- [ ] **Step 5:** Run focused tests and `red_check.py` before any `test:` commit; commit implementation with explicit paths and DCO sign-off.

### Task 5: Parity, docs, and lane gates

**Commit:** `docs: document bounded pentesting evidence`

**Files:** `tests/parity/routes_status.json`, `docs/reference/PARITY.md`, A10 matrix, design §14, user docs, relevant tests.

- [ ] **Step 1:** Mark pentesting report/scan route and tool/CLI parity according to implemented coverage; add the BootUI CLI commands to `MATCHED_TOOLS` with `pytest.mark.bootui("cli:pentest report|scan")`, update the matched-tools pin, and update the existing dropped-tools row in `PARITY.md:132`. Mark `pentesting/captured.json` `n-a` with difference `golden contains an empty list; item shape cannot establish matched parity` if the route golden is still empty; otherwise classify its actual fixture shape.
- [ ] **Step 2:** Verify scenario names map to tests, registry order and report golden match BootUI v2.5.0, and the asynchronous deadline limitation is accurately described.
- [ ] **Step 3:** Run lane tests, `uv run ruff check`, `uv run ruff format --check`, and `uv run pyright`; report counts and results.
- [ ] **Step 4:** Record final transport deviations in the matrix and spec §14; commit docs with explicit paths and `git commit -s`.

## Definition of done

- [ ] High-tier review acceptance is recorded before implementation.
- [ ] All Critical/High scenarios have named passing tests; inactive, guard, read-only, and GET-purity gates hold.
- [ ] BootUI probe sequence, retention limits, redirect behavior, rule registry, and report DTO are covered; ASGI and BootUI contract fixtures are distinct.
- [ ] Secrets never escape; incomplete ASGI evidence never appears clean; synchronous event-loop blocking is documented as uninterruptible.
- [ ] MCP and CLI report/scan actions match BootUI's distinct response shapes and use existing gates and parity classifications.
- [ ] Parity status, A10 matrix, and design §14 reflect the implementation.
- [ ] Lane tests and repository gates pass; live verification describes ASGI-only evidence.
