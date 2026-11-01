# Lane D1: 2.2.0 Envelope, Dismissed Findings, Overview, and Core Panel Drift

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

- **Lane ID:** `D1`
- **Goal:** Bring the global API envelope (`GET/POST/DELETE /dismissed-findings`, `overview` run stamp & `"Scorecard"` title, security header deduplication, and `config`/`beans`/`mappings`/`loggers`/`cli` MCP projection defaults) to BootUI 2.2.0 contract parity.
- **Spec sections:** §9 D1, §6.1 (definition of done), §10.2 (Order 2, committed lane), §10.3 (lane gate & review requirements); contract `docs/reference/BOOTUI-CONTRACT-0.4-DRIFT.md` §§1–6, 9 and `docs/reference/BOOTUI-CONTRACT-MVP.md` §§1, 10.
- **Worker profile:** **M**, **judgement-heavy** (touches `src/sharpit/engine/guard.py` and shared advisor dismissal state; requires `codex` or `claude-flavio`).
- **Dependencies:** Foundation commit **F** (spec §10.2 Order 0) must be merged first. D1 merges before Wave G (`G1`, `G2`) and Wave A (`P1`–`P3`) so advisor panels inherit `DismissedFinding` support.
- **Files this lane MAY touch:**
  - `src/sharpit/engine/guard.py`
  - `src/sharpit/engine/headers.py`
  - `src/sharpit/engine/panels.py`
  - `src/sharpit/engine/context.py`
  - `src/sharpit/engine/advisors/dismissals.py`
  - `src/sharpit/engine/advisors/report.py`
  - `src/sharpit/engine/collectors/overview.py`
  - `src/sharpit/engine/collectors/restapi/service.py`
  - `src/sharpit/engine/tools.py` (or the split MCP projection module created by F)
  - `src/sharpit/fastapi/adapter.py` (or the envelope/dismissed-findings route module split by F)
  - `tests/engine/test_guard.py`, `tests/engine/test_dismissals.py`, `tests/engine/test_overview.py`, `tests/engine/test_tools.py`, `tests/fastapi/test_dismissed_findings_api.py`, `tests/fastapi/test_security_headers.py`, `tests/test_conformance.py`
  - `.superpowers/sdd/0.4.0/lanes/D1/*`
- **Files this lane MUST NOT touch (spec §10.3 protected files & other lanes):**
  - `scripts/dev/lane_gate.py`, `tests/complexity_baseline.json` (except lowering a count), `sonar-baseline.txt`, `tests/engine/test_import_boundary.py` rules, overhead budget constants, `uv.lock`, `pyproject.toml` dependency lists.
  - Capture modules (`src/sharpit/engine/capture/*` — Lane D2), DB/runtime modules (`pools.py`, `alembic.py`, `health.py`, `threads.py` — Lane D3), `vulns/*`, `mcp.py`, `restapi/rules.py` (Lane D4), or any new 0.4.0 panel collector (`P1`–`P10`, `G1`–`G2`).

## Definition of Done Coverage (Spec §6.1)

| §6.1 Item | Requirement | Satisfying Task |
|---|---|---|
| 1 | Golden fixture parity (`tests/fixtures/bootui/2.2.0/` + `nullable.json`) & `field-map.md` | Task 3 (Step 4) |
| 2 | Guard chain on every route (`security headers → trusted source → Host → cross-site → token → panel access`) | Task 0, Task 2 (Steps 1–3) |
| 3 | Masking before filtering/output across HTTP, MCP, CLI (`expose-values` modes) | Task 1 (Step 1), Task 2 (Step 2), Task 3 (Step 3) |
| 4 | `no_side_effects` on all GET routes and MCP tools (`GET /dismissed-findings`, `overview`, `get_config`, `get_beans`) | Task 2 (Step 2), Task 3 (Step 4) |
| 5 | MCP & CLI parity (`McpAgentViews.INVENTORY_DEFAULT_LIMIT = 25`, `propertySuggestions` stripped on MCP) | Task 3 (Steps 2–3) |
| 6 | Ported BootUI 2.2.0 tests with `# ported: Class.method` citations | Task 1 (Step 1), Task 2 (Steps 1–2), Task 3 (Steps 1–2) |
| 7 | Defensive degradation & optional-dependency gate (`--resolution lowest-direct` & `no-sqlalchemy` logs) | Task 3 (Step 4) |
| 8 | Overhead budgets untouched and passing | Task 3 (Step 4) |
| 9 | Quality gates (`ruff check`, `ruff format --check`, `pyright`, full `pytest`, `test_code_shape.py`) | Task 3 (Step 4) |
| 10 | Live verification against mounted FastAPI app (`live-verify.log`) | Task 3 (Step 4) |

