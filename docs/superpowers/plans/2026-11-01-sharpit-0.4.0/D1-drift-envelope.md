# Lane D1: 2.2.0 Envelope, Dismissed Findings, Overview, and Core Panel Drift

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

- **Lane ID:** `D1`
- **Evidence folder:** `.superpowers/sdd/0.4.0/lanes/D1/`
- **Goal:** Bring the global API envelope (`GET/POST/DELETE /dismissed-findings`, `overview` run stamp & `"Scorecard"` title, security header deduplication, and `config`/`beans`/`mappings`/`loggers`/`cli` MCP projection defaults) to BootUI 2.2.0 contract parity.
- **Spec sections:** §9 D1, §6.1 (definition of done), §10.2 (Order 2, committed lane), §10.3 (lane gate & review requirements); contract `docs/reference/BOOTUI-CONTRACT-0.4-DRIFT.md` §§1–6, 9 and `docs/reference/BOOTUI-CONTRACT-MVP.md` §§1, 10.
- **Worker profile:** **M**, **judgement-heavy** (touches `src/sharpit/engine/guard.py` and shared advisor dismissal state; default worker in `PLAN.md`: `claude-flavio (Opus)`).
- **Depends on:** `F` (`F-foundation.md` §"Foundation consumer interface table"). `G1G2`, `D2`, `D3`, and `D4` depend on `D1` so advisor panels and the pytest plugin inherit `DismissedFinding` support.
- **Foundation interfaces consumed (`F-foundation.md` §"Foundation consumer interface table"):**
  - `sharpit.fastapi.routes.dismissed_findings`, `sharpit.fastapi.routes.overview`, `sharpit.fastapi.routes.panels`, `sharpit.fastapi.adapter` (`_read_capped(request: Request, cap: int) -> bytes | None`, `GuardMiddleware.send_with_headers`)
  - `sharpit.engine.tools` (compatibility facade) and `sharpit.engine.tool_stubs.*`
  - `tests.golden.assert_parity(sharpit_id: str, name: str, payload: Mapping[str, Any]) -> None`
  - `tests/safety/` and `tests/masking/` packages (`tests/safety/test_d1_safety.py`, `tests/masking/test_d1_masking.py`)
- **Files this lane MAY touch:**
  - `src/sharpit/engine/guard.py`
  - `src/sharpit/engine/headers.py`
  - `src/sharpit/engine/panels.py`
  - `src/sharpit/engine/context.py`
  - `src/sharpit/engine/advisors/dismissals.py`
  - `src/sharpit/engine/advisors/report.py`
  - `src/sharpit/engine/collectors/overview.py`
  - `src/sharpit/engine/collectors/restapi/service.py`
  - `src/sharpit/engine/tools.py` (and `src/sharpit/engine/tool_stubs/{config,beans}.py` if split by `F`)
  - `src/sharpit/fastapi/adapter.py`, `src/sharpit/fastapi/routes/dismissed_findings.py` (new or stubbed by `F`), `src/sharpit/fastapi/routes/overview.py`
  - `tests/engine/advisors/test_dismissals.py`, `tests/engine/advisors/test_advisor_report.py`, `tests/engine/test_guard.py`, `tests/engine/test_headers.py`, `tests/engine/test_panels.py`, `tests/engine/test_overview.py`, `tests/engine/test_context.py`, `tests/engine/test_tools.py`, `tests/fastapi/test_dismissed_rules_api.py`, `tests/fastapi/test_dismissed_findings_api.py` (new), `tests/safety/test_d1_safety.py` (new), `tests/masking/test_d1_masking.py` (new)
  - `.superpowers/sdd/0.4.0/lanes/D1/{predict-council.md,handoff.md,findings.md,field-map.md,checklist.md}`
