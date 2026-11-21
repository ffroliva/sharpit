# A10 Bounded Synthetic Security Checks Implementation Plan

> Run `/sharpit:status --feature a10-bounded-synthetic-security-checks` for the next unchecked step. Complete one task at a time and run `/sharpit:check` before each commit.

**Goal:** Add an explicitly invoked pentesting scan that evaluates bounded synthetic host-app evidence without opening a socket or exposing raw response data.

**Architecture:** Keep rule evaluation and DTO construction in the framework-free pentesting engine package; the FastAPI adapter constructs the synthetic ASGI requests and captures bounded response metadata. Reuse existing action, panel, single-flight, masking, MCP, CLI, and route patterns. GET returns initial or cached output; POST, MCP scan, and CLI scan are actions.

**Tech Stack:** Python 3.12+, Starlette/FastAPI ASGI interfaces, existing sharpit engine utilities, pytest, and sanitized BootUI fixtures.

**Review gate:** Complete a high-tier review of this plan and record acceptance before implementation begins. The gate covers host-code execution by synthetic requests, action gates, transport limits, and the unresolved synchronous-call limitation below.

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
| High | Probe blocks or times out | Enforce cooperative async deadline and cancellation. In-process cancellation cannot stop synchronous host code blocking the event loop; report this as a transport limit and make no hard deadline guarantee for it. |
| High | Output limits drift from BootUI | Pin limits and redirect behavior from `PentestingLocalHttpResponse.java` and `JavaPentestingLocalHttpClient.java`. |
| Medium | PT findings cannot be dismissed | Add pentesting rule ownership and apply dismissals to initial, cached, and scanned reports. |

## File map

- `src/sharpit/engine/collectors/pentesting/`: bounded evidence, rules, report DTO, and service.
- `src/sharpit/fastapi/pentesting_probe.py`: ASGI request construction and response capture.
- `src/sharpit/fastapi/routes/pentesting.py`: report and scan route handlers; compose from `routes/__init__.py` without growing that file's route logic.
- `src/sharpit/engine/advisors/registry.py` and dismissal service: PT rule ownership and dismissal application.
- `src/sharpit/engine/tools04/`, CLI catalog/dispatch: BootUI report and scan tools with standard action gates.
- `tests/engine/collectors/pentesting/`, `tests/fastapi/`, and CLI/MCP tests: unit, integration, purity, and action-gate coverage.
- `tests/fixtures/bootui/2.5.0/pentesting/`: sanitized scanned report golden.
- `tests/parity/routes_status.json`, `docs/reference/PARITY.md`, and `docs/reference/matrix-updates/0.8.0-a10.tsv`: parity and adaptations.
- `docs/superpowers/specs/2026-10-30-sharpit-mvp-design.md` §14: final deviations.

### Task 1: Freeze the BootUI probe and retention contract

**Commit:** `test: define bounded pentesting probe contract`

**Files:** probe and FastAPI tests; `docs/reference/matrix-updates/0.8.0-a10.tsv`.

**Interfaces:** Defines the GET/OPTIONS evidence consumed by Tasks 2–4.

- [ ] **Step 1:** Assert exactly GET then OPTIONS at `/__bootui_pentesting__/missing-resource`; GET has `Accept: text/html`; OPTIONS has `Origin: https://evil.example` and `Access-Control-Request-Method: GET`. Port the request-order assertion from `PentestingScannerTests.java:563` and add the `# ported:` citation to the pytest case.
- [ ] **Step 2:** Pin the 8 KiB body byte budget (`BoundedBodyReader.java`), 8,192 decoded body-character ceiling, 64 header names, 128 values, 256 characters per name, 4,096 per value, 16 KiB total header characters, 2-second BootUI connect/request timeout, and `Redirect.NEVER`. Cite `PentestingLocalHttpResponse.java`, `JavaPentestingLocalHttpClient.java`, and the bounded reader beside tests; the ASGI adapter has no connect phase or redirects to follow.
- [ ] **Step 3:** Assert overflow, redirect, Host rejection, and cooperative timeout become incomplete evidence; include a synchronous blocker limitation test that does not claim in-process interruption.
- [ ] **Step 4:** Run the named tests and `uv run python scripts/dev/red_check.py <node ids>`; commit tests and matrix rows with explicit `git add` and `git commit -s`.

### Task 2: Implement the bounded in-process ASGI probe

**Commit:** `feat: add bounded in-process pentesting probe`

**Files:** `engine/collectors/pentesting/`, `fastapi/pentesting_probe.py`, focused tests.

**Interfaces:** Adapter returns framework-neutral bounded evidence; engine imports no Starlette/FastAPI.