## Review Focus

1. **Global write policy on `/dismissed-findings` (`guard.py:47, 308-324`)**: `GET /dismissed-findings` must be allowed whenever sharpit is active (even if all advisor panels are disabled or `read_only=True`), whereas `POST` and `DELETE /dismissed-findings` must return `403 {"error": "Panel access denied", "panel": "dismissed-findings", "reason": "sharpit is in read-only mode (SHARPIT_READ_ONLY=true); write action on 'dismissed-findings' was blocked."}` when `settings.read_only=True`. Pinned by `test_mvc_global_read_only_blocks_the_mutations_but_not_the_list` in **Task 2**.
2. **Error body never echoes raw request payload or `note` on `/dismissed-findings`**: Malformed JSON, wrong field types, blank `ruleId`/`identity`, or array payloads on `POST`/`DELETE /dismissed-findings` must return the fixed message `"Request body must be a JSON object with string fields ruleId, identity and an optional note."` without quoting the body or note (which may hold sensitive user notes). Pinned by `test_mvc_refuses_bad_bodies_with_a_fixed_message_that_never_quotes_the_note` and `test_mvc_reads_the_body_as_bytes_so_the_framework_never_logs_the_note` in **Task 2**.
3. **YAML round-trip fidelity & Base64URL note encoding in `DismissalStore` (`dismissals.py`)**: Notes may contain newlines, colons, quotes, or Unicode; they serialize as `n=<base64url_no_pad>` after `<ruleId> <identity>`, preserve unrelated YAML sections (`dismissedRules:`, custom keys) and unparseable lines (`ignored` count), enforce `MAX_FINDINGS = 1000` (HTTP 409) and `MAX_NOTE_LENGTH = 200` (HTTP 400), and produce byte-identical rewrites. Pinned by `test_preserves_other_top_level_sections_across_writes`, `test_repeated_writes_are_byte_stable`, and `test_dismissed_findings_note_and_cap_validation` in **Task 1**.
4. **Duplicate security headers on streaming/multi-chunk or pre-header responses (`adapter.py:135-142`)**: `GuardMiddleware.send_with_headers` currently appends `security_headers(is_ui)` without checking existing response headers or repeated `http.response.start` events. Deduplicate case-insensitively by header name so each baseline header appears once. Pinned by `test_security_headers_are_not_duplicated_when_downstream_sets_them` in **Task 2**.
5. **Overview `run` identity stability vs restart ordinal (`context.py`, `overview.py`)**: `instanceId` (8-char lowercase hex) is fixed per Python process, while `runId` (8-char lowercase hex), `ordinal` (1-based `itertools.count(1)`), and `startedAt` (epoch ms) advance on each `SharpitContext` creation. Pinned by `test_overview_emits_run_metadata_and_scorecard_panel_title` in **Task 3**.

---

### Task 0: Safety Pre-Check (`/sharpit:predict` and `/sharpit:llm-council --tier high`)

Because D1 modifies `src/sharpit/engine/guard.py` (`_GLOBAL_WRITE_SUBJECTS` and `_panel_access`) and `GuardMiddleware` header injection, `AGENTS.md` (Safety model) requires running `/sharpit:predict` and `/sharpit:llm-council --tier high` before writing code.

**Files:**
- Create: `.superpowers/sdd/0.4.0/lanes/D1/predict-council.md`

- [ ] **Step 1: Run `/sharpit:predict` with the exact D1 safety brief**