- **Files this lane MUST NOT touch (spec §10.3 & conventions C2/C5):**
  - `scripts/dev/lane_gate.py`, `tests/complexity_baseline.json` (unless every touched value strictly decreases or an entry is removed), `sonar-baseline.txt`, `tests/engine/test_import_boundary.py` rules, overhead budget constants, `uv.lock`, `pyproject.toml` dependency lists.
  - `tests/test_safety_matrix.py` and `tests/test_masking_corpus.py` (C5: add D1 rows only in `tests/safety/test_d1_safety.py` and `tests/masking/test_d1_masking.py`).
  - `.superpowers/sdd/0.4.0/lanes/*/review.md` and `.superpowers/sdd/0.4.0/lanes/*/gate/*` or `live-verify.md` (C2: written only by the coordinator/reviewer in the integration worktree; `lane_gate.py` refuses lane diffs touching them).
  - Capture modules (`src/sharpit/engine/capture/*` — Lane `D2`), DB/runtime modules (`pools.py`, `alembic.py`, `health.py`, `threads.py` — Lane `D3`), `vulns/*`, `mcp.py`, `restapi/rules.py` (Lane `D4`), or any other lane's collector.

## Definition of Done Coverage (Spec §6.1 — C8 Order)

| # | Spec §6.1 Item (in spec order) | Satisfying Task |
|---|---|---|
| 1 | **Golden parity:** `tests/golden.py::assert_parity` against `tests/fixtures/bootui/2.2.0/<sharpit-id>/<name>.json` + `nullable.json`, and `field-map.md` | Task 3 (Step 4) |
| 2 | **Ported tests:** each ported behaviour test cites `# ported: <BootUI class>.<method>` | Task 1 (Step 1), Task 2 (Step 1), Task 3 (Step 1) |
| 3 | **Safety & masking:** `no_side_effects` on every GET; panel in `PANELS` with `actionCapable` and `SHARPIT_PANELS_<ID>_ENABLED/_READ_ONLY`; guard chain unchanged; `tests/safety/test_d1_safety.py` & `tests/masking/test_d1_masking.py` | Task 0, Task 1 (Step 1), Task 2 (Steps 1–3), Task 3 (Step 4) |
| 4 | **Gatekeeper / import boundary:** optional imports via gatekeepers only (§6.3); `tests/engine/test_import_boundary.py` green | Task 3 (Step 4) |
| 5 | **Overhead budget:** hot-path overhead budget tests (`tests/fastapi/test_capture_overhead.py`, `tests/fastapi/test_sql_trace_overhead.py`) untouched and green | Task 3 (Step 4) |
| 6 | **MCP read-only:** MCP exposes read tools only (`get_config`, `get_beans` with `INVENTORY_DEFAULT_LIMIT = 25` and `propertySuggestions` stripped on MCP); action tools CLI-only | Task 3 (Steps 1–3) |
| 7 | **Svelte 5 view:** `N/A — envelope/drift lane; UI placeholders and Scorecard label are handled by F / panel views` | N/A |
| 8 | **Four gates + lowest-direct + no-SQLAlchemy:** `ruff check`, `ruff format --check`, `pyright`, `pytest` green in lane worktree; coordinator records `gate/*.log` in integration worktree | Task 3 (Step 4) |
| 9 | **Live check:** coordinator records `live-verify.md` in integration worktree against `examples/fastapi_sqla` | Task 3 (Step 4) |
| 10 | **Handoff:** `.superpowers/sdd/0.4.0/lanes/D1/handoff.md` current (§10.3) | Task 3 (Step 4) |

## Review Focus

