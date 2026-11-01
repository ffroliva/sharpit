# G3 — GitHub Action and Job Summary Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development or superpowers:executing-plans. One task/commit at a time; begin after F is merged.

**Goal:** Provide a safe composite GitHub Action for invoking sharpit in CI and a CLI summary that turns its JSON report into escaped Markdown.

**Architecture:** Keep action orchestration in root `action.yml`; pass user-controlled values through environment variables and split pytest arguments in Python using `shlex`. Add a pure `sharpit.report summary` command over existing reports and golden-test its Markdown.

**Tech Stack:** GitHub composite actions, Python 3.12+, pytest, `shlex`, Markdown escaping; no network in tests.

**Spec:** `docs/superpowers/specs/2026-11-01-sharpit-0.4.0-design.md` §5.3, §10.3.

## Header and ownership

- **Lane:** G3.
- **Worker profile:** M, judgement-heavy (shell injection boundary, quoting, summary UX).
- **Dependencies:** G1G2 (exactly as PLAN.md). F is an indirect dependency through G1G2.
- **May touch:** Create `action.yml`; create focused summary CLI module under `src/sharpit/` and add dispatch in `src/sharpit/__main__.py` or project script wiring as current layout requires; tests under `tests/action/` and `tests/`; summary golden under `tests/fixtures/`; this lane’s evidence folder.
- **Must not touch:** G1G2 gate/baseline or plugin code; G4 docs/dependabot; panels/UI; report schema except reading additive keys; `scripts/dev/lane_gate.py`; dependency lists, `uv.lock`, complexity/sonar baselines, overhead budget constants.

## Global constraints

- Every action input reaches shell through `env:`; no `${{ }}` expression inside `run:`; every shell expansion is double-quoted.
- `pytest-args` is parsed with Python `shlex`, never shell word splitting.
- Action sharpit version is a literal, bumped by `/sharpit:release`; no tags/publishing in this lane.
- Summary is pure: JSON input to Markdown, no network/environment reads; escape every interpolated value.

## Review Focus

1. Malicious pytest args with spaces, quotes, semicolons or substitutions: `test_action_pytest_args_are_shlex_split_not_shell_evaluated`.
2. GitHub expression injection: `test_action_has_no_expressions_inside_run_and_all_inputs_use_env` parses YAML and inspects `run`/`env` nodes.
3. Paths with spaces: `test_action_quotes_every_expansion` statically checks every shell step.
4. Markdown metacharacters in finding values: `test_summary_escapes_markdown_values` covers pipes, brackets, backticks, angle brackets and newlines.
5. Oversized finding lists: `test_summary_limits_findings_to_top_20_and_reports_totals`.

---

### Task 1: Add pure summary renderer and CLI entry point

**Files:** Create `src/sharpit/report/summary.py` (or a focused module consistent with existing CLI dispatch); modify `src/sharpit/__main__.py` only as needed; create `tests/test_report_summary.py` and `tests/fixtures/report-summary.md`.

**Interfaces:** `render_summary(report: Mapping[str, object]) -> str` returns Markdown with status, mode, totals, baseline counts when present, and at most 20 top findings. Escape every interpolated value; use stable ordering. `python -m sharpit.report summary <report.json>` is implemented by `src/sharpit/report/__main__.py`, writes Markdown to stdout and exits nonzero on unreadable/invalid JSON.

- [ ] **Step 1: Failing tests.** `test_summary_golden`, Review Focus 4–5, `test_summary_has_status_mode_totals`, `test_summary_includes_baseline_counts_when_present`, `test_summary_without_baseline_is_stable`, `test_summary_cli_reads_report_and_writes_stdout`, `test_summary_cli_invalid_json_returns_error`.
- [ ] **Step 2: Run `tests/test_report_summary.py`; expected assertion failures, not import/collection errors.**
- [ ] **Step 3: Implement pure renderer and CLI dispatch.** No environment or network access.
- [ ] **Step 4: Run tests; expect golden and behavior assertions pass.**
- [ ] **Step 5: Commit** `feat: add sharpit report Markdown summary command`.

### Task 2: Define and statically verify composite action inputs

**Files:** Create root `action.yml`; create `tests/action/test_action_definition.py`.

**Interfaces:** Inputs exactly `pytest-args`, `report-only` (default `true`), `baseline`, `fail-on`, `report-path`, `install` (`pip` default, `none` supported), `runner` (default `python -m pytest`). Composite steps install literal sharpit version when requested, invoke selected runner with parsed pytest args and sharpit flags, render report, then append it to `$GITHUB_STEP_SUMMARY`.

- [ ] **Step 1: Failing tests.** Review Focus 1–3; `test_action_declares_all_inputs_and_defaults`, `test_action_version_is_literal`, `test_action_respects_install_none`, `test_action_forwards_report_only_baseline_fail_on_and_report_path`, `test_action_runner_default`, `test_action_invokes_summary_cli`, `test_action_has_no_unquoted_or_expression_run_values`.
- [ ] **Step 2: Run static tests; expected missing-action or exact-rule assertions fail.**
- [ ] **Step 3: Implement composite action.** Copy inputs through `env`, quote expansions, and use Python `shlex.split` then `subprocess` argv (never concatenate into shell command text).
- [ ] **Step 4: Run action static tests; expected PASS.**
- [ ] **Step 5: Commit** `feat: add safe sharpit GitHub Action`.

### Task 3: Record manual wheel verification and lane handoff

**Files:** Create `.superpowers/sdd/0.4.0/lanes/G3/lane-report.md`, `handoff.md`.