Run workflow `skills/predict/SKILL.md` with this exact brief:
> **Proposal (Lane D1):** (1) Add `"/dismissed-findings": "dismissed-findings"` to `_GLOBAL_WRITE_SUBJECTS` in `src/sharpit/engine/guard.py:47` so `GET {api}/dismissed-findings` is allowed without a panel id and `POST`/`DELETE {api}/dismissed-findings` are gated by global `settings.read_only` (returning `403` with `read_only_reason("dismissed-findings", True)`) after the full guard chain (`security headers → trusted source → Host allow-list → cross-site → token`); (2) Read `POST`/`DELETE /dismissed-findings` bodies as raw capped bytes (`_read_capped`, 64 KiB max), require `Content-Type: application/json` (415 otherwise), never echo user input or `note` in 400 error responses, and persist `<ruleId> <identity> [n=<base64url_no_pad>]` under `dismissedFindings:` in `<state_dir>/sharpit.yml` with `MAX_FINDINGS=1000` (409) and `MAX_NOTE_LENGTH=200` (400); (3) Deduplicate security headers case-insensitively in `GuardMiddleware.send_with_headers` so downstream headers cannot cause duplicate `X-Content-Type-Options` or `Content-Security-Policy` headers while preserving sharpit's baseline security headers.

- [ ] **Step 2: Run `/sharpit:llm-council --tier high` with the exact D1 council brief**

Run workflow `skills/llm-council/SKILL.md` (`--tier high`) with the same brief plus `src/sharpit/engine/guard.py:39-106, 308-324` and `src/sharpit/engine/advisors/dismissals.py:1-143`. Record both verdicts in `.superpowers/sdd/0.4.0/lanes/D1/predict-council.md`. Stop if either verdict is NO-GO.

---

### Task 1: `DismissalStore` Support for `dismissedFindings` and Advisor Occurrence Matching

**Files:**
- Modify: `src/sharpit/engine/advisors/dismissals.py:1-143`
- Modify: `src/sharpit/engine/advisors/report.py:28-66`
- Modify: `src/sharpit/engine/collectors/restapi/service.py:81-95`
- Test: `tests/engine/test_dismissals.py`

**Interfaces:**
- Produces in `src/sharpit/engine/advisors/dismissals.py`:
  - `MAX_FINDINGS: Final[int] = 1000`
  - `MAX_NOTE_LENGTH: Final[int] = 200`
  - `@dataclass(frozen=True, slots=True) class DismissedFinding: rule_id: str; identity: str; note: str | None = None` with `def to_dto(self) -> dict[str, str | None]`
  - `@dataclass(frozen=True, slots=True) class Findings: dismissed: list[DismissedFinding]; ignored: int` with `def to_dto(self) -> dict[str, Any]`
  - `Snapshot`: adds `findings: list[DismissedFinding] = field(default_factory=list)` and `findings_ignored: int = 0`; `def is_finding_dismissed(self, rule_id: str, *identities: str | None) -> bool`
  - `DismissalStore`:
    - `def list_findings(self) -> Findings`
    - `def dismiss_finding(self, rule_id: str, identity: str, note: str | None = None) -> Findings`
    - `def restore_finding(self, rule_id: str, identity: str) -> Findings`

- [ ] **Step 1: Write failing unit tests in `tests/engine/test_dismissals.py`**

Add ported tests citing BootUI 2.2.0 `DismissedRulesStoreTests`:
- `# ported: DismissedRulesStoreTests.preservesOtherTopLevelSectionsAcrossWrites` (`test_preserves_other_top_level_sections_across_writes`: dismissing a rule and a finding preserves both `dismissedRules:` and `dismissedFindings:` plus unrelated top-level YAML sections).
- `# ported: DismissedRulesStoreTests.repeatedWritesAreByteStable` (`test_repeated_writes_are_byte_stable`: dismissing the same `(rule_id, identity, note)` twice produces byte-identical `sharpit.yml` and updates the note in place).
- `test_dismissed_findings_note_and_cap_validation`: verifies Base64URL no-pad round-trip for notes with spaces/newlines/Unicode, whitespace-only note normalizes to `None`, `len(note) > 200` raises `DismissalValidationError("Dismissed finding note must be at most 200 characters.")`, >1000 distinct findings raises `DismissalCapError("Too many dismissed findings: restore some before dismissing more.")`, and malformed lines under `dismissedFindings:` increment `ignored` and survive rewrites.
- `test_build_advisor_report_marks_dismissed_finding_by_identity_or_fingerprint`: verifies `build_advisor_report` and `RestApiCollector` treat an occurrence as dismissed when `Snapshot.is_finding_dismissed(rule.id, occ.id, occ.fingerprint)` matches.