1. **Global write policy on `/dismissed-findings` (`src/sharpit/engine/guard.py:42, 47, 287-288, 308-324`; `src/sharpit/engine/panels.py:51-55`)**: `GET /dismissed-findings` must be allowed whenever sharpit is active (even if all advisor panels are disabled or `read_only=True`), whereas `POST` and `DELETE /dismissed-findings` must return `403` via `_panel_denied("dismissed-findings", read_only_reason("dismissed-findings", True))` with exact verbatim body `{"error": "sharpit panel access denied", "panel": "dismissed-findings", "reason": "sharpit is read-only via SHARPIT_READ_ONLY=true"}` when `settings.read_only=True`. Pinned by `test_mvc_global_read_only_blocks_the_mutations_but_not_the_list` in **Task 2**.
2. **Error body never echoes raw request payload or `note` on `/dismissed-findings`**: Malformed JSON, wrong field types, blank `ruleId`/`identity`, or array payloads on `POST`/`DELETE /dismissed-findings` must return the fixed message `"Request body must be a JSON object with string fields ruleId, identity and an optional note."` without quoting the body or note (which may hold sensitive user notes), reading the body via `await _read_capped(request, small_cap)` (`src/sharpit/fastapi/adapter.py:490, 604-614`). Pinned by `test_mvc_refuses_bad_bodies_with_a_fixed_message_that_never_quotes_the_note` and `test_mvc_reads_the_body_as_bytes_so_the_framework_never_logs_the_note` in **Task 2**.
3. **YAML round-trip fidelity & Base64URL note encoding in `DismissalStore` (`src/sharpit/engine/advisors/dismissals.py:43-127`)**: Notes may contain newlines, colons, quotes, or Unicode; they serialize as `n=<base64url_no_pad>` after `<ruleId> <identity>`, preserve unrelated YAML sections (`dismissedRules:`, custom keys) and unparseable lines (`ignored` count), enforce `MAX_FINDINGS = 1000` (HTTP 409) and `MAX_NOTE_LENGTH = 200` (HTTP 400), and produce byte-identical rewrites. `DismissalStore.dismissed_set(self) -> set[str]` merges rule IDs from `self.list()` and finding identities from `self.list_findings()` for advisor services and `G1G2`. Pinned by `test_preserves_other_top_level_sections_across_writes`, `test_repeated_writes_are_byte_stable`, and `test_dismissed_findings_note_and_cap_validation` in **Task 1**.
4. **Per-header case-insensitive deduplication in `GuardMiddleware.send_with_headers` (`src/sharpit/fastapi/adapter.py:135-142`, `src/sharpit/engine/headers.py:20-32`)**: `GuardMiddleware.send_with_headers` currently gates the entire `security_headers("api")` loop on `if "content-security-policy" not in headers:`. Deduplicate each header from `security_headers("api")` case-insensitively by header name (`if name.lower() not in headers:`) so pre-existing individual downstream headers (e.g. `X-Content-Type-Options`, `Cache-Control`) are never duplicated while missing baseline headers are still added. Pinned by `test_security_headers_are_not_duplicated_when_downstream_sets_them` in **Task 2**.
5. **Overview `run` identity stability vs restart ordinal (`src/sharpit/engine/context.py:25-61`, `src/sharpit/engine/collectors/overview.py:19-40`)**: `instanceId` (8-char lowercase hex) is fixed per Python process, while `runId` (8-char lowercase hex), `ordinal` (1-based `itertools.count(1)`), and `startedAt` (epoch ms) advance on each `SharpitContext` creation. Pinned by `test_overview_emits_run_metadata_and_scorecard_panel_title` in **Task 3**.

---

### Task 0: Safety Pre-Check (`/sharpit:predict` and `/sharpit:llm-council --tier high`)

Because `D1` modifies `src/sharpit/engine/guard.py` (`_GLOBAL_WRITE_SUBJECTS` and `_panel_access`) and `GuardMiddleware` header injection, `AGENTS.md` (Safety model) requires running `/sharpit:predict` and `/sharpit:llm-council --tier high` before writing code.

**Files:**
- Create: `.superpowers/sdd/0.4.0/lanes/D1/predict-council.md`

- [ ] **Step 1: Run `/sharpit:predict` with the exact D1 safety brief**