**Interfaces:** Lane report records locally built wheel version/path, exact action invocation, result and summary. This is evidence only; no network test or publishing (§5.3).

- [ ] **Step 1:** After implementation, run action once against locally built wheel; record invocation and result. Do not publish/tag.
- [ ] **Step 2:** Run four gates and targeted static/golden tests; save logs pinned to head SHA.
- [ ] **Step 3: Commit** `docs: record action lane verification`.

### Action contract test matrix

The static test fixture uses a minimal composite action with the same YAML shape so each rejection is attributed to the targeted policy. The tests do not call GitHub or install packages.

- [ ] **Step 1:** Assert each of the seven inputs is declared with the exact default and description; optional empty values remain valid.
- [ ] **Step 2:** Assert all input values used in shell occur first in the step’s `env` mapping and the `run` text contains no `${{` expression.
- [ ] **Step 3:** Assert each `$VARIABLE` reference in shell is quoted, including report path, GitHub summary path, runner, and install selector.
- [ ] **Step 4:** Assert pytest arguments are parsed from the environment with `shlex.split` and passed as distinct argv elements; test a quoted `-k` expression and a semicolon payload as data.
- [ ] **Step 5:** Assert `install: none` skips installation and still invokes the selected runner; default `pip` installs the action’s literal sharpit version.
- [ ] **Step 6:** Assert the action uses report-only default true, forwards optional baseline/fail-on/report-path only when provided, and does not hide the pytest exit code.

### Summary rendering contract

The summary renderer consumes the report shape and ignores unknown additive keys. Tests should cover reports in `pass`, `fail`, and `unknown` states, and both gate and report-only modes; finding order is deterministic by severity then stable fingerprint.

- [ ] **Step 1:** Golden-test one report with no baseline and one with baseline counts; both include status, mode, totals, and up to 20 findings.
- [ ] **Step 2:** Assert markdown escaping leaves no raw line break from a value and neutralizes table pipes, links, emphasis, inline code, and HTML.
- [ ] **Step 3:** Assert totals report the full finding count even when only the top 20 are rendered.
- [ ] **Step 4:** Assert an unknown report’s reasons are rendered safely and do not disappear when status is fail.
- [ ] **Step 5:** Assert invalid JSON produces a concise CLI error and nonzero result without a traceback or output file.

### File ownership notes

Do not add a third-party YAML parser solely for this lane. Reuse an existing project test dependency if available; otherwise static checks may parse the small action document with a focused test helper that validates only the structural invariants above. Keep the production renderer independent of pytest and GitHub environment variables.

## Lane evidence checklist

`.superpowers/sdd/0.4.0/lanes/G3/` contains implementer-owned `handoff.md`, `lane-report.md`, `findings.md`, `field-map.md` (`N/A — not a panel lane`), and `checklist.md`. Checklist follows spec §6.1 items 1–10 in order, mapped to owning tasks with evidence paths or `N/A` plus reason. Coordinator/reviewer alone creates `review.md`, `gate/<name>.log` for ruff-check, ruff-format, pyright, pytest, lowest-direct and no-sqlalchemy, and `live-verify.md` in integration; lane diff cannot touch these paths.

## Definition of done

- [ ] Tasks 1–3 cover all §5.3 inputs/defaults, safe env boundary/quoting, shlex parsing, literal version, pure golden-tested summary and local wheel evidence.
- [ ] Action static and summary golden tests plus four gates pass.
- [ ] Lane evidence passes `scripts/dev/lane_gate.py`; no publishing or tagging occurs.

## Canonical lane conventions (C1–C8)

- Lane id is exactly `G3`; evidence folder is `.superpowers/sdd/0.4.0/lanes/G3/`.
- All lanes consume module names and signatures in F's consumer interface table.
- Golden fixture paths and `tests/golden.py::assert_parity(sharpit_id: str, name: str, payload: Mapping[str, Any]) -> None` follow C3, with no flat panel files.
- A red is a defect-naming assertion, not import/collection failure. No spike test is owned by G3.
- Do not edit shared safety/masking matrices; use `tests/safety/test_g3_safety.py` and `tests/masking/test_g3_masking.py` if needed.
- PLAN.md Review Focus test names remain canonical: `test_action_pytest_args_are_shlex_split_not_shell_evaluated`, `test_action_has_no_expressions_inside_run_and_all_inputs_use_env`, `test_action_quotes_every_expansion`, `test_summary_escapes_markdown_values`, and `test_summary_limits_findings_to_top_20_and_reports_totals`.
- Dependencies are exactly `G1G2`.
- Checklist follows §6.1 items 1–10 in order; all panel-specific items are `N/A — not a panel lane`, while applicable handoff evidence maps to G3's tasks.

| Spec §6.1 item | G3 task / evidence owner |
|---|---|
| 1 Golden parity | N/A — action/summary lane, not a panel lane. |
| 2 Ported behavior tests | N/A — no BootUI panel behavior is ported. |
| 3 Safety and masking | N/A — no panel data source or new secret source. |
| 4 Gatekeeper | N/A — no new runtime library. |
| 5 Hot-path overhead | N/A — no hot-path code change. |
| 6 MCP read-only surface | N/A — no MCP surface change. |
| 7 Svelte view | N/A — no panel view. |
| 8 Four gates | Task 3, Step 2: run four gates; coordinator owns gate logs. |
| 9 Live check | N/A — no panel implementation; integration reviewer owns live verification. |
| 10 Handoff | Task 3: lane report and current handoff. |
