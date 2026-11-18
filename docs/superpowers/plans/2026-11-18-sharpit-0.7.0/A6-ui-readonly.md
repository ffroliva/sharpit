# A6: read-only policy in the UI

> **For agentic workers:** one task at a time; `/sharpit:check` before every commit; `scripts/dev/red_check.py`
> before every `test:` commit. Read the named BootUI files at `v2.4.0` in a BootUI clone; never from a summary.

**Goal:** sharpit 0.7.0 matches BootUI 2.4.0 (#1602) read-only panel policy in the UI: `ApiError` displays
`"<reason> (HTTP 403)"` for panel access refusals, panel access refusals are not treated as "server unreachable",
action targets fail closed via a canonical `panelActionReason(panel)` helper in BootUI's priority order, and all action
buttons use this helper. Overview run-all policy differences are recorded.

**Architecture:** Frontend port in Svelte 5 + TypeScript under `ui/`. Backend guard (`src/sharpit/engine/guard.py`)
already emits 403 `{"error": "sharpit panel access denied", "panel": panel, "reason": reason}` and remains unchanged.
The UI layers error formatting in `ui/src/lib/api.ts` and `ui/src/lib/loadError.ts`, canonical action policy in
`ui/src/lib/panelState.ts`, and applies `panelActionReason(panel)` to all mutating views and controls.

**Predict verdict:** not required (frontend only; server safety model and architecture rules unchanged).

## Scenarios

| Scenario | Expected behaviour | BootUI source |
|---|---|---|
| Panel access refusal (403) | `ApiError` message is `"<reason> (HTTP 403)"` when status is 403 and `error === "sharpit panel access denied"`; other HTTP errors remain `HTTP <status>` | `bootui-ui/.../api.js:8-27`, `api.test.js` |
| Policy text with network phrase | `describeLoadError` keeps `serverUnreachable: false` and preserves canonical refusal message | `bootui-ui/.../loadError.js:40-54`, `loadError.test.js` |
| Unresolved / missing panel | `panelActionReason(panel)` fails closed returning action permissions unavailable | `bootui-ui/.../panelState.js:4-11`, `panelState.test.js` |
| Disabled panel | `panelActionReason` returns configuration disabled reason (`enabled=false`) | `bootui-ui/.../panelState.js:6`, `panelState.test.js` |
| Structurally unavailable panel | `panelActionReason` returns `unavailableReason` or fallback | `bootui-ui/.../panelState.js:7`, `panelState.test.js` |
| Read-only panel | `panelActionReason` returns `readOnlyReason` or `'This panel is read-only.'` | `bootui-ui/.../panelState.js:8`, `panelState.test.js` |
| Writable panel | `panelActionReason` returns `null` | `bootui-ui/.../panelState.js:10`, `panelState.test.js` |
| Mutating actions across views | Action buttons and handlers check `panelActionReason(panel)` before triggering mutations; disabled and title reflect reason | `bootui-ui/.../views/actionPolicy.test.js` |
| Overview run-all | sharpit Overview has no run-all or advisor scorecards; documented in matrix fragment | `bootui-ui/.../views/Overview.vue` |

## Tasks

### Task 1: `ApiError` canonical refusal format and load error classification

**Files:** `ui/src/lib/api.ts`, `ui/src/lib/loadError.ts` (new), `ui/tests/unit/api.test.ts`, `ui/tests/unit/loadError.test.ts` (new).

- [ ] **Step 1:** Write failing tests for `ApiError` formatting and `isPanelAccessError` in `ui/tests/unit/api.test.ts`, and `describeLoadError`/`formatLoadError` in `ui/tests/unit/loadError.test.ts`.
- [ ] **Step 2:** Implement `isPanelAccessDenied`, `isPanelAccessError`, and update `ApiError` constructor in `ui/src/lib/api.ts`.
- [ ] **Step 3:** Implement `toErrorMessage`, `isAbortError`, `isServerUnreachableError`, `describeLoadError`, `formatLoadErrorDescription`, and `formatLoadError` in `ui/src/lib/loadError.ts`.
- [ ] **Step 4:** Verify unit tests pass and commit.

### Task 2: Canonical `panelActionReason` helper

**Files:** `ui/src/lib/panelState.ts` (new), `ui/tests/unit/panelState.test.ts` (new).

- [ ] **Step 1:** Write failing tests in `ui/tests/unit/panelState.test.ts` checking BootUI's evaluation order: null/unresolved -> disabled -> unavailable -> readOnly -> non-boolean readOnly -> writable (null).
- [ ] **Step 2:** Implement `panelDisabledReason` and `panelActionReason` in `ui/src/lib/panelState.ts`.
- [ ] **Step 3:** Verify unit tests pass and commit.

### Task 3: Unify action buttons across views to use `panelActionReason`

**Files:** `ui/src/views/*.svelte`, `ui/src/components/AdvisorPanel.svelte`, `ui/tests/component/actionPolicy.test.ts` (new).

- [ ] **Step 1:** Write component tests in `ui/tests/component/actionPolicy.test.ts` testing policy changes, disabled button states, and late 403 refusal messages.
- [ ] **Step 2:** Update views (`Alembic.svelte`, `Exceptions.svelte`, `Health.svelte`, `HttpProbe.svelte`, `Loggers.svelte`, `MySql.svelte`, `PostgreSql.svelte`, `ServerStatus.svelte`, `SqlTrace.svelte`, `Traces.svelte`, `Transactions.svelte`, `Vulnerabilities.svelte`, and advisors `Architecture.svelte`, `DatabaseAdvisor.svelte`, `Fastapi.svelte`, `RestApi.svelte`, `Security.svelte`) to derive `actionReason = $derived(panelActionReason(panel))` and remove ad-hoc read-only checks.
- [ ] **Step 3:** Run vitest suite to verify all existing and new tests pass and commit.

### Task 4: Overview deviation fragment

**Files:** `docs/reference/matrix-updates/a6-ui-readonly.tsv` (new).

- [ ] **Step 1:** Create `docs/reference/matrix-updates/a6-ui-readonly.tsv` recording that sharpit Overview displays facts only and has no scanner cards or run-all.
- [ ] **Step 2:** Commit `docs:` update.

### Task 5: Build static UI and execute test gates

**Files:** `src/sharpit/ui/static/**`.

- [ ] **Step 1:** Rebuild UI with `npm run build` in `ui/` (updating `src/sharpit/ui/static/`).
- [ ] **Step 2:** Run Python tests (`test_ui_no_html.py`, `test_ui_rules.py`, `test_code_shape.py`, `test_install.py`, etc.).
- [ ] **Step 3:** Run `ruff check`, `ruff format --check`, `pyright`, and vitest test suite.
- [ ] **Step 4:** Commit built static assets and finalize report.