Run workflow `skills/predict/SKILL.md` with this exact brief:
> **Proposal (Lane D1):** (1) Add `"/dismissed-findings": "dismissed-findings"` to `_GLOBAL_WRITE_SUBJECTS` in `src/sharpit/engine/guard.py:47` so `GET {api}/dismissed-findings` is allowed without a panel id and `POST`/`DELETE {api}/dismissed-findings` are gated by global `settings.read_only` (returning `403` via `_panel_denied("dismissed-findings", read_only_reason("dismissed-findings", True))`, i.e. `{"error": "sharpit panel access denied", "panel": "dismissed-findings", "reason": "sharpit is read-only via SHARPIT_READ_ONLY=true"}`) after the full guard chain (`security headers → trusted source → Host allow-list → cross-site → token`); (2) Read `POST`/`DELETE /dismissed-findings` bodies as raw capped bytes (`await _read_capped(request, small_cap)`, 64 KiB max), require `Content-Type: application/json` (415 otherwise), never echo user input or `note` in 400 error responses, and persist `<ruleId> <identity> [n=<base64url_no_pad>]` under `dismissedFindings:` in `<state_dir>/sharpit.yml` with `MAX_FINDINGS=1000` (409) and `MAX_NOTE_LENGTH=200` (400); (3) Check each header from `security_headers("api")` case-insensitively in `GuardMiddleware.send_with_headers` (`src/sharpit/fastapi/adapter.py:135-142`) so individual headers set downstream are not duplicated.

- [ ] **Step 2: Run `/sharpit:llm-council --tier high` with the exact D1 council brief**

Run workflow `skills/llm-council/SKILL.md` (`--tier high`) with the same brief plus `src/sharpit/engine/guard.py:39-106, 287-324` and `src/sharpit/engine/advisors/dismissals.py:1-128`. Record both verdicts in `.superpowers/sdd/0.4.0/lanes/D1/predict-council.md`. Stop if either verdict is NO-GO.

---

### Task 1: `DismissalStore` Support for `dismissedFindings` and Advisor Occurrence Matching

**Files:**
- Modify: `src/sharpit/engine/advisors/dismissals.py:1-128`
- Modify: `src/sharpit/engine/advisors/report.py:28-66`
- Modify: `src/sharpit/engine/collectors/restapi/service.py:83-95, 127-177`
- Test: `tests/engine/advisors/test_dismissals.py`, `tests/engine/advisors/test_advisor_report.py`

**Interfaces:**
- Produces in `src/sharpit/engine/advisors/dismissals.py`:
  - `MAX_FINDINGS: Final[int] = 1000`
  - `MAX_NOTE_LENGTH: Final[int] = 200`
  - `@dataclass(frozen=True, slots=True) class DismissedFinding: rule_id: str; identity: str; note: str | None = None` with `def to_dto(self) -> dict[str, str | None]`
  - `@dataclass(frozen=True, slots=True) class Findings: dismissed: list[DismissedFinding]; ignored: int` with `def to_dto(self) -> dict[str, Any]`
  - `DismissalStore`:
    - `def list_findings(self) -> Findings`
    - `def dismiss_finding(self, rule_id: str, identity: str, note: str | None = None) -> Findings`
    - `def restore_finding(self, rule_id: str, identity: str) -> Findings`
    - `def dismissed_set(self) -> set[str]` (merges rule IDs from `self.list().dismissed` and finding identities from `self.list_findings().dismissed`; consumed by `RestApiService.report`/`_scan` in `src/sharpit/engine/collectors/restapi/service.py:129, 152` and by `G1G2` in `pytest_plugin`)
- Updates `apply_dismissals(report: Mapping[str, Any], dismissed: Collection[str], occurrences: Mapping[str, Sequence[tuple[str, str]]] | None = None) -> dict[str, Any]` (`src/sharpit/engine/advisors/report.py:28-66`) and `_run(done: _Evaluation, dismissed: Collection[str], fail_on: Severity, app: str | None) -> AdvisorRun` (`src/sharpit/engine/collectors/restapi/service.py:83-87`) so findings dismissed via `DismissalStore.dismissed_set()` or `(rule_id, identity)` are marked dismissed and counted in `dismissedTotal`.

- [ ] **Step 1: Add minimal stubs in `dismissals.py`, then write failing unit tests in `tests/engine/advisors/test_dismissals.py` and `tests/engine/advisors/test_advisor_report.py` (C4: RED must be an assertion failure, never `ImportError`/`AttributeError`)**

