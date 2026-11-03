# Lane F5: foundation for 0.5.0 (behaviour-neutral)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development (or executing-plans), one task
> at a time, `/sharpit:check` before every commit. Steps use `- [ ]` checkboxes.

| | |
|---|---|
| **Lane id** | `F5` (worktree `C:\development\github\sharpit-wt\0.5.0-F5`, branch `lane/0.5.0-F5`) |
| **Goal** | Shared pieces the 0.5.0 lanes need, so no two lanes edit the same file: `engine/sqla/` package, `engine/appsource.py`, `engine/advisors/scan.py`, the 0.5.0 settings rows, the 0.5.0 surface test and the lane-gate council check. No user-visible change. |
| **Spec** | §4 (4.1–4.4), §9 |
| **Worker** | codex gpt-6-luna, high |
| **Council** | required for Task 1 only (architecture rule 4 changes): `council.md` before Task 1 code |
| **Depends on** | T-unbounded-read merged to `main` (or F5 rebases onto it before Task 1) |
| **May touch** | `src/sharpit/engine/sqla.py` → `src/sharpit/engine/sqla/{__init__,listeners,readonly,events,orm,inspect}.py` (move only), `tests/engine/test_import_boundary.py` (rule 4 text + planted violation), `AGENTS.md` (rule 4 line, Layout line), `src/sharpit/engine/appsource.py` (new), `src/sharpit/engine/advisors/scan.py` (new), `src/sharpit/engine/advisors/__init__.py` (export), `src/sharpit/engine/advisors/registry.py` (the four new `AdvisorSpec` rows: `security` `SEC-*`, `architecture` `ARCH-*`, `fastapi` `FASTAPI-*` + kept `SPRING-*`, `database-advisor` `DB-*`; so no advisor lane edits the registry), `src/sharpit/settings.py` (new fields + env rows only), `scripts/dev/lane_gate.py` (council check, release parameter), `tests/scripts/test_lane_gate.py`, `tests/engine/test_appsource.py`, `tests/engine/advisors/test_scan.py`, `tests/test_surface_05.py`, `tests/test_settings_05.py`, the implementer files in `.superpowers/sdd/0.5.0/lanes/F5/` |
| **Must NOT touch** | any collector, route, tool, panel flag or UI file; existing budget constants; `tests/complexity_baseline.json` (except lowering); `review.md`/`gate/` paths |

**Architecture:** Task 1 is a pure move with re-exports: every `from sharpit.engine.sqla import X` keeps working,
proven by the unchanged suite. Tasks 2–3 add new modules no production path calls yet (their callers are the advisor
lanes). Task 4 adds dataclass fields with defaults equal to "off".

## Review Focus

1. The split changes behaviour: the full suite, the SQL Trace and N+1 budget tests pass unchanged (budgets untouched).
2. `appsource` imports or executes application code, or follows a symlink out of the root.
3. Rule 4 still bites: a planted `import sqlalchemy` in `engine/collectors/` fails `test_import_boundary`.

## Tasks

### Task 0: council

- [ ] **Step 1:** `/sharpit:llm-council --tier high` on spec §4.1 (package vs single file; the owner's O6 answer is
  an input). Write `council.md` (verdicts, the ruling). If the ruling is "single file", skip Task 1 and note it in
  `handoff.md`; PLAN.md's `engine/sqla/` chain then reads `engine/sqla.py`.

### Task 1: `engine/sqla/` package

**Files:** the move listed in May-touch; `tests/engine/test_import_boundary.py`; `AGENTS.md`.

- [ ] **Step 1:** Red commit `test: sqlalchemy gatekeeper is the sqla package`:
  - `test_sqla_package_is_the_only_sqlalchemy_importer` — walks `src/sharpit`, asserts every module importing
    `sqlalchemy` is under `engine/sqla/` (red: today the rule names one file and the package does not exist, so the
    assertion lists `engine/sqla/__init__.py` as missing).
  - `test_planted_sqlalchemy_import_outside_package_fails` — the existing planted-violation pattern, pointed at
    `engine/collectors/`.
- [ ] **Step 2:** Move code by concern; `__init__.py` re-exports the public names (`__all__` unchanged). No line of
  logic edited. Each new module < 400 lines.
- [ ] **Step 3:** Full suite (background) green; the overhead budget tests green with their constants unchanged.
  Commit `refactor: sqlalchemy gatekeeper becomes the engine/sqla package`.

### Task 2: `engine/appsource.py`

**Interfaces:** Produces `build_index(root: Path, *, max_files: int = 2000, max_file_bytes: int = 524288) ->
SourceIndex`; `SourceIndex(modules: Mapping[str, ModuleInfo], limitations: tuple[str, ...], truncated: bool)`;
`ModuleInfo(name, path, tree: ast.Module, imports: tuple[ImportRef, ...], functions: tuple[FunctionRef, ...])`;
`resolve_package_root(app: object, modules: Mapping[str, ModuleType]) -> Path | None` (reads module globals only).

