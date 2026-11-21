# A10 Bounded Synthetic Security Checks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an explicitly invoked pentesting scan that evaluates bounded synthetic host-app evidence without opening a socket or exposing raw response data.

**Architecture:** Keep rule evaluation and DTO construction in the framework-free pentesting engine package and implement the synthetic request through the FastAPI adapter's ASGI port. Reuse the existing action, panel, single-flight, masking, and route patterns. The scan is action-only; GET returns initial or cached output.

**Tech Stack:** Python 3.12+, Starlette/FastAPI ASGI interfaces, existing sharpit engine utilities, pytest, sanitized BootUI golden fixtures.

**Predict verdict:** GO WITH CONDITIONS, confidence 7/10. Before implementation, council must resolve the source mismatch: prediction describes one GET, but v2.5.0 `PentestingScanner.java` sends both GET and OPTIONS. Pin source and tests; do not choose probe count from the prediction summary.

## Global Constraints

- Reads have no side effects: no GET route and no read MCP or CLI tool of the console installed in a host application may open a socket, write a file, change a logger level or change `os.environ`.
- Actions follow BootUI: action routes are POST or DELETE only where BootUI has the same action; after MCP/CLI enablement as applicable, the guard chain, enabled panel, non-read-only panel, and single-flight where BootUI uses it.
- Secrets are masked before filtering and before any output (JSON, errors, MCP, CLI).
- Network is used only by actions that call out in BootUI too; failures are reported and locks released.
- Introspection is defensive: FastAPI/Starlette internals change between versions; degrade, never crash the host.
- Python `>=3.12`; runtime dependencies exactly `starlette` and `packaging`; `fastapi` is optional outside `sharpit/fastapi/`.
- Each ported test cites its BootUI source: `# ported: PentestingScannerTests.<method>`.
- No module under `src/` over 1000 lines; ratchets only go down.

## Risk register

| Severity | Risk | Mitigation |
|---|---|---|
| Critical | An action leaks a credential from response headers/body or host exception | Keep raw values out of findings/status/errors; test a secret-bearing host response. |
| Critical | A synthetic request executes host behavior from a read path or bypasses panel/guard checks | Probe only after POST action gates; GET purity and read-only refusal tests. |
| High | ASGI evidence is mistaken for listener/TLS evidence | Label report as in-process ASGI evidence; preserve BootUI disclaimer intent and explicitly state it does not measure deployed edge/TLS. |
| High | ASGI behavior differs from listener behavior or unsupported response cannot finish | Bound the call; report timeout, streaming, lifespan, or unsupported response limitations as incomplete. |
| High | Prediction's one-GET description diverges from pinned BootUI GET+OPTIONS | Council resolves the source/test mismatch before implementation and records the accepted method in the matrix/spec. |
| High | Oversized body/header causes memory or latency growth | Enforce the verified BootUI retention/body bounds before constructing output. |

## File map

- `src/sharpit/engine/collectors/pentesting/`: bounded context, deterministic rules, report DTO and service.
- `src/sharpit/fastapi/`: adapter implementation for ASGI invocation and route wiring.
- `src/sharpit/fastapi/routes/__init__.py`: route composition and action gates, following existing advisor routes.
- `tests/engine/collectors/pentesting/` and `tests/fastapi/`: unit, integration, no-side-effects and single-flight tests.
- `tests/fixtures/bootui/2.5.0/pentesting/`: sanitized scanned report golden.
- `docs/reference/matrix-updates/0.8.0-a10.tsv` and `docs/superpowers/specs/2026-10-30-sharpit-mvp-design.md` §14: accepted transport/body deviations only.

### Task 1: Freeze probe and output contract

**Commit:** `test: define bounded pentesting probe contract`

**Files:** `tests/engine/collectors/pentesting/test_probe.py`; `tests/fastapi/test_pentesting_api.py`; A10 matrix fragment.

**Interfaces:** Defines probe request/evidence expectations consumed by Tasks 2–4. Resolve the GET versus GET+OPTIONS question against `PentestingScanner.java`, `PentestingChecks.java`, and `PentestingScannerTests.java` at v2.5.0 before setting assertions.

- [ ] **Step 1:** Add tests for fixed path and method count, response body/header retention bounds, deadline timeout, and failed/truncated probe becoming incomplete evidence. Expected red: assertions on observed requests/limits/status fail, not import or collection errors.
- [ ] **Step 2:** Run focused tests with `uv run pytest -q -n 4 tests/engine/collectors/pentesting/test_probe.py tests/fastapi/test_pentesting_api.py`; capture the named failing assertions and run `uv run python scripts/dev/red_check.py <node ids>` before a `test:` commit.
- [ ] **Step 3:** Record only council-approved adaptations in `docs/reference/matrix-updates/0.8.0-a10.tsv`; use the existing TSV columns and add the matching spec §14 row as part of its implementation task.
- [ ] **Step 4:** Commit the contract tests and matrix decision with `git add <explicit paths>` and `git commit -s -m "test: define bounded pentesting probe contract"`.

### Task 2: Implement bounded in-process ASGI probe

**Commit:** `feat: add bounded in-process pentesting probe`

**Files:** `src/sharpit/engine/collectors/pentesting/probe.py`; `src/sharpit/fastapi/pentesting_probe.py`; `tests/engine/collectors/pentesting/test_probe.py`; `tests/fastapi/test_pentesting_api.py`.

**Interfaces:** Engine receives a framework-neutral probe result/context; FastAPI adapter owns ASGI request construction and returns bounded response metadata. Engine must not import Starlette/FastAPI.