First add minimal stub signatures (`DismissedFinding`, `Findings(dismissed=[], ignored=0)`, and `DismissalStore.{list_findings,dismiss_finding,restore_finding,dismissed_set}` returning empty `Findings([], 0)` / `set()`) so test collection succeeds and fails on assertions. Then add tests citing BootUI 2.2.0 `DismissedRulesStoreTests`:
- `# ported: DismissedRulesStoreTests.preservesOtherTopLevelSectionsAcrossWrites` (`test_preserves_other_top_level_sections_across_writes`: dismissing a rule and a finding preserves both `dismissedRules:` and `dismissedFindings:` plus unrelated top-level YAML sections).
- `# ported: DismissedRulesStoreTests.repeatedWritesAreByteStable` (`test_repeated_writes_are_byte_stable`: dismissing the same `(rule_id, identity, note)` twice produces byte-identical `sharpit.yml` and updates the note in place).
- `test_dismissed_findings_note_and_cap_validation`: verifies Base64URL no-pad round-trip for notes with spaces/newlines/Unicode, whitespace-only note normalizes to `None`, `len(note) > 200` raises `DismissalValidationError("Dismissed finding note must be at most 200 characters.")`, >1000 distinct findings raises `DismissalCapError("Too many dismissed findings: restore some before dismissing more.")`, and malformed lines under `dismissedFindings:` increment `ignored` and survive rewrites.
- `test_apply_dismissals_marks_dismissed_finding_by_identity_or_fingerprint`: verifies `apply_dismissals` (`src/sharpit/engine/advisors/report.py:28-66`) and `RestApiService._run` (`src/sharpit/engine/collectors/restapi/service.py:83-87`) mark an occurrence as dismissed when its `id` or `fingerprint` is in `store.dismissed_set()`.

- [ ] **Step 2: Run `uv run pytest -q tests/engine/advisors/test_dismissals.py tests/engine/advisors/test_advisor_report.py` and verify RED**

Expected failure: `AssertionError` on `list_findings().dismissed` / `apply_dismissals` count (not `ImportError` or `AttributeError`).

- [ ] **Step 3: Implement `DismissedFinding`, `Findings`, YAML `dismissedFindings:` parser/serializer, and advisor matching**

In `src/sharpit/engine/advisors/dismissals.py`:
- Validate `rule_id` (`_RULE_ID_RE`, max 64 chars, no whitespace), `identity` (trimmed non-empty, max 512 chars, no whitespace/control chars), and `note` (trimmed; empty becomes `None`; `len(note) <= 200`, no `\x00`).
- Encode note as `n=` + `base64.urlsafe_b64encode(note.encode("utf-8")).decode("ascii").rstrip("=")` on `  - <ruleId> <identity>[ n=<b64>]` lines under `dismissedFindings:`.
- Implement `DismissalStore.dismissed_set(self) -> set[str]` returning `set(self.list().dismissed) | {f.identity for f in self.list_findings().dismissed}` and wire `RestApiService.report` / `RestApiService._scan` (`src/sharpit/engine/collectors/restapi/service.py:129, 152`) to pass `self._ctx.dismissals.dismissed_set()` into `apply_dismissals` and `_run`.

- [ ] **Step 4: Run `uv run pytest -q tests/engine/advisors/test_dismissals.py tests/engine/advisors/test_advisor_report.py` and commit**

Expected: PASS. Commit: `feat(advisors): add dismissedFindings YAML store and occurrence matching`.

---

### Task 2: Guard Policy, `/dismissed-findings` HTTP Routes, Security Header Deduplication, and `"Scorecard"` Title

