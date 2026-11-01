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
- **Dependencies:** F and G1G2 merged; starts only after G1G2. Per §2 it is committed after
  G1G2.
- **May touch:** `src/sharpit/pytest_plugin/options.py` (`PluginOptions`, `resolve`, lines
  13–55); `src/sharpit/pytest_plugin/apps.py` and `terminal.py` (created by F's responsibility
  split; if F names differ, F must map those responsibilities before G6 starts); corresponding
  post-F hook modules; `src/sharpit/engine/testsession/finish.py` only for advisor status input;
  `tests/pytest_plugin/test_plugin_apps.py`, new `test_plugin_gate_defaults.py`,
  `test_plugin_terminal.py`; lane evidence folder.
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

1. **No app / exactly one app / multiple candidates:** `test_spike_f3_no_app_is_not_unknown`,
`test_autodetect_single_app_reports_module_attribute`, `test_autodetect_ambiguous_uses_none`,
`test_autodetect_never_imports` in Task 1.
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

**Interfaces:** Consumes `PluginOptions.app` and G1G2 report/status behavior. Produces
`autodetect_app() -> tuple[str, object] | None` and `select_app(explicit: str | None) ->
tuple[str, object] | None`; candidate diagnostics are returned as strings, not printed by engine
code.

- [ ] **Step 1: Write failing pytester cases.** `test_spike_f3_no_app_is_not_unknown` creates
  the clean spike shape: one passing test, no sharpit install and no `--sharpit-app`; assert 0
  exit, `rest-api` is `SKIPPED`, reason names `--sharpit-app module:attr`, and SQL capture
  status remains independently evaluated. On 0.3.0 expect exit 1 with `advisor 'rest-api' could
  not assess: no application`. Add single-app, ambiguous-app and no-import cases from Review
  Focus.
- [ ] **Step 2: Run only these tests on 0.3.0.** Expected: no-app assertion fails specifically
  on current unknown/exit 1; fixture setup and collection succeed.
- [ ] **Step 3: Implement `autodetect_app()`.** Scan a snapshot of `sys.modules` and module
  globals; accept FastAPI/Starlette instances, use only one candidate, and return none with
  candidate descriptions for zero or multiple candidates. Do not import modules or call app
  code. Explicit `--sharpit-app` retains precedence.
- [ ] **Step 4: Verify targeted tests.** Expected: unique app is used and prints `sharpit: using
  app <module>:<attr> (pass --sharpit-app to choose)`; zero/multiple apps skip only `rest-api`
  and do not make status unknown.
- [ ] **Step 5: Commit** `feat: autodetect pytest app for sharpit advisor`.

### Task 2: Add explicit require-app compatibility option

**Files:** Modify `src/sharpit/pytest_plugin/options.py`; post-F option registration module
(created by F); tests `tests/pytest_plugin/test_plugin_options.py` and
`test_plugin_gate_defaults.py`.

**Interfaces:** Extend `PluginOptions` with `require_app: bool`; expose `--sharpit-require-app`
and ini `sharpit_require_app`, default false. App selector from Task 1 consumes it at session
finish.

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

**Interfaces:** Add `verbose: bool` resolved from `--sharpit-verbose` or pytest verbosity >=2
(`-vv`). Terminal formatter consumes merged findings/status/report path and writes no individual
non-failing advisor notes unless verbose.

- [ ] **Step 1: Add failing pytester tests** named in Review Focus; assert default output has
  gate failures, status and exactly one `sharpit: N advisor notes in <report path>` count line;
  assert JSON and JUnit still include the same findings and verbose mode prints notes.
- [ ] **Step 2: Run on 0.3.0;** expected default terminal assertions fail because notes print
  individually and the count line is absent.
- [ ] **Step 3: Implement summary behavior** in `terminal.py`; preserve `-vv` behavior and do
  not change the report/JUnit render path.
- [ ] **Step 4: Verify** quiet, `--sharpit-verbose`, `-vv`, and gate failure output.
- [ ] **Step 5: Commit** `feat: quiet non-failing sharpit advisor output`.

## Lane evidence checklist

`.superpowers/sdd/0.4.0/lanes/G6/` must contain `handoff.md`, `review.md` (fresh reviewer,
different id, head SHA, final line `VERDICT: APPROVE`), `findings.md` (every finding fixed with
red-test name or parked with reason), `field-map.md` (`N/A — no DTO keys changed`),
`checklist.md` mapping applicable §6.1 items to test/report evidence and marking panel-only
items not applicable, and `gate/` logs for four gates plus lowest-direct and no-SQLAlchemy
pinned to the head SHA.

## Definition of done

- [ ] Task 1 satisfies §5.5 F3 autodetect, skip-with-warning, ambiguity and no-import behavior.
- [ ] Task 2 satisfies §5.5 `--sharpit-require-app` / ini compatibility and records the §11
  deviation.
- [ ] Task 3 satisfies §5.5 F4 quiet default, count line, verbose opt-in, and unchanged
  JSON/JUnit.
- [ ] Spike F3 is reproduced red on 0.3.0 for the no-app unknown/exit-1 reason; all Review Focus
  tests are green in the lane.