- [ ] **Step 1:** Confirm Task 1 failures are named behavior assertions.
- [ ] **Step 2:** Implement fixed GET then OPTIONS requests with BootUI headers and limits, literal loopback Host, redirects inapplicable to direct ASGI, and no socket use.
- [ ] **Step 3:** Run through host middleware; classify `TrustedHostMiddleware` rejection and unavailable listener-added headers as incomplete, never clean. Preserve root path; treat unsupported streaming/response behavior as incomplete.
- [ ] **Step 4:** Apply BootUI's 2-second request budget to cooperative async work and cancel it on expiry. State in the result that a synchronous callable blocking the event loop cannot be interrupted in-process; do not promise a hard elapsed-time bound for that case.
- [ ] **Step 5:** Run focused tests and commit with explicit paths and `git commit -s`.

### Task 3: Port checks, report DTO, and dismissals

**Commit:** `feat: add BootUI pentesting checks`

**Files:** pentesting engine, `engine/advisors/registry.py`, dismissal/report service, tests, sanitized golden.

**Interfaces:** Consumes bounded evidence; produces BootUI-compatible report with sharpit's masking and dismissal behavior.

- [ ] **Step 1:** Add registry order assertion against `PentestingCheckRegistry.java:35-64`; exclude retired IDs.
- [ ] **Step 2:** Port active checks and named BootUI cases for headers, CSP, HSTS, framing, error disclosure, and technology disclosure. Add `# ported:` citations at test definitions.
- [ ] **Step 3:** Assert complete DTO keys, nulls, camelCase, IDs, titles, severities, remediation, and stable order. Unobserved listener headers and incomplete probes must not yield clean no-finding results.
- [ ] **Step 4:** Add PT ownership and test dismissal of an initial, cached, and scanned finding. `advisor_for()` currently owns only registered advisors (`engine/advisors/registry.py:52-74`); unknown IDs are refused by `owning_panel()` (`engine/advisors/dismissals.py:91-96`).
- [ ] **Step 5:** Create the sanitized golden using fixture conventions; keep response secrets and live host content out. Run red check and focused tests, then commit.

### Task 4: Wire GET and gated scan actions

**Commit:** `feat: expose gated pentesting scan`

**Files:** focused pentesting route module and route composition, panel registry, FastAPI/MCP/CLI routes and catalogs, tests.

**Interfaces:** GET returns initial/cached report without invoking host code. POST, MCP `pentest_scan`, and CLI `pentest scan` run the same action; report reads expose `get_pentest_report` and `pentest report`.

- [ ] **Step 1:** Add tests for inactive 404, guard rejection, disabled/read-only refusal, GET purity using `no_side_effects`, and host call counts.
- [ ] **Step 2:** Add MCP-off refusal, MCP read-only refusal, CLI action gates, and action catalogue/schema parity. BootUI fixture entries are `tools.json:2029-2067`; both MCP tools and CLI report/scan commands exist.
- [ ] **Step 3:** Add overlap and failure-release tests; match BootUI single-flight behavior for cooperative probes.
- [ ] **Step 4:** Implement routes in `fastapi/routes/pentesting.py`, route composition, MCP and CLI parity using existing tools patterns.
- [ ] **Step 5:** Run focused tests and `red_check.py` before any `test:` commit; commit implementation with explicit paths and DCO sign-off.

### Task 5: Parity, docs, and lane gates

**Commit:** `docs: document bounded pentesting evidence`

**Files:** `tests/parity/routes_status.json`, `docs/reference/PARITY.md`, A10 matrix, design §14, user docs, relevant tests.

- [ ] **Step 1:** Mark pentesting report/scan route and tool/CLI parity according to implemented coverage; update the existing dropped-tools row in `PARITY.md:132`.
- [ ] **Step 2:** Verify scenario names map to tests, registry order and report golden match BootUI v2.5.0, and the asynchronous deadline limitation is accurately described.
- [ ] **Step 3:** Run lane tests, `uv run ruff check`, `uv run ruff format --check`, and `uv run pyright`; report counts and results.
- [ ] **Step 4:** Record final transport deviations in the matrix and spec §14; commit docs with explicit paths and `git commit -s`.

## Definition of done

- [ ] High-tier review acceptance is recorded before implementation.
- [ ] All Critical/High scenarios have named passing tests; inactive, guard, read-only, and GET-purity gates hold.
- [ ] BootUI probe sequence, retention limits, redirect behavior, rule registry, and report DTO are covered.
- [ ] Secrets never escape; incomplete ASGI evidence never appears clean; synchronous event-loop blocking is documented as uninterruptible.
- [ ] MCP and CLI report/scan actions match BootUI and use existing gates.
- [ ] Parity status, A10 matrix, and design §14 reflect the implementation.
- [ ] Lane tests and repository gates pass; live verification describes ASGI-only evidence.