**Files:**
- Modify: `src/sharpit/engine/guard.py:42, 47, 287-288, 308-324`
- Modify: `src/sharpit/engine/headers.py:20-32`
- Modify: `src/sharpit/engine/panels.py:21, 51-55`
- Modify: `src/sharpit/fastapi/adapter.py:135-142, 489-540, 604-614` (and `src/sharpit/fastapi/routes/dismissed_findings.py` if split by `F`)
- Test: `tests/engine/test_guard.py`, `tests/engine/test_headers.py`, `tests/engine/test_panels.py`, `tests/fastapi/test_dismissed_findings_api.py` (new), `tests/safety/test_d1_safety.py` (new), `tests/masking/test_d1_masking.py` (new)

**Interfaces:**
- Consumes: `DismissalStore.list_findings`, `dismiss_finding`, `restore_finding`, `DismissalValidationError`, `DismissalCapError`, `DismissalStorageError` from Task 1; `_read_capped(request: Request, cap: int) -> bytes | None` (`src/sharpit/fastapi/adapter.py:604`); `security_headers("api")` (`src/sharpit/engine/headers.py:20`).
- Produces:
  - `_GLOBAL_WRITE_SUBJECTS = {"/dismissed-rules": "dismissed-rules", "/dismissed-findings": "dismissed-findings"}` in `src/sharpit/engine/guard.py:47`.
  - Routes `GET {api}/dismissed-findings`, `POST {api}/dismissed-findings`, `DELETE {api}/dismissed-findings`.
  - Per-header case-insensitive deduplication in `GuardMiddleware.send_with_headers` (`src/sharpit/fastapi/adapter.py:135-142`) using `security_headers("api")`.
  - `Panel("overview", "Scorecard", None, None)` in `src/sharpit/engine/panels.py:21`.

- [ ] **Step 1: Write failing guard, route, header, and safety/masking tests**

In `tests/engine/test_guard.py`, `tests/engine/test_headers.py`, `tests/engine/test_panels.py`, `tests/fastapi/test_dismissed_findings_api.py`, `tests/safety/test_d1_safety.py`, and `tests/masking/test_d1_masking.py`, add:
- `# ported: DismissedFindingsControllerTests.mvcDismissesListsAndRestoresAFindingWithItsNote` (`test_mvc_dismisses_lists_and_restores_a_finding_with_its_note`)
- `# ported: DismissedFindingsControllerTests.mvcRefusesBadBodiesWithAFixedMessageThatNeverQuotesTheNote` (`test_mvc_refuses_bad_bodies_with_a_fixed_message_that_never_quotes_the_note`)
- `# ported: DismissedFindingsControllerTests.mvcGlobalReadOnlyBlocksTheMutationsButNotTheList` (`test_mvc_global_read_only_blocks_the_mutations_but_not_the_list`: asserts `403` with `{"error": "sharpit panel access denied", "panel": "dismissed-findings", "reason": "sharpit is read-only via SHARPIT_READ_ONLY=true"}`)
- `# ported: DismissedFindingsControllerTests.mvcReadsTheBodyAsBytesSoTheFrameworkNeverLogsTheNote` (`test_mvc_reads_the_body_as_bytes_so_the_framework_never_logs_the_note`)
- `test_dismissed_findings_requires_json_content_type_and_enforces_409_503` (415 on missing `application/json`, 409 on cap > 1000, 503 when `state_dir=None`, `no_side_effects` fixture on `GET /sharpit/api/dismissed-findings` in `tests/safety/test_d1_safety.py`, and secret-note error non-echo in `tests/masking/test_d1_masking.py`).
- `test_security_headers_are_not_duplicated_when_downstream_sets_them` and `test_overview_panel_title_is_scorecard`.

- [ ] **Step 2: Run `uv run pytest -q tests/engine/test_guard.py tests/engine/test_headers.py tests/engine/test_panels.py tests/fastapi/test_dismissed_findings_api.py tests/safety/test_d1_safety.py tests/masking/test_d1_masking.py` and verify RED**

Expected failure: `AssertionError` on 404 for `/sharpit/api/dismissed-findings`, duplicate `x-content-type-options` header count, and `'Overview' == 'Scorecard'`.

- [ ] **Step 3: Implement guard subject, routes, header deduplication, and `"Scorecard"` panel title**

