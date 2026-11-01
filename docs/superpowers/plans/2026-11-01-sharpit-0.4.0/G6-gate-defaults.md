# G6 — Gate Defaults Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development or
> superpowers:executing-plans. One task/commit at a time; run `/sharpit:check` before each commit.

**Goal:** Make a clean `pytest --sharpit` run usable without `--sharpit-app` and keep
non-failing advisor notes out of the default terminal output.

**Architecture:** Extend the plugin's app-selection and terminal-summary responsibilities after
F splits `pytest_plugin/__init__.py`. App autodetection reads already-loaded module globals
only. Missing or ambiguous apps skip only `rest-api`; SQL capture blindness remains unknown.
Reports retain all advisor findings regardless of terminal verbosity.

**Tech Stack:** Python >=3.12, pytest/pytester, FastAPI/Starlette as optional test dependencies.

**Spec:** `docs/superpowers/specs/2026-11-01-sharpit-0.4.0-design.md` §§2, 5.5 (F3/F4), 11,
10.2–10.3.

## Header and ownership

- **Lane:** G6 (committed; F3 + F4).
- **Worker profile:** M, judgement-heavy (pytest lifecycle, safe introspection, fail-closed
  status).
- **Dependencies:** F only. G6 runs beside D1 and owns no-app behavior and `SKIPPED`.
- **May touch:** F table modules `src/sharpit/pytest_plugin/options.py`, `apps.py`, `session.py` (xdist workeroutput key), `terminal.py`; `src/sharpit/engine/advisors/findings.py` (`AdvisorRun.status` adds `SKIPPED`); `src/sharpit/engine/testsession/outcome.py` (`_advisor_summary`, `_worst`, `_unknown_reasons`); both `report.schema.json` copies; `tests/pytest_plugin/`; lane evidence folder.
- **Must not touch:** `src/sharpit/pytest_plugin/__init__.py` compatibility facade or G1G2-owned
  gate/baseline modules; `engine/guard.py`, capture/SQL sources, other lanes' modules, panel
  registries/routes/UI; `scripts/dev/lane_gate.py`, import-boundary rules, overhead constants,
  complexity/sonar baselines, dependency lists, `uv.lock`.

## Global constraints

- Python `>=3.12`; runtime deps exactly `starlette` and `packaging`; pytest and FastAPI stay
  optional.
- No import or invocation of an application module while autodetecting; inspect only
  `sys.modules` globals.
- No-app behavior does not suppress SQL capture blindness or any other unknown reason.
- Keep `sharpit-report/1` and JSON/JUnit content unchanged for F4; terminal output alone is
  quieted.
- Tests reproduce spike cases in fixture apps and show the named defect on 0.3.0 (§5.5).

## Review Focus

1. **No app / exactly one app / multiple candidates:** `test_autodetect_single_prints_choice`, `test_autodetect_ambiguous_uses_none`, and `test_autodetect_never_imports` in Task 1; spike case `test_spike_f3_clean_suite_reaches_green`.
2. **App class and global-value lookalikes:**
`test_autodetect_accepts_fastapi_and_starlette_only` in Task 1; attributes of other types must
not count.
3. **Require-app restores old fail-closed behavior:** `test_require_app_no_app_is_unknown` and
`test_require_app_ini_true_is_unknown` in Task 2.
4. **Quiet output must not hide failures or report data:** `test_verbose_keeps_advisor_notes`,
`test_default_terminal_counts_notes_but_reports_keep_findings`, and
`test_gate_failure_still_printed` in Task 3.

---

### Task 1: Reproduce F3 and autodetect a unique loaded app

**Files:** Modify post-F `src/sharpit/pytest_plugin/apps.py` (created by F; current code is
`_load_app` at `__init__.py:511`, app assessment at `:525–545`, `pytest_sessionfinish` at
`:646`); tests `tests/pytest_plugin/test_plugin_apps.py` and `test_plugin_gate_defaults.py`.