- [ ] **Step 1:** Red commit with tests in `tests/engine/test_appsource.py`:
  - `test_appsource_never_imports_or_follows_symlinks` — a package whose `__init__.py` raises on import and a
    symlink to a directory outside the root: index built, the import never ran (sentinel file absent), symlinked
    modules absent, a limitation names the skip.
  - `test_bounded_files_and_size` — 5 files with `max_files=3` → 3 modules, `truncated is True`; a file over
    `max_file_bytes` skipped with a limitation.
  - `test_resolve_package_root_from_factory_app` — app created in `create_app()` inside `src/pkg/app.py`, held by
    `pkg.main.app` → root `src/pkg`.
  - `test_syntax_error_file_is_a_limitation` — not a crash.
- [ ] **Step 2:** Implement with `ast.parse`, `tokenize.open` (encoding), `os.scandir(follow_symlinks=False)`.
- [ ] **Step 3:** Green. Commit `feat: bounded app-source AST index for advisors`.

### Task 3: `engine/advisors/scan.py`

**Interfaces:** `AdvisorScan(spec: AdvisorSpec, rules: Sequence[Rule], run: Callable[[ScanInput], ScanResult])` with
`report() -> dict`, `scan(input) -> dict` (single-flight; a second call while running → 409
`"sharpit action already in progress"`), `violations(rule_id, scan_id, offset, limit) -> dict` (paged, `limit`
clamped to 1000, unknown rule → 404 verbatim from WAVE-B §1). Report keys per WAVE-B §1 (`localOnly`, `disclaimer`,
`scan`, `severityCounts` with every severity, `rules`, ...).

- [ ] **Step 1:** Red commit, `tests/engine/advisors/test_scan.py` with a two-rule fake advisor:
  `test_advisor_scan_core_not_scanned_shape` (matches the `architecture` golden's pre-scan keys via
  `assert_parity("architecture", "captured", ...)` with the fake's disclaimer), `test_advisor_scan_core_single_flight`,
  `test_advisor_scan_core_violations_paged`, `test_advisor_scan_core_unknown_rule_404`,
  `test_advisor_scan_core_severity_counts_list_every_severity`, `test_advisor_scan_core_dismissal_applies`.
- [ ] **Step 2:** Implement on `engine/singleflight.py`, `engine/paging.py`, `advisors/dismissals.py`.
- [ ] **Step 3:** Green. Commit `feat: shared rule-advisor scan core`.

### Task 4: settings, surface, gate

- [ ] **Step 1:** Red commit:
  - `tests/test_settings_05.py::test_05_settings_defaults_and_env` — each new field (spec §4.4 list, plus
    `app_package: str | None = None`) has its default and its `SHARPIT_*` env override; invalid → fail-safe +
    warning.
  - `tests/test_surface_05.py::test_unimplemented_panel_has_no_surface_05` — parametrised over the eight ids
    (`transactions`, `mysql`, `security`, `security-logs`, `database-advisor`, `architecture`, `fastapi-security`,
    `fastapi`): with the flag `False`, absent from `/panels`, MCP `tools/list`, the CLI and the nav; its path 404s.
    (Red only for the settings test; the surface test is a pin, mutation-proven by flipping one flag in a scratch
    tree, recorded in `findings.md`.)
  - `tests/engine/advisors/test_scan.py::test_05_advisor_specs_registered` — the four `AdvisorSpec` rows exist with
    their id prefixes, and dismissals for an unknown prefix are still rejected.
  - `tests/scripts/test_lane_gate.py::test_lane_gate_refuses_missing_council_verdict` — a lane plan whose header row
    `| **Council** |` value starts with `required` or `**required**`, and no `council.md` in the lane folder → refused
    with a message naming the file.
  - `tests/scripts/test_lane_gate.py::test_lane_gate_release_is_a_parameter` — `lane_gate.py` hardcodes `0.4.0`
    (`LANES` at `:41`, the worktree default at `:798`); `--release 0.5.0` (default read from the integration branch
    name `release/<x>`) selects `.superpowers/sdd/0.5.0/lanes` and `0.5.0-<lane>`. Expected failure: unknown option.
- [ ] **Step 2:** Implement. **Step 3:** Green + full gate (background). Commit
  `feat: 0.5.0 settings, surface pin and council check in the lane gate`.

## Evidence (`.superpowers/sdd/0.5.0/lanes/F5/`)

`handoff.md` (consumer interface table: every new name, module and signature the lanes consume), `findings.md`,
`field-map.md` (`N/A — not a panel lane`), `checklist.md`, `council.md`.