- In `src/sharpit/engine/guard.py:47`, add `"/dismissed-findings": "dismissed-findings"` to `_GLOBAL_WRITE_SUBJECTS`.
- In `src/sharpit/engine/panels.py:21`, change `Panel("overview", "Overview", None, None)` to `Panel("overview", "Scorecard", None, None)`.
- In `GuardMiddleware.send_with_headers` (`src/sharpit/fastapi/adapter.py:135-142`), iterate `for name, value in security_headers("api"):` and append `(name.encode("latin-1"), value.encode("latin-1"))` only when `name.lower() not in headers`.
- In `src/sharpit/fastapi/adapter.py` (or `src/sharpit/fastapi/routes/dismissed_findings.py`), register `GET`, `POST`, and `DELETE` on `f"{api}/dismissed-findings"`. Read the body via `await _read_capped(request, small_cap)` (`small_cap = min(cap, 65_536)`), require `application/json` (415 `{"error": "Content-Type must be application/json."}` matching `/dismissed-rules` at `adapter.py:514-518`), parse JSON dict with string `ruleId` and `identity` plus optional string/null `note`, and return `400 {"error": "Request body must be a JSON object with string fields ruleId, identity and an optional note."}` on any shape/type error without echoing the payload.

- [ ] **Step 4: Run tests and commit**

Run `uv run pytest -q tests/engine/test_guard.py tests/engine/test_headers.py tests/engine/test_panels.py tests/fastapi/test_dismissed_findings_api.py tests/safety/test_d1_safety.py tests/masking/test_d1_masking.py`. Commit: `feat(api): add /dismissed-findings routes, header dedup, and Scorecard title`.

---

### Task 3: Overview `run` DTO, MCP Default Limits (`config`/`beans`), and Golden Conformance

**Files:**
- Modify: `src/sharpit/engine/context.py:1-62`
- Modify: `src/sharpit/engine/collectors/overview.py:19-40`
- Modify: `src/sharpit/engine/tools.py:160-175, 425-445` (and `src/sharpit/engine/tool_stubs/{config,beans}.py` if split by `F`)
- Test: `tests/engine/test_overview.py`, `tests/engine/test_context.py`, `tests/engine/test_tools.py`

**Interfaces:**
- Consumes: `tests/golden.py::assert_parity(sharpit_id: str, name: str, payload: Mapping[str, Any]) -> None` from `F`.
- Produces:
  - `SharpitContext.instance_id: str`, `run_id: str`, `run_ordinal: int`, `started_at_ms: int` in `src/sharpit/engine/context.py`.
  - `overview_dto` key `"run": {"instanceId": str, "runId": str, "ordinal": int, "startedAt": int}` in `src/sharpit/engine/collectors/overview.py`.
  - `INVENTORY_DEFAULT_LIMIT: Final[int] = 25` applied in `get_config` and `get_beans` when `limit` is omitted on MCP, and `propertySuggestions` omitted from `get_config` MCP projection (`docs/reference/BOOTUI-CONTRACT-0.4-DRIFT.md` §§3, 6).

- [ ] **Step 1: Write failing tests in `tests/engine/test_overview.py` and `tests/engine/test_tools.py`**

- `test_overview_emits_run_metadata_and_scorecard_panel_title`: asserts `overview["run"]` contains `instanceId` (8 hex chars, constant across contexts in-process), `runId` (8 hex chars, distinct per context), `ordinal` (increments by 1), and `startedAt` (epoch ms int), and checks `assert_parity("overview", "default", overview)`.
- `# ported: McpAgentViewsTests.configDefaultLimitAndStripsPropertySuggestions` and `# ported: McpAgentViewsTests.beansDefaultLimit`: asserts MCP `get_config({})` and `get_beans({})` cap rows to `25` (`INVENTORY_DEFAULT_LIMIT`) when `limit` is omitted and `get_config` MCP output does not contain `propertySuggestions`, while HTTP `GET /sharpit/api/config` still emits `"propertySuggestions": []`.