**Interfaces:** Use one name everywhere: `autodetect_apps() -> tuple[tuple[str, object], ...]`. `select_app(explicit: str | None, candidates: Sequence[tuple[str, object]]) -> tuple[str, object] | None` selects only an explicit app or one unique candidate. Consume `PluginOptions.app` and F's session/terminal modules. Iterate `vars(mod).values()` only when `type(mod) is ModuleType`; never call `getattr` or PEP 562 `__getattr__`. Match by exact type and MRO against framework classes already in `sys.modules`; dedupe by `id()`, drop mounted inner apps and sharpit's own sub-app. Each xdist worker ships candidate `module:attr` names in `workeroutput`; the controller decides uniqueness over the union and drops `rest-api` runs if multiple distinct apps appear. `test_autodetect_ambiguous_across_workers_uses_none` uses two workers and two apps.

- [ ] **Step 1: Write failing pytester cases.** `test_spike_f3_clean_suite_reaches_green` creates
  the clean spike shape: one passing test, no sharpit install and no `--sharpit-app`; assert 0
  exit, `rest-api` is `SKIPPED`, reason names `--sharpit-app module:attr`, and SQL capture
  status remains independently evaluated. On 0.3.0 expect exit 1 from the no-app unknown. Add `test_autodetect_single_prints_choice`, `test_autodetect_ambiguous_uses_none`, and `test_autodetect_never_imports`.
- [ ] **Step 2: Run only these tests on 0.3.0.** Expected: no-app assertion fails specifically
  on current unknown/exit 1; fixture setup and collection succeed.
- [ ] **Step 3: Implement `autodetect_apps()`.** Scan a snapshot of `sys.modules` and module
  globals; accept FastAPI/Starlette instances, use only one candidate, and return none with
  candidate descriptions for zero or multiple candidates. Do not import modules or call app
  code. Explicit `--sharpit-app` retains precedence.
- [ ] **Step 4: Verify targeted tests.** Unique app prints exactly `sharpit: using app <module>:<attr> (pass --sharpit-app to choose)`; multiple candidates print `sharpit: several apps found (<m:a>, <m:a>); pass --sharpit-app module:attr`; no app prints `sharpit: no application found; rest-api skipped (pass --sharpit-app module:attr)`. Assert each line in terminal output; no-app and ambiguity skip only `rest-api` and do not make status unknown.
- [ ] **Step 5: Commit** `feat: autodetect pytest app for sharpit advisor`.

### Task 2: Add explicit require-app compatibility option

**Files:** Modify `src/sharpit/pytest_plugin/options.py`; post-F option registration module
(created by F); tests `tests/pytest_plugin/test_plugin_options.py` and
`test_plugin_gate_defaults.py`.

**Interfaces:** Extend `PluginOptions` with `require_app: bool`; expose `--sharpit-require-app` and ini `sharpit_require_app`, default false. App selector from Task 1 consumes it at session finish. Add `SKIPPED` to `AdvisorRun.status`; `_advisor_summary`, `_worst`, and `_unknown_reasons` treat no-app rest-api as skipped without an unknown reason by default, and as unknown when require-app is true. Add `SKIPPED` to both report schema copies and record the additive enum in spec §11.

- [ ] **Step 1: Add failing cases** `test_require_app_no_app_is_unknown`,
  `test_require_app_cli_and_ini`, and `test_explicit_app_ignores_autodetect_candidates`;
  expected on 0.3.0: option is unknown and old no-app run remains unknown without an explicit
  app.
- [ ] **Step 2: Run cases on 0.3.0;** expected named option/status assertions fail, not plugin
  collection.
- [ ] **Step 3: Implement the option and precedence.** When true, no detected app keeps the
  0.3.0 unknown reason; when false, skip the advisor. Log the compatibility change in the lane
  report/spec §11 as specified by §5.5.
- [ ] **Step 4: Verify** CLI and ini defaults, explicit option precedence, and unknown exit
  behavior.
- [ ] **Step 5: Commit** `feat: add sharpit require-app compatibility option`.

### Task 3: Quiet non-failing advisor notes by default

**Files:** Modify `src/sharpit/pytest_plugin/options.py`, post-F
`src/sharpit/pytest_plugin/terminal.py` (created by F; current `pytest_terminal_summary` is
`__init__.py:698–729`); tests `tests/pytest_plugin/test_plugin_terminal.py` and
`test_plugin_reports.py`.