- [ ] **Step 2: Run `uv run pytest -q tests/engine/test_dismissals.py` and verify RED**

Expected failure: `ImportError: cannot import name 'DismissedFinding' from 'sharpit.engine.advisors.dismissals'` (or `AttributeError: 'DismissalStore' object has no attribute 'list_findings'`).

- [ ] **Step 3: Implement `DismissedFinding`, `Findings`, YAML `dismissedFindings:` parser/serializer, and advisor matching**

In `src/sharpit/engine/advisors/dismissals.py`:
- Validate `rule_id` (`_RULE_ID_RE`, max 64 chars, no whitespace), `identity` (trimmed non-empty, max 512 chars, no whitespace/control chars), and `note` (trimmed; empty becomes `None`; `len(note) <= 200`, no `\x00`).
- Encode note as `n=` + `base64.urlsafe_b64encode(note.encode("utf-8")).decode("ascii").rstrip("=")` on `  - <ruleId> <identity>[ n=<b64>]` lines under `dismissedFindings:`.
- Update `build_advisor_report` (`src/sharpit/engine/advisors/report.py:28-66`) and `RestApiCollector` (`src/sharpit/engine/collectors/restapi/service.py:83-87`) to accept `dismissed_findings: set[tuple[str, str]] | None = None` (or `Snapshot`) so findings matching `(rule_id, occ.id)` or `(rule_id, occ.fingerprint)` are counted in `dismissedTotal` / filtered when `include_dismissed=False`.

- [ ] **Step 4: Run `uv run pytest -q tests/engine/test_dismissals.py` and commit**

Expected: PASS. Commit: `feat(advisors): add dismissedFindings YAML store and occurrence matching`.

---

### Task 2: Guard Policy, `/dismissed-findings` HTTP Routes, Security Header Deduplication, and `"Scorecard"` Title