- [ ] **Step 2: Run `uv run pytest -q tests/engine/test_overview.py tests/engine/test_tools.py` and verify RED**

Expected failure: `AssertionError` on `'run' in overview` in `test_overview.py` and `'propertySuggestions' not in result` in `test_tools.py`.

- [ ] **Step 3: Implement `SharpitContext` run stamp, `overview_dto["run"]`, and MCP `get_config`/`get_beans` projection**

- In `src/sharpit/engine/context.py`, define module-level `_INSTANCE_ID: Final[str] = secrets.token_hex(4)` and `_RUN_ORDINAL = itertools.count(1)`. Populate `instance_id`, `run_id = secrets.token_hex(4)`, `run_ordinal = next(_RUN_ORDINAL)`, and `started_at_ms = int(time.time() * 1000)` on `SharpitContext`.
- In `src/sharpit/engine/collectors/overview.py:26-39`, add `"run": {"instanceId": ctx.instance_id, "runId": ctx.run_id, "ordinal": ctx.run_ordinal, "startedAt": ctx.started_at_ms}` (with fallback defaults when `ctx` is `None`).
- In `src/sharpit/engine/tools.py`, apply `INVENTORY_DEFAULT_LIMIT = 25` when `limit` is `None` for MCP calls to `get_config` and `get_beans`, and strip `propertySuggestions` in the MCP `get_config` projection while keeping CLI/HTTP full reports intact.

- [ ] **Step 4: Run verification gates in the lane worktree, update implementer evidence, and commit**

Run detached with timeout and log files:
1. `uv run ruff check && uv run ruff format --check && uv run pyright`
2. `uv run pytest -q tests/engine/test_overview.py tests/engine/test_context.py tests/engine/test_tools.py tests/engine/advisors/test_dismissals.py tests/engine/advisors/test_advisor_report.py tests/engine/test_guard.py tests/engine/test_headers.py tests/engine/test_panels.py tests/fastapi/test_dismissed_rules_api.py tests/fastapi/test_dismissed_findings_api.py tests/safety/test_d1_safety.py tests/masking/test_d1_masking.py tests/engine/test_import_boundary.py tests/test_code_shape.py`
3. Update `.superpowers/sdd/0.4.0/lanes/D1/{field-map.md,findings.md,checklist.md,handoff.md}` (never touch `review.md` or `gate/`).
4. Commit: `feat(overview,mcp): add 2.2.0 run metadata and MCP inventory default limits`.

---

## Lane Evidence Checklist (`lane_gate.py` — Spec §10.3 & C2)

**Written by the implementer in the lane worktree (`.superpowers/sdd/0.4.0/lanes/D1/`):**
- [ ] `predict-council.md` — GO verdict from `/sharpit:predict` and `/sharpit:llm-council --tier high` (Task 0).
- [ ] `field-map.md` — Every BootUI 2.2.0 key for `dismissed-findings`, `overview`, `config`, `mappings`, `loggers`, `beans`, `cli` mapped to its Python source or `tests/fixtures/bootui/2.2.0/<sharpit-id>/nullable.json` entry.
- [ ] `findings.md` — `finding → test → red` table; every row `fixed` (with red-test name) or `parked` (with reason).
- [ ] `checklist.md` — Spec §6.1's 10 items in spec §6.1's exact order (1 golden parity … 10 handoff), each with an evidence path or `N/A` + reason.
- [ ] `handoff.md` — Current state: last green command, next step (`ready-for-review`), open findings (`none`).

**Written by the coordinator/reviewer in the integration worktree ONLY (never touched by the lane's diff; `lane_gate.py` refuses it):**
- [ ] `review.md` — Fresh reviewer subagent (`reviewer_id != implementer_id`) + `/code-review high` + `ponytail-review` (required because D1 touches `guard.py`), naming the head commit SHA, ending with `VERDICT: APPROVE`.
- [ ] `gate/{ruff-check,ruff-format,pyright,pytest,lowest-direct,no-sqlalchemy}.log` and `live-verify.md`.