- [ ] **Step 1:** Run the Task 1 contract test and verify it fails on the named behavioral assertions.
- [ ] **Step 2:** Implement a fixed synthetic path and only the council-approved methods; cap elapsed time, retained headers, and inspected body using verified BootUI limits. Convert host exceptions, timeouts, and unsupported streaming/lifespan cases to explicit incomplete evidence without exposing exception text.
- [ ] **Step 3:** Test scope `root_path`, host middleware execution, response truncation, timeout, and no sockets. Keep unsupported behavior as incomplete evidence.
- [ ] **Step 4:** Run the focused engine and FastAPI tests, then commit with `git add <explicit paths>` and `git commit -s -m "feat: add bounded in-process pentesting probe"`.

### Task 3: Port A10 rules and report contract

**Commit:** `feat: add BootUI pentesting checks`

**Files:** `src/sharpit/engine/collectors/pentesting/`; `tests/engine/collectors/pentesting/test_checks.py`; `tests/fixtures/bootui/2.5.0/pentesting/scanned.captured.json`; `tests/fixtures/bootui/2.5.0/pentesting/meta.json`.

**Interfaces:** Consumes the Task 2 framework-neutral evidence and produces report/check DTOs. Port active check registry order and checks from v2.5.0 `PentestingCheckRegistry.java` and `PentestingChecks.java`; exclude retired IDs.

- [ ] **Step 1:** Port named BootUI tests for missing security headers, frame protection, Referrer-Policy, CSP, XSS header, HSTS, COOP/CORP, verbose error disclosure, and technology disclosure. Every ported case includes `# ported: PentestingScannerTests.<method>`.
- [ ] **Step 2:** Add assertions for every DTO key, null fields, camelCase, stable check/finding order, exact IDs/titles/severity/remediation, and sanitized evidence. Expected red: contract-field/order/value assertions identify the missing behavior.
- [ ] **Step 3:** Generate or hand-sanitize the 2.5.0 golden using repository fixture conventions; no live host response or secret-bearing body is committed.
- [ ] **Step 4:** Implement the smallest engine rules/report that satisfy the tests, run focused tests, then commit with `git add <explicit paths>` and `git commit -s -m "feat: add BootUI pentesting checks"`.

### Task 4: Wire panel, report GET, and gated scan POST

**Commit:** `feat: expose gated pentesting scan`

**Files:** `src/sharpit/engine/panels.py`; `src/sharpit/fastapi/routes/__init__.py` or focused route module; `src/sharpit/fastapi/adapter.py` only if required by existing wiring; `tests/fastapi/test_pentesting_api.py`; `tests/conftest.py` only if fixture changes are necessary.

**Interfaces:** Route delegates to pentesting service through the existing `SharpitContext`; POST uses existing guard and panel access decisions plus single-flight. GET returns initial/cached report and does no app invocation.

- [ ] **Step 1:** Add tests for inactive 404, guard rejection, disabled/read-only panel refusal, GET purity using `no_side_effects`, and no host invocation from GET. Expected red: response status/call-count assertions fail.
- [ ] **Step 2:** Add scan overlap and failure-release tests; assert 409 busy while active and successful subsequent scan after a probe failure.
- [ ] **Step 3:** Implement report GET and scan POST using existing route/action patterns; do not add MCP scan or CLI action absent BootUI catalogue precedent.
- [ ] **Step 4:** Run focused tests and `uv run python scripts/dev/red_check.py <node ids>` before any `test:` commit; commit implementation with `git add <explicit paths>` and `git commit -s -m "feat: expose gated pentesting scan"`.

### Task 5: Parity, docs, and lane gates

**Commit:** `docs: document bounded pentesting evidence`

**Files:** `docs/reference/matrix-updates/0.8.0-a10.tsv`; `docs/superpowers/specs/2026-10-30-sharpit-mvp-design.md` §14; user docs only if the action is user-visible; relevant pentesting tests.

**Interfaces:** Matrix/spec document the final deviations; docs describe the endpoint/action and ASGI evidence boundary without implying deployed-edge or TLS validation.

- [ ] **Step 1:** Verify all Critical/High scenario names map to implemented tests; extend existing tests only where necessary.
- [ ] **Step 2:** Verify active registry order and goldens against BootUI v2.5.0, including retired-rule exclusion and the approved probe method count.
- [ ] **Step 3:** Run lane tests, `uv run ruff check`, `uv run ruff format --check`, and `uv run pyright`; report exact results. Run doc tests `uv run pytest -q -n 4 tests/test_docs*.py` only if they exist.
- [ ] **Step 4:** Commit the final matrix/spec/docs changes with `git add <explicit paths>` and `git commit -s -m "docs: document bounded pentesting evidence"`.

## Definition of done

- [ ] All steps checked and each commit signed off with DCO.
- [ ] All Critical/High scenario tests pass; inactive, cross-site/guarded, read-only, and GET-purity conditions hold.
- [ ] Probe limits and failure/truncation reporting are verified; raw response values and exception text never escape.
- [ ] Report golden matches the accepted BootUI v2.5.0 contract and excludes retired rules.
- [ ] Accepted deviations are recorded in the A10 matrix fragment and spec §14.
- [ ] `uv run ruff check`, `uv run ruff format --check`, `uv run pyright`, and relevant lane tests pass.
- [ ] `/sharpit:live-verify` evidence exists for the changed endpoint; results are described as in-process ASGI evidence.

Plan complete. Next: `/sharpit:status --feature a10-bounded-synthetic-security-checks`, then execute task by task with `superpowers:subagent-driven-development`.