**Files:**
- Modify: `src/sharpit/engine/guard.py:47, 308-324`
- Modify: `src/sharpit/engine/headers.py:1-32`
- Modify: `src/sharpit/engine/panels.py:21`
- Modify: `src/sharpit/fastapi/adapter.py:135-142, 434-466` (or F's split route module)
- Test: `tests/engine/test_guard.py`, `tests/fastapi/test_dismissed_findings_api.py`, `tests/fastapi/test_security_headers.py`

**Interfaces:**
- Consumes: `DismissalStore.list_findings`, `dismiss_finding`, `restore_finding`, `DismissalValidationError`, `DismissalCapError`, `DismissalStorageError` from Task 1.
- Produces:
  - `_GLOBAL_WRITE_SUBJECTS = {"/dismissed-rules": "dismissed-rules", "/dismissed-findings": "dismissed-findings"}` in `src/sharpit/engine/guard.py:47`.
  - Routes `GET {api}/dismissed-findings`, `POST {api}/dismissed-findings`, `DELETE {api}/dismissed-findings`.
  - `merge_security_headers(existing: Sequence[tuple[bytes, bytes]], *, is_ui: bool) -> list[tuple[bytes, bytes]]` in `src/sharpit/engine/headers.py`.
  - `Panel("overview", "Scorecard", None, None)` in `src/sharpit/engine/panels.py:21`.

- [ ] **Step 1: Write failing guard, route, and header tests**

In `tests/engine/test_guard.py` and `tests/fastapi/test_dismissed_findings_api.py`, add:
- `# ported: DismissedFindingsControllerTests.mvcDismissesListsAndRestoresAFindingWithItsNote`
- `# ported: DismissedFindingsControllerTests.mvcRefusesBadBodiesWithAFixedMessageThatNeverQuotesTheNote`
- `# ported: DismissedFindingsControllerTests.mvcGlobalReadOnlyBlocksTheMutationsButNotTheList`
- `# ported: DismissedFindingsControllerTests.mvcReadsTheBodyAsBytesSoTheFrameworkNeverLogsTheNote`
- `test_dismissed_findings_requires_json_content_type_and_enforces_409_503` (415 on missing `application/json`, 409 on cap > 1000, 503 when `state_dir=None`, `no_side_effects` fixture on `GET /sharpit/api/dismissed-findings`).
- In `tests/fastapi/test_security_headers.py`: `test_security_headers_are_not_duplicated_when_downstream_sets_them` and `test_overview_panel_title_is_scorecard`.

- [ ] **Step 2: Run `uv run pytest -q tests/engine/test_guard.py tests/fastapi/test_dismissed_findings_api.py tests/fastapi/test_security_headers.py` and verify RED**

Expected failure: 404 on `/sharpit/api/dismissed-findings` and assertion failure `'Overview' == 'Scorecard'`.

- [ ] **Step 3: Implement guard subject, routes, header deduplication, and `"Scorecard"` panel title**

- In `src/sharpit/engine/guard.py:47`, add `"/dismissed-findings": "dismissed-findings"` to `_GLOBAL_WRITE_SUBJECTS`.
- In `src/sharpit/engine/panels.py:21`, change `Panel("overview", "Overview", None, None)` to `Panel("overview", "Scorecard", None, None)`.
- In `src/sharpit/engine/headers.py`, implement `merge_security_headers` replacing any existing case-insensitive match with sharpit's baseline security header so each header is emitted exactly once; call it from `GuardMiddleware.send_with_headers` (`src/sharpit/fastapi/adapter.py:135-142`).
- In `src/sharpit/fastapi/adapter.py` (around lines 434–466), register `GET`, `POST`, and `DELETE` on `f"{api}/dismissed-findings"`. Read the body via `await _read_capped(request)`, require `application/json` (415 `{"error": "Unsupported Media Type"}`), parse JSON dict with string `ruleId` and `identity` plus optional string/null `note`, and return `400 {"error": "Request body must be a JSON object with string fields ruleId, identity and an optional note."}` on any shape/type error without echoing the payload.

- [ ] **Step 4: Run tests and commit**

Run `uv run pytest -q tests/engine/test_guard.py tests/fastapi/test_dismissed_findings_api.py tests/fastapi/test_security_headers.py`. Commit: `feat(api): add /dismissed-findings routes, header dedup, and Scorecard title`.

---

### Task 3: Overview `run` DTO, MCP Default Limits (`config`/`beans`), and Golden Conformance

**Files:**
- Modify: `src/sharpit/engine/context.py:1-62`
- Modify: `src/sharpit/engine/collectors/overview.py:19-40`
- Modify: `src/sharpit/engine/tools.py:160-175, 425-445` (or F's split MCP module)
- Test: `tests/engine/test_overview.py`, `tests/engine/test_tools.py`, `tests/test_conformance.py`

**Interfaces:**
- Produces:
  - `SharpitContext.instance_id: str`, `run_id: str`, `run_ordinal: int`, `started_at_ms: int` in `src/sharpit/engine/context.py`.
  - `overview_dto` key `"run": {"instanceId": str, "runId": str, "ordinal": int, "startedAt": int}` in `src/sharpit/engine/collectors/overview.py`.
  - `INVENTORY_DEFAULT_LIMIT: Final[int] = 25` applied in `get_config` and `get_beans` when `limit` is omitted on MCP, and `propertySuggestions` omitted from `get_config` MCP projection (`docs/reference/BOOTUI-CONTRACT-0.4-DRIFT.md` §§3, 6).

- [ ] **Step 1: Write failing tests in `tests/engine/test_overview.py` and `tests/engine/test_tools.py`**

- `test_overview_emits_run_metadata_and_scorecard_panel_title`: asserts `overview["run"]` contains `instanceId` (8 hex chars, constant across contexts in-process), `runId` (8 hex chars, distinct per context), `ordinal` (increments by 1), and `startedAt` (epoch ms int).
- `# ported: McpAgentViewsTests.configDefaultLimitAndStripsPropertySuggestions` and `# ported: McpAgentViewsTests.beansDefaultLimit`: asserts MCP `get_config({})` and `get_beans({})` cap rows to `25` (`INVENTORY_DEFAULT_LIMIT`) when `limit` is omitted and `get_config` MCP output does not contain `propertySuggestions`, while HTTP `GET /sharpit/api/config` still emits `"propertySuggestions": []`.

- [ ] **Step 2: Run `uv run pytest -q tests/engine/test_overview.py tests/engine/test_tools.py` and verify RED**

Expected failure: `KeyError: 'run'` in `test_overview.py` and `AssertionError: 'propertySuggestions' in result` in `test_tools.py`.

- [ ] **Step 3: Implement `SharpitContext` run stamp, `overview_dto["run"]`, and MCP `get_config`/`get_beans` projection**

- In `src/sharpit/engine/context.py`, define module-level `_INSTANCE_ID: Final[str] = secrets.token_hex(4)` and `_RUN_ORDINAL = itertools.count(1)`. Populate `instance_id`, `run_id = secrets.token_hex(4)`, `run_ordinal = next(_RUN_ORDINAL)`, and `started_at_ms = int(time.time() * 1000)` on `SharpitContext`.
- In `src/sharpit/engine/collectors/overview.py:26-39`, add `"run": {"instanceId": ctx.instance_id, "runId": ctx.run_id, "ordinal": ctx.run_ordinal, "startedAt": ctx.started_at_ms}` (with fallback defaults when `ctx` is `None`).
- In `src/sharpit/engine/tools.py`, apply `INVENTORY_DEFAULT_LIMIT = 25` when `limit` is `None` for MCP calls to `get_config` and `get_beans`, and strip `propertySuggestions` in the MCP `get_config` projection while keeping CLI/HTTP full reports intact.

- [ ] **Step 4: Run full verification gates, update lane evidence, and commit**

Run detached with timeout and log files:
1. `uv run ruff check && uv run ruff format --check && uv run pyright`
2. `uv run pytest -q tests/engine/test_overview.py tests/engine/test_tools.py tests/engine/test_dismissals.py tests/engine/test_guard.py tests/fastapi/test_dismissed_findings_api.py tests/fastapi/test_security_headers.py tests/test_conformance.py tests/test_code_shape.py`
3. Record `--resolution lowest-direct` pytest run in `.superpowers/sdd/0.4.0/lanes/D1/lowest-direct.log` and `--ignore` SQLAlchemy run in `.superpowers/sdd/0.4.0/lanes/D1/no-sqlalchemy.log` (each naming `HEAD` SHA).
4. Run `skills/live-verify/SKILL.md` against `/sharpit/api/overview`, `/sharpit/api/panels`, `/sharpit/api/dismissed-findings`, `/sharpit/api/config`, `/sharpit/api/mappings`, `/sharpit/api/loggers`, `/sharpit/api/beans`, `/sharpit/api/cli` and save `.superpowers/sdd/0.4.0/lanes/D1/live-verify.log`.
5. Commit: `feat(overview,mcp): add 2.2.0 run metadata and MCP inventory default limits`.

---

## Lane Evidence Checklist (`lane_gate.py` — Spec §10.3)

Before requesting merge, `.superpowers/sdd/0.4.0/lanes/D1/` MUST contain:
- [ ] `predict-council.md` — GO verdict from `/sharpit:predict` and `/sharpit:llm-council --tier high` (Task 0).
- [ ] `field-map.md` — Every BootUI 2.2.0 key for `dismissed-findings`, `overview`, `config`, `mappings`, `loggers`, `beans`, `cli` mapped to its Python source or `nullable.json` entry.
- [ ] `findings.md` — `finding → test → red` table; every row `fixed` (with red-test name) or `parked` (with reason).
- [ ] `checklist.md` — All 10 items of spec §6.1 checked with evidence file paths (`lowest-direct.log`, `no-sqlalchemy.log`, `live-verify.log`, each naming the head commit SHA).
- [ ] `handoff.md` — Current state: last green command, next step (`ready-to-merge`), open findings (`none`).
- [ ] `review.md` — Fresh reviewer subagent (`reviewer_id != implementer_id`) + `/code-review high` + `ponytail-review` (required because D1 touches `guard.py`), naming the head commit SHA, ending with `VERDICT: APPROVE`.