**Interfaces:** Add `verbose: bool` resolved from `--sharpit-verbose` or pytest verbosity >=2 (`-vv`). Terminal formatter consumes merged findings/status/report path and omits non-failing advisor findings from `gate counts:` unless verbose. Summary adds exactly `sharpit: <N> advisor notes in <report path>`.

- [ ] **Step 1: Add failing pytester tests** named in Review Focus; assert default output has
  gate failures, status and exactly one `sharpit: <N> advisor notes in <report path>` count line;
  assert JSON and JUnit still include the same findings and verbose mode prints notes.
- [ ] **Step 2: Run on 0.3.0;** expected default terminal assertions fail because notes print
  individually and the count line is absent.
- [ ] **Step 3: Implement summary behavior** in `terminal.py`; preserve `-vv` behavior and do
  not change the report/JUnit render path.
- [ ] **Step 4: Verify** quiet, `--sharpit-verbose`, `-vv`, gate failure output, and the four gates; update the current lane handoff. Coordinator stores gate logs in integration evidence.
- [ ] **Step 5: Commit** `feat: quiet non-failing sharpit advisor output`.

## Lane evidence checklist

`.superpowers/sdd/0.4.0/lanes/G6/` contains implementer-owned `handoff.md`, `findings.md`, `field-map.md` (`N/A — not a panel lane`), and `checklist.md`. Checklist follows spec §6.1 items 1–10 in order, mapped to owning tasks with evidence paths or `N/A` plus reason. Coordinator/reviewer alone creates `review.md`, `gate/<name>.log` for ruff-check, ruff-format, pyright, pytest, lowest-direct and no-sqlalchemy, and `live-verify.md` in integration; lane diff cannot touch those paths.

## Definition of done

- [ ] Task 1 satisfies §5.5 F3 autodetect, skip-with-warning, ambiguity and no-import behavior.
- [ ] Task 2 satisfies §5.5 `--sharpit-require-app` / ini compatibility and records the §11
  deviation.
- [ ] Task 3 satisfies §5.5 F4 quiet default, count line, verbose opt-in, and unchanged
  JSON/JUnit.
- [ ] Spike F3 is reproduced red on 0.3.0 for the no-app unknown/exit-1 reason; all Review Focus
  tests are green in the lane.

## Canonical lane conventions (C1–C8)

- Lane id is exactly `G6`; evidence folder is `.superpowers/sdd/0.4.0/lanes/G6/`.
- All lanes consume module names and signatures in F's consumer interface table.
- Golden fixture paths and `tests/golden.py::assert_parity(sharpit_id: str, name: str, payload: Mapping[str, Any]) -> None` follow C3, with no flat panel files.
- A red is a defect-naming assertion, not import/collection failure. Spike tests assert desired behavior and are red on 0.3.0.
- Do not edit shared safety/masking matrices; use `tests/safety/test_g6_safety.py` and `tests/masking/test_g6_masking.py` if needed.
- PLAN.md Review Focus names are canonical: `test_autodetect_single_prints_choice`, `test_autodetect_ambiguous_uses_none`, and `test_autodetect_never_imports`.
- Dependencies are exactly `F`; G6 runs beside D1.
- Checklist follows spec §6.1 items 1–10 in order, mapped to owning tasks; non-panel items are `N/A` with reason.

| Spec §6.1 item | G6 task / evidence owner |
|---|---|
| 1 Golden parity | N/A — gate-defaults lane, not a panel lane. |
| 2 Ported behavior tests | N/A — no BootUI panel behavior is ported. |
| 3 Safety and masking | N/A — no panel source or new secret source. |
| 4 Gatekeeper | N/A — no new library import. |
| 5 Hot-path overhead | N/A — no hot-path code change. |
| 6 MCP read-only surface | N/A — no MCP surface change. |
| 7 Svelte view | N/A — no panel view. |
| 8 Four gates | Task 3: final targeted verification; coordinator owns gate logs. |
| 9 Live check | N/A — no panel implementation; integration reviewer owns live verification. |
| 10 Handoff | Task 3: update current handoff with output and next step. |
